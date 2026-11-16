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

"""Ticket 02 Seam 1 tests: immutable prefix, /tmp exec tee, atomic staging, cancel, and [PLE_ROLLUP]."""

from __future__ import annotations

import asyncio
import base64
import contextlib
from decimal import Decimal
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

from hypothesis import given, settings, strategies as st
import pytest
import websockets

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
  sys.path.insert(0, str(TESTS_DIR))

from test_seam1_gate import OFFICIAL_GOOGLE_CLOUD_MODELS, StubOpenAIServer, _contains_token, _free_tcp_port, _load_repo_module, _safe_subprocess_env, _sse_text_reply, _sse_tool_call_reply  # noqa: E402

CONTAINER_CMD_TYPES = frozenset({"exec", "write_file", "read_file", "http"})
_RAW_RATES = {
  "claude-opus-5-5": ("4.00", "5.00", "0.20", "20.00"), "gemini-4-argon": ("4.00", "4.00", "0.20", "20.00"),
  "gemini-3.8-flash": ("1.50", "1.50", "0.15", "7.50"), "gemini-3.1-pro-preview": ("2.00", "2.00", "0.20", "12.00"),
  "glm-5.2": ("1.40", "1.40", "0.14", "4.40"), "gemma-4-26b": ("0.15", "0.15", "0.015", "0.60"),
  "llama-4-maverick": ("0.35", "0.35", "0.35", "1.15"), "gpt-oss-120b": ("0.09", "0.09", "0.09", "0.36"),
}
STAGE2_RATES_PER_M = {k: tuple(Decimal(x) for x in v) for k, v in _RAW_RATES.items()}


@contextlib.contextmanager
def _env_scope(**updates: str):
  prev = {k: os.environ.get(k) for k in updates}
  os.environ.update(updates)
  try:
    yield
  finally:
    for k, v in prev.items():
      os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


