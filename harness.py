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

"""Tool-calling harness for any OpenAI-compatible model endpoint.

Connects to `MODEL_BASE_URL` (falling back to `MODEL_PROXY_URL` or
`OPENAI_BASE_URL`) using `MODEL_API_KEY` (falling back to `MODEL_PROXY_KEY` or
`OPENAI_API_KEY`) and `MODEL_NAME`. The model works in the task container
through four built-in tools (`bash`, `read_file`, `write_file`, `edit_file`)
plus the task's own MCP tools, and finishes when it provides a complete answer
without calling a tool. That answer becomes the final message. Calls go to the
Chat Completions API, or to the Responses API for OpenAI's GPT-6 models
(`RESPONSES_MODELS`).

Optional environment variables: `MAX_OUTPUT_TOKENS` (default `32000`),
`COMPACT_AT_TOKENS` (default `150000`), and `REASONING_EFFORT` (default `max`
for Claude, GLM, GPT-6 and DeepSeek-V4, omitted for Gemma and Llama, and `high`
for other models).
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
from decimal import Decimal
import json
import os
from pathlib import Path
import posixpath
import re
import shlex
import sys
import types
from typing import Any
import uuid

import deliverable_audit
import openai
import taskbridge
import urllib.parse

_AUDIT_SCRIPT_B64 = base64.b64encode(
    Path(__file__).with_name("deliverable_audit.py").read_bytes()
).decode("ascii")

MODEL = os.environ.get("MODEL_NAME", "")
MAX_EFFORT_MODELS = ("claude", "glm", "gpt-6", "deepseek-v4")
OMIT_EFFORT_MODELS = ("gemma", "llama")
SECRET_ENV_VARS = (
    "MODEL_API_KEY",
    "MODEL_PROXY_KEY",
    "OPENAI_API_KEY",
    "JUDGE_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "HF_TOKEN",
)
URL_ENV_VARS = (
    "MODEL_BASE_URL",
    "MODEL_PROXY_URL",
    "OPENAI_BASE_URL",
    "ANTHROPIC_BASE_URL",
    "GOOGLE_GEMINI_BASE_URL",
)
_SECRET_PATTERNS = (
    (re.compile(r"(https?://)([^/\s@]+)@"), r"\1[REDACTED]@"),
    (re.compile(r'([?&](?:api_?key|key|token|access_token)=)[^&#\s"\']+', re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-+/=:~]{4,}"), r"\1[REDACTED]"),
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"
            r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
        ),
        "[REDACTED]",
    ),
    (
        re.compile(
            r"(?<![A-Za-z0-9])(?:"
            r"sk-[A-Za-z0-9_\-]{8,}"
            r"|AIza[A-Za-z0-9_\-]{16,}"
            r"|hf_[A-Za-z0-9_\-]{16,}"
            r"|gh[pousr]_[A-Za-z0-9_]{16,}"
            r"|github_pat_[A-Za-z0-9_]{16,}"
            r"|AKIA[0-9A-Z]{16}"
            r"|xox[baprs]-[A-Za-z0-9\-]{10,}"
            r")"
        ),
        "[REDACTED]",
    ),
)


def resolve_reasoning_effort(
    model_name: str, configured_effort: str | None = None
) -> str | None:
  """Resolves static family-valid reasoning effort, or None when unsupported."""
  configured = (configured_effort or "").strip().lower()
  if configured in ("none", "off", "omit"):
    return None
  if configured:
    return configured
  lower = (model_name or "").lower()
  if any(m in lower for m in OMIT_EFFORT_MODELS):
    return None
  if any(m in lower for m in MAX_EFFORT_MODELS):
    return "max"
  return "high"


def _collect_secret_values() -> list[str]:
  """Collects active credential strings from environment variables and URLs."""
  found: set[str] = set()
  for key in SECRET_ENV_VARS:
    val = (os.environ.get(key) or "").strip()
    if len(val) >= 4 and val.lower() not in {"none", "null", "empty"}:
      found.add(val)
  for key in URL_ENV_VARS:
    raw_url = (os.environ.get(key) or "").strip()
    if not raw_url:
      continue
    try:
      parsed = urllib.parse.urlsplit(raw_url)
    except ValueError:
      continue
    user = parsed.username or ""
    pwd = parsed.password or ""
    unq_user = urllib.parse.unquote(user) if user else ""
    unq_pwd = urllib.parse.unquote(pwd) if pwd else ""
    for item in (user, unq_user, pwd, unq_pwd):
      if len(item) >= 4 and item.lower() not in {"none", "null", "empty"}:
        found.add(item)
    if user and pwd:
      found.add(f"{user}:{pwd}")
      found.add(f"{unq_user}:{unq_pwd}")
    for qk, qvals in urllib.parse.parse_qs(parsed.query).items():
      if qk.lower() in {"api_key", "apikey", "key", "token", "access_token"}:
        for qv in qvals:
          if len(qv) >= 4:
            found.add(qv)
  return sorted(found, key=len, reverse=True)


def redact_secrets(text: str) -> str:
  """Replaces configured credentials and bearer/key tokens with [REDACTED]."""
  if not text:
    return text
  redacted = text
  for secret in _collect_secret_values():
    redacted = redacted.replace(secret, "[REDACTED]")
  for pat, repl in _SECRET_PATTERNS:
    redacted = pat.sub(repl, redacted)
  return redacted


STAGE2_RATES_PER_M: dict[str, tuple[Decimal, Decimal, Decimal, Decimal]] = {
    "claude-opus-5-5": (Decimal("4.00"), Decimal("5.00"), Decimal("0.20"), Decimal("20.00")),
    "gemini-4-argon": (Decimal("4.00"), Decimal("4.00"), Decimal("0.20"), Decimal("20.00")),
    "gemini-3.8-flash": (Decimal("1.50"), Decimal("1.50"), Decimal("0.15"), Decimal("7.50")),
    "gemini-3.1-pro-preview": (Decimal("2.00"), Decimal("2.00"), Decimal("0.20"), Decimal("12.00")),
    "glm-5.2": (Decimal("1.40"), Decimal("1.40"), Decimal("0.14"), Decimal("4.40")),
    "gemma-4-26b": (Decimal("0.15"), Decimal("0.15"), Decimal("0.015"), Decimal("0.60")),
    "llama-4-maverick": (Decimal("0.35"), Decimal("0.35"), Decimal("0.35"), Decimal("1.15")),
    "gpt-oss-120b": (Decimal("0.09"), Decimal("0.09"), Decimal("0.09"), Decimal("0.36")),
}


def _uget(obj: Any, name: str) -> Any:
  if obj is None:
    return None
  if isinstance(obj, dict):
    return obj.get(name)
  val = getattr(obj, name, None)
  if val is not None:
    return val
  extra = getattr(obj, "model_extra", None)
  return extra.get(name) if isinstance(extra, dict) else None


def normalize_usage(usage: Any) -> tuple[int, int, int, int]:
  """Normalizes OpenAI or Anthropic usage into (uncached_input, cache_write, cache_read, output)."""
  if usage is None:
    return (0, 0, 0, 0)
  prompt_tokens = _uget(usage, "prompt_tokens")
  completion_tokens = _uget(usage, "completion_tokens")
  input_tokens = _uget(usage, "input_tokens")
  output_tokens = _uget(usage, "output_tokens")
  cc_in = _uget(usage, "cache_creation_input_tokens")
  cr_in = _uget(usage, "cache_read_input_tokens")
  if input_tokens is not None and (prompt_tokens is None or cc_in is not None or cr_in is not None):
    uncached = max(0, int(input_tokens or 0))
    cache_write = max(0, int(cc_in or 0))
    cache_read = max(0, int(cr_in or 0))
    raw_out = output_tokens if output_tokens is not None else (completion_tokens or 0)
    return (uncached, cache_write, cache_read, max(0, int(raw_out or 0)))
  raw_p = max(0, int(prompt_tokens or 0))
  details = _uget(usage, "prompt_tokens_details")
  raw_cr = _uget(details, "cached_tokens")
  if raw_cr is None:
    raw_cr = _uget(usage, "cached_tokens")
  if raw_cr is None:
    raw_cr = cr_in
  raw_cw = _uget(details, "cache_write_tokens")
  if raw_cw is None:
    raw_cw = _uget(details, "cache_creation_tokens")
  if raw_cw is None:
    raw_cw = _uget(usage, "cache_write_tokens")
  if raw_cw is None:
    raw_cw = _uget(usage, "cache_creation_tokens")
  if raw_cw is None:
    raw_cw = cc_in
  cache_read = min(raw_p, max(0, int(raw_cr or 0)))
  cache_write = min(raw_p - cache_read, max(0, int(raw_cw or 0)))
  uncached = raw_p - cache_read - cache_write
  raw_out = completion_tokens if completion_tokens is not None else (output_tokens or 0)
  return (uncached, cache_write, cache_read, max(0, int(raw_out or 0)))


def stage2_cost_usd(
    model_name: str, uncached: int, cache_write: int, cache_read: int, output: int
) -> Decimal:
  """Computes January-2027 Stage-2 list cost in USD using exact Decimal arithmetic."""
  tail = (model_name or "").strip().lower().rsplit("/", 1)[-1]
  rates = STAGE2_RATES_PER_M.get(tail)
  if rates is None:
    return Decimal("0")
  return (
      Decimal(uncached) * rates[0]
      + Decimal(cache_write) * rates[1]
      + Decimal(cache_read) * rates[2]
      + Decimal(output) * rates[3]
  ) / Decimal(1_000_000)


def _sanitize_rollup_str(text: str, limit: int = 500) -> str:
  clean = redact_secrets(text or "")
  clean = re.sub(r"[\x00-\x1f\x7f-\x9f  ]+", " ", clean).strip()
  return redact_secrets(clean)[:limit]


def _build_client() -> openai.AsyncOpenAI:
  base_url = (
      os.environ.get("MODEL_BASE_URL")
      or os.environ.get("MODEL_PROXY_URL")
      or os.environ.get("OPENAI_BASE_URL")
  )
  api_key = (
      os.environ.get("MODEL_API_KEY")
      or os.environ.get("MODEL_PROXY_KEY")
      or os.environ.get("OPENAI_API_KEY")
      or "none"
  )
  return openai.AsyncOpenAI(
      base_url=base_url,
      api_key=api_key,
      max_retries=0,
      timeout=900,
  )


# OpenAI's GPT-6 models only support function tools combined with
# reasoning_effort on the Responses API. Other models also switch to
# /v1/responses if /v1/chat/completions returns a 400 directing them there.
RESPONSES_MODELS = ("gpt-6",)
RESPONSES_ONLY = re.compile(
    r"/v1/responses|not supported.{0,80} in /v1/chat/completions"
)
# Claude reuses a cached prompt prefix only where a request marks one
# (marked()); other models cache on their own.
CACHE_MARK = "claude" in MODEL.lower()
TOOL_RESULT_CHARS = 30_000
# MCP tools are offered as functions up to this many characters of JSON in all
DIRECT_MCP_CHARS = 40_000
# functions one request may offer (OpenAI's limit), the built-in four included
MAX_TOOLS = 128
KEEP_RECENT_RESULTS = 12
FINISH_MARGIN_SEC = 180
RETRY_WAITS = (5, 15, 30, 60, 120)
# How endpoints word an error saying the conversation no longer fits (xAI's:
# "maximum prompt length is N but the request contains M tokens"). OpenAI's
# error for too many tools ("'tools': array too long") does not match.
CONTEXT_FULL = re.compile(
    r"context.?(length|window|size|limit)|maximum context|too many"
    r" tokens|prompt is too long|maximum prompt length"
    r"|(input|prompt|request|messages?)\b[^.]{0,40}(too long|exceed)"
    r"|exceed[^.]{0,40}(token|context)",
    re.I,
)
# The context window and the prompt's share of it, as vLLM, OpenAI, Anthropic,
# Gemini and xAI word them in such an error.
WINDOW_RE = re.compile(
    r"maximum context length (?:is |of )?(\d+)"
    r"|context (?:window|length|size)(?: limit)?(?: is| of)? (\d+)"
    r"|tokens? > (\d+) maximum|maximum number of tokens allowed \((\d+)\)"
    r"|maximum prompt length is (\d+)",
    re.I,
)
PROMPT_RE = re.compile(
    r"(\d+) input tokens|(\d+) in the messages|prompt is too long: (\d+)"
    r"|input token count \((\d+)\)|request contains (\d+) tokens",
    re.I,
)
MIN_OUTPUT = 1024  # the fewest output tokens to ask for
# characters an unread tool result keeps, however full the context
UNREAD_KEEP = 600
# tokens left free in the window, since tokenizers count a little differently
CONTEXT_MARGIN = 1024
# How endpoints word an error refusing a parameter or value outright, unlike one
# that names a smaller maximum.
UNSUPPORTED = re.compile(
    r"unsupported|unrecogni[sz]ed|unknown|not supported|does not support|not"
    r" (allowed|permitted)"
    r"|extra (inputs|fields)|unexpected",
    re.I,
)
# The standard fields of a streamed tool call, of its function, and of a reply's
# delta. Any other field an endpoint sends goes back with the message: Gemini
# refuses a tool call without its thought signature, which comes in the call's
# extra_content.
CALL_FIELDS = {"index", "id", "type", "function"}
FUNCTION_FIELDS = {"name", "arguments"}
DELTA_FIELDS = {
    "role",
    "content",
    "tool_calls",
    "function_call",
    "refusal",
    "audio",
    "annotations",
    "reasoning_content",
    "reasoning",
}

SYSTEM = """You are an expert engineer working on a task in a Linux container. Your tools act inside it: bash (it \
starts in {workdir}), read_file, write_file and edit_file. The container has no internet access.{mcp}

