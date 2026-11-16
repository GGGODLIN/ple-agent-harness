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

"""Seam 1 acceptance tests for WebSocket v1 protocol, model-family effort, and secret redaction."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import importlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from typing import Any

import pytest
import websockets
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
OFFICIAL_GOOGLE_CLOUD_MODELS = {
  "google-cloud/gemini-4-argon",
  "google-cloud/gemini-3.8-flash",
  "google-cloud/gemini-3.1-pro-preview",
  "google-cloud/claude-opus-5-5",
  "google-cloud/gpt-oss-120b",
  "google-cloud/glm-5.2",
  "google-cloud/gemma-4-26b",
  "google-cloud/llama-4-maverick",
}


SAFE_ENV_KEYS = (
  "PATH",
  "HOME",
  "TMPDIR",
  "LANG",
  "LC_ALL",
  "PYTHONPATH",
  "VIRTUAL_ENV",
  "USER",
  "SYSTEMROOT",
)


def _safe_subprocess_env(overrides: dict[str, str] | None = None) -> dict[str, str]:
  env = {k: os.environ[k] for k in SAFE_ENV_KEYS if k in os.environ}
  if overrides:
    env.update(overrides)
  return env


def _free_tcp_port() -> int:
  with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.bind(("127.0.0.1", 0))
    return int(sock.getsockname()[1])


def _contains_token(haystack: str, needle: str) -> bool:
  return needle in haystack


def _load_repo_module(module_name: str) -> Any:
  module_path = REPO_ROOT / f"{module_name}.py"
  assert module_path.is_file(), f"missing required entrypoint {module_name}.py"
  repo_str = str(REPO_ROOT)
  if repo_str not in sys.path:
    sys.path.insert(0, repo_str)
  if module_name == "harness" and "deliverable_audit" in sys.modules:
    importlib.reload(sys.modules["deliverable_audit"])
  if module_name in sys.modules:
    return importlib.reload(sys.modules[module_name])
  return importlib.import_module(module_name)


class StubOpenAIServer:
  """Minimal async HTTP server speaking OpenAI Chat Completions SSE at Seam 1."""

  def __init__(self, handler: Any):
    self._handler = handler
    self.requests: list[dict[str, Any]] = []
    self._server: asyncio.AbstractServer | None = None
    self.port: int = 0

  @property
  def base_url(self) -> str:
    return f"http://127.0.0.1:{self.port}/v1"

  async def __aenter__(self) -> StubOpenAIServer:
    self._server = await asyncio.start_server(
      self._handle_conn, "127.0.0.1", 0
    )
    sockets = self._server.sockets or []
    self.port = int(sockets[0].getsockname()[1])
    return self

  async def __aexit__(self, *exc: Any) -> None:
    if self._server is not None:
      self._server.close()
      await self._server.wait_closed()

  async def _handle_conn(
    self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
  ) -> None:
    try:
      header_bytes = await reader.readuntil(b"\r\n\r\n")
      header_text = header_bytes.decode("utf-8", errors="replace")
      lines = header_text.split("\r\n")
      request_line = lines[0]
      method, path, _ = request_line.split(" ", 2)
      headers: dict[str, str] = {}
      for line in lines[1:]:
        if ":" in line:
          k, v = line.split(":", 1)
          headers[k.strip().lower()] = v.strip()
      content_length = int(headers.get("content-length", "0"))
      body_bytes = await reader.readexactly(content_length) if content_length else b""
      payload = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
      record = {"method": method, "path": path, "headers": headers, "json": payload}
      self.requests.append(record)

      status, content_type, resp_body = await self._handler(record, len(self.requests))
      reason = {200: "OK", 400: "Bad Request", 401: "Unauthorized"}.get(
        status, "Error"
      )
      raw_resp = (
        f"HTTP/1.1 {status} {reason}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(resp_body)}\r\n"
        "Connection: close\r\n\r\n"
      ).encode("utf-8") + resp_body
      writer.write(raw_resp)
      await writer.drain()
    except (asyncio.IncompleteReadError, ConnectionError):
      pass
    finally:
      writer.close()
      with contextlib.suppress(Exception):
        await writer.wait_closed()


def _sse_text_reply(text: str, model: str = "stub-model") -> bytes:
  chunks = [
    {
      "id": "chatcmpl-1",
      "object": "chat.completion.chunk",
      "model": model,
      "choices": [
        {"index": 0, "delta": {"role": "assistant", "content": text}, "finish_reason": None}
      ],
    },
    {
      "id": "chatcmpl-1",
      "object": "chat.completion.chunk",
      "model": model,
      "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
      "usage": {"prompt_tokens": 25, "completion_tokens": 8, "total_tokens": 33},
    },
  ]
  body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
  return body.encode("utf-8")


def _sse_tool_call_reply(
  call_id: str, name: str, arguments_obj: dict[str, Any], model: str = "stub-model"
) -> bytes:
  chunks = [
    {
      "id": "chatcmpl-tool",
      "object": "chat.completion.chunk",
      "model": model,
      "choices": [
        {
          "index": 0,
          "delta": {
            "role": "assistant",
            "tool_calls": [
              {
                "index": 0,
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments_obj)},
              }
            ],
          },
          "finish_reason": None,
        }
      ],
    },
    {
      "id": "chatcmpl-tool",
      "object": "chat.completion.chunk",
      "model": model,
      "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
      "usage": {"prompt_tokens": 30, "completion_tokens": 12, "total_tokens": 42},
    },
  ]
  body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
  return body.encode("utf-8")


def test_repository_contract_and_apache_attribution() -> None:
  required_files = [
    "submission.yaml",
    "requirements.txt",
    "LICENSE",
    "taskbridge.py",
    "serve.py",
    "harness.py",
    ".gitignore",
  ]
  for rel in required_files:
    assert (REPO_ROOT / rel).is_file(), f"missing required root file: {rel}"

  submission_raw = (REPO_ROOT / "submission.yaml").read_text(encoding="utf-8")
  submission = yaml.safe_load(submission_raw)
  assert isinstance(submission, dict)
  assert isinstance(submission.get("name"), str) and submission["name"].strip()
  assert submission.get("model_api") in OFFICIAL_GOOGLE_CLOUD_MODELS
  assert "{src}/requirements.txt" in str(submission.get("install", ""))
  assert "{src}/serve.py" in str(submission.get("serve", ""))

  # Positive control + secret/local-path absence check on submission.yaml
  sk_prefix = "sk" + "-"
  users_prefix = "/" + "Users/"
  sample_dirty = f"API_KEY: {sk_prefix}live-xyz {users_prefix}someone/secret"
  assert _contains_token(sample_dirty, sk_prefix) is True
  assert _contains_token(sample_dirty, users_prefix) is True
  has_sk = _contains_token(submission_raw, sk_prefix)
  has_users_path = _contains_token(submission_raw, users_prefix)
  assert not has_sk, "submission.yaml contains key prefix"
  assert not has_users_path, "submission.yaml contains machine-local path"

  reqs = [
    line.strip()
    for line in (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.strip().startswith("#")
  ]
  assert "openai==3.26.1" in reqs
  assert "websockets==15.0.1" in reqs

  license_text = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")
  assert "Apache License" in license_text
  assert "Version 2.0" in license_text

  for py_file in ("taskbridge.py", "serve.py", "harness.py"):
    header = "\n".join(
      (REPO_ROOT / py_file).read_text(encoding="utf-8").splitlines()[:20]
    )
    assert "Copyright 2026 Google LLC" in header, f"{py_file} missing Google LLC copyright"
    assert "Apache License, Version 2.0" in header, f"{py_file} missing Apache-2.0 header"
  for mod_file in ("taskbridge.py", "harness.py"):
    mod_header = "\n".join(
      (REPO_ROOT / mod_file).read_text(encoding="utf-8").splitlines()[:20]
    )
    assert "Modified from google-research/ple (Apache-2.0)" in mod_header, f"{mod_file} missing modification notice"

  gitignore_lines = [
    line.strip().rstrip("/")
    for line in (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.strip().startswith("#")
  ]
  for expected_ignored in (".venv", "__pycache__", ".pytest_cache", ".scratch"):
    assert expected_ignored in gitignore_lines, f".gitignore missing {expected_ignored}"
  assert "artifacts" not in gitignore_lines, ".gitignore must never ignore artifacts/"


def test_serve_entrypoint_websocket_smoke_and_mcp_roundtrip() -> None:
  assert (REPO_ROOT / "serve.py").is_file(), "missing serve.py"

  async def _scenario() -> None:
    async def stub_handler(
      req: dict[str, Any], call_num: int
    ) -> tuple[int, str, bytes]:
      messages = req["json"].get("messages", [])
      tool_Messages = [m for m in messages if m.get("role") == "tool"]
      user_text = next(
        (m.get("content", "") for m in messages if m.get("role") == "user"), ""
      )
      if "smoke" in user_text:
        if not tool_Messages:
          return (
            200,
            "text/event-stream",
            _sse_tool_call_reply("call_smoke_1", "bash", {"command": "echo smoke-ok"}),
          )
        return (
          200,
          "text/event-stream",
          _sse_text_reply(f"Smoke completed: {tool_Messages[-1]['content'].strip()}"),
        )
      if not tool_Messages:
        return (
          200,
          "text/event-stream",
          _sse_tool_call_reply("call_mcp_1", "demo__ping", {"target": "lab"}),
        )
      return (
        200,
        "text/event-stream",
        _sse_text_reply(f"MCP completed: {tool_Messages[-1]['content'].strip()}"),
      )

    ws_port = _free_tcp_port()
    async with StubOpenAIServer(stub_handler) as stub:
      env = _safe_subprocess_env({
        "PORT": str(ws_port),
        "MODEL_BASE_URL": stub.base_url,
        "MODEL_API_KEY": "stub-token",
        "MODEL_NAME": "google-cloud/glm-5.2",
      })
      proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(REPO_ROOT / "serve.py"),
        cwd=str(REPO_ROOT),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
      )
      try:
        assert proc.stdout is not None
        ready_line = await asyncio.wait_for(proc.stdout.readline(), timeout=15.0)
        assert f"listening on {ws_port}" in ready_line.decode("utf-8")

        ws_url = f"ws://127.0.0.1:{ws_port}"

        # 1) Smoke task roundtrip (exec + done + immutable prefix check)
        async with websockets.connect(ws_url) as ws:
          await ws.send(
            json.dumps({
              "type": "task",
              "instruction": "Run smoke check via bash",
              "workdir": "/workspace",
              "limits": {"agent_timeout_sec": 60},
            })
          )
          done_frame: dict[str, Any] | None = None
          while done_frame is None:
            raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
            frame = json.loads(raw)
            if frame["type"] == "exec":
              await ws.send(
                json.dumps({
                  "type": "result",
                  "id": frame["id"],
                  "ok": True,
                  "exit_code": 0,
                  "output": "smoke-ok\n",
                  "truncated": False,
                  "timed_out": False,
                })
              )
            elif frame["type"] in ("done", "error"):
              done_frame = frame
          assert done_frame["type"] == "done"
          assert "smoke-ok" in done_frame["final_message"]

        assert len(stub.requests) == 2
        assert stub.requests[0]["json"]["messages"][:2] == stub.requests[1]["json"]["messages"][:2]

        # 2) MCP task roundtrip (http initialize + tools/list + tools/call + done)
        async with websockets.connect(ws_url) as ws:
          await ws.send(
            json.dumps({
              "type": "task",
              "instruction": "Call MCP ping tool",
              "workdir": "/workspace",
              "mcp_servers": [{"name": "demo", "url": "http://127.0.0.1:18080/mcp"}],
              "limits": {"agent_timeout_sec": 60},
            })
          )
          mcp_done: dict[str, Any] | None = None
          while mcp_done is None:
            raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
            frame = json.loads(raw)
            if frame["type"] == "http":
              rpc = json.loads(base64.b64decode(frame["body_b64"]).decode("utf-8"))
              rpc_method = rpc.get("method")
              rpc_id = rpc.get("id")
              if rpc_method == "initialize":
                rpc_resp: dict[str, Any] | None = {
                  "jsonrpc": "2.0",
                  "id": rpc_id,
                  "result": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "demo", "version": "1.0"},
                  },
                }
              elif rpc_method == "notifications/initialized":
                rpc_resp = None
              elif rpc_method == "tools/list":
                rpc_resp = {
                  "jsonrpc": "2.0",
                  "id": rpc_id,
                  "result": {
                    "tools": [
                      {
                        "name": "ping",
                        "description": "Ping test server",
                        "inputSchema": {
                          "type": "object",
                          "properties": {"target": {"type": "string"}},
                        },
                      }
                    ]
                  },
                }
              elif rpc_method == "tools/call":
                rpc_resp = {
                  "jsonrpc": "2.0",
                  "id": rpc_id,
                  "result": {
                    "content": [{"type": "text", "text": "pong-from-mcp"}],
                    "isError": False,
                  },
                }
              else:
                rpc_resp = {"jsonrpc": "2.0", "id": rpc_id, "result": {}}

              resp_bytes = (
                json.dumps(rpc_resp).encode("utf-8") if rpc_resp is not None else b""
              )
              await ws.send(
                json.dumps({
                  "type": "result",
                  "id": frame["id"],
                  "ok": True,
                  "status": 200 if rpc_resp is not None else 202,
                  "headers": {"content-type": "application/json"},
                  "body_b64": base64.b64encode(resp_bytes).decode("ascii"),
                  "truncated": False,
                })
              )
            elif frame["type"] in ("done", "error"):
              mcp_done = frame
          assert mcp_done["type"] == "done"
          assert "pong-from-mcp" in mcp_done["final_message"]
      finally:
        proc.terminate()
        with contextlib.suppress(asyncio.TimeoutError):
          await asyncio.wait_for(proc.wait(), timeout=5.0)
        if proc.returncode is None:
          proc.kill()
          await proc.wait()

  asyncio.run(_scenario())


def test_model_family_reasoning_effort_payloads(monkeypatch: pytest.MonkeyPatch) -> None:
  taskbridge = _load_repo_module("taskbridge")
  harness = _load_repo_module("harness")

  async def _run_solve_for_model(
    model_name: str, configured_effort: str | None = None
  ) -> dict[str, Any]:
    async def stub_handler(
      req: dict[str, Any], _call_num: int
    ) -> tuple[int, str, bytes]:
      body = req["json"]
      lower_model = str(body.get("model", "")).lower()
      if ("gemma" in lower_model or "llama" in lower_model) and "reasoning_effort" in body:
        err = {"error": {"message": "reasoning_effort is not supported for this model"}}
        return (400, "application/json", json.dumps(err).encode("utf-8"))
      return (200, "text/event-stream", _sse_text_reply("verified answer", model_name))

    async with StubOpenAIServer(stub_handler) as stub:
      monkeypatch.setenv("MODEL_BASE_URL", stub.base_url)
      monkeypatch.setenv("MODEL_API_KEY", "stub-key")
      monkeypatch.setenv("MODEL_NAME", model_name)
      if configured_effort is None:
        monkeypatch.delenv("REASONING_EFFORT", raising=False)
      else:
        monkeypatch.setenv("REASONING_EFFORT", configured_effort)

      ws_port = _free_tcp_port()
      server_task = asyncio.create_task(
        taskbridge.serve_forever(harness.solve, port=ws_port)
      )
      try:
        ws = None
        for _ in range(50):
          try:
            ws = await websockets.connect(f"ws://127.0.0.1:{ws_port}")
            break
          except OSError as exc:
            if isinstance(exc, TimeoutError):
              raise
            await asyncio.sleep(0.05)
        assert ws is not None
        async with ws:
          await ws.send(
            json.dumps({"type": "task", "instruction": "Say verified answer"})
          )
          while True:
            frame = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
            if frame["type"] in ("done", "error"):
              assert frame["type"] == "done"
              assert "verified answer" in frame["final_message"]
              break
      finally:
        server_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
          await server_task

      assert len(stub.requests) == 1
      return stub.requests[0]["json"]

  async def _all_cases() -> None:
    claude_req = await _run_solve_for_model("google-cloud/claude-opus-5-5")
    assert claude_req.get("reasoning_effort") == "max"

    glm_req = await _run_solve_for_model("google-cloud/glm-5.2")
    assert glm_req.get("reasoning_effort") == "max"

    gemini_req = await _run_solve_for_model("google-cloud/gemini-4-argon")
    assert gemini_req.get("reasoning_effort") == "high"

    gpt_oss_req = await _run_solve_for_model("google-cloud/gpt-oss-120b")
    assert gpt_oss_req.get("reasoning_effort") == "high"

    gemma_req = await _run_solve_for_model("google-cloud/gemma-4-26b")
    assert "reasoning_effort" not in gemma_req

    llama_req = await _run_solve_for_model("google-cloud/llama-4-maverick")
    assert "reasoning_effort" not in llama_req

    override_req = await _run_solve_for_model(
      "google-cloud/gemini-4-argon", configured_effort="medium"
    )
    assert override_req.get("reasoning_effort") == "medium"

  asyncio.run(_all_cases())


def test_unauthorized_and_unreachable_proxy_emit_redacted_error_frames(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  taskbridge = _load_repo_module("taskbridge")
  harness = _load_repo_module("harness")
  fake_secret = "ple-proxy-synth-token-991"

  # Positive control using the exact same matcher helper
  raw_unredacted = f"Error code: 401 - Invalid API key {fake_secret} rejected by proxy"
  assert _contains_token(raw_unredacted, fake_secret) is True

  async def _collect_ws_frames(ws_port: int) -> tuple[list[dict[str, Any]], str]:
    stderr_buf = io.StringIO()
    with contextlib.redirect_stderr(stderr_buf):
      server_task = asyncio.create_task(
        taskbridge.serve_forever(harness.solve, port=ws_port)
      )
      frames: list[dict[str, Any]] = []
      try:
        ws = None
        for _ in range(50):
          try:
            ws = await websockets.connect(f"ws://127.0.0.1:{ws_port}")
            break
          except OSError as exc:
            if isinstance(exc, TimeoutError):
              raise
            await asyncio.sleep(0.05)
        assert ws is not None
        async with ws:
          await ws.send(
            json.dumps({
              "type": "task",
              "instruction": "Probe failing proxy",
              "limits": {"agent_timeout_sec": 4},
            })
          )
          while True:
            frame = json.loads(await asyncio.wait_for(ws.recv(), timeout=10.0))
            frames.append(frame)
            if frame["type"] in ("done", "error"):
              break
      finally:
        server_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
          await server_task
    return frames, stderr_buf.getvalue()

  async def _scenario() -> None:
    # 1) Unauthorized 401 where upstream echoes the secret in error body
    async def unauthorized_handler(
      _req: dict[str, Any], _call_num: int
    ) -> tuple[int, str, bytes]:
      err = {
        "error": {
          "message": f"Unauthorized token {fake_secret} for MODEL_PROXY_URL",
          "type": "authentication_error",
        }
      }
      return (401, "application/json", json.dumps(err).encode("utf-8"))

    async with StubOpenAIServer(unauthorized_handler) as stub:
      monkeypatch.delenv("MODEL_BASE_URL", raising=False)
      monkeypatch.setenv("MODEL_PROXY_URL", stub.base_url)
      monkeypatch.setenv("OPENAI_API_KEY", fake_secret)
      monkeypatch.setenv("MODEL_API_KEY", fake_secret)
      monkeypatch.setenv("MODEL_NAME", "google-cloud/glm-5.2")

      frames_401, stderr_401 = await _collect_ws_frames(_free_tcp_port())
      terminal_401 = frames_401[-1]
      log_frames_401 = [f for f in frames_401 if f.get("type") == "log"]
      assert terminal_401["type"] == "error"
      assert "401" in terminal_401["message"]
      assert len(log_frames_401) >= 1
      assert log_frames_401[0]["text"].strip() != ""

      sanitized_401 = json.dumps(frames_401) + "\n" + stderr_401
      leaked_401 = _contains_token(sanitized_401, fake_secret)
      assert not leaked_401, "synthetic secret leaked in 401 frames or stderr"

    # 2) Unreachable MODEL_PROXY_URL with credentials in URL & env
    closed_port = _free_tcp_port()
    monkeypatch.delenv("MODEL_BASE_URL", raising=False)
    monkeypatch.setenv(
      "MODEL_PROXY_URL", f"http://user:{fake_secret}@127.0.0.1:{closed_port}/v1"
    )
    monkeypatch.setenv("OPENAI_API_KEY", fake_secret)
    monkeypatch.setenv("MODEL_API_KEY", fake_secret)
    monkeypatch.setenv("MODEL_NAME", "google-cloud/glm-5.2")

    frames_unreach, stderr_unreach = await _collect_ws_frames(_free_tcp_port())
    terminal_unreach = frames_unreach[-1]
    log_frames_unreach = [f for f in frames_unreach if f.get("type") == "log"]
    assert terminal_unreach["type"] == "error"
    assert terminal_unreach["message"].strip() != ""
    assert len(log_frames_unreach) >= 1
    assert log_frames_unreach[0]["text"].strip() != ""

    sanitized_unreach = json.dumps(frames_unreach) + "\n" + stderr_unreach
    leaked_unreach = _contains_token(sanitized_unreach, fake_secret)
    assert not leaked_unreach, "synthetic secret leaked in unreachable frames or stderr"

  asyncio.run(_scenario())