def _sse_reply(*, text: str = "", calls: list[tuple[str, str, dict[str, Any]]] | None = None, finish_reason: str = "stop", usage: dict[str, Any] | None = None, model: str = "google-cloud/claude-opus-5-5") -> bytes:
  delta: dict[str, Any] = {"role": "assistant"}
  if text:
    delta["content"] = text
  if calls:
    delta["tool_calls"] = [{"index": i, "id": cid, "type": "function", "function": {"name": fn, "arguments": json.dumps(a)}} for i, (cid, fn, a) in enumerate(calls)]
  default_u = {"prompt_tokens": 20, "completion_tokens": 5, "total_tokens": 25}
  chunks = [{"id": "c1", "object": "chat.completion.chunk", "model": model, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]}, {"id": "c1", "object": "chat.completion.chunk", "model": model, "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}], "usage": usage if usage is not None else default_u}]
  return ("".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n").encode("utf-8")


async def _run_ws_session(harness_mod: Any, taskbridge_mod: Any, workdir: Path, *, mcp_servers: list[dict[str, Any]] | None = None, fail_write_nums: set[int] | None = None, cancel_on_cmd_num: int | None = None, cancel_trigger: asyncio.Event | None = None) -> tuple[list[dict[str, Any]], int | None]:
  ws_port, frames, cancelled_at = _free_tcp_port(), [], None
  cmd_count = write_count = exec_count = 0
  fail_writes = fail_write_nums or set()
  with contextlib.redirect_stderr(io.StringIO()):
    server_task = asyncio.create_task(taskbridge_mod.serve_forever(harness_mod.solve, port=ws_port))
    try:
      ws = None
      for _ in range(40):
        try:
          ws = await websockets.connect(f"ws://127.0.0.1:{ws_port}")
          break
        except OSError:
          await asyncio.sleep(0.02)
      assert ws is not None
      async with ws:
        await ws.send(json.dumps({"type": "task", "instruction": "Solve task", "workdir": str(workdir), "mcp_servers": mcp_servers or [], "limits": {"agent_timeout_sec": 60}}))

        async def _watch_trigger() -> None:
          nonlocal cancelled_at
          if cancel_trigger is not None:
            await cancel_trigger.wait()
            if cancelled_at is None:
              cancelled_at = len(frames)
              await ws.send(json.dumps({"type": "cancel"}))

        trig_task = asyncio.create_task(_watch_trigger())
        try:
          while True:
            frame = json.loads(await asyncio.wait_for(ws.recv(), timeout=4.0))
            frames.append(frame)
            ftype = frame.get("type")
            if ftype in ("done", "error"):
              break
            if ftype in CONTAINER_CMD_TYPES:
              cmd_count += 1
              if cancel_on_cmd_num is not None and cmd_count == cancel_on_cmd_num and cancelled_at is None:
                cancelled_at = len(frames)
                await ws.send(json.dumps({"type": "cancel"}))
                continue
              if cancelled_at is not None:
                continue
            if ftype == "exec":
              exec_count += 1
              proc = subprocess.run(["bash", "-c", frame["command"]], cwd=str(workdir), env=_safe_subprocess_env({"PLEBENCH_EXEC_ID": f"ple-exec-{exec_count}"}), capture_output=True, timeout=4.0)
              raw_out = (proc.stdout + proc.stderr).decode("utf-8", errors="replace")
              await ws.send(json.dumps({"type": "result", "id": frame["id"], "ok": True, "exit_code": proc.returncode, "output": raw_out[:100_000], "truncated": len(raw_out) > 100_000, "timed_out": False}))
            elif ftype == "read_file":
              target = Path(frame["path"])
              res = {"type": "result", "id": frame["id"], "ok": False, "error": "No such file"} if not target.is_file() else {"type": "result", "id": frame["id"], "ok": True, "content_b64": base64.b64encode(d := target.read_bytes()).decode("ascii"), "size": len(d), "truncated": False}
              await ws.send(json.dumps(res))
            elif ftype == "write_file":
              write_count += 1
              target, chunk = Path(frame["path"]), base64.b64decode(frame["content_b64"])
              target.parent.mkdir(parents=True, exist_ok=True)
              if write_count in fail_writes:
                target.write_bytes(chunk[:3])
                await ws.send(json.dumps({"type": "result", "id": frame["id"], "ok": False, "error": "ENOSPC simulated mid-write failure"}))
              else:
                with target.open("ab" if frame.get("append") else "wb") as fh:
                  fh.write(chunk)
                await ws.send(json.dumps({"type": "result", "id": frame["id"], "ok": True, "size": target.stat().st_size}))
            elif ftype == "http":
              await ws.send(json.dumps({"type": "result", "id": frame["id"], "ok": False, "error": "unexpected http"}))
        finally:
          trig_task.cancel()
          with contextlib.suppress(asyncio.CancelledError):
            await trig_task
    finally:
      server_task.cancel()
      with contextlib.suppress(asyncio.CancelledError):
        await server_task
  return frames, cancelled_at


async def _run_stub(stub_fn: Any, workdir: Path, *, env: dict[str, str], no_retry: bool = False, **ws_kw: Any) -> tuple[list[dict[str, Any]], int | None, list[dict[str, Any]]]:
  taskbridge, harness = _load_repo_module("taskbridge"), _load_repo_module("harness")
  if no_retry:
    harness.RETRY_WAITS = ()
  async with StubOpenAIServer(stub_fn) as stub, contextlib.nullcontext():
    with _env_scope(MODEL_BASE_URL=stub.base_url, **env):
      frames, c_at = await _run_ws_session(harness, taskbridge, workdir, **ws_kw)
      return frames, c_at, stub.requests


def evaluate_p1_oracle(workdir: Path, expected_files: dict[str, bytes], frames: list[dict[str, Any]], cancelled_at: int | None) -> bool:
  all_disk = [p for p in workdir.rglob("*") if p.is_file()]
  deliverables = {str(p.relative_to(workdir)): p.read_bytes() for p in all_disk if not p.name.startswith("._ple_stage_")}
  if deliverables != expected_files or (cancelled_at is None and any(p.name.startswith("._ple_stage_") for p in all_disk)):
    return False
  if any(not Path(f["path"]).name.startswith("._ple_stage_") or not str(Path(f["path"]).parent).startswith(str(workdir)) for f in frames if f.get("type") == "write_file"):
    return False
  if not frames or frames[-1].get("type") != "done":
    return False
  final_msg = str(frames[-1].get("final_message", ""))
  if any(str(workdir / rel) not in final_msg or f"{len(data)} bytes" not in final_msg for rel, data in expected_files.items()):
    return False
  if cancelled_at is not None:
    if any(f.get("type") in CONTAINER_CMD_TYPES for f in frames[cancelled_at:]) or not any(f.get("type") == "usage" for f in frames):
      return False
    if len(frames) < 2 or frames[-2].get("type") != "log" or not str(frames[-2].get("text", "")).startswith("[PLE_ROLLUP] "):
      return False
  return True


def evaluate_p2_oracle(model_name: str, payloads: list[dict[str, Any]], usage_frames: list[dict[str, Any]], rollup: dict[str, Any]) -> bool:
  exp_u = exp_cw = exp_cr = exp_out = 0
  for u in payloads:
    if "input_tokens" in u and ("prompt_tokens" not in u or u.get("prompt_tokens") is None or "cache_creation_input_tokens" in u or "cache_read_input_tokens" in u):
      ui, cw, cr = max(0, int(u.get("input_tokens") or 0)), max(0, int(u.get("cache_creation_input_tokens") or 0)), max(0, int(u.get("cache_read_input_tokens") or 0))
      out = max(0, int(u["output_tokens"] if u.get("output_tokens") is not None else (u.get("completion_tokens") or 0)))
    else:
      raw_p, det = max(0, int(u.get("prompt_tokens") or 0)), u.get("prompt_tokens_details") or {}
      cr = min(raw_p, max(0, int(det.get("cached_tokens", u.get("cached_tokens", 0)) or 0)))
      cw = min(raw_p - cr, max(0, int(det.get("cache_write_tokens", det.get("cache_creation_tokens", u.get("cache_write_tokens", 0))) or 0)))
      ui, out = raw_p - cr - cw, max(0, int(u.get("completion_tokens") or 0))
    exp_u, exp_cw, exp_cr, exp_out = exp_u + ui, exp_cw + cw, exp_cr + cr, exp_out + out
  rates = STAGE2_RATES_PER_M[model_name.lower().rsplit("/", 1)[-1]]
  exp_cost = (Decimal(exp_u) * rates[0] + Decimal(exp_cw) * rates[1] + Decimal(exp_cr) * rates[2] + Decimal(exp_out) * rates[3]) / Decimal(1_000_000)
  got = (rollup.get("uncached_input_tokens", -1), rollup.get("cache_write_tokens", -1), rollup.get("cache_read_tokens", -1), rollup.get("output_tokens", -1))
  if any(v < 0 for v in got) or got != (exp_u, exp_cw, exp_cr, exp_out) or rollup.get("input_tokens") != exp_u + exp_cw + exp_cr:
    return False
  if sum(int(f.get("input_tokens", 0)) for f in usage_frames) != exp_u + exp_cw + exp_cr or sum(int(f.get("cache_read_tokens", 0)) for f in usage_frames) != exp_cr:
    return False
  try:
    return abs(Decimal(str(rollup["cost_usd"])) - exp_cost) <= Decimal("1e-9")
  except Exception:
    return False


def evaluate_p4_oracle(frames: list[dict[str, Any]], fake_secret: str) -> bool:
  if len(frames) < 2 or frames[-1].get("type") not in ("done", "error") or frames[-2].get("type") != "log":
    return False
  term_text = str(frames[-1].get("final_message", "")) + "\n" + str(frames[-1].get("message", ""))
  if fake_secret and (fake_secret in term_text):
    return False
  line = frames[-2].get("text", "")
  if not isinstance(line, str) or not line.startswith("[PLE_ROLLUP] "):
    return False
  if "\n" in line or "\r" in line or any(ord(ch) < 0x20 for ch in line) or (fake_secret in line):
    return False
  try:
    parsed = json.loads(line[len("[PLE_ROLLUP] ") :])
  except ValueError:
    return False
  req_keys = {"status", "model", "uncached_input_tokens", "cache_write_tokens", "cache_read_tokens", "output_tokens", "cost_usd"}
  return isinstance(parsed, dict) and req_keys.issubset(parsed.keys())


def test_immutable_prefix_static_effort_compaction_and_empty_mcp(tmp_path: Path) -> None:
  (tmp_path / "doc.txt").write_text("X" * 800, encoding="utf-8")

  async def _scenario() -> None:
    async def clean_h(_req: dict[str, Any], n: int) -> tuple[int, str, bytes]:
      if n == 1:
        return (200, "text/event-stream", _sse_reply(calls=[(f"c1_{i}", "read_file", {"path": "doc.txt"}) for i in range(13)], finish_reason="tool_calls", usage={"prompt_tokens": 500, "completion_tokens": 20, "total_tokens": 520}))
      if n == 2:
        return (200, "text/event-stream", _sse_reply(calls=[("c2_0", "read_file", {"path": "doc.txt"})], finish_reason="tool_calls", usage={"prompt_tokens": 900, "completion_tokens": 15, "total_tokens": 915}))
      return (200, "text/event-stream", _sse_reply(text="All turns done", finish_reason="stop"))

    async def err_h(req: dict[str, Any], n: int) -> tuple[int, str, bytes]:
      if n < 3:
        return await clean_h(req, n)
      return (400, "application/json", json.dumps({"error": {"message": "transient reasoning_effort note on bad gateway", "type": "invalid_request_error"}}).encode("utf-8"))

    env = {"MODEL_API_KEY": "stub-key", "MODEL_NAME": "google-cloud/claude-opus-5-5", "REASONING_EFFORT": "high", "COMPACT_AT_TOKENS": "100"}
    frames, _, reqs = await _run_stub(clean_h, tmp_path, env=env, mcp_servers=[])
    assert not any(f.get("type") == "http" for f in frames) and len(reqs) == 3
    sys0, tools0 = reqs[0]["json"]["messages"][0], reqs[0]["json"]["tools"]
    assert "._ple_stage_" in json.dumps(sys0)
    assert all(r["json"]["messages"][0] == sys0 and r["json"]["tools"] == tools0 and r["json"].get("reasoning_effort") == "high" for r in reqs[1:])
    assert any("context: cut " in f.get("text", "") for f in frames if f.get("type") == "log")

    frames2, _, reqs2 = await _run_stub(err_h, tmp_path, env=env, mcp_servers=[])
    assert frames2[-1]["type"] == "error" and all(r["json"].get("reasoning_effort") == "high" for r in reqs2)

  asyncio.run(asyncio.wait_for(_scenario(), timeout=5.0))


def test_stateless_exec_preserves_exec_id_and_tees_large_output_to_tmp(tmp_path: Path) -> None:
  async def _scenario() -> None:
    cmd1 = "cd / && FOO_TMP=leaked && printf 'ID1=%s\\n' \"$PLEBENCH_EXEC_ID\" && python3 -c 'import sys; sys.stdout.write(\"H\"*45000 + \"MID_SENTINEL_77\" + \"T\"*65000); sys.exit(7)'"
    cmd2 = "printf 'PWD=%s|FOO=%s|ID2=%s\\n' \"$(pwd)\" \"${FOO_TMP:-unset}\" \"$PLEBENCH_EXEC_ID\""

    async def h(_req: dict[str, Any], n: int) -> tuple[int, str, bytes]:
      if n in (1, 2):
        return (200, "text/event-stream", _sse_tool_call_reply(f"b{n}", "bash", {"command": cmd1 if n == 1 else cmd2}))
      return (200, "text/event-stream", _sse_text_reply("exec verified"))

    _, _, reqs = await _run_stub(h, tmp_path, env={"MODEL_API_KEY": "stub-key", "MODEL_NAME": "google-cloud/glm-5.2"})
    t1_out, t2_out = reqs[1]["json"]["messages"][-1]["content"], reqs[2]["json"]["messages"][-1]["content"]
    try:
      assert "exit code 7" in t1_out and "ID1=ple-exec-1" in t1_out and len(t1_out) <= 30_500
      m = re.search(r"\[full_log:\s*(/tmp/\.ple_work_[A-Za-z0-9_]+/cmd_0001\.log)\]", t1_out)
      assert m is not None
      full_log = Path(m.group(1)).read_text(encoding="utf-8")
      assert len(full_log) > 110_000 and "MID_SENTINEL_77" in full_log
      assert f"PWD={tmp_path.resolve()}|FOO=unset|ID2=ple-exec-2" in t2_out or f"PWD={tmp_path}|FOO=unset|ID2=ple-exec-2" in t2_out
      assert list(tmp_path.iterdir()) == []
    finally:
      for text in (t1_out, t2_out):
        for match in re.findall(r"/tmp/\.ple_work_[A-Za-z0-9_]+", text):
          shutil.rmtree(match, ignore_errors=True)

  asyncio.run(asyncio.wait_for(_scenario(), timeout=5.0))


def test_atomic_staging_midwrite_failure_and_cancel_zero_io(tmp_path: Path) -> None:
  async def _scenario() -> None:
    async def write_h(_req: dict[str, Any], n: int) -> tuple[int, str, bytes]:
      if n == 1:
        return (200, "text/event-stream", _sse_tool_call_reply("w1", "write_file", {"path": "out/ans.txt", "content": "alpha-v1"}))
      if n == 2:
        return (200, "text/event-stream", _sse_tool_call_reply("w2", "edit_file", {"path": "out/ans.txt", "old_text": "v1", "new_text": "v2-clean"}))
      if n == 3:
        return (200, "text/event-stream", _sse_tool_call_reply("w3", "write_file", {"path": "out/ans.txt", "content": "corrupt-attempt"}))
      return (200, "text/event-stream", _sse_text_reply(f"Delivered {tmp_path / 'out/ans.txt'} (14 bytes)"))

    env = {"MODEL_API_KEY": "stub-key", "MODEL_NAME": "google-cloud/glm-5.2"}
    frames, _, _ = await _run_stub(write_h, tmp_path, env=env, fail_write_nums={3})
    assert evaluate_p1_oracle(tmp_path, {"out/ans.txt": b"alpha-v2-clean"}, frames, None)

    c_dir = tmp_path / "cancel_zero"
    c_dir.mkdir()
    in_stream, release_stream = asyncio.Event(), asyncio.Event()

    async def slow_h(_req: dict[str, Any], _n: int) -> tuple[int, str, bytes]:
      in_stream.set()
      with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(release_stream.wait(), timeout=1.5)
      return (200, "text/event-stream", _sse_text_reply("late"))

    c_frames, c_idx, _ = await _run_stub(slow_h, c_dir, env=env, cancel_trigger=in_stream)
    release_stream.set()
    assert c_idx is not None and evaluate_p1_oracle(c_dir, {}, c_frames, c_idx)
    assert json.loads(c_frames[-2]["text"][len("[PLE_ROLLUP] ") :])["status"] == "cancelled"

  asyncio.run(asyncio.wait_for(_scenario(), timeout=5.0))


def test_cross_provider_stage2_pricing_and_redacted_rollup(tmp_path: Path) -> None:
  fake_secret = "sk-" + "ple-synth-9988776655"
  assert _contains_token(f"err {fake_secret}", fake_secret) is True

  async def _scenario() -> None:
    u1 = {"input_tokens": 1000, "cache_creation_input_tokens": 2000, "cache_read_input_tokens": 5000, "output_tokens": 400}
    u2 = {"prompt_tokens": 9000, "completion_tokens": 600, "total_tokens": 9600, "prompt_tokens_details": {"cached_tokens": 7000, "cache_write_tokens": 500}}

    async def mixed_h(_req: dict[str, Any], n: int) -> tuple[int, str, bytes]:
      if n == 1:
        return (200, "text/event-stream", _sse_reply(text="part1 ", finish_reason="length", usage=u1))
      return (200, "text/event-stream", _sse_reply(text=f"ok 0 Bearer {fake_secret}", finish_reason="stop", usage=u2))

    env = {"MODEL_API_KEY": fake_secret, "MODEL_NAME": "google-cloud/claude-opus-5-5"}
    frames, _, _ = await _run_stub(mixed_h, tmp_path, env=env)
    p4_ok = evaluate_p4_oracle(frames, fake_secret)
    assert p4_ok, "mixed rollup P4 check failed"
    done_leaked = _contains_token(str(frames[-1].get("final_message", "")), fake_secret)
    assert not done_leaked, "secret leaked in done final_message"
    rollup = json.loads(frames[-2]["text"][len("[PLE_ROLLUP] ") :])
    p2_ok = evaluate_p2_oracle("google-cloud/claude-opus-5-5", [u1, u2], [f for f in frames if f.get("type") == "usage"], rollup)
    assert p2_ok, "Stage-2 P2 pricing conservation failed"

    async def err_h(_req: dict[str, Any], _n: int) -> tuple[int, str, bytes]:
      return (401, "application/json", json.dumps({"error": {"message": f"Auth failed\r\n\x07key={fake_secret}\nline3", "type": "authentication_error"}}).encode("utf-8"))

    err_frames, _, _ = await _run_stub(err_h, tmp_path, env=env, no_retry=True)
    assert err_frames[-1]["type"] == "error"
    err_p4_ok = evaluate_p4_oracle(err_frames, fake_secret)
    assert err_p4_ok, "error rollup P4 check failed"

  asyncio.run(asyncio.wait_for(_scenario(), timeout=5.0))


def test_sync_final_message_preserves_prose_and_excludes_scratch_paths(tmp_path: Path) -> None:
  taskbridge, harness = _load_repo_module("taskbridge"), _load_repo_module("harness")
  assert not hasattr(harness, "client") and not hasattr(harness, "EFFORT") and not hasattr(harness, "COMPACT_AT_TOKENS")

  async def _scenario() -> None:
    in_turn5, release_turn5 = asyncio.Event(), asyncio.Event()
    prose_summary = "Computed optimal beam section S200 with safety factor 1.85."
    scratch_facts = f"/tmp/.ple_work_scratch_test_{os.getpid()}/facts.json"

    async def _h(_req: dict[str, Any], n: int) -> tuple[int, str, bytes]:
      if n == 1:
        return (200, "text/event-stream", _sse_reply(calls=[("w1", "write_file", {"path": "beam.txt", "content": "S200 sf=1.8"}), ("w2", "write_file", {"path": scratch_facts, "content": "{\"sf\": 1.85}"})], finish_reason="tool_calls"))
      if n == 2:
        return (200, "text/event-stream", _sse_reply(text=prose_summary, finish_reason="stop"))
      if n == 3:
        return (200, "text/event-stream", _sse_reply(text="VERIFIER_FAIL: 1. Add exact 1.85 digit in beam.txt", finish_reason="stop"))
      if n == 4:
        return (200, "text/event-stream", _sse_reply(calls=[("w3", "write_file", {"path": "beam.txt", "content": "S200 sf=1.85\n"})], finish_reason="tool_calls"))
      in_turn5.set()
      with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(release_turn5.wait(), timeout=1.5)
      return (200, "text/event-stream", _sse_reply(text="Partial incomplete fragment", finish_reason="stop"))

    try:
      frames, _, _ = await _run_stub(_h, tmp_path, env={"MODEL_API_KEY": "stub-k", "MODEL_NAME": "google-cloud/glm-5.2", "PLE_ENABLE_VERIFIER": "1"}, cancel_trigger=in_turn5)
      release_turn5.set()
      final_msg = str(frames[-1].get("final_message", ""))
      assert prose_summary in final_msg
      assert f"{tmp_path / 'beam.txt'} (13 bytes)" in final_msg
      assert ".ple_work_" not in final_msg
      assert "Partial incomplete fragment" not in final_msg
    finally:
      shutil.rmtree(Path(scratch_facts).parent, ignore_errors=True)

    dummy_session = taskbridge.Session(None, {"type": "task", "instruction": "Test", "workdir": "/workspace"})
    ag = harness.Agent(dummy_session)
    try:
      assert ag._is_deliverable_target("/workspace/out.md") is True
      assert ag._is_deliverable_target("/filesystem/out.md") is True
      assert ag._is_deliverable_target("/tmp/scratch_script.py") is False
      assert ag._is_deliverable_target(f"/tmp/.ple_work_{ag.session_tag}/facts.json") is False
    finally:
      await ag.close()

  asyncio.run(asyncio.wait_for(_scenario(), timeout=6.0))


def test_redact_secrets_patterns_url_userinfo_and_hybrid_openai_usage() -> None:
  harness = _load_repo_module("harness")
  judge_key = "ple-judge-" + "secret-token-7788"
  url_user = "ple_url_user_99"
  url_pass_raw = "ple@pass/secret#42"
  url_pass_enc = "ple%40pass%2Fsecret%2342"
  tok_ai = "AIza" + "SyPleSynthKey0123456789abcdef"
  tok_hf = "hf_" + "pleSynthTokenAbcdef0123456789"
  tok_ghp = "ghp_" + "pleSynthGithubToken0123456789"
  tok_ghpat = "github_pat_" + "11ABCDEF0_pleSynthPat0123456789"
  tok_aws = "AKIA" + "IOSFODNN7PLESYNTH"
  tok_slack = "xoxb-" + "1234567890-pleSynthSlack"
  tok_bearer = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.ple+synth/tok=1:~"
  tok_q = "qparam_synth_secret_5566"
  pem_hdr = "-----BEGIN " + "RSA PRIVATE KEY-----"

  sample = (
    f"judge={judge_key} user={url_user} pass={url_pass_raw} "
    f"url=https://api.example.com/v1?api_key={tok_q}&other=1 "
    f"auth=Bearer {tok_bearer} g={tok_ai} h={tok_hf} gh1={tok_ghp} "
    f"gh2={tok_ghpat} aws={tok_aws} sl={tok_slack} pem={pem_hdr}"
  )
  assert all(_contains_token(sample, s) for s in (judge_key, url_user, url_pass_raw, tok_q, tok_bearer, tok_ai, tok_hf, tok_ghp, tok_ghpat, tok_aws, tok_slack, pem_hdr))

  with _env_scope(
    JUDGE_API_KEY=judge_key,
    ANTHROPIC_BASE_URL=f"https://{url_user}:{url_pass_enc}@proxy.example.com/v1",
  ):
    scrubbed = harness.redact_secrets(sample)

  leaked = any(
    _contains_token(scrubbed, s)
    for s in (judge_key, url_user, url_pass_raw, tok_q, tok_bearer, tok_ai, tok_hf, tok_ghp, tok_ghpat, tok_aws, tok_slack, pem_hdr)
  )
  assert not leaked, "redact_secrets left sensitive token unredacted"

  hybrid_u = {"prompt_tokens": 1000, "completion_tokens": 200, "cache_read_input_tokens": 600, "cache_creation_input_tokens": 150}
  assert harness.normalize_usage(hybrid_u) == (250, 150, 600, 200)


@settings(max_examples=15, deadline=None)
@given(actions=st.lists(st.one_of(st.tuples(st.just("write"), st.sampled_from(["a.txt", "nested/b.txt"]), st.text(alphabet="abcdef0123456789 ", min_size=1, max_size=40), st.booleans(), st.booleans()), st.tuples(st.just("cancel"))), min_size=1, max_size=8))
def test_pbt_p1_atomic_staging_and_cancel_guardian(actions: list[tuple[Any, ...]], tmp_path_factory: pytest.TempPathFactory) -> None:
  workdir = tmp_path_factory.mktemp("p1")
  expected: dict[str, bytes] = {}
  fail_nums: set[int] = set()
  cancel_cmd: int | None = None
  w_idx = cmd_idx = 0
  scripted: list[tuple[str, dict[str, Any]]] = []

  for act in actions:
    if act[0] == "cancel":
      cancel_cmd = cmd_idx + 1
      scripted.append(("bash", {"command": "echo should-cancel"}))
      break
    _, rel, content, append, should_fail = act
    cmd_idx += (1 if append else 0) + 2
    w_idx += 1
    if should_fail:
      fail_nums.add(w_idx)
    else:
      expected[rel] = (expected.get(rel, b"") if append else b"") + content.encode("utf-8")
    scripted.append(("write_file", {"path": rel, "content": content, "append": append}))

  async def _h(_req: dict[str, Any], n: int) -> tuple[int, str, bytes]:
    if n <= len(scripted):
      return (200, "text/event-stream", _sse_tool_call_reply(f"p1_{n}", scripted[n - 1][0], scripted[n - 1][1]))
    summary = "Delivered: " + ", ".join(f"{workdir / k} ({len(v)} bytes)" for k, v in expected.items()) if expected else "Done empty"
    return (200, "text/event-stream", _sse_text_reply(summary))

  frames, c_at, _ = asyncio.run(asyncio.wait_for(_run_stub(_h, workdir, env={"MODEL_API_KEY": "stub-p1", "MODEL_NAME": "google-cloud/glm-5.2"}, fail_write_nums=fail_nums, cancel_on_cmd_num=cancel_cmd), timeout=5.0))
  assert evaluate_p1_oracle(workdir, expected, frames, c_at)


@settings(max_examples=15, deadline=None)
@given(model_name=st.sampled_from(sorted(OFFICIAL_GOOGLE_CLOUD_MODELS)), payloads=st.lists(st.one_of(st.fixed_dictionaries({"prompt_tokens": st.integers(0, 50_000), "completion_tokens": st.integers(0, 10_000), "total_tokens": st.just(0), "prompt_tokens_details": st.fixed_dictionaries({"cached_tokens": st.integers(0, 60_000), "cache_write_tokens": st.integers(0, 20_000)})}), st.fixed_dictionaries({"input_tokens": st.integers(0, 50_000), "cache_creation_input_tokens": st.integers(0, 20_000), "cache_read_input_tokens": st.integers(0, 50_000), "output_tokens": st.integers(0, 10_000)})), min_size=1, max_size=20))
def test_pbt_p2_stage2_conservation_and_pricing_guardian(model_name: str, payloads: list[dict[str, Any]], tmp_path_factory: pytest.TempPathFactory) -> None:
  workdir = tmp_path_factory.mktemp("p2")

  async def _h(_req: dict[str, Any], n: int) -> tuple[int, str, bytes]:
    return (200, "text/event-stream", _sse_reply(text="x", finish_reason="stop" if n >= len(payloads) else "length", usage=payloads[n - 1], model=model_name))

  frames, _, _ = asyncio.run(asyncio.wait_for(_run_stub(_h, workdir, env={"MODEL_API_KEY": "stub-p2", "MODEL_NAME": model_name}), timeout=5.0))
  rollup = json.loads(frames[-2]["text"][len("[PLE_ROLLUP] ") :])
  assert evaluate_p2_oracle(model_name, payloads, [f for f in frames if f.get("type") == "usage"], rollup)


@settings(max_examples=15, deadline=None)
@given(chunks=st.lists(st.text(alphabet="abcXYZ012\n\r\t\x07\x1b\"\\{}[]:,", min_size=1, max_size=30), min_size=1, max_size=5), is_err=st.booleans())
def test_pbt_p4_single_line_secret_free_rollup_guardian(chunks: list[str], is_err: bool, tmp_path_factory: pytest.TempPathFactory) -> None:
  workdir = tmp_path_factory.mktemp("p4")
  fake_secret = "sk-" + "ple-pbt-secret-42424242"
  dirty = f"{fake_secret}\n".join(chunks) + f" Bearer {fake_secret}"

  async def _h(_req: dict[str, Any], _n: int) -> tuple[int, str, bytes]:
    if is_err:
      return (401, "application/json", json.dumps({"error": {"message": dirty}}).encode("utf-8"))
    return (200, "text/event-stream", _sse_reply(text=f"ok {dirty}", finish_reason="stop"))

  frames, _, _ = asyncio.run(asyncio.wait_for(_run_stub(_h, workdir, env={"MODEL_API_KEY": fake_secret, "MODEL_NAME": "google-cloud/glm-5.2"}, no_retry=True), timeout=5.0))
  p4_ok = evaluate_p4_oracle(frames, fake_secret)
  assert p4_ok, "PBT P4 rollup check failed"


def test_oracle_calibration_rejects_individual_bad_states(tmp_path: Path) -> None:
  fake_secret = "sk-" + "ple-calib-secret-88888888"
  (tmp_path / "a.txt").write_bytes(b"ok")
  good_rollup = {"status": "done", "model": "google-cloud/claude-opus-5-5", "uncached_input_tokens": 1000, "cache_write_tokens": 0, "cache_read_tokens": 0, "output_tokens": 500, "input_tokens": 1000, "cost_usd": 0.014}
  good_frames = [{"type": "write_file", "path": str(tmp_path / "._ple_stage_x_1")}, {"type": "usage", "input_tokens": 1000, "output_tokens": 500, "cache_read_tokens": 0}, {"type": "log", "text": "[PLE_ROLLUP] " + json.dumps(good_rollup, separators=(",", ":"))}, {"type": "done", "final_message": f"{tmp_path / 'a.txt'} (2 bytes)"}]
  payload = [{"input_tokens": 1000, "output_tokens": 500}]
  p1_good = evaluate_p1_oracle(tmp_path, {"a.txt": b"ok"}, good_frames, None)
  p2_good = evaluate_p2_oracle("google-cloud/claude-opus-5-5", payload, [good_frames[1]], good_rollup)
  p4_good = evaluate_p4_oracle(good_frames, fake_secret)
  assert p1_good and p2_good and p4_good, "calibration baseline must pass"
  (tmp_path / "._ple_stage_leak").write_bytes(b"x")
  assert evaluate_p1_oracle(tmp_path, {"a.txt": b"ok"}, good_frames, None) is False
  (tmp_path / "._ple_stage_leak").unlink()
  assert evaluate_p1_oracle(tmp_path, {"a.txt": b"ok"}, [good_frames[1], {"type": "exec", "command": "ls"}, good_frames[2], good_frames[3]], 1) is False
  assert evaluate_p2_oracle("google-cloud/claude-opus-5-5", payload, [good_frames[1]], {**good_rollup, "uncached_input_tokens": 999}) is False
  assert evaluate_p2_oracle("google-cloud/claude-opus-5-5", payload, [good_frames[1]], {**good_rollup, "cost_usd": 0.014000005}) is False
  p4_nl = evaluate_p4_oracle([*good_frames[:-2], {"type": "log", "text": "[PLE_ROLLUP] {\"a\":\n1}"}, good_frames[-1]], fake_secret)
  assert p4_nl is False, "newline in rollup must fail"
  p4_bad_json = evaluate_p4_oracle([*good_frames[:-2], {"type": "log", "text": "[PLE_ROLLUP] {not-json"}, good_frames[-1]], fake_secret)
  assert p4_bad_json is False, "malformed rollup JSON must fail"
  p4_leak_rollup = evaluate_p4_oracle([*good_frames[:-2], {"type": "log", "text": f"[PLE_ROLLUP] {json.dumps({**good_rollup, 'err': fake_secret})}"}, good_frames[-1]], fake_secret)
  assert p4_leak_rollup is False, "secret in rollup must fail"
  p4_leak_done = evaluate_p4_oracle([*good_frames[:-1], {"type": "done", "final_message": f"ans {fake_secret}"}], fake_secret)
  assert p4_leak_done is False, "secret in done frame must fail"