How to work:
- Read the whole task, then look at the files you were given before choosing an approach.
- Work in small, verified steps. Compute numbers with code rather than by hand, and check units.
- When the task says how the result is checked (a time limit, a format, a test), check it that way yourself.
- Write each deliverable exactly where, under the name and in the format the task asks for. Author a valid baseline \
early, then refine it: stage updates in same-directory ._ple_stage_* temporary files and promote with os.replace \
(write_file and edit_file do this automatically).
- Produce office and binary formats (docx, xlsx, pdf, ...) with code, such as python3 and the libraries in the \
container, so they are real files of that format. For new .xlsx workbooks, use XlsxWriter and pass both the formula \
expression and precomputed value to write_formula so cached values exist immediately.
- When multiple deliverables share calculated numbers, record canonical values in {work_dir}/facts.json and \
verify every deliverable matches them.
- On quantitative design or sizing tasks with a cost/performance objective, run a self-checked Python optimization \
script (using scipy or catalog search with `assert` checks verifying both a nominal pass and a violated-constraint \
failure) before finalizing.
- Before you finish, open every deliverable again and check that it is complete and readable.
- You have about {minutes} minutes in total; the time left is shown after the results of your tools.

When the work is done, answer without calling a tool: a short summary of what you delivered (the path of each file) \
and the key results. That answer is graded together with your files."""

VERIFIER_SYSTEM = """You are an independent read-only engineering auditor. Using only bash and read_file, inspect the \
produced deliverables in {workdir} against the task requirements (units, constraints, completeness, readability). Do \
not modify any file. Reply starting with VERIFIER_PASS if every requirement is satisfied, or VERIFIER_FAIL: followed \
by a concise numbered list of concrete defects."""

MCP_DIRECT = """

The task also offers its own tools (the functions named <server>__<tool>). Finalize and verify your calculations before invoking irreversible external MCP actions."""

MCP_CATALOG = """

