# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# Modified from google-research/ple (Apache-2.0)

"""Serve-protocol plumbing for a PLEBench harness (`docs/protocol.md`).

Provides the WebSocket server, one `Session` per task, and an `MCPClient` for
the task's MCP servers:

    import taskbridge

    async def solve(session):
        result = await session.exec("ls -la")
        ...
        return "Wrote /app/output/report.md: ..."     # the final message

    taskbridge.run(solve)                             # listens on $PORT

Uses only the Python standard library plus `websockets`.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import itertools
import json
import math
import os
import re
import sys
import time
from typing import Any
import urllib.parse

from websockets.asyncio.server import serve as _ws_serve
from websockets.exceptions import ConnectionClosed

# Limits the evaluator enforces (docs/protocol.md). It counts a message past one
# of them as malformed, or closes the connection.
MAX_FRAME = 16 << 20  # one message, in either direction
MAX_HTTP_BYTES = 10_000_000  # an http request's body
MAX_WRITE_BYTES = 10_000_000  # one write_file's data
# limits.exec_timeout_sec: a longer exec or http timeout is cut to this
MAX_TIMEOUT_SEC = 600
HTTP_METHODS = ("GET", "POST", "DELETE", "PUT", "PATCH", "HEAD", "OPTIONS")

# This file's own limits.
# a longer final message is cut, so that done fits in one message
MAX_FINAL_CHARS = 1_000_000
# write_file sends a larger file in parts of this size, under MAX_WRITE_BYTES
WRITE_CHUNK = 4 << 20


class Cancelled(Exception):  # pylint: disable=g-bad-exception-name
  """Raised when the evaluator cancels the task or closes the connection."""


class TaskError(Exception):
  """Raised when the evaluator returns `ok: false` or a request is invalid."""


class Session:
  """One task session; requests may run concurrently and await their results."""

  def __init__(self, ws: Any, task: dict[str, Any]):
    self.ws = ws
    self.task = task
    self.instruction: str = task["instruction"]
    self.workdir: str = task.get("workdir") or "/"
    limits, servers = task.get("limits"), task.get("mcp_servers")
    self.limits: dict[str, Any] = limits if isinstance(limits, dict) else {}
    self.mcp_servers: list[dict[str, Any]] = (
        [s for s in servers if isinstance(s, dict)]
        if isinstance(servers, list)
        else []
    )
    budget = self.limits.get("agent_timeout_sec")
    self.deadline = (
        time.monotonic() + budget
        if isinstance(budget, (int, float)) and budget > 0
        else None
    )
    self.final_message = ""
    self.cancelled = asyncio.Event()
    self._ids = itertools.count(1)
    self._waiting: dict[str, asyncio.Future[dict[str, Any]]] = {}
    self._lock = asyncio.Lock()

  def time_left(self) -> float | None:
    """Returns remaining seconds before the task deadline, or `None`."""
    return None if self.deadline is None else self.deadline - time.monotonic()

  async def send(self, message: dict[str, Any]) -> None:
    """Serializes `message` and sends it over the WebSocket.

    Args:
      message: Protocol message dictionary to send.
    """
    await self._send(_frame(message))

  async def _send(self, frame: str) -> None:
    """Sends a pre-serialized JSON frame over the WebSocket under a lock.

    Args:
      frame: Serialized JSON message string.
    """
    async with self._lock:
      await self.ws.send(frame)

  async def _read(self) -> None:
    """Reads evaluator frames and dispatches results to waiting futures.

    Skips frames that are not JSON objects. When reading stops due to a
    `cancel` frame, socket closure, or error, marks the session as cancelled
    and fails all pending request futures with `Cancelled`.
    """
    try:
      async for frame in self.ws:
        try:
          msg = json.loads(frame)
        except ValueError:
          msg = None
        if not isinstance(msg, dict):
          print(
              "taskbridge: skipped a frame that is not a JSON object:"
              f" {str(frame)[:200]!r}",
              file=sys.stderr,
              flush=True,
          )
          continue
        rid = msg.get("id")
        if (
            msg.get("type") == "result"
            and isinstance(rid, str)
            and rid in self._waiting
        ):
          future = self._waiting.pop(rid)
          if not future.done():
            future.set_result(msg)
        elif msg.get("type") == "cancel":
          break
    except ConnectionClosed:
      pass
    # Logged here; waiting requests are released in the finally block below.
    except Exception as exc:  # pylint: disable=broad-exception-caught
      print(
          "taskbridge: stopped reading the evaluator's messages:"
          f" {type(exc).__name__}: {exc}",
          file=sys.stderr,
          flush=True,
      )
    finally:
      self.cancelled.set()
      for future in self._waiting.values():
        if not future.done():
          future.set_exception(Cancelled())
      self._waiting.clear()

  async def request(self, kind: str, **fields: Any) -> dict[str, Any]:
    """Sends one protocol request and awaits its matching result frame.

    Omits fields whose value is `None`.

    Args:
      kind: Request `type` (e.g., `exec`, `read_file`, `write_file`, `http`).
      **fields: Additional request fields to include when not `None`.

    Returns:
      The evaluator's `result` message dictionary.

    Raises:
      Cancelled: If the task is cancelled or the WebSocket closes.
      TaskError: If the serialized message exceeds `MAX_FRAME`.
    """
    if self.cancelled.is_set():
      raise Cancelled()
    rid = str(next(self._ids))
    message = {
        "type": kind,
        "id": rid,
        **{k: v for k, v in fields.items() if v is not None},
    }
    frame = _frame(message)  # a message over MAX_FRAME raises here
    future = asyncio.get_running_loop().create_future()
    self._waiting[rid] = future
    try:
      try:
        await self._send(frame)
      except ConnectionClosed:
        self.cancelled.set()
        if future.done() and not future.cancelled():
          # the reader may have failed it already: read its exception, or
          # asyncio logs it as never retrieved
          future.exception()
        raise Cancelled() from None
      return await future
    finally:
      self._waiting.pop(rid, None)

  async def exec(self, command: str, timeout_sec: int = 120) -> dict[str, Any]:
    """Runs `bash -c command` inside the task container in `workdir`.

    Args:
      command: Shell command string to execute.
      timeout_sec: Timeout in seconds (clamped to `1..MAX_TIMEOUT_SEC`).

    Returns:
      Result dictionary with `exit_code`, `output`, `truncated`, and
      `timed_out`.

    Raises:
      TaskError: If the command is invalid or the evaluator reports an error.
      Cancelled: If the session is cancelled while waiting.
    """
    result = await self.request(
        "exec",
        command=_text("exec: the command", command),
        timeout_sec=_seconds(timeout_sec),
    )
    if not result.get("ok", True):
      raise TaskError(result.get("error"))
    return result

  async def read_file(self, path: str) -> bytes:
    """Reads the entire contents of `path` from the task container.

    Args:
      path: File path inside the task container.

    Returns:
      Raw bytes of the file.

    Raises:
      TaskError: If the read fails or the file exceeds the 10 MB single-read
        limit.
      Cancelled: If the session is cancelled while waiting.
    """
    result = await self.read_result(path)
    if not result.get("ok"):
      raise TaskError(result.get("error"))
    if result.get("truncated"):
      raise TaskError(
          f"{path} is {result.get('size')} bytes, over the 10 MB a read"
          " returns; read it in parts"
      )
    return base64.b64decode(result["content_b64"])

  async def read_result(self, path: str) -> dict[str, Any]:
    """Sends a `read_file` request and returns the raw evaluator result.

    Args:
      path: File path inside the task container.

    Returns:
      Evaluator result dictionary with `ok`, `content_b64`, `size`, and
      `truncated` (or `error`).
    """
    return await self.request(
        "read_file", path=_text("read_file: the path", path)
    )

  async def write_file(
      self, path: str, data: bytes | str, append: bool = False
  ) -> int:
    """Writes `data` to `path` in the task container in `WRITE_CHUNK` parts.

    Args:
      path: Destination path inside the task container.
      data: Bytes or UTF-8 string content to write.
      append: Whether to append to an existing file instead of overwriting.

    Returns:
      The resulting file size in bytes as reported by the evaluator.

    Raises:
      TaskError: If `path` or `data` is invalid or the write fails.
      Cancelled: If the session is cancelled while waiting.
    """
    path = _text("write_file: the path", path)
    if not isinstance(data, (bytes, bytearray, str)):
      raise TaskError("write_file: the data is bytes or text")
    data = data.encode() if isinstance(data, str) else bytes(data)
    size = 0
    for start in range(0, max(len(data), 1), WRITE_CHUNK):
      chunk = data[start : start + WRITE_CHUNK]
      result = await self.request(
          "write_file",
          path=path,
          append=bool(append) or start > 0,
          content_b64=base64.b64encode(chunk).decode(),
      )
      if not result.get("ok"):
        raise TaskError(result.get("error"))
      size = result.get("size", size)
    return size

  async def http(
      self,
      url: str,
      method: str = "POST",
      headers: dict[str, str] | None = None,
      body: bytes = b"",
      timeout_sec: int = 120,
  ) -> dict[str, Any]:
    """Performs an HTTP request inside the task container to an MCP server.

    Args:
      url: Target URL under one of the task's `mcp_servers`.
      method: HTTP method (`GET`, `POST`, `DELETE`, `PUT`, `PATCH`, `HEAD`,
        `OPTIONS`).
      headers: Optional mapping of HTTP request header names to values.
      body: Request body bytes (at most `MAX_HTTP_BYTES`).
      timeout_sec: Request timeout in seconds.

    Returns:
      A dictionary with `status`, `headers`, `body` (bytes), and `truncated`.

    Raises:
      TaskError: If the request parameters are disallowed or the evaluator
        returns `ok: false`.
      Cancelled: If the session is cancelled while waiting.
    """
    url = _text("http: the url", url)
    if not mcp_allows(url, self.mcp_servers):
      raise TaskError(
          f"http: {url} is not one of the task's MCP servers, nor a path"
          " under one"
      )
    method = str(method or "GET").upper()
    if method not in HTTP_METHODS:
      raise TaskError(f"http: the method is one of {', '.join(HTTP_METHODS)}")
    headers = headers or {}
    if not isinstance(headers, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in headers.items()
    ):
      raise TaskError("http: the headers are names and values, as text")
    for k, v in headers.items():
      _text("http: a header", f"{k}:{v}")
    if not isinstance(body, (bytes, bytearray)):
      raise TaskError("http: the body is bytes")
    if len(body) > MAX_HTTP_BYTES:
      raise TaskError(
          f"http: the body is {len(body)} bytes, over the {MAX_HTTP_BYTES} an"
          " http request carries"
      )
    result = await self.request(
        "http",
        url=url,
        method=method,
        headers=headers,
        timeout_sec=_seconds(timeout_sec),
        body_b64=base64.b64encode(body).decode(),
    )
    if not result.get("ok", True):
      raise TaskError(result.get("error"))
    return {
        "status": result["status"],
        "headers": result.get("headers") or {},
        "body": base64.b64decode(result.get("body_b64") or ""),
        "truncated": bool(result.get("truncated")),
    }

  async def log(self, text: str) -> None:
    """Sends a progress log message (up to 20,000 characters) to the evaluator.

    Args:
      text: Log message string.
    """
    with contextlib.suppress(ConnectionClosed):
      await self.send({"type": "log", "text": text[:20000]})

  async def usage(
      self,
      model: str,
      input_tokens: int = 0,
      output_tokens: int = 0,
      cache_read_tokens: int = 0,
  ) -> None:
    """Reports token usage for a model call to the evaluator.

    Args:
      model: Model identifier string.
      input_tokens: Total input/prompt tokens (including cache reads/writes).
      output_tokens: Output/completion tokens.
      cache_read_tokens: Cached input tokens read.
    """
    with contextlib.suppress(ConnectionClosed):
      await self.send({
          "type": "usage",
          "model": model,
          "input_tokens": positive_int(input_tokens, 0),
          "output_tokens": positive_int(output_tokens, 0),
          "cache_read_tokens": positive_int(cache_read_tokens, 0),
      })


def _frame(message: dict[str, Any]) -> str:
  """Serializes `message` as JSON and checks that it fits within `MAX_FRAME`.

  Args:
    message: Protocol message dictionary.

  Returns:
    The ASCII-escaped JSON string representation of `message`.

  Raises:
    TaskError: If the serialized frame exceeds `MAX_FRAME` bytes.
  """
  # ASCII (non-ASCII is escaped), so its length is its size in bytes
  frame = json.dumps(message)
  if len(frame) > MAX_FRAME:
    hint = (
        "write a long script with write_file and run that"
        if message.get("type") == "exec"
        else "send less"
    )
    raise TaskError(
        f"{message.get('type')}: the message is {len(frame)} bytes, over the"
        f" protocol's {MAX_FRAME >> 20} MiB; {hint}"
    )
  return frame


def _final(text: str) -> str:
  """Truncates `text` to `MAX_FINAL_CHARS` so `done` fits in one frame.

  Args:
    text: Final message string.

  Returns:
    The original or truncated final message string.
  """
  if len(text) <= MAX_FINAL_CHARS:
    return text
  return text[:MAX_FINAL_CHARS] + "\n[... the rest of this message was cut]"


def _text(what: str, value: Any) -> str:
  """Validates that `value` is a non-empty UTF-8 string without NUL bytes.

  Args:
    what: Description of the field being validated (used in error messages).
    value: Value to validate.

  Returns:
    The validated string `value`.

  Raises:
    TaskError: If `value` is empty, not a `str`, contains NUL, or has unpaired
      UTF-16 surrogates.
  """
  if not isinstance(value, str) or not value:
    raise TaskError(f"{what} is empty or not text")
  if "\x00" in value:
    raise TaskError(f"{what} holds a NUL byte")
  try:
    value.encode("utf-8")
  except UnicodeEncodeError:
    raise TaskError(
        f"{what} is not valid UTF-8 (an unpaired surrogate)"
    ) from None
  return value


def _seconds(value: Any) -> int:
  """Clamps a timeout value to `1..MAX_TIMEOUT_SEC` (or `120` when `None`).

  Compares integers directly so huge ints are clamped without overflowing
  `float()`.

  Args:
    value: Timeout in seconds (`int`, `float`, or `None`).

  Returns:
    Clamped integer timeout in seconds.

  Raises:
    TaskError: If `value` is not `None` and not a finite `int` or `float`.
  """
  if value is None:
    return 120
  if (
      isinstance(value, bool)
      or not isinstance(value, (int, float))
      or (isinstance(value, float) and not math.isfinite(value))
  ):
    raise TaskError("timeout_sec is a number of seconds")
  return min(max(1, int(value)), MAX_TIMEOUT_SEC)


def mcp_allows(url: str, servers: list[dict[str, Any]]) -> bool:
  """Checks whether `url` is permitted by the evaluator's MCP server rules.

  Allows exact MCP server URLs (optionally followed by a query string) or
  subpaths beneath them. Rejects `.` or `..` segments, encoded slashes or
  backslashes, literal backslashes, and `;` path parameters.

  Args:
    url: Candidate HTTP target URL.
    servers: List of MCP server descriptor dictionaries from the task message.

  Returns:
    `True` if the evaluator permits an `http` request to `url`, else `False`.
  """
  try:
    path = urllib.parse.urlsplit(url).path
  except ValueError:
    return False
  decoded = urllib.parse.unquote(path)
  if (
      "%2f" in path.lower()
      or "%5c" in path.lower()
      or "\\" in path
      or ";" in decoded
      or {".", ".."} & set(decoded.split("/"))
  ):
    return False
  for server in servers:
    base = str(server.get("url") or "")
    if base and (
        url == base
        or ("?" not in base and url.startswith(base + "?"))
        or url.startswith(base.rstrip("/") + "/")
    ):
      return True
  return False


async def _session(ws: Any, handler: Any) -> None:
  """Handles a single evaluator WebSocket connection from `task` to `done`.

  Args:
    ws: Connected WebSocket server protocol instance.
    handler: Async callable `handler(session)` returning the final message.
  """
  try:
    task = json.loads(await ws.recv())
  except ConnectionClosed:
    return
  except ValueError:
    task = None
  if (
      not isinstance(task, dict)
      or task.get("type") != "task"
      or not isinstance(task.get("instruction"), str)
  ):
    with contextlib.suppress(ConnectionClosed):
      await ws.send(
          json.dumps(
              {"type": "error", "message": "expected a task message first"}
          )
      )
    return
  session = Session(ws, task)
  reader = asyncio.create_task(
      session._read()  # pylint: disable=protected-access
  )
  work = asyncio.create_task(handler(session))
  stop = asyncio.create_task(session.cancelled.wait())
  try:
    done, _ = await asyncio.wait(
        {work, stop}, return_when=asyncio.FIRST_COMPLETED
    )
    exc = (
        work.exception()
        if work in done and not work.cancelled()
        else Cancelled()
    )
    if exc is None:
      answer = work.result()
      await session.send({
          "type": "done",
          "final_message": _final(
              answer
              if isinstance(answer, str) and answer
              else session.final_message
          ),
      })
    elif not isinstance(exc, Cancelled):
      print(
          f"harness error: {type(exc).__name__}: {exc}",
          file=sys.stderr,
          flush=True,
      )
      if session.final_message:
        # a summary written before the failure still reaches the graders, who
        # read the final message
        await session.log(
            f"harness error after its summary: {type(exc).__name__}: {exc}"[
                :2000
            ]
        )
        await session.send(
            {"type": "done", "final_message": _final(session.final_message)}
        )
      else:
        await session.send(
            {"type": "error", "message": f"{type(exc).__name__}: {exc}"[:2000]}
        )
    else:
      # The evaluator closes the socket 10 s after cancel: give the handler 2 s
      # to return its answer, then cancel it and wait up to 6 s more.
      await asyncio.wait({work}, timeout=2)
      if not work.done():
        work.cancel()
        await asyncio.wait({work}, timeout=6)
      answer = (
          work.result()
          if work.done() and not work.cancelled() and work.exception() is None
          else None
      )
      final = (
          answer
          if isinstance(answer, str) and answer
          else session.final_message
      )
      await session.send({
          "type": "done",
          "final_message": _final(final or "(stopped: time is up)"),
      })
  except ConnectionClosed:
    pass
  finally:
    for t in (work, stop, reader):
      t.cancel()


async def serve_forever(handler: Any, port: int | None = None) -> None:
  """Listens for evaluator WebSocket connections on `port` indefinitely.

  Args:
    handler: Async callable `handler(session)` invoked per task connection.
    port: TCP port to listen on (defaults to `$PORT` or `8765`).
  """
  port = int(port or os.environ.get("PORT", 8765))

  async def on_connect(ws):
    await _session(ws, handler)

  async with _ws_serve(
      on_connect, "0.0.0.0", port, max_size=MAX_FRAME, ping_interval=None
  ):
    print(f"listening on {port}", flush=True)
    await asyncio.Future()


def run(handler: Any, port: int | None = None) -> None:
  """Serves `handler(session)` on `$PORT` until interrupted.

  Args:
    handler: Async callable `handler(session)` returning the final message.
    port: Optional TCP port override (defaults to `$PORT` or `8765`).
  """
  with contextlib.suppress(KeyboardInterrupt):
    asyncio.run(serve_forever(handler, port))


class MCPError(RuntimeError):
  """Raised when an MCP server returns an HTTP/JSON-RPC error or bad reply."""


class MCPClient:
  """Streamable-HTTP MCP client calling a task's MCP server via `Session.http`.

  Sends JSON-RPC POST requests and parses JSON or Server-Sent Events (SSE)
  responses. Raises `MCPError` on MCP-level failures and `TaskError` when
  `Session.http` rejects a request.
  """

  VERSION = "2025-06-18"  # the MCP protocol version asked for

  def __init__(
      self,
      session: Session,
      url: str,
      *,
      client: str = "harness",
      timeout_sec: int = 300,
  ):
    self.session, self.url, self.client, self.timeout_sec = (
        session,
        url,
        client,
        timeout_sec,
    )
    self.headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    self._ids = itertools.count(1)

  async def rpc(
      self,
      method: str,
      params: dict[str, Any] | None = None,
      notify: bool = False,
  ) -> dict[str, Any] | None:
    """Sends a JSON-RPC request or notification to the MCP server.

    Args:
      method: JSON-RPC method name (e.g., `initialize`, `tools/list`).
      params: Optional JSON-RPC `params` object.
      notify: If `True`, sends a notification without an `id` and returns
        `None`.

    Returns:
      The JSON-RPC `result` dictionary, or `None` when `notify` is `True`.

    Raises:
      MCPError: If the response is truncated, has an HTTP status >= 400, returns
        a JSON-RPC error object, or contains no matching response message.
    """
    message = {
        "jsonrpc": "2.0",
        "method": method,
        **({"params": params} if params is not None else {}),
    }
    if not notify:
      message["id"] = next(self._ids)
    reply = await self.session.http(
        self.url,
        "POST",
        dict(self.headers),
        json.dumps(message).encode(),
        timeout_sec=self.timeout_sec,
    )
    if reply.get("truncated"):
      raise MCPError(
          f"{method}: the answer is larger than the protocol carries"
      )
    for key, value in reply["headers"].items():
      if key.lower() == "mcp-session-id":
        self.headers["Mcp-Session-Id"] = value
    if notify:
      return None
    body = reply["body"].decode("utf-8", "replace")
    if reply["status"] >= 400:
      raise MCPError(f"{method}: HTTP {reply['status']}: {body[:300]!r}")
    for answer in self.messages(body):
      if answer.get("id") == message["id"]:
        if "error" in answer:
          raise MCPError(f"{method}: {answer['error']}")
        return (
            answer["result"] if isinstance(answer.get("result"), dict) else {}
        )
    raise MCPError(f"{method}: no answer in {body[:300]!r}")

  @staticmethod
  def messages(body: str) -> list[dict[str, Any]]:
    """Extracts JSON-RPC message objects from a JSON or SSE response body.

    Args:
      body: Decoded HTTP response body string (raw JSON or SSE stream).

    Returns:
      List of parsed JSON-RPC message dictionaries found in `body`.
    """
    text = body.strip()
    if text.startswith(("{", "[")):
      chunks = [text]
    else:
      chunks = [
          "\n".join(
              line[5:].lstrip()
              for line in block.splitlines()
              if line.startswith("data:")
          )
          for block in re.split(r"\r?\n\r?\n", text)
      ]
    found = []
    for chunk in filter(None, chunks):
      try:
        data = json.loads(chunk)
      except ValueError:
        continue
      found += [
          m
          for m in (data if isinstance(data, list) else [data])
          if isinstance(m, dict)
      ]
    return found

  async def initialize(self) -> dict[str, Any]:
    """Performs the MCP `initialize` handshake and records the protocol version.

    Returns:
      The server's `initialize` result dictionary.
    """
    result = await self.rpc(
        "initialize",
        {
            "protocolVersion": self.VERSION,
            "capabilities": {},
            "clientInfo": {"name": self.client, "version": "1.0"},
        },
    )
    version = result.get("protocolVersion")
    self.headers["MCP-Protocol-Version"] = (
        version if isinstance(version, str) and version else self.VERSION
    )
    await self.rpc("notifications/initialized", notify=True)
    return result

  async def list_tools(self, max_pages: int = 100) -> list[dict[str, Any]]:
    """Lists all named tools exposed by the MCP server across paginated results.

    Args:
      max_pages: Maximum number of `tools/list` pages to fetch.

    Returns:
      List of tool definition dictionaries with normalized `description` and
      `inputSchema` fields.
    """
    tools, cursor = [], None
    for _ in range(max_pages):
      page = await self.rpc("tools/list", {"cursor": cursor} if cursor else {})
      found = page.get("tools") if isinstance(page.get("tools"), list) else []
      tools += [
          {
              **t,
              "description": str(t.get("description") or ""),
              "inputSchema": (
                  t["inputSchema"]
                  if isinstance(t.get("inputSchema"), dict)
                  else {}
              ),
          }
          for t in found
          if isinstance(t, dict)
          and isinstance(t.get("name"), str)
          and t["name"]
      ]
      cursor = page.get("nextCursor")
      if not cursor:
        break
    return tools

  async def call_tool(
      self, name: str, arguments: dict[str, Any]
  ) -> dict[str, Any]:
    """Invokes tool `name` on the MCP server with `arguments`.

    Args:
      name: Tool name to call.
      arguments: Tool input arguments dictionary.

    Returns:
      The `tools/call` result dictionary from the MCP server.
    """
    return await self.rpc("tools/call", {"name": name, "arguments": arguments})


def positive_int(value: Any, default: int, cap: int | None = None) -> int:
  """Parses a positive integer from a tool argument, falling back to `default`.

  Rounds fractional numbers up and clamps the result to `cap` when given. Zero,
  negative values, booleans, `None`, or unparseable values return `default` (so
  `0` passed by a model to mean "no limit" becomes `default` rather than `1`).

  Args:
    value: Raw argument value (number, numeric string, or other).
    default: Fallback integer when `value` is not a positive finite number.
    cap: Optional upper bound on the returned integer.

  Returns:
    A positive integer (or `default`), clamped to `cap` if specified.
  """
  number = 0.0
  if isinstance(value, int) and not isinstance(value, bool):
    number = value  # an int stays an int: float() overflows past about 1e308
  elif not isinstance(value, bool):
    with contextlib.suppress(TypeError, ValueError, OverflowError):
      number = float(value)
  limit = math.ceil(number) if 0 < number < math.inf else default
  return limit if cap is None else min(limit, cap)