The task also offers its own tools, listed below by server. Call mcp_find to see a tool's parameters, then mcp_call \
to run it. Finalize and verify your calculations before invoking irreversible external MCP actions.
{catalog}"""

SUMMARY_PROMPT = """The conversation is getting long, so the earlier turns will be removed. Write notes that let you \
continue without them: what the task requires, what you found in the files, every file you created or changed (with \
its path and state), the numbers and decisions so far, and what remains to do. Be specific."""


def tool(
    name: str, description: str, required: list[str], **properties: Any
) -> dict[str, Any]:
  """Builds an OpenAI function-tool definition dictionary.

  Args:
    name: Tool function name.
    description: Human-readable tool description.
    required: List of required parameter names.
    **properties: Parameter JSON Schema definitions keyed by parameter name.

  Returns:
    An OpenAI function-tool specification dictionary.
  """
  return {
      "type": "function",
      "function": {
          "name": name,
          "description": description,
          "parameters": {
              "type": "object",
              "properties": properties,
              "required": required,
          },
      },
  }


TOOLS = [
    tool(
        "bash",
        "Run a bash command in the task container and return its exit code and"
        " output. Each call starts a new shell in the working directory: only"
        " files persist between calls.",
        ["command"],
        command={"type": "string"},
        timeout_sec={
            "type": "integer",
            "description": (
                "Stop the command after this many seconds (default 120)."
            ),
        },
    ),
    tool(
        "read_file",
        "Read a text file from the task container.",
        ["path"],
        path={"type": "string"},
    ),
    tool(
        "write_file",
        "Create or overwrite a file in the task container; parent directories"
        " are created.",
        ["path", "content"],
        path={"type": "string"},
        content={"type": "string"},
        append={
            "type": "boolean",
            "description": (
                "Add to the end of the file instead (write a large file in"
                " parts)."
            ),
        },
    ),
    tool(
        "edit_file",
        "Replace exact text in a file. old_text must occur exactly once unless"
        " replace_all is true.",
        ["path", "old_text", "new_text"],
        path={"type": "string"},
        old_text={"type": "string"},
        new_text={"type": "string"},
        replace_all={"type": "boolean"},
    ),
]
MCP_TOOLS = [
    tool(
        "mcp_find",
        "Show the description and parameters of the task's own tools that match"
        " a query.",
        ["query"],
        query={
            "type": "string",
            "description": "A tool name, or words describing what you need.",
        },
    ),
    tool(
        "mcp_call",
        "Run one of the task's own tools.",
        ["tool", "arguments"],
        tool={"type": "string", "description": "The tool's name as listed."},
        arguments={"type": "object"},
    ),
]


def clip(text: str, limit: int = TOOL_RESULT_CHARS) -> str:
  """Truncates `text` in the middle if it exceeds `limit` characters.

  Args:
    text: String to clip.
    limit: Maximum character length before truncation.

  Returns:
    The original string if within `limit`, or a middle-truncated string.
  """
  if len(text) <= limit:
    return text
  head = limit * 2 // 3
  return (
      f"{text[:head]}\n[... {len(text) - limit} characters cut"
      f" ...]\n{text[-(limit - head):]}"
  )


def parse_arguments(call: dict[str, Any]) -> dict[str, Any] | str:
  """Parses a tool call's arguments into a dict or returns an error string.

  Rewrites `call["arguments"]` as canonical JSON (`"{}"` when invalid) because
  endpoints reject conversations containing malformed tool-call arguments.

  Args:
    call: Tool-call dictionary with an `arguments` JSON string field.

  Returns:
    The parsed arguments dictionary, or an error string for the model.
  """

  def reject(constant):
    raise ValueError(f"{constant} is not valid JSON")

  try:
    args = json.loads(call["arguments"] or "{}", parse_constant=reject)
    if not isinstance(args, dict):
      raise ValueError("the arguments must be a JSON object")
    call["arguments"] = (
        json.dumps(args, ensure_ascii=False)
        .encode("utf-8", "replace")
        .decode("utf-8")
    )
    return args
  except ValueError as exc:
    call["arguments"] = "{}"
    return (
        f"error: the arguments are not a valid JSON object ({exc}); send the"
        " call again"
    )


def unique_name(name: str, taken: Any) -> str:
  """Truncates `name` to 64 chars and appends `_2`, `_3`, ... if in `taken`.

  Args:
    name: Desired function name.
    taken: Collection or mapping of already-used function names.

  Returns:
    A unique function name of at most 64 characters.
  """
  candidate, n = name[:64], 1
  while candidate in taken:
    n += 1
    candidate = f"{name[:63 - len(str(n))]}_{n}"
  return candidate


def visible(text: str) -> str:
  """Strips `<think>...</think>` reasoning blocks from `text`.

  Args:
    text: Assistant response content string.

  Returns:
    The trimmed response text with inline `<think>` blocks removed.
  """
  return re.sub(r"<think>.*?(</think>|$)", "", text or "", flags=re.S).strip()


def extra_fields(part: Any, known: set[str]) -> dict[str, Any]:
  """Extracts non-null extra fields from a streamed SDK object `part`.

  The OpenAI SDK stores undeclared provider fields in `part.model_extra`.

  Args:
    part: Streamed Pydantic model object (delta, tool call, or function).
    known: Set of standard field names to exclude.

  Returns:
    Dictionary of extra fields not in `known` whose values are not `None`.
  """
  fields = getattr(part, "model_extra", None) or {}
  return {k: v for k, v in fields.items() if k not in known and v is not None}


def merged(old: Any, new: Any, key: str = "") -> Any:
  """Merges a single delta's extra field value `new` into `old`.

  Merges dictionaries key-by-key, concatenates lists, and replaces scalars.
  Delegates `thinking_blocks` lists to `thinking_blocks()`.

  Args:
    old: Accumulated field value so far.
    new: Incoming delta field value.
    key: Field name being merged.

  Returns:
    The merged field value.
  """
  if key == "thinking_blocks" and isinstance(new, list):
    return thinking_blocks(old if isinstance(old, list) else [], new)
  if isinstance(old, dict) and isinstance(new, dict):
    return {**old, **{k: merged(old.get(k), v, k) for k, v in new.items()}}
  if isinstance(old, list) and isinstance(new, list):
    return old + new
  return new


def thinking_blocks(
    blocks: list[dict[str, Any]], new: list[Any]
) -> list[dict[str, Any]]:
  """Accumulates streamed Claude `thinking_blocks` deltas.

  Joins consecutive deltas into the current block until a `signature` closes it;
  redacted blocks (containing `data`) arrive whole and are kept separate.

  Args:
    blocks: Existing list of accumulated thinking blocks.
    new: New list of thinking block deltas from the stream chunk.

  Returns:
    Updated list of thinking block dictionaries.
  """
  out = [dict(b) for b in blocks]
  for b in new:
    if not isinstance(b, dict):
      continue
    last = out[-1] if out else None
    if (
        last is None
        or last.get("signature")
        or last.get("data")
        or b.get("data")
        or last.get("type") != b.get("type")
    ):
      out.append(dict(b))
      continue
    last["thinking"] = (last.get("thinking") or "") + (b.get("thinking") or "")
    if b.get("signature"):
      last["signature"] = b["signature"]
  return out


def signed(block: Any) -> bool:
  """Returns whether `block` has a `signature` or redacted `data` field.

  Args:
    block: Candidate thinking block dictionary.

  Returns:
    `True` if Claude will accept `block` in a subsequent turn, else `False`.
  """
  return isinstance(block, dict) and bool(
      block.get("signature") or block.get("data")
  )


def drop_thinking(
    message: dict[str, Any], unless: Any = lambda block: False
) -> dict[str, Any]:
  """Filters `thinking_blocks` in `message`, keeping blocks matching `unless`.

  Args:
    message: Assistant message dictionary to modify in place.
    unless: Predicate `unless(block)` returning `True` for blocks to keep.

  Returns:
    The modified `message` dictionary.
  """
  if isinstance(message.get("thinking_blocks"), list):
    message["thinking_blocks"] = [
        b for b in message["thinking_blocks"] if unless(b)
    ]
  fields = message.get("provider_specific_fields")
  if isinstance(fields, dict) and isinstance(
      fields.get("thinking_blocks"), list
  ):
    message["provider_specific_fields"] = {
        **fields,
        "thinking_blocks": [b for b in fields["thinking_blocks"] if unless(b)],
    }
  return message


def marked(
    messages: list[dict[str, Any]], cache_mark: bool | None = None
) -> list[dict[str, Any]]:
  """Returns the messages a Chat Completions call sends.

  For Claude, this is a copy whose system prompt and newest message carry
  `cache_control` (2 of Claude's 4 cache breakpoints), so every turn reads the
  conversation so far from the cache instead of paying for all of it again.
  The stored conversation stays as it is.

  Args:
    messages: The conversation so far.
    cache_mark: Optional override indicating whether Claude cache markers apply.

  Returns:
    `messages` itself for other models, or the marked copy for Claude.
  """
  if not (CACHE_MARK if cache_mark is None else cache_mark):
    return messages
  out = list(messages)
  for i in {0, len(out) - 1}:
    m, content = out[i], out[i].get("content")
    if isinstance(content, str) and content:
      out[i] = {
          **m,
          "content": [{
              "type": "text",
              "text": content,
              "cache_control": {"type": "ephemeral"},
          }],
      }
    else:
      out[i] = {**m, "cache_control": {"type": "ephemeral"}}
  return out


def response_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
  """Converts Chat Completions messages into Responses API input items.

  Assistant turns produced by the Responses API are replayed using their saved
  output items (including encrypted reasoning). Each function call takes its id
  and name from the turn's stored tool call, and its arguments as
  `parse_arguments` rewrote them.

  Args:
    messages: Conversation messages in Chat Completions format.

  Returns:
    The `input` list for a Responses API call.
  """
  items = []
  for m in messages:
    if m["role"] == "tool":
      items.append({
          "type": "function_call_output",
          "call_id": m["tool_call_id"],
          "output": m["content"],
      })
    elif m["role"] != "assistant":
      items.append({"role": m["role"], "content": m["content"]})
    elif "output_items" in m:
      calls = iter(m.get("tool_calls") or [])
      for item in m["output_items"]:
        call = None
        if item.get("type") == "function_call":
          call = next(calls, None)
        if call:
          item = {
              **item,
              "call_id": call["id"],
              "name": call["function"]["name"],
              "arguments": call["function"]["arguments"],
          }
        items.append(item)
    else:
      if m.get("content"):
        items.append({"role": "assistant", "content": m["content"]})
      items += [
          {
              "type": "function_call",
              "call_id": c["id"],
              "name": c["function"]["name"],
              "arguments": c["function"]["arguments"],
          }
          for c in m.get("tool_calls") or []
      ]
  return items


def chat_usage(usage: Any) -> Any:
  """Returns Responses API `usage` in the shape `record` and `report` read.

  Args:
    usage: A Responses API usage object, or None.

  Returns:
    An object with `prompt_tokens`, `completion_tokens` and
    `prompt_tokens_details.cached_tokens`, as Chat Completions reports them, or
    None.
  """
  if usage is None:
    return None
  details = getattr(usage, "input_tokens_details", None)
  return types.SimpleNamespace(
      prompt_tokens=usage.input_tokens or 0,
      completion_tokens=usage.output_tokens or 0,
      prompt_tokens_details=types.SimpleNamespace(
          cached_tokens=getattr(details, "cached_tokens", 0) or 0
      ),
  )


class MCPServer(taskbridge.MCPClient):
  """Client wrapper for a single task MCP server and its discovered tools."""

  def __init__(self, session: taskbridge.Session, spec: dict[str, Any]):
    super().__init__(session, spec["url"], client="custom-harness")
    self.name = spec["name"]
    self.tools: list[dict[str, Any]] = []

  async def start(self) -> None:
    """Initializes the MCP session and fetches the server's tool list."""
    await self.initialize()
    self.tools = await self.list_tools()

  async def call(self, name: str, arguments: dict[str, Any]) -> str:
    """Calls tool `name` on the MCP server and formats the result as text.

    Args:
      name: Unprefixed MCP tool name on this server.
      arguments: Tool input arguments dictionary.

    Returns:
      Formatted text output (prefixed with `error: ` if `isError` is set).
    """
    result = await self.call_tool(name, arguments)
    parts = []
    content = (
        result.get("content") if isinstance(result.get("content"), list) else []
    )
    for item in content:
      kind = item.get("type") if isinstance(item, dict) else None
      if kind == "text":
        parts.append(str(item.get("text", "")))
      elif kind == "resource":
        parts.append(json.dumps(item.get("resource"))[:TOOL_RESULT_CHARS])
      elif kind == "resource_link":  # its uri, name and mimeType
        parts.append(json.dumps(item)[:TOOL_RESULT_CHARS])
      else:
        parts.append(f"[{kind or 'unknown'} content not shown]")
    if not parts and result.get("structuredContent") is not None:
      parts.append(json.dumps(result["structuredContent"]))
    text = "\n".join(parts) or "(no content)"
    return f"error: {text}" if result.get("isError") else text


class Reply:
  """Accumulates a streamed chat-completion response and its tool calls."""

  def __init__(self):
    self.text, self.reasoning, self.calls, self.usage, self.finish = (
        "",
        "",
        {},
        None,
        None,
    )
    self.extra = {}  # fields beyond DELTA_FIELDS, sent back with the message
    self._by_index, self._by_id, self._last = {}, {}, None

  def add_call(self, part: Any) -> None:
    """Adds one streamed tool-call delta to the accumulated calls.

    Groups deltas by `index`, or by `id` when an endpoint omits or reuses
    `index`. Deltas with neither continue the most recent call unless
    `_another_call` detects a new call boundary. Preserves provider-specific
    extra fields on both the call and its `function`.

    Args:
      part: Streamed tool-call delta object from a completion chunk.
    """
    index, call_id = (
        getattr(part, "index", None),
        getattr(part, "id", None) or "",
    )
    function = getattr(part, "function", None)
    name = (getattr(function, "name", None) or "") if function else ""
    key = self._by_index.get(index) if index is not None else None
    if (
        key is not None
        and call_id
        and self.calls[key]["id"] not in ("", call_id)
    ):
      key = None
    if (
        key is not None
        and not call_id
        and name
        and self._another_call(self.calls[key], name)
    ):
      key = None
    if key is None and call_id:
      key = self._by_id.get(call_id)
    if (
        key is None
        and index is None
        and not call_id
        and self._last is not None
        and not (name and self._another_call(self.calls[self._last], name))
    ):
      key = self._last
    if key is None:
      key = len(self.calls)
      self.calls[key] = {
          "id": "",
          "name": "",
          "arguments": "",
          "extra": {},
          "function_extra": {},
      }
    if index is not None:
      self._by_index[index] = key
    if call_id:
      self._by_id[call_id] = key
    call = self.calls[key]
    call["id"] = call["id"] or call_id
    call["name"] = call["name"] or name
    call["arguments"] += (
        (getattr(function, "arguments", None) or "") if function else ""
    )
    call["extra"] = merged(call["extra"], extra_fields(part, CALL_FIELDS))
    if function:
      call["function_extra"] = merged(
          call["function_extra"], extra_fields(function, FUNCTION_FIELDS)
      )
    self._last = key

  @staticmethod
  def _another_call(call: dict[str, Any], name: str) -> bool:
    """Checks whether a nameless-ID delta for `name` starts a new tool call.

    Returns `True` when `call` already has a function name and either `name`
    differs or `call["arguments"]` is already a complete JSON object.

    Args:
      call: Currently accumulating tool-call dictionary.
      name: Function name on the incoming delta.

    Returns:
      `True` if the delta begins a separate tool call, else `False`.
    """
    if not call["name"]:
      return False
    if name != call["name"]:
      return True
    try:
      return isinstance(json.loads(call["arguments"]), dict)
    except ValueError:
      return False

  def message(self) -> dict[str, Any]:
    """Builds the assistant message dict for the conversation history.

    Preserves provider-specific fields while stripping unsigned thinking blocks
    that Claude would reject.

    Returns:
      The formatted assistant message dictionary.
    """
    message = {**self.extra, "role": "assistant", "content": self.text or None}
    if self.calls:
      message["tool_calls"] = [
          {
              **c["extra"],
              "id": c["id"],
              "type": "function",
              "function": {
                  **c["function_extra"],
                  "name": c["name"],
                  "arguments": c["arguments"],
              },
          }
          for c in self.calls.values()
      ]
    if self.reasoning:
      message["reasoning_content"] = self.reasoning
    return drop_thinking(message, unless=signed)


class OutOfTime(Exception):  # pylint: disable=g-bad-exception-name
  """Raised when retrying a failed model call would exceed the time budget."""


class CutOff(asyncio.TimeoutError):  # pylint: disable=g-bad-exception-name
  """Raised when a streamed reply is cut off by its per-call deadline."""


class StreamBadRequest(openai.OpenAIError):  # pylint: disable=g-bad-exception-name
  """Raised when an SSE stream reports a non-retryable bad request error.

  OpenAI streams report errors via `type` and `code` strings (such as
  `invalid_request_error` or `context_length_exceeded`) instead of an HTTP 400
  status. Treating them as 400-equivalent allows `remedy()` to adjust the
  request rather than retrying it unchanged.
  """


# `type` or `code` values of an in-stream error that mark a bad request
BAD_REQUEST = frozenset({
    "invalid_request_error",
    "context_length_exceeded",
    "invalid_value",
    "invalid_prompt",
})


def stream_error(error: Any) -> openai.OpenAIError:
  """Classifies an in-stream error object as a bad request or a truncated stream.

  Args:
    error: Error object or dict reported inside an SSE stream.

  Returns:
    `StreamBadRequest` if the error type, code, or message indicates an invalid
    request or context overflow; otherwise `StreamCut` so the call is retried.
  """
  def field(name: str) -> Any:
    if isinstance(error, dict):
      return error.get(name)
    return getattr(error, name, None)

  message = str(field("message") or "")
  named = {field("type"), field("code")} & BAD_REQUEST
  if named or CONTEXT_FULL.search(message):
    return StreamBadRequest(message)
  return StreamCut(f"the stream reported an error: {message}")


class StreamCut(openai.OpenAIError):  # pylint: disable=g-bad-exception-name
  """Raised when an SSE stream ends before reporting a finish reason.

  Indicates a dropped connection, proxy timeout, or transient in-stream error.
  The partial response is discarded and the call is retried.
  """


class Agent:
  """Manages the conversation, tool execution, and context compaction loop."""

  def __init__(self, session: taskbridge.Session):
    self.session = session
    self.model = os.environ.get("MODEL_NAME", MODEL)
    self.cache_mark = "claude" in self.model.lower()
    self.compact_at_tokens = int(os.environ.get("COMPACT_AT_TOKENS", "150000"))
    self.client = _build_client()
    self.tools = list(TOOLS)
    self.mcp: dict[str, tuple[MCPServer, dict[str, Any]]] = {}
    self.messages: list[dict[str, Any]] = []
    self.prompt_tokens = 0
    # Each call asks for output_limit(): output_ceiling (MAX_OUTPUT_TOKENS,
    # lowered by shrink_output when the endpoint refuses that many), or less
    # when the context window has less room beside the prompt.
    self.output_ceiling = int(os.environ.get("MAX_OUTPUT_TOKENS", "32000"))
    self.context_window: int | None = None  # learned from a context-full error
    self.max_output = self.output_ceiling  # the limit the last call asked for
    # max_tokens once an endpoint refuses this one
    self.token_limit = "max_completion_tokens"
    # empty when omitted for family or once an endpoint refuses it
    resolved_effort = resolve_reasoning_effort(
        self.model, os.environ.get("REASONING_EFFORT")
    )
    self.effort = {"reasoning_effort": resolved_effort} if resolved_effort else {}
    # whether calls go to the Responses API rather than Chat Completions
    model_tail = self.model.lower().rsplit("/", 1)[-1]
    self.responses = model_tail.startswith(RESPONSES_MODELS)
    self.finish_margin = FINISH_MARGIN_SEC
    self.session_tag = uuid.uuid4().hex[:12]
    self.cmd_seq = 0
    self.stage_seq = 0
    self.delivered: dict[str, int] = {}
    self.uncached_input_tokens = 0
    self.cache_write_tokens = 0
    self.cache_read_tokens = 0
    self.output_tokens = 0
    self.cost_usd = Decimal("0")
    self.usage_emitted = 0
    self.audit_outcome = "not_run"
    self.audit_repairs = 0
    self.opt_rounds = 0
    self.verifier_runs = 0
    self.verifier_repairs = 0
    self._workdir_dirty = False
    self._needs_reaudit = False
    self._audit_staged = False
    self._has_self_checked_opt = False
    self._opt_converged = False
    self._last_summary_prose = ""

  def _is_deliverable_target(self, target: str) -> bool:
    norm_t = posixpath.normpath(target)
    if norm_t.startswith(("/tmp/.ple_work_", "/private/tmp/.ple_work_")):
      return False
    norm_w = posixpath.normpath(self.session.workdir)
    w_in_tmp = norm_w in ("/tmp", "/private/tmp") or norm_w.startswith(("/tmp/", "/private/tmp/"))
    t_in_tmp = norm_t in ("/tmp", "/private/tmp") or norm_t.startswith(("/tmp/", "/private/tmp/"))
    if t_in_tmp and not w_in_tmp:
      return False
    return True

  def _sync_final_message(self, prose: str = "") -> str:
    clean_prose = redact_secrets(prose)
    if clean_prose.strip():
      self._last_summary_prose = clean_prose
    effective_prose = self._last_summary_prose
    manifest = "\n".join(f"{p} ({sz} bytes)" for p, sz in self.delivered.items())
    if not effective_prose:
      return f"Delivered files:\n{manifest}" if manifest else redact_secrets(self.session.final_message)
    if manifest and any(f"{p} ({sz} bytes)" not in effective_prose for p, sz in self.delivered.items()):
      return f"{effective_prose}\n\nDelivered files:\n{manifest}"
    return effective_prose

  async def close(self) -> None:
    """Closes the underlying HTTP client."""
    await self.client.close()

  async def run(self) -> str:
    """Runs the agent tool-calling loop until the task is complete.

    Returns:
      The final summary message produced by the agent.
    """
    mcp = await self.connect_mcp()
    left = self.session.time_left()
    # time kept for the final summary: FINISH_MARGIN_SEC, or a quarter of a
    # short task's time
    self.finish_margin = (
        FINISH_MARGIN_SEC
        if left is None
        else min(FINISH_MARGIN_SEC, max(left, 0) / 4)
    )
    self.messages = [
        {
            "role": "system",
            "content": SYSTEM.format(
                workdir=self.session.workdir,
                work_dir=f"/tmp/.ple_work_{self.session_tag}",
                mcp=mcp,
                minutes=int(left / 60) if left else "unlimited",
            ),
        },
        {"role": "user", "content": self.session.instruction},
    ]
    # head: the text of an answer cut off at the output limit
    nudges, head = 0, ""
    while True:
      if self.session.cancelled.is_set():
        raise taskbridge.Cancelled("cancelled")
      left = self.session.time_left()
      if left is not None and left < self.finish_margin:
        return await self.finish("Time is almost up.")
      try:
        reply = await self.complete(head=head)
      except OutOfTime as exc:
        if not self.session.final_message and len(self.messages) <= 2:
          raise RuntimeError(redact_secrets(str(exc))) from None
        return await self.finish(
            "Time is almost up, and the model is not answering."
        )
      # what it streamed is the answer if the summary call fails too
      except CutOff:
        return await self.finish("Time is almost up.")
      arguments = [parse_arguments(call) for call in reply.calls.values()]
      if reply.text or reply.calls:
        # A turn with neither (its output went to hidden reasoning, or a content
        # filter stopped it) is not sent back: endpoints refuse an assistant
        # message with null content and no tool calls.
        self.messages.append(reply.message())
      text = visible(head + reply.text)
      if text and not reply.calls:
        self.session.final_message = self._sync_final_message(text)
      elif text and not self.delivered and not self._last_summary_prose:
        self.session.final_message = redact_secrets(text)
      if not reply.calls:
        if visible(reply.text) and reply.finish == "length":
          # cut off at the output limit: ask for the rest, and reset the
          # empty-turn count
          nudges, head = 0, head + reply.text
          self.messages.append({
              "role": "user",
              "content": (
                  f"Your reply was cut off at the {self.max_output}-token"
                  " output limit. Continue where it stopped, and put long"
                  " content in files with write_file rather than in a reply."
              ),
          })
          continue
        if visible(reply.text) or nudges >= 2:
          if visible(reply.text):
            next_prompt = await self._post_completion_gate(text)
            if next_prompt is not None:
              nudges, head = 0, ""
              self.messages.append({"role": "user", "content": next_prompt})
              continue
          return self.session.final_message or text
        nudges += 1  # only consecutive empty turns end the run
        self.messages.append({
            "role": "user",
            "content": (
                "Continue the task; when it is done, answer with "
                "your summary of the deliverables."
            ),
        })
        continue
      nudges, head = 0, ""
      for call, args in zip(reply.calls.values(), arguments):
        if self.session.cancelled.is_set():
          raise taskbridge.Cancelled("cancelled")
        result = (
            await self.run_tool(call["name"], args)
            if isinstance(args, dict)
            else args
        )
        if reply.finish == "length" and isinstance(args, str):
          result += (
              f" Your reply hit the {self.max_output}-token output limit; write"
              " large files in parts."
          )
        self.messages.append(
            {"role": "tool", "tool_call_id": call["id"], "content": result}
        )
      left = self.session.time_left()
      if left is not None:
        self.messages[-1]["content"] += f"\n[{int(left // 60)} minutes left]"
      if self.prompt_tokens > self.compact_at():
        await self.compact()

  async def finish(self, why: str) -> str:
    """Prompts the model for a final summary without tools when time is up.

    Args:
      why: Reason string prepended to the wrap-up prompt.

    Returns:
      The final summary text, falling back to `self.session.final_message`.
    """
    left_pre = self.session.time_left()
    if (
        (bool(self.delivered) or self._workdir_dirty)
        and self._needs_reaudit
        and (left_pre is None or left_pre > 60)
        and not self.session.cancelled.is_set()
    ):
      with contextlib.suppress(taskbridge.TaskError):
        await self.audit_deliverables()
      self.session.final_message = self._sync_final_message()
    self.messages.append({
        "role": "user",
        "content": (
            f"{why} Stop working now and answer with your final "
            "summary: what you delivered, where, and the key results."
        ),
    })
    left = self.session.time_left()
    if left is None:
      reserve = 0.0
    else:
      bounded = max(left, 0.0)
      share = bounded - min(30.0, bounded * 0.25)
      reserve = left - max(5.0, share)
    try:
      text = visible(
          (
              await self.complete(tool_choice="none", reserve=reserve, head="")
          ).text
      )
    except (CutOff, openai.OpenAIError, OutOfTime, RuntimeError):
      text = ""
    if text:
      self.session.final_message = self._sync_final_message(text)
    return self.session.final_message or text

  async def connect_mcp(self) -> str:
    """Connects to the task's MCP servers and registers their tools.

    Exposes a small set of MCP tools directly as OpenAI functions; for larger
    tool sets, lists their names in the system prompt and exposes `mcp_find`
    and `mcp_call`.

    Returns:
      The system-prompt section describing the available MCP tools.
    """
    for spec in self.session.mcp_servers:
      server = MCPServer(self.session, spec)
      try:
        await server.start()
      except (taskbridge.TaskError, RuntimeError, ValueError) as exc:
        await self.session.log(f"MCP server {server.name} unavailable: {exc}")
        continue
      for t in server.tools:
        name = re.sub(r"[^A-Za-z0-9_-]", "_", f"{server.name}__{t['name']}")
        self.mcp[unique_name(name, self.mcp)] = (server, t)
      await self.session.log(
          f"MCP server {server.name}: {len(server.tools)} tools"
      )
    if not self.mcp:
      return ""
    functions = [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": (t.get("description") or t["name"])[:1024],
                "parameters": (
                    {
                        k: v
                        for k, v in (t.get("inputSchema") or {}).items()
                        if k != "$schema"
                    }
                    or {"type": "object", "properties": {}}
                ),
            },
        }
        for name, (_, t) in self.mcp.items()
    ]
    if (
        len(json.dumps(functions)) <= DIRECT_MCP_CHARS
        and len(self.tools) + len(functions) <= MAX_TOOLS
    ):
      self.tools += functions
      return MCP_DIRECT
    self.tools += MCP_TOOLS
    servers: dict[str, list[str]] = {}
    for name, (server, _) in self.mcp.items():
      servers.setdefault(server.name, []).append(name)
    return MCP_CATALOG.format(
        catalog="\n".join(
            f"{s}: {', '.join(names)}" for s, names in servers.items()
        )
    )

  def find_mcp(self, query: str) -> str:
    """Finds MCP tools matching `query` and formats their schemas.

    Returns as many matching tool schemas as fit within `TOOL_RESULT_CHARS`
    (always at least one, without truncating any individual schema).

    Args:
      query: Tool name or search keywords.

    Returns:
      Formatted descriptions and JSON parameter schemas of matching tools.
    """
    words = [w for w in re.split(r"[^a-z0-9]+", query.lower()) if w]

    def score(item):
      name, (_, t) = item
      text = f"{name} {t.get('description') or ''}".lower()
      return (
          (query == name) * 100
          + sum(w in name.lower() for w in words) * 3
          + sum(w in text for w in words)
      )

    best = [
        item
        for item in sorted(self.mcp.items(), key=score, reverse=True)[:8]
        if score(item) > 0
    ]
    if not best:
      return (
          f"no tool matches {query!r}; the names are listed in the system"
          " prompt"
      )
    found = [
        f"{name}: {(t.get('description') or '')[:400]}\nparameters:"
        f" {json.dumps(t.get('inputSchema') or {})}"
        for name, (_, t) in best
    ]
    while len(found) > 1 and len("\n\n".join(found)) > TOOL_RESULT_CHARS:
      found.pop()
    return "\n\n".join(found)

  async def complete(
      self,
      tool_choice: str = "auto",
      reserve: float | None = None,
      head: str | None = None,
      messages: list[dict[str, Any]] | None = None,
      tools: list[dict[str, Any]] | None = None,
  ) -> Reply:
    """Streams one model completion with retries and context-limit recovery.

    Stops streaming `reserve` seconds before the task deadline. Automatically
    adapts token limit parameters, shrinks output ceilings, or compacts the
    conversation when the endpoint reports a context-length error.

    Args:
      tool_choice: OpenAI `tool_choice` value (`"auto"` or `"none"`).
      reserve: Seconds before the task deadline at which to cut off the call.
      head: Prefix text from a prior length-truncated reply, if continuing.

    Returns:
      The completed `Reply` object.

    Raises:
      OutOfTime: If a transient error occurs and there is not enough time left
        to wait and retry.
      CutOff: If the response is still streaming when `reserve` is reached.
      openai.APIError: If a non-retryable API error occurs or retries are
        exhausted.
      StreamCut: If every stream, retries included, ends without a finish
        reason.
    """
    reserve = self.finish_margin if reserve is None else reserve
    waits = iter(RETRY_WAITS)
    while True:
      if self.session.cancelled.is_set():
        raise taskbridge.Cancelled("cancelled")
      try:
        reply = await self.stream(
            self.messages if messages is None else messages,
            tool_choice,
            reserve,
            head,
            tools=tools,
        )
        if reply.finish is None:
          raise StreamCut("the stream ended without a finish reason")
        saved_pt = self.prompt_tokens
        await self.record(reply)
        if messages is not None:
          self.prompt_tokens = saved_pt
        return reply
      except openai.APIStatusError as exc:
        if exc.status_code == 400 and await self.remedy(str(exc)):
          continue
        if not (exc.status_code in (408, 409, 429) or exc.status_code >= 500):
          safe_err = redact_secrets(f"{type(exc).__name__}: {exc}")
          await self.session.log(f"model call failed ({safe_err[:300]})")
          raise RuntimeError(safe_err) from None
        failure = exc
      except StreamBadRequest as exc:
        if await self.remedy(str(exc)):
          continue
        safe_err = redact_secrets(f"{type(exc).__name__}: {exc}")
        await self.session.log(f"model call failed ({safe_err[:300]})")
        raise RuntimeError(safe_err) from None
      # a connection error, a timeout, or a stream that errored or ended early
      except (openai.APIError, StreamCut) as exc:
        failure = exc
      safe_err = redact_secrets(f"{type(failure).__name__}: {failure}")
      wait = next(waits, None)
      if wait is None:
        await self.session.log(f"model call failed ({safe_err[:300]})")
        raise RuntimeError(safe_err) from None
      left = self.session.time_left()
      if left is not None and left - wait < reserve:
        await self.session.log(
            f"model call failed ({safe_err[:300]}); no time left to wait"
            f" {wait}s"
        )
        raise OutOfTime(safe_err[:300]) from None
      await self.session.log(
          f"model call failed ({safe_err[:300]}); again in {wait}s"
      )
      try:
        await asyncio.wait_for(self.session.cancelled.wait(), timeout=wait)
        raise taskbridge.Cancelled("cancelled")
      except asyncio.TimeoutError:
        pass

  async def remedy(self, error: str) -> bool:
    """Adjusts request parameters for the next call after a bad request.

    Args:
      error: The error message returned by a 400 response or stream failure.

    Returns:
      True if the request parameters were adjusted and the call can be retried.
    """
    if CONTEXT_FULL.search(error):
      # The conversation does not fit. Try in this order:
      # 1. fewer output tokens, when the error shows that alone makes room
      #    (restored as the prompt shrinks);
      # 2. compact() what the model has already read;
      # 3. fewer output tokens anyway, when the error did not give the
      #    prompt's size;
      # 4. cut_unread(), the tool results the model has not read yet.
      sent, measured = self.max_output, self.learn_context(error)
      if (
          measured
          and self.room() >= MIN_OUTPUT
          and self.output_limit() < sent
      ):
        return True
      return bool(
          await self.compact(force=True)
          or (not measured and self.output_limit() < sent)
          or self.cut_unread()
      )
    return (
        self.use_responses(error)
        or self.use_max_tokens(error)
        or self.drop_effort(error)
        or self.shrink_output(error)
    )

  def use_responses(self, error: str) -> bool:
    """Switches to the Responses API if a Chat Completions 400 points there.

    Args:
      error: Error message string from a 400 `APIStatusError`.

    Returns:
      `True` if calls now go to the Responses API.
    """
    if self.responses or not RESPONSES_ONLY.search(error):
      return False
    self.responses = True
    return True

  def use_max_tokens(self, error: str) -> bool:
    """Switches to `max_tokens` if `error` rejects `max_completion_tokens`.

    Args:
      error: Error message string from a 400 `APIStatusError`.

    Returns:
      `True` if the token limit parameter was switched to `max_tokens`.
    """
    if (
        self.token_limit != "max_completion_tokens"
        or "max_completion_tokens" not in error
        or not UNSUPPORTED.search(error)
    ):
      return False
    self.token_limit = "max_tokens"
    return True

  def drop_effort(self, error: str) -> bool:
    """Stops sending `reasoning_effort` once an endpoint refuses it.

    A model without reasoning, or a server that does not know the parameter,
    answers `400` naming it (`reasoning.effort` on the Responses API).

    Args:
      error: Error message string from a 400 `APIStatusError`.

    Returns:
      `True` if `reasoning_effort` was being sent and is now dropped.
    """
    if any(m.get("role") == "assistant" for m in self.messages):
      return False
    if not self.effort or not re.search(r"reasoning[._]effort", error):
      return False
    self.effort = {}
    return True

  def shrink_output(self, error: str) -> bool:
    """Lowers `output_ceiling` when `error` indicates a smaller output limit.

    Args:
      error: Error message string from a 400 `APIStatusError`.

    Returns:
      `True` if `output_ceiling` was reduced, else `False`.
    """
    if UNSUPPORTED.search(error):
      return False
    limit = re.search(r"(\d+)\s*\(exclusive\)", error)
    stated = re.search(
        r"at most (\d+)|(\d+), which is the maximum|maximum (?:allowed"
        r" )?(?:number of )?(?:output|"
        r"completion) tokens (?:is |of )?(\d+)",
        error,
        re.I,
    )
    if limit:
      new = int(limit.group(1)) - 1
    elif stated:
      new = int(next(g for g in stated.groups() if g))
    elif re.search(
        r"max_?(completion_)?tokens|maxOutputTokens|output tokens", error, re.I
    ):
      new = self.max_output // 2
    else:
      return False
    if new >= self.max_output or new < MIN_OUTPUT:
      return False
    self.output_ceiling = new
    return True

  def learn_context(self, error: str) -> bool:
    """Extracts context window and prompt token counts from `error`.

    Args:
      error: Error message string from a context-length `APIStatusError`.

    Returns:
      `True` if both `context_window` and `prompt_tokens` are now known.
    """
    window, prompt = WINDOW_RE.search(error), PROMPT_RE.search(error)
    if window:
      self.context_window = int(next(g for g in window.groups() if g))
    if prompt:
      self.prompt_tokens = int(next(g for g in prompt.groups() if g))
    return bool(prompt and self.context_window)

  def room(self) -> int | None:
    """Returns remaining output token capacity in the known context window.

    Returns:
      Available tokens beside the prompt, or `None` if the window size is
      unknown.
    """
    return (
        self.context_window - self.prompt_tokens - CONTEXT_MARGIN
        if self.context_window
        else None
    )

  def output_limit(self) -> int:
    """Computes the max output tokens to request on the next completion call.

    Returns:
      `output_ceiling`, clamped down to `room()` when known (never below
      `MIN_OUTPUT`).
    """
    room = self.room()
    return (
        self.output_ceiling
        if room is None
        else max(MIN_OUTPUT, min(self.output_ceiling, room))
    )

  def compact_at(self) -> int:
    """Returns the prompt token threshold at which to trigger compaction.

    Returns:
      `COMPACT_AT_TOKENS`, or a lower threshold when the known context window
      requires more room for output.
    """
    if not self.context_window:
      return self.compact_at_tokens
    room = min(self.output_ceiling, self.context_window // 2)
    return max(
        self.context_window // 4,
        min(
            self.compact_at_tokens,
            self.context_window - room - CONTEXT_MARGIN,
        ),
    )

  def estimate_prompt_tokens(self) -> int:
    """Estimates prompt token count at four JSON characters per token.

    Skips `output_items`, which repeat a Responses API turn's text and calls
    plus encrypted reasoning whose length does not track its token count.

    Returns:
      Estimated number of tokens in `self.messages`.
    """
    return (
        sum(
            len(json.dumps({k: v for k, v in m.items() if k != "output_items"}))
            for m in self.messages
        )
        // 4
    )

  async def stream(
      self,
      messages: list[dict[str, Any]],
      tool_choice: str,
      reserve: float,
      head: str | None = None,
      tools: list[dict[str, Any]] | None = None,
  ) -> Reply:
    """Streams a single chat completion call up to `reserve` seconds before end.

    If `head` is provided and the stream is cut off or cancelled, updates
    `self.session.final_message` with `visible(head + reply.text)`.

    Args:
      messages: Conversation message list to send.
      tool_choice: OpenAI `tool_choice` setting (`"auto"` or `"none"`).
      reserve: Seconds to hold back before the session deadline.
      head: Prefix text from an earlier truncated response, or `None`.

    Returns:
      The accumulated `Reply` instance.

    Raises:
      CutOff: If the stream times out at `left - reserve`.
      asyncio.CancelledError: If the task is cancelled during streaming.
    """
    left = self.session.time_left()
    self.max_output = self.output_limit()
    reply = Reply()

    active_tools = self.tools if tools is None else tools

    async def read():
      if self.responses:
        await self.respond(reply, messages, tool_choice, tools=active_tools)
        return
      stream = await self.client.chat.completions.create(
          model=self.model,
          messages=marked(messages, self.cache_mark),
          tools=active_tools,
          tool_choice=tool_choice,
          stream=True,
          stream_options={"include_usage": True},
          **self.effort,
          **{self.token_limit: self.max_output},
      )
      async for chunk in stream:
        reply.usage = chunk.usage or reply.usage
        if not chunk.choices:
          continue
        delta = chunk.choices[0].delta
        reply.finish = chunk.choices[0].finish_reason or reply.finish
        reply.text += delta.content or ""
        reply.reasoning += (
            getattr(delta, "reasoning_content", None)
            or getattr(delta, "reasoning", None)
            or ""
        )
        reply.extra = merged(reply.extra, extra_fields(delta, DELTA_FIELDS))
        for part in delta.tool_calls or []:
          reply.add_call(part)

    read_task = asyncio.create_task(read())
    cancel_task = asyncio.create_task(self.session.cancelled.wait())
    timeout = None if left is None else max(0.0, left - reserve)
    try:
      done, _ = await asyncio.wait(
          {read_task, cancel_task},
          timeout=timeout,
          return_when=asyncio.FIRST_COMPLETED,
      )
      if cancel_task in done or self.session.cancelled.is_set():
        read_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
          await read_task
        if not self._last_summary_prose and (head or (head is not None and not self.delivered)):
          partial = redact_secrets(visible(head + reply.text))
          if partial:
            self.session.final_message = partial
        raise taskbridge.Cancelled("cancelled")
      if not done:
        read_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
          await read_task
        if not self._last_summary_prose and (head or (head is not None and not self.delivered)):
          partial = redact_secrets(visible(head + reply.text))
          if partial:
            self.session.final_message = partial
        raise CutOff() from None
      await read_task
    except asyncio.CancelledError:
      if not self._last_summary_prose and (head or (head is not None and not self.delivered)):
        partial = redact_secrets(visible(head + reply.text))
        if partial:
          self.session.final_message = partial
      raise
    except openai.APIError as exc:
      # the SDK raises an error sent inside a chat stream as an APIError
      said = {
          "message": getattr(exc, "message", None) or str(exc),
          "type": getattr(exc, "type", None),
          "code": getattr(exc, "code", None),
      }
      if isinstance(exc, openai.APIStatusError) or isinstance(
          stream_error(said), StreamCut
      ):
        raise
      raise StreamBadRequest(said["message"]) from exc
    finally:
      cancel_task.cancel()
      with contextlib.suppress(asyncio.CancelledError):
        await cancel_task
      if not read_task.done():
        read_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
          await read_task
    for n, call in reply.calls.items():
      call["id"] = call["id"] or f"call_{n}_{len(self.messages)}"
      # some open models leak chat-template tokens into it
      call["name"] = call["name"].split("<|")[0].strip()
    return reply

  async def respond(
      self,
      reply: Reply,
      messages: list[dict[str, Any]],
      tool_choice: str,
      tools: list[dict[str, Any]] | None = None,
  ) -> None:
    """Streams a single Responses API call into `reply`.

    Keeps the conversation in Chat Completions format and converts it on each
    call via `response_input`. Because `store=False`, each response's output
    items (including encrypted reasoning) are saved and echoed back on
    subsequent turns. If the stream ends before `response.completed` or
    `response.incomplete`, `reply.finish` remains `None` so the call is retried.

    Args:
      reply: The `Reply` to populate as events arrive.
      messages: Conversation message list to send.
      tool_choice: `"auto"` or `"none"`.

    Raises:
      StreamCut: If the stream reports a transient error.
      StreamBadRequest: If the stream reports a non-retryable bad request.
    """
    effort = self.effort.get("reasoning_effort")
    active_tools = self.tools if tools is None else tools
    stream = await self.client.responses.create(
        model=self.model,
        input=response_input(messages),
        tools=[
            {"type": "function", **t["function"], "strict": False}
            for t in active_tools
        ],
        tool_choice=tool_choice,
        stream=True,
        store=False,
        include=["reasoning.encrypted_content"],
        max_output_tokens=self.max_output,
        **({"reasoning": {"effort": effort}} if effort else {}),
    )
    async for event in stream:
      kind = getattr(event, "type", "")
      if kind == "response.output_text.delta":
        reply.text += event.delta or ""
      elif kind in ("error", "response.failed"):
        raise stream_error(
            getattr(getattr(event, "response", None), "error", None) or event
        )
      elif kind in ("response.completed", "response.incomplete"):
        done = event.response
        items = [i.model_dump(exclude_none=True) for i in done.output or []]
        reply.extra = {"output_items": items}
        reply.text = "".join(
            part.get("text", "")
            for item in items
            if item.get("type") == "message"
            for part in item.get("content") or []
            if part.get("type") == "output_text"
        )
        for item in items:
          if item.get("type") == "function_call":
            reply.calls[len(reply.calls)] = {
                "id": item.get("call_id") or "",
                "name": item.get("name") or "",
                "arguments": item.get("arguments") or "",
                "extra": {},
                "function_extra": {},
            }
        reply.usage = chat_usage(done.usage)
        reason = getattr(done.incomplete_details, "reason", None)
        if kind == "response.completed":
          reply.finish = "tool_calls" if reply.calls else "stop"
        else:
          reply.finish = reason if reason == "content_filter" else "length"

  async def record(self, reply: Reply) -> None:
    """Updates `prompt_tokens` from `reply` and reports token usage.

    Args:
      reply: Completed `Reply` from `stream()`.
    """
    if reply.usage is None:
      self.prompt_tokens = self.estimate_prompt_tokens()
      return
    uncached, cw, cr, _ = normalize_usage(reply.usage)
    self.prompt_tokens = uncached + cw + cr
    await self.report(reply)

  async def report(self, reply: Reply) -> None:
    """Reports normalized token usage and accumulates Stage-2 cost."""
    if reply.usage is None:
      return
    uncached, cw, cr, out = normalize_usage(reply.usage)
    self.uncached_input_tokens += uncached
    self.cache_write_tokens += cw
    self.cache_read_tokens += cr
    self.output_tokens += out
    self.cost_usd += stage2_cost_usd(self.model, uncached, cw, cr, out)
    self.usage_emitted += 1
    await self.session.usage(self.model, uncached + cw + cr, out, cr)

  async def emit_rollup(
      self, status: str, summary: str = "", error: str = ""
  ) -> None:
    """Emits a single-line secret-redacted [PLE_ROLLUP] JSON log frame."""
    total_in = (
        self.uncached_input_tokens
        + self.cache_write_tokens
        + self.cache_read_tokens
    )
    payload = {
        "status": _sanitize_rollup_str(status, 32),
        "model": _sanitize_rollup_str(self.model, 128),
        "uncached_input_tokens": self.uncached_input_tokens,
        "cache_write_tokens": self.cache_write_tokens,
        "cache_read_tokens": self.cache_read_tokens,
        "output_tokens": self.output_tokens,
        "input_tokens": total_in,
        "cost_usd": round(float(self.cost_usd), 12),
        "audit_outcome": _sanitize_rollup_str(self.audit_outcome, 32),
        "opt_rounds": self.opt_rounds,
        "verifier_runs": self.verifier_runs,
        "summary": _sanitize_rollup_str(summary, 400),
        "error": _sanitize_rollup_str(error, 400),
    }
    line = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
    await self.session.log(f"[PLE_ROLLUP] {line}")

  async def run_tool(self, name: str, args: dict[str, Any]) -> str:
    """Dispatches a tool call by `name` and returns its clipped text output."""
    if self.session.cancelled.is_set():
      raise taskbridge.Cancelled("cancelled")
    await self.session.log(f"{name} {redact_secrets(json.dumps(args))[:400]}")
    try:
      if name == "mcp_call":
        name, args = str(args.get("tool", "")), args.get("arguments") or {}
        args = json.loads(args) if isinstance(args, str) else args
        if name not in self.mcp:
          return f"error: no tool named {name!r}; use mcp_find"
      if name in self.mcp:
        server, t = self.mcp[name]
        return clip(await server.call(t["name"], args))
      if name == "mcp_find":
        return self.find_mcp(str(args.get("query", "")))
      handler = {
          "bash": self.bash,
          "read_file": self.read_file,
          "write_file": self.write_file,
          "edit_file": self.edit_file,
      }.get(name)
      return (
          clip(await handler(**args))
          if handler
          else f"error: there is no tool named {name}"
      )
    except taskbridge.TaskError as exc:
      return f"error: {exc}"
    except (
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        RuntimeError,
    ) as exc:
      return f"error: {type(exc).__name__}: {exc}"

  def path(self, path: str) -> str:
    """Resolves `path` relative to `self.session.workdir` if not absolute.

    Args:
      path: Absolute or workdir-relative file path.

    Returns:
      The resolved container path string.
    """
    raw = (
        path
        if path.startswith("/")
        else posixpath.join(self.session.workdir, path)
    )
    return posixpath.normpath(raw)

  def _audit_bootstrap_cmd(self, work_dir: str) -> str:
    q_dir = shlex.quote(work_dir)
    audit_py = f"{work_dir}/deliverable_audit.py"
    q_audit = shlex.quote(audit_py)
    q_wdir = shlex.quote(self.session.workdir)
    if self._audit_staged:
      return f"python3 {q_audit} hook-pre {q_wdir} {q_dir} >/dev/null 2>&1 || true"
    write_py = (
        "import base64, pathlib; "
        f"p = pathlib.Path({audit_py!r}); "
        "p.exists() or p.write_bytes("
        f"base64.b64decode({_AUDIT_SCRIPT_B64!r}))"
    )
    return (
        f"{{ python3 -c {shlex.quote(write_py)} && python3 {q_audit} hook-pre"
        f" {q_wdir} {q_dir}; }} >/dev/null 2>&1 || true"
    )

  async def audit_deliverables(self) -> list[str]:
    """Runs Task-side deliverable audit and OOXML `<v>` patcher in `/tmp/.ple_work_*`."""
    if self.session.cancelled.is_set():
      raise taskbridge.Cancelled("cancelled")
    work_dir = f"/tmp/.ple_work_{self.session_tag}"
    q_dir = shlex.quote(work_dir)
    q_audit = shlex.quote(f"{work_dir}/deliverable_audit.py")
    q_wdir = shlex.quote(self.session.workdir)
    q_deliv = shlex.quote(json.dumps(list(self.delivered.keys())))
    boot = self._audit_bootstrap_cmd(work_dir)
    cmd = f"mkdir -p -- {q_dir} && {boot} && python3 {q_audit} audit {q_wdir} {q_dir} {q_deliv}"
    res = await self.session.exec(cmd, timeout_sec=45)
    out = res.get("output") or ""
    marker = "__PLE_AUDIT_JSON__:"
    idx = out.find(marker)
    if idx >= 0:
      self._audit_staged = True
    if res.get("exit_code", 0) != 0 or idx < 0:
      self.audit_outcome = "error"
      await self.session.log("[PLE_AUDIT] error: audit command failed")
      return []
    try:
      data = json.loads(out[idx + len(marker) :].strip())
    except ValueError as exc:
      self.audit_outcome = "error"
      await self.session.log(f"[PLE_AUDIT] error: {redact_secrets(str(exc))[:200]}")
      return []
    if not isinstance(data, dict):
      self.audit_outcome = "error"
      await self.session.log("[PLE_AUDIT] error: invalid audit payload")
      return []
    self.audit_outcome = str(data.get("outcome") or "pass")
    self._needs_reaudit = False
    for path_k, sz in (data.get("sizes") or {}).items():
      if path_k in self.delivered:
        self.delivered[path_k] = int(sz)
    findings = [str(x) for x in (data.get("findings") or [])]
    detail = "; ".join(findings)[:800] if findings else "ok"
    await self.session.log(f"[PLE_AUDIT] {self.audit_outcome}: {redact_secrets(detail)}")
    return findings

  async def run_verifier(self, candidate_text: str) -> str | None:
    """Runs a single clean-context read-only `VERIFIER` audit using `TOOLS[:2]`."""
    self.verifier_runs += 1
    v_tools = list(TOOLS[:2])
    v_messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": VERIFIER_SYSTEM.format(workdir=self.session.workdir),
        },
        {
            "role": "user",
            "content": (
                f"Task instruction:\n{self.session.instruction}\n\n"
                f"Candidate summary:\n{candidate_text}"
            ),
        },
    ]
    for _ in range(4):
      if self.session.cancelled.is_set():
        raise taskbridge.Cancelled("cancelled")
      left = self.session.time_left()
      if left is not None and left < self.finish_margin:
        return None
      v_reply = await self.complete(messages=v_messages, tools=v_tools)
      if not v_reply.calls:
        return visible(v_reply.text)
      v_args = [parse_arguments(c) for c in v_reply.calls.values()]
      v_messages.append(v_reply.message())
      saved_dirty = self._needs_reaudit
      for call, args in zip(v_reply.calls.values(), v_args):
        if call["name"] not in ("bash", "read_file"):
          result = "error: verifier is strictly read-only"
        elif isinstance(args, dict):
          result = await self.run_tool(call["name"], args)
        else:
          result = args
        v_messages.append(
            {"role": "tool", "tool_call_id": call["id"], "content": result}
        )
      self._needs_reaudit = saved_dirty
    return None

  async def _post_completion_gate(self, text: str) -> str | None:
    if self.session.cancelled.is_set():
      raise taskbridge.Cancelled("cancelled")
    should_audit = (bool(self.delivered) or self._workdir_dirty) and self._needs_reaudit
    left = self.session.time_left()
    if left is not None and left < self.finish_margin * 1.5:
      if should_audit:
        await self.audit_deliverables()
      return None
    if should_audit:
      findings = await self.audit_deliverables()
      self.session.final_message = self._sync_final_message(text)
      if findings and self.audit_repairs < 1:
        self.audit_repairs += 1
        bullets = "\n".join(f"- {item}" for item in findings[:10])
        return (
            "Deliverable audit flagged issues that must be fixed before"
            f" finishing:\n{bullets}\nRepair the deliverables, re-verify"
            " consistency, and provide your updated final summary."
        )
    max_opt = min(3, max(0, int(os.environ.get("PLE_MAX_OPT_ROUNDS", "3") or "3")))
    if self._has_self_checked_opt and "OPTIMIZATION_CONVERGED" in text:
      self._opt_converged = True
    if (
        (bool(self.delivered) or self._workdir_dirty)
        and deliverable_audit.is_quantitative_optimization_task(
            self.session.instruction
        )
        and not self._opt_converged
        and self.opt_rounds < max_opt
    ):
      self.opt_rounds += 1
      return (
          f"Optimization pass ({self.opt_rounds}/{max_opt}): Run a"
          " self-checked Python optimization script (include `assert` checks"
          " verifying both a nominal feasible design pass and a"
          " violated-constraint failure) using scipy or catalog search to"
          " improve the objective within all constraints. Stage improved"
          " deliverables via ._ple_stage_* + os.replace, or reply"
          " OPTIMIZATION_CONVERGED with your final summary once certified"
          " optimal."
      )
    if (
        os.environ.get("PLE_ENABLE_VERIFIER", "0").strip() == "1"
        and self.verifier_runs == 0
    ):
      verdict = await self.run_verifier(text)
      if (
          verdict
          and not verdict.lstrip().upper().startswith("VERIFIER_PASS")
          and self.verifier_repairs < 1
      ):
        self.verifier_repairs += 1
        return (
            "Clean-context read-only VERIFIER audit found gaps (1 targeted"
            f" repair pass):\n{verdict}\nFix these gaps in the deliverables"
            " and provide your updated final summary."
        )
    return None

  async def bash(self, command: str, timeout_sec: int = 120) -> str:
    """Executes `command` with bash and tees full output into `/tmp/.ple_work_*`."""
    if self.session.cancelled.is_set():
      raise taskbridge.Cancelled("cancelled")
    cap = int(self.session.limits.get("exec_timeout_sec") or 600)
    left = self.session.time_left()
    if left is not None:
      cap = min(cap, max(1, int(left - self.finish_margin)))
    self.cmd_seq += 1
    work_dir = f"/tmp/.ple_work_{self.session_tag}"
    log_path = f"{work_dir}/cmd_{self.cmd_seq:04d}.log"
    q_dir = shlex.quote(work_dir)
    q_log = shlex.quote(log_path)
    q_cmd = shlex.quote(command)
    q_audit = shlex.quote(f"{work_dir}/deliverable_audit.py")
    q_wdir = shlex.quote(self.session.workdir)
    pre_hook = self._audit_bootstrap_cmd(work_dir)
    wrapped = (
        f"mkdir -p -- {q_dir} && {pre_hook} && {{ PLE_WORK_DIR={q_dir} bash -c {q_cmd} > {q_log} 2>&1;"
        f" __ple_rc=$?; head -c 40000 {q_log};"
        f" if [ $(wc -c < {q_log}) -gt 40000 ]; then"
        " printf '\\n[... middle omitted ...]\\n';"
        f" tail -c 10000 {q_log}; fi;"
        f" python3 {q_audit} hook-post {q_wdir} {q_dir} 2>/dev/null || true;"
        " exit $__ple_rc; }"
    )
    result = await self.session.exec(
        wrapped, taskbridge.positive_int(timeout_sec, 120, cap)
    )
    if not result.get("timed_out"):
      self._audit_staged = True
    if "assert" in command and result.get("exit_code") == 0 and not result.get("timed_out"):
      self._has_self_checked_opt = True
    raw_out = result["output"] or ""
    if raw_out.endswith("\n__PLE_DIRTY__"):
      raw_out = raw_out[: -len("\n__PLE_DIRTY__")]
      self._workdir_dirty = True
      self._needs_reaudit = True
    if result.get("timed_out"):
      self._workdir_dirty = True
      self._needs_reaudit = True
    note = " (timed out)" if result.get("timed_out") else ""
    preview = clip(raw_out or "(no output)", TOOL_RESULT_CHARS - 200)
    return f"exit code {result['exit_code']}{note}\n{preview}\n[full_log: {log_path}]"

  async def read_file(self, path: str) -> str:
    """Reads a UTF-8 text file from `path` in the task container."""
    if self.session.cancelled.is_set():
      raise taskbridge.Cancelled("cancelled")
    data = await self.session.read_file(self.path(path))
    if b"\0" in data[:8192]:
      return (
          f"{path} is a binary file ({len(data)} bytes); inspect it with bash"
          " (python3, unzip -l, ...)"
      )
    return data.decode("utf-8", "replace") or "(empty file)"

  async def write_file(
      self, path: str, content: str, append: bool = False
  ) -> str:
    """Atomically stages `content` via same-directory `._ple_stage_*` + `os.replace`."""
    if self.session.cancelled.is_set():
      raise taskbridge.Cancelled("cancelled")
    target = self.path(path)
    payload = content.encode("utf-8")
    if append:
      res = await self.session.read_result(target)
      if res.get("ok"):
        if res.get("truncated"):
          raise taskbridge.TaskError(
              f"{path} is {res.get('size')} bytes, over the 10 MB read limit"
          )
        payload = base64.b64decode(res["content_b64"]) + payload
      else:
        err_l = str(res.get("error") or "").lower()
        if not any(k in err_l for k in ("no such file", "not found", "enoent", "does not exist")):
          raise taskbridge.TaskError(res.get("error"))
    if self.session.cancelled.is_set():
      raise taskbridge.Cancelled("cancelled")
    parent = posixpath.dirname(target) or "/"
    self.stage_seq += 1
    stage_path = posixpath.join(
        parent, f"._ple_stage_{self.session_tag}_{self.stage_seq}"
    )
    q_stage = shlex.quote(stage_path)
    q_target = shlex.quote(target)
    try:
      await self.session.write_file(stage_path, payload, append=False)
    except taskbridge.TaskError:
      if not self.session.cancelled.is_set():
        with contextlib.suppress(taskbridge.TaskError):
          await self.session.exec(f"rm -f -- {q_stage}", timeout_sec=15)
      raise
    if self.session.cancelled.is_set():
      raise taskbridge.Cancelled("cancelled")
    promo = await self.session.exec(
        "python3 -c 'import os, sys; os.replace(sys.argv[1], sys.argv[2])'"
        f" {q_stage} {q_target}",
        timeout_sec=30,
    )
    if promo.get("exit_code", 1) != 0:
      if not self.session.cancelled.is_set():
        with contextlib.suppress(taskbridge.TaskError):
          await self.session.exec(f"rm -f -- {q_stage}", timeout_sec=15)
      raise taskbridge.TaskError(
          promo.get("output") or f"failed to promote {stage_path} to {target}"
      )
    if path.endswith(".py") and "assert " in content:
      self._has_self_checked_opt = True
    if self._is_deliverable_target(target):
      self.delivered[target] = len(payload)
      self._needs_reaudit = True
      self.session.final_message = self._sync_final_message()
    elif posixpath.basename(target) == "facts.json":
      self._workdir_dirty = True
      self._needs_reaudit = True
    return f"{path} now holds {len(payload)} bytes"

  async def edit_file(
      self, path: str, old_text: str, new_text: str, replace_all: bool = False
  ) -> str:
    """Replaces `old_text` with `new_text` in `path` via atomic staging."""
    if self.session.cancelled.is_set():
      raise taskbridge.Cancelled("cancelled")
    text = (await self.session.read_file(self.path(path))).decode("utf-8")
    count = text.count(old_text) if old_text else 0
    if count == 0:
      return f"error: old_text was not found in {path}"
    if count > 1 and not replace_all:
      return (
          f"error: old_text occurs {count} times in {path}; add context to make"
          " it unique, or set replace_all"
      )
    await self.write_file(
        path,
        text.replace(old_text, new_text, -1 if replace_all else 1),
    )
    return f"replaced {count if replace_all else 1} occurrence(s) in {path}"

  def unread(self) -> list[dict[str, Any]]:
    """Returns tool result messages appended after the last assistant turn.

    Returns:
      List of unread `"tool"` role message dictionaries.
    """
    last = max(
        (n for n, m in enumerate(self.messages) if m["role"] == "assistant"),
        default=0,
    )
    return [m for m in self.messages[last:] if m["role"] == "tool"]

  async def compact(self, force: bool = False) -> bool:
    """Compacts conversation history without modifying unread tool results.

    First truncates older read tool outputs (keeping `KEEP_RECENT_RESULTS`
    unless `force` is `True`). If that is insufficient, summarizes older turns
    via a model call. Claude's thinking blocks stay on the kept turns: a block's
    signature does not depend on the turns before it, and Claude refuses a tool
    loop whose newest turn lost its block.

    Args:
      force: Whether compaction was triggered by a context-full error.

    Returns:
      `True` if any tool results were truncated or turns were summarized.
    """
    unread = {id(m) for m in self.unread()}
    results = [
        (n, m) for n, m in enumerate(self.messages) if m["role"] == "tool"
    ]
    # with `force`, the endpoint's own count of the prompt wins when it is
    # larger: the estimate can run low
    cuts, size = [], max(
        self.estimate_prompt_tokens(), self.prompt_tokens if force else 0
    )
    for n, m in results if force else results[:-KEEP_RECENT_RESULTS]:
      if force and self.context_window and size <= self.compact_at():
        break
      if len(m["content"]) > 600 and id(m) not in unread:
        size -= (len(m["content"]) - 400) // 4
        m["content"] = (
            m["content"][:400]
            + "\n[... removed to save context; run the tool again if needed"
            " ...]"
        )
        cuts.append(n)
    if cuts:
      await self.session.log(f"context: cut {len(cuts)} old tool results")
      self.prompt_tokens = self.estimate_prompt_tokens()
      if (
          not force
          or not self.context_window
          or self.prompt_tokens <= self.compact_at()
      ):
        return True
    cut = len(self.messages) - 6
    # the kept turns must not start with tool results whose call was replaced by
    # the notes
    while cut > 3 and self.messages[cut]["role"] == "tool":
      cut -= 1
    if cut < 10:  # too few turns to be worth a notes call
      return bool(cuts)
    try:
      notes = await self.stream(
          self.messages[:cut] + [{"role": "user", "content": SUMMARY_PROMPT}],
          "none",
          self.finish_margin,
      )
    except (openai.APIError, StreamCut, asyncio.TimeoutError) as exc:
      safe_note_err = redact_secrets(str(exc))[:200] or "out of time"
      await self.session.log(f"context: notes failed ({safe_note_err})")
      return bool(cuts)
    await self.report(notes)
    if notes.finish is None:
      await self.session.log(
          "context: the notes were cut short, so the turns are kept"
      )
      return bool(cuts)
    text = visible(notes.text)
    if not text:
      await self.session.log(
          "context: the notes came back empty, so the turns are kept"
      )
      return bool(cuts)
    if notes.finish == "length":
      text += "\n[the notes were cut off at the output limit]"
    self.messages = (
        self.messages[:2]
        + [{
            "role": "user",
            "content": (
                "Your notes on the work so far (earlier "
                "turns were removed to save context):\n"
                + text
            ),
        }]
        + self.messages[cut:]
    )
    await self.session.log(f"context: replaced {cut - 2} messages with notes")
    self.prompt_tokens = self.estimate_prompt_tokens()
    return True

  def cut_unread(self) -> bool:
    """Truncates unread tool results as a last resort when context is full.

    Clips each unread tool output exceeding `2 * UNREAD_KEEP` to an equal share
    of the remaining context window (or halves it when the window size is
    unknown).

    Returns:
      `True` if at least one unread tool result was shortened, else `False`.
    """
    unread = [m for m in self.unread() if len(m["content"]) > 2 * UNREAD_KEEP]
    if not unread:
      return False
    share = None
    if self.context_window:
      rest = (
          self.estimate_prompt_tokens()
          - sum(len(m["content"]) for m in unread) // 4
      )
      share = (self.compact_at() - rest) * 4 // len(unread)
    for m in unread:
      size = len(m["content"])
      # a share within 100 characters of the size would barely shrink it
      keep = size // 2 if share is None or share >= size - 100 else share
      m["content"] = clip(m["content"], max(UNREAD_KEEP, keep))
    self.prompt_tokens = self.estimate_prompt_tokens()
    return True


async def solve(session: taskbridge.Session) -> str:
  """Runs `Agent` on `session` and emits tail-pinned `[PLE_ROLLUP]` before exit."""
  agent = Agent(session)
  print(
      f"task: workdir {session.workdir}, model {agent.model},"
      f" {len(session.mcp_servers)} MCP server(s)",
      file=sys.stderr,
  )
  try:
    answer = await agent.run()
    if session.cancelled.is_set():
      raise taskbridge.Cancelled("cancelled")
    if agent.usage_emitted == 0:
      await session.usage(agent.model, 0, 0, 0)
    final_ans = redact_secrets(
        answer if isinstance(answer, str) and answer else session.final_message
    )
    session.final_message = final_ans
    await agent.emit_rollup("done", summary=final_ans)
    return final_ans
  except (taskbridge.Cancelled, asyncio.CancelledError):
    if agent.usage_emitted == 0:
      await session.usage(agent.model, 0, 0, 0)
    final_ans = redact_secrets(
        session.final_message or "(stopped: time is up)"
    )
    session.final_message = final_ans
    await agent.emit_rollup("cancelled", summary=final_ans)
    return final_ans
  except Exception as exc:
    safe_err = redact_secrets(f"{type(exc).__name__}: {exc}")
    if session.final_message:
      safe_final = redact_secrets(session.final_message)
      session.final_message = safe_final
      print(f"harness error: {safe_err}", file=sys.stderr, flush=True)
      await session.log(f"harness error after its summary: {safe_err}"[:2000])
      await agent.emit_rollup("error", summary=safe_final, error=safe_err)
      return safe_final
    await agent.emit_rollup("error", summary="", error=safe_err)
    raise RuntimeError(safe_err) from None
  finally:
    await agent.close()

