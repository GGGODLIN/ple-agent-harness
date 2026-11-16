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

"""Ticket 03 Seam 1 tests: permissive deps, OOXML <v> audit (P3), bounded optimization, and VERIFIER."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
from typing import Any
import xml.etree.ElementTree as ET
import zipfile

from hypothesis import given, settings, strategies as st
import openpyxl
import pytest
import websockets
import xlsxwriter

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
  sys.path.insert(0, str(TESTS_DIR))

from test_seam1_core import CONTAINER_CMD_TYPES, _run_stub, _sse_reply, evaluate_p2_oracle  # noqa: E402
from test_seam1_gate import REPO_ROOT, _sse_text_reply, _sse_tool_call_reply  # noqa: E402

COPYLEFT_RE = re.compile(r"\b(?:pymupdf|fitz|formulas)\b", re.IGNORECASE)


def _has_copyleft_ref(text: str) -> bool:
  return COPYLEFT_RE.search(text) is not None


def _path_without_soffice(tmp_dir: Path) -> str:
  py_dir = Path(sys.executable).parent
  if (py_dir / "soffice").exists():
    shim_bin = tmp_dir / ".ple_no_soffice_bin"
    shim_bin.mkdir(parents=True, exist_ok=True)
    for name in ("python3", "python"):
      link = shim_bin / name
      if not link.exists():
        link.symlink_to(sys.executable)
    head = str(shim_bin)
  else:
    head = str(py_dir)
  rest = [
    e for e in os.environ.get("PATH", "").split(os.pathsep)
    if e and Path(e) != py_dir and not (Path(e) / "soffice").exists()
  ]
  return os.pathsep.join([head, *rest])


async def _run_audit_ws(
  stub_fn: Any,
  workdir: Path,
  *,
  instruction: str,
  env: dict[str, str],
  mcp_servers: list[dict[str, Any]] | None = None,
  exec_path: str | None = None,
  limits: dict[str, Any] | None = None,
  exec_override: Any = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
  frames, _, reqs = await _run_stub(
    stub_fn,
    workdir,
    env=env,
    instruction=instruction,
    mcp_servers=mcp_servers,
    exec_path=exec_path,
    limits=limits,
    exec_override=exec_override,
  )
  for blob in (json.dumps(frames), json.dumps(reqs)):
    for m in re.findall(r"/tmp/\.ple_work_[A-Za-z0-9_]+", blob):
      shutil.rmtree(m, ignore_errors=True)
  rline = str(frames[-2].get("text", ""))
  rollup = json.loads(rline[len("[PLE_ROLLUP] ") :]) if rline.startswith("[PLE_ROLLUP] ") else {}
  return frames, reqs, rollup


def evaluate_p3_oracle(
  xlsx_path: Path, expected_formulas: dict[tuple[str, str], str], expected_values: dict[tuple[str, str], Any],
  expected_error_tokens: set[str], audit_texts: list[str], audit_outcome: str,
) -> bool:
  if not xlsx_path.is_file() or not zipfile.is_zipfile(xlsx_path):
    return False
  with zipfile.ZipFile(xlsx_path, "r") as zf:
    if "xl/workbook.xml" not in zf.namelist():
      return False
    wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
  calc_els = [el for el in wb_root.iter() if el.tag.endswith("calcPr")]
  if not calc_els or calc_els[0].attrib.get("fullCalcOnLoad") not in ("1", "true"):
    return False
  wb_f = openpyxl.load_workbook(xlsx_path, data_only=False)
  wb_v = openpyxl.load_workbook(xlsx_path, data_only=True)
  try:
    for (sheet, coord), exp_f_sub in expected_formulas.items():
      got_f = wb_f[sheet][coord].value
      if not isinstance(got_f, str) or not got_f.startswith("=") or exp_f_sub.upper() not in got_f.upper():
        return False
    for (sheet, coord), exp_val in expected_values.items():
      got_v = wb_v[sheet][coord].value
      if got_v is None:
        return False
      if isinstance(exp_val, bool):
        if got_v is not exp_val:
          return False
      elif isinstance(exp_val, (int, float)):
        if not isinstance(got_v, (int, float)) or isinstance(got_v, bool):
          return False
        if abs(float(got_v) - float(exp_val)) > 1e-5 * max(1.0, abs(float(exp_val))):
          return False
      elif str(got_v) != str(exp_val):
        return False
  finally:
    wb_f.close()
    wb_v.close()
  joined = "\n".join(audit_texts)
  if expected_error_tokens:
    return audit_outcome == "flagged" and all(tok in joined for tok in expected_error_tokens)
  return audit_outcome == "pass"


def test_permissive_dependency_manifests_and_system_guidance(tmp_path: Path) -> None:
  assert _has_copyleft_ref("PyMuPDF==1.24.0\nformulas==1.2.8\nimport fitz") is True
  reqs_text = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
  reqs_set = {ln.strip() for ln in reqs_text.splitlines() if ln.strip() and not ln.strip().startswith("#")}
  assert reqs_set == {"openai==3.26.1", "websockets==15.0.1", "XlsxWriter==3.3.1", "openpyxl==3.1.5", "python-docx==1.2.0", "pdfplumber==0.11.10", "scipy==1.17.1", "pint==0.25.2"}
  repo_sources = "\n".join(p.read_text(encoding="utf-8") for p in sorted(REPO_ROOT.glob("*.py")) + [REPO_ROOT / "requirements.txt", REPO_ROOT / "submission.yaml"])
  has_banned = _has_copyleft_ref(repo_sources)
  assert not has_banned, "copyleft package referenced in manifests or harness code"

  async def _scenario() -> None:
    _, reqs, _ = await _run_audit_ws(lambda _r, _n: asyncio.sleep(0, result=(200, "text/event-stream", _sse_text_reply("ready"))), tmp_path, instruction="Say ready", env={"MODEL_API_KEY": "stub-k", "MODEL_NAME": "google-cloud/glm-5.2"})
    sys_prompt = reqs[0]["json"]["messages"][0]["content"]
    assert "XlsxWriter" in sys_prompt and "facts.json" in sys_prompt and "assert" in sys_prompt

  asyncio.run(asyncio.wait_for(_scenario(), timeout=8.0))


def test_ooxml_audit_without_soffice_and_facts_json_crosscheck(tmp_path: Path) -> None:
  xlsx_path = tmp_path / "model.xlsx"
  wb = xlsxwriter.Workbook(str(xlsx_path))
  ws_in, ws_calc = wb.add_worksheet("Inputs"), wb.add_worksheet("Calcs")
  for coord, val in (("A1", "Load_kN"), ("B1", 100.0), ("A2", "Factor"), ("B2", 1.5), ("A3", "Span_m"), ("B3", 4.0)):
    ws_in.write(coord, val)
  ws_calc.write_formula("B1", "=NORM.S.DIST(1.96,TRUE)", None, 0.9750021)
  ws_calc.write_formula("B2", "=ROUND(Inputs!B1*Inputs!B2+Inputs!B3^2,2)", None, 166.0)
  wb.close()
  no_soffice_path = _path_without_soffice(tmp_path)
  assert shutil.which("soffice", path=no_soffice_path) is None

  async def _scenario() -> None:
    py_bad = (
      f"import json, os, openpyxl; wb=openpyxl.load_workbook({str(xlsx_path)!r}); "
      "wb['Inputs']['B1']=120.0; wb['Calcs']['B3']='=IF(B2>180,\"PASS\",\"FAIL\")'; "
      f"wb['Calcs']['B4']='=Inputs!B1/0'; wb.save({str(xlsx_path)!r}); "
      "open(os.environ['PLE_WORK_DIR']+'/facts.json','w').write(json.dumps({'design_load': 196.0}))"
    )
    py_fix = f"import openpyxl; wb=openpyxl.load_workbook({str(xlsx_path)!r}); wb['Calcs']['B4']='=ROUND(B2/Inputs!B3,2)'; wb.save({str(xlsx_path)!r})"

    async def _h(_req: dict[str, Any], n: int) -> tuple[int, str, bytes]:
      if n == 1:
        return (200, "text/event-stream", _sse_reply(calls=[("c1", "bash", {"command": f"python3 -c {shlex.quote(py_bad)}"}), ("c2", "write_file", {"path": "summary.md", "content": "Report\ndesign_load: 150.0 kN\n"})], finish_reason="tool_calls"))
      if n == 2:
        return (200, "text/event-stream", _sse_text_reply("Initial candidate summary"))
      if n == 3:
        return (200, "text/event-stream", _sse_reply(calls=[("c3", "bash", {"command": f"python3 -c {shlex.quote(py_fix)}"}), ("c4", "write_file", {"path": "summary.md", "content": "Report\ndesign_load: 196.0 kN\n"})], finish_reason="tool_calls"))
      return (200, "text/event-stream", _sse_text_reply("Final verified summary"))

    frames, reqs, rollup = await _run_audit_ws(_h, tmp_path, instruction="Update model.xlsx and summary.md with consistent design_load.", env={"MODEL_API_KEY": "stub-k", "MODEL_NAME": "google-cloud/glm-5.2", "PLE_ENABLE_VERIFIER": "0"}, exec_path=no_soffice_path)
    assert len(reqs) == 4
    repair_prompt = reqs[2]["json"]["messages"][-1]["content"]
    assert "#DIV/0!" in repair_prompt and "design_load" in repair_prompt
    audit_logs = [str(f.get("text", "")) for f in frames if f.get("type") == "log"]
    assert evaluate_p3_oracle(xlsx_path, {("Calcs", "B1"): "NORM.S.DIST", ("Calcs", "B2"): "ROUND", ("Calcs", "B3"): "IF", ("Calcs", "B4"): "ROUND"}, {("Calcs", "B1"): 0.9750021, ("Calcs", "B2"): 196.0, ("Calcs", "B3"): "PASS", ("Calcs", "B4"): 49.0}, set(), audit_logs, str(rollup.get("audit_outcome", "")))

  asyncio.run(asyncio.wait_for(_scenario(), timeout=8.0))


def test_conditional_optimization_cap_vs_zero_overhead_tasks(tmp_path: Path) -> None:
  async def _scenario() -> None:
    check_cmd = "python3 -c 'f=lambda d: d>=0.15; assert f(0.20); assert not f(0.10); print(12400)'"

    async def _opt_h(_req: dict[str, Any], n: int) -> tuple[int, str, bytes]:
      if n == 1:
        return (200, "text/event-stream", _sse_tool_call_reply("w1", "write_file", {"path": "design.json", "content": "{\"d\": 0.25, \"cost\": 15000}"}))
      if n in (2, 4, 6, 8):
        return (200, "text/event-stream", _sse_text_reply(f"Candidate design pass {n}"))
      return (200, "text/event-stream", _sse_tool_call_reply(f"b{n}", "bash", {"command": check_cmd}))

    _, opt_reqs, opt_rollup = await _run_audit_ws(_opt_h, tmp_path / "opt_cap", instruction="Size the steel pipe diameter and wall thickness to minimize total life-cycle cost subject to pressure <= 12 MPa.", env={"MODEL_API_KEY": "stub-k", "MODEL_NAME": "google-cloud/claude-opus-5-5", "PLE_ENABLE_VERIFIER": "0"})
    assert opt_rollup.get("opt_rounds") == 3 and opt_rollup.get("verifier_runs") == 0
    sys0, tools0 = opt_reqs[0]["json"]["messages"][0], opt_reqs[0]["json"]["tools"]
    assert all(r["json"]["messages"][0] == sys0 and r["json"]["tools"] == tools0 for r in opt_reqs[1:])

    async def _conv_h(_req: dict[str, Any], n: int) -> tuple[int, str, bytes]:
      if n == 1:
        return (200, "text/event-stream", _sse_tool_call_reply("cw1", "write_file", {"path": "design.json", "content": "{\"d\": 0.20, \"cost\": 12400}"}))
      if n == 2:
        return (200, "text/event-stream", _sse_text_reply("Initial feasible design"))
      if n == 3:
        return (200, "text/event-stream", _sse_tool_call_reply("cb1", "bash", {"command": check_cmd}))
      return (200, "text/event-stream", _sse_text_reply("OPTIMIZATION_CONVERGED: certified minimum cost 12400"))

    _, _, conv_rollup = await _run_audit_ws(_conv_h, tmp_path / "opt_conv", instruction="Select heat exchanger tube layout parameters to minimize total capital cost under pressure drop <= 35 kPa.", env={"MODEL_API_KEY": "stub-k", "MODEL_NAME": "google-cloud/glm-5.2", "PLE_ENABLE_VERIFIER": "0"})
    assert conv_rollup.get("opt_rounds") == 1 and conv_rollup.get("verifier_runs") == 0

    async def _memo_h(_req: dict[str, Any], n: int) -> tuple[int, str, bytes]:
      if n == 1:
        return (200, "text/event-stream", _sse_tool_call_reply("mw1", "write_file", {"path": "memo.md", "content": "# Qualitative Disposition Memo\nApproved.\n"}))
      return (200, "text/event-stream", _sse_text_reply("Memo delivered"))

    _, memo_reqs, memo_rollup = await _run_audit_ws(_memo_h, tmp_path / "memo", instruction="Write a qualitative engineering memo reviewing safety governance procedures in memo.md.", env={"MODEL_API_KEY": "stub-k", "MODEL_NAME": "google-cloud/glm-5.2", "PLE_ENABLE_VERIFIER": "0"})
    assert len(memo_reqs) == 2 and memo_rollup.get("opt_rounds") == 0 and memo_rollup.get("verifier_runs") == 0

    smoke_frames, smoke_reqs, smoke_rollup = await _run_audit_ws(lambda _r, _n: asyncio.sleep(0, result=(200, "text/event-stream", _sse_text_reply("SMOKE_OK"))), tmp_path / "smoke", instruction="Smoke check: reply SMOKE_OK.", env={"MODEL_API_KEY": "stub-k", "MODEL_NAME": "google-cloud/glm-5.2"})
    assert len(smoke_reqs) == 1 and not any(f.get("type") in CONTAINER_CMD_TYPES for f in smoke_frames)
    assert smoke_rollup.get("opt_rounds") == 0 and smoke_rollup.get("verifier_runs") == 0 and smoke_rollup.get("audit_outcome") == "not_run"

    async def _mcp_h(_req: dict[str, Any], n: int) -> tuple[int, str, bytes]:
      if n == 1:
        return (200, "text/event-stream", _sse_tool_call_reply("m1", "lab__status", {}))
      return (200, "text/event-stream", _sse_text_reply("Lab status confirmed"))

    mcp_frames, mcp_reqs, mcp_rollup = await _run_audit_ws(_mcp_h, tmp_path / "mcp", instruction="Query lab__status via MCP and report.", env={"MODEL_API_KEY": "stub-k", "MODEL_NAME": "google-cloud/glm-5.2"}, mcp_servers=[{"name": "lab", "url": "http://127.0.0.1:19999/mcp"}])
    assert len(mcp_reqs) == 2 and not any(f.get("type") == "exec" for f in mcp_frames)
    assert mcp_rollup.get("opt_rounds") == 0 and mcp_rollup.get("verifier_runs") == 0 and mcp_rollup.get("audit_outcome") == "not_run"

  asyncio.run(asyncio.wait_for(_scenario(), timeout=8.0))


def test_verifier_toggle_clean_context_readonly_and_unified_rollup(tmp_path: Path) -> None:
  async def _scenario() -> None:
    usages = [
      {"input_tokens": 400, "cache_creation_input_tokens": 1000, "cache_read_input_tokens": 0, "output_tokens": 80},
      {"input_tokens": 200, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 1200, "output_tokens": 60},
      {"input_tokens": 300, "cache_creation_input_tokens": 500, "cache_read_input_tokens": 0, "output_tokens": 40},
      {"input_tokens": 150, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 700, "output_tokens": 50},
      {"input_tokens": 250, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 1300, "output_tokens": 70},
      {"input_tokens": 180, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 1500, "output_tokens": 45},
    ]

    async def _vh(_req: dict[str, Any], n: int) -> tuple[int, str, bytes]:
      u, model = usages[n - 1], "google-cloud/claude-opus-5-5"
      if n == 1:
        return (200, "text/event-stream", _sse_reply(calls=[("w1", "write_file", {"path": "calc.txt", "content": "torque = 55"})], finish_reason="tool_calls", usage=u, model=model))
      if n == 2:
        return (200, "text/event-stream", _sse_reply(text="Draft torque written", finish_reason="stop", usage=u, model=model))
      if n == 3:
        return (200, "text/event-stream", _sse_reply(calls=[("vr1", "read_file", {"path": "calc.txt"})], finish_reason="tool_calls", usage=u, model=model))
      if n == 4:
        return (200, "text/event-stream", _sse_reply(text="VERIFIER_FAIL: 1. Missing N*m unit in calc.txt", finish_reason="stop", usage=u, model=model))
      if n == 5:
        return (200, "text/event-stream", _sse_reply(calls=[("w2", "write_file", {"path": "calc.txt", "content": "torque = 55 N*m\n"})], finish_reason="tool_calls", usage=u, model=model))
      return (200, "text/event-stream", _sse_reply(text="Final torque 55 N*m delivered", finish_reason="stop", usage=u, model=model))

    frames, reqs, rollup = await _run_audit_ws(
      _vh, tmp_path, instruction="Compute shaft torque with SI units in calc.txt.",
      env={"MODEL_API_KEY": "stub-k", "MODEL_NAME": "google-cloud/claude-opus-5-5", "PLE_ENABLE_VERIFIER": "1"},
    )
    assert len(reqs) == 6 and rollup.get("verifier_runs") == 1
    assert [t["function"]["name"] for t in reqs[2]["json"]["tools"]] == ["bash", "read_file"]
    assert len(reqs[2]["json"]["messages"]) == 2
    assert (tmp_path / "calc.txt").read_text(encoding="utf-8") == "torque = 55 N*m\n"
    usage_frames = [f for f in frames if f.get("type") == "usage"]
    assert len(usage_frames) == 6 and evaluate_p2_oracle("google-cloud/claude-opus-5-5", usages, usage_frames, rollup)

  asyncio.run(asyncio.wait_for(_scenario(), timeout=8.0))


def test_untouched_xlsx_baseline_volatile_today_and_blank_cmp(tmp_path: Path) -> None:
  work = tmp_path / "work"
  work.mkdir()
  no_soffice_path = _path_without_soffice(tmp_path)

  untouched_path = work / "untouched_ref.xlsx"
  wb_u = xlsxwriter.Workbook(str(untouched_path))
  ws_u = wb_u.add_worksheet("Ref")
  ws_u.write_formula("A1", "=TODAY()", None, 46300)
  wb_u.close()
  untouched_before = untouched_path.read_bytes()

  corrupt_fixture = work / "corrupt_fixture.xlsx"
  corrupt_fixture.write_bytes(b"PK\x03\x04corrupt-zip-bytes")

  edit_path = work / "editable.xlsx"
  wb_e = xlsxwriter.Workbook(str(edit_path))
  ws_in, ws_c = wb_e.add_worksheet("Inputs"), wb_e.add_worksheet("Calcs")
  ws_in.write_number("B1", 100.0)
  ws_in.write_number("B3", 5.0)
  ws_c.write_formula("C1", "=TODAY()", None, 46342)
  ws_c.write_formula("C2", '=IF(Inputs!B2="","",Inputs!B1/Inputs!B2)', None, "")
  ws_c.write_formula("C3", '=IF(Inputs!B3="","",Inputs!B1/Inputs!B3)', None, 20.0)
  ws_c.write_formula("C4", '=IF(999<"a",IF("z"<TRUE,1,0),0)', None, 1)
  wb_e.close()

  async def _scenario() -> None:
    async def _qual_h(_req: dict[str, Any], _n: int) -> tuple[int, str, bytes]:
      return (200, "text/event-stream", _sse_text_reply("Qualitative corrosion memorandum complete."))

    _, _, qual_rollup = await _run_audit_ws(
      _qual_h,
      work,
      instruction="Write a qualitative engineering memorandum assessing pipe corrosion.",
      env={"MODEL_API_KEY": "stub-k", "MODEL_NAME": "google-cloud/glm-5.2", "PLE_ENABLE_VERIFIER": "0"},
      exec_path=no_soffice_path,
    )
    assert qual_rollup["audit_outcome"] == "not_run" and qual_rollup["opt_rounds"] == 0
    assert untouched_path.read_bytes() == untouched_before

    py_mod = f"import openpyxl; wb=openpyxl.load_workbook({str(edit_path)!r}); wb['Inputs']['B1']=250.0; wb.save({str(edit_path)!r})"

    async def _edit_h(_req: dict[str, Any], n: int) -> tuple[int, str, bytes]:
      if n == 1:
        return (200, "text/event-stream", _sse_tool_call_reply("b1", "bash", {"command": f"python3 -c {shlex.quote(py_mod)}"}))
      return (200, "text/event-stream", _sse_text_reply("Updated editable.xlsx input load."))

    _, _, edit_rollup = await _run_audit_ws(
      _edit_h,
      work,
      instruction="Update editable.xlsx input load.",
      env={"MODEL_API_KEY": "stub-k", "MODEL_NAME": "google-cloud/glm-5.2", "PLE_ENABLE_VERIFIER": "0"},
      exec_path=no_soffice_path,
    )
    assert edit_rollup["audit_outcome"] == "pass"
    assert untouched_path.read_bytes() == untouched_before

    wb_v = openpyxl.load_workbook(edit_path, data_only=True)
    try:
      assert wb_v["Calcs"]["C1"].value == 46342
      assert wb_v["Calcs"]["C2"].value in ("", None)
      assert abs(float(wb_v["Calcs"]["C3"].value) - 50.0) < 1e-6
      assert wb_v["Calcs"]["C4"].value == 1
    finally:
      wb_v.close()

  asyncio.run(asyncio.wait_for(_scenario(), timeout=8.0))


def test_multi_root_sibling_deliverables_and_small_facts_tolerance(tmp_path: Path) -> None:
  work = tmp_path / "work"
  fs_root = tmp_path / "filesystem_sim"
  work.mkdir()
  fs_root.mkdir()
  no_soffice_path = _path_without_soffice(tmp_path)

  ref_xlsx = work / "baseline_ref.xlsx"
  wb_r = xlsxwriter.Workbook(str(ref_xlsx))
  ws_r = wb_r.add_worksheet("Sheet1")
  ws_r.write_formula("A1", "=NOW()", None, 46342.5)
  wb_r.close()
  ref_bytes = ref_xlsx.read_bytes()

  out_xlsx = work / "deliverable.xlsx"
  sibling_md = fs_root / "sibling_report.md"

  async def _scenario() -> None:
    py_bad = (
      f"import json, os, openpyxl; wb=openpyxl.load_workbook({str(ref_xlsx)!r}); "
      "wb['Sheet1']['A1']='=15+15'; wb['Sheet1']['A2']='strain_ratio = 0.0040'; "
      f"wb.save({str(out_xlsx)!r}); "
      "open(os.environ['PLE_WORK_DIR']+'/facts.json','w').write(json.dumps({'sum_val': 30.0, 'strain_ratio': 0.019}))"
    )
    py_fix = "import json, os; open(os.environ['PLE_WORK_DIR']+'/facts.json','w').write(json.dumps({'sum_val': 30.0, 'strain_ratio': 0.004}))"

    async def _h(_req: dict[str, Any], n: int) -> tuple[int, str, bytes]:
      if n == 1:
        return (200, "text/event-stream", _sse_reply(calls=[
          ("b1", "bash", {"command": f"python3 -c {shlex.quote(py_bad)}"}),
          ("w1", "write_file", {"path": str(sibling_md), "content": "sum_val = 30.0\nstrain_ratio = 0.0040\n"}),
        ], finish_reason="tool_calls"))
      if n == 2:
        return (200, "text/event-stream", _sse_text_reply("Initial multi-root summary"))
      if n == 3:
        return (200, "text/event-stream", _sse_tool_call_reply("b2", "bash", {"command": f"python3 -c {shlex.quote(py_fix)}"}))
      return (200, "text/event-stream", _sse_text_reply("Aligned facts.json summary"))

    _, reqs, rollup = await _run_audit_ws(
      _h,
      work,
      instruction="Generate deliverable.xlsx and external sibling_report.md aligned with facts.json.",
      env={"MODEL_API_KEY": "stub-k", "MODEL_NAME": "google-cloud/glm-5.2", "PLE_ENABLE_VERIFIER": "0"},
      exec_path=no_soffice_path,
    )
    assert len(reqs) == 4
    repair_msg = reqs[2]["json"]["messages"][-1]["content"]
    assert "strain_ratio" in repair_msg and "sibling_report.md" in repair_msg
    assert ref_xlsx.read_bytes() == ref_bytes
    assert rollup["audit_outcome"] == "pass"
    wb_check = openpyxl.load_workbook(out_xlsx, data_only=True)
    try:
      assert wb_check["Sheet1"]["A1"].value == 30
    finally:
      wb_check.close()

  asyncio.run(asyncio.wait_for(_scenario(), timeout=8.0))


def test_audit_error_resilience_finish_reaudit_and_opt_latch_across_verifier(tmp_path: Path) -> None:
  async def _scenario() -> None:
    # 1. Corrupt audit JSON output over WebSocket exec_result does not crash session
    def _corrupt_audit_exec(cmd: str, _idx: int) -> dict[str, Any] | None:
      if "deliverable_audit.py" in cmd and " audit " in cmd:
        return {"ok": True, "exit_code": 0, "output": "__PLE_AUDIT_JSON__:{not-valid-json", "timed_out": False}
      return None

    async def _err_h(_req: dict[str, Any], n: int) -> tuple[int, str, bytes]:
      if n == 1:
        return (200, "text/event-stream", _sse_tool_call_reply("w1", "write_file", {"path": "out.txt", "content": "ok\n"}))
      return (200, "text/event-stream", _sse_text_reply("Summary despite audit error."))

    err_frames, _, err_rollup = await _run_audit_ws(
      _err_h,
      tmp_path / "err_audit",
      instruction="Write out.txt.",
      env={"MODEL_API_KEY": "stub-k", "MODEL_NAME": "google-cloud/glm-5.2", "PLE_ENABLE_VERIFIER": "0"},
      exec_override=_corrupt_audit_exec,
    )
    err_logs = [str(f.get("text", "")) for f in err_frames if f.get("type") == "log"]
    assert err_rollup["audit_outcome"] == "error" and any("[PLE_AUDIT] error" in lg for lg in err_logs)

    # 2. Failing bash assert does not satisfy self-check, write_file assert does, and _opt_converged latches across VERIFIER
    async def _latch_h(_req: dict[str, Any], n: int) -> tuple[int, str, bytes]:
      if n == 1:
        return (200, "text/event-stream", _sse_reply(calls=[
          ("b1", "bash", {"command": "python3 -c 'assert False'"}),
          ("w1", "write_file", {"path": "opt_check.py", "content": "x = 2\nassert x > 0\n"}),
        ], finish_reason="tool_calls"))
      if n == 2:
        return (200, "text/event-stream", _sse_text_reply("OPTIMIZATION_CONVERGED: optimal diameter 0.20 m"))
      if n == 3:
        return (200, "text/event-stream", _sse_text_reply("VERIFIER_FAIL: 1. Add SI units"))
      return (200, "text/event-stream", _sse_text_reply("Added SI units to summary (0.20 m)."))

    _, latch_reqs, latch_rollup = await _run_audit_ws(
      _latch_h,
      tmp_path / "opt_latch",
      instruction="Size steel pipe diameter to minimize total capital cost.",
      env={"MODEL_API_KEY": "stub-k", "MODEL_NAME": "google-cloud/glm-5.2", "PLE_ENABLE_VERIFIER": "1"},
    )
    assert len(latch_reqs) == 4
    assert latch_rollup["verifier_runs"] == 1 and latch_rollup["opt_rounds"] == 0

    # 3. Timed-out bash marks workdir dirty and finish() runs re-audit when 60 < time_left <= 180
    def _timeout_bash_exec(cmd: str, _idx: int) -> dict[str, Any] | None:
      if "sleep_timeout_sim" in cmd:
        return {"ok": True, "exit_code": 124, "output": "partial", "timed_out": True}
      return None

    async def _fin_h(_req: dict[str, Any], n: int) -> tuple[int, str, bytes]:
      if n == 1:
        return (200, "text/event-stream", _sse_tool_call_reply("b1", "bash", {"command": "sleep_timeout_sim"}))
      return (200, "text/event-stream", _sse_text_reply("Wrap-up summary after timeout."))

    fin_frames, _, _ = await _run_audit_ws(
      _fin_h,
      tmp_path / "finish_audit",
      instruction="Run analysis before deadline.",
      env={"MODEL_API_KEY": "stub-k", "MODEL_NAME": "google-cloud/glm-5.2", "PLE_ENABLE_VERIFIER": "0"},
      limits={"agent_timeout_sec": 120},
      exec_override=_timeout_bash_exec,
    )
    fin_logs = [str(f.get("text", "")) for f in fin_frames if f.get("type") == "log"]
    assert "Wrap-up summary after timeout." in str(fin_frames[-1].get("final_message", ""))
    assert any("[PLE_AUDIT]" in lg for lg in fin_logs)

  asyncio.run(asyncio.wait_for(_scenario(), timeout=8.0))


@settings(max_examples=12, deadline=None)
@given(
  seeded_v=st.floats(min_value=0.05, max_value=0.99, allow_nan=False, allow_infinity=False),
  a1_init=st.integers(min_value=2, max_value=40),
  a1_new=st.integers(min_value=3, max_value=60),
  a2=st.floats(min_value=1.25, max_value=8.5, allow_nan=False, allow_infinity=False),
  a3=st.integers(min_value=1, max_value=25),
  label=st.text(alphabet="ABCDEFGH012345_", min_size=2, max_size=12),
  err_case=st.sampled_from([None, ("=1/0", "#DIV/0!"), ("=MissingSheet!A1", "#REF!"), ("=\"bad\"+5", "#VALUE!"), ("=UNKNOWN_PLE_FN(1)", "#NAME?")]),
)
def test_pbt_p3_ooxml_cached_values_and_error_flagging_guardian(
  seeded_v: float, a1_init: int, a1_new: int, a2: float, a3: int, label: str, err_case: tuple[str, str] | None, tmp_path_factory: pytest.TempPathFactory,
) -> None:
  workdir = tmp_path_factory.mktemp("p3")
  xlsx_path = workdir / "book.xlsx"
  seeded_round, a2_round = round(seeded_v, 6), round(a2, 3)
  wb = xlsxwriter.Workbook(str(xlsx_path))
  ws_in, ws_sum = wb.add_worksheet("Inputs"), wb.add_worksheet("Summary")
  for coord, val in (("A1", a1_init), ("A2", a2_round), ("A3", a3), ("C1", label)):
    ws_in.write(coord, val)
  ws_sum.write_formula("B1", "=BETA.DIST(0.4,2,5,TRUE)", None, seeded_round)
  ws_sum.write_formula("B2", "=ROUND(Inputs!A1*Inputs!A2+Inputs!A3,4)", None, round(a1_init * a2_round + a3, 4))
  wb.close()

  extra_err = f"wb['Summary']['B4']={err_case[0]!r}; " if err_case else ""
  edit_py = f"import openpyxl; wb=openpyxl.load_workbook({str(xlsx_path)!r}); wb['Inputs']['A1']={a1_new}; wb['Summary']['B3']='=SUM(Inputs!A1:A3)'; {extra_err}wb.save({str(xlsx_path)!r})"

  async def _h(_req: dict[str, Any], n: int) -> tuple[int, str, bytes]:
    if n == 1:
      return (200, "text/event-stream", _sse_tool_call_reply("e1", "bash", {"command": f"python3 -c {shlex.quote(edit_py)}"}))
    return (200, "text/event-stream", _sse_text_reply("Workbook updated"))

  frames, _, rollup = asyncio.run(asyncio.wait_for(_run_audit_ws(
    _h, workdir, instruction="Update book.xlsx cells.",
    env={"MODEL_API_KEY": "stub-p3", "MODEL_NAME": "google-cloud/glm-5.2", "PLE_ENABLE_VERIFIER": "0"},
    exec_path=_path_without_soffice(workdir),
  ), timeout=8.0))
  exp_f = {("Summary", "B1"): "BETA.DIST", ("Summary", "B2"): "ROUND", ("Summary", "B3"): "SUM"}
  exp_v: dict[tuple[str, str], Any] = {("Inputs", "C1"): label, ("Summary", "B1"): seeded_round, ("Summary", "B2"): round(a1_new * a2_round + a3, 4), ("Summary", "B3"): round(a1_new + a2_round + a3, 6)}
  exp_errs: set[str] = set()
  if err_case is not None:
    exp_f[("Summary", "B4")] = err_case[0].lstrip("=")[:4]
    exp_v[("Summary", "B4")] = err_case[1]
    exp_errs.add(err_case[1])
  assert evaluate_p3_oracle(xlsx_path, exp_f, exp_v, exp_errs, [str(f.get("text", "")) for f in frames if f.get("type") == "log"], str(rollup.get("audit_outcome", "")))


def test_p3_oracle_calibration_rejects_individual_mutations(tmp_path: Path) -> None:
  good_xlsx = tmp_path / "good.xlsx"
  wb = xlsxwriter.Workbook(str(good_xlsx))
  ws = wb.add_worksheet("Summary")
  ws.write_number("A1", 10)
  ws.write_formula("B1", "=NORM.S.DIST(1.96,TRUE)", None, 0.975)
  ws.write_formula("B2", "=A1*3", None, 30)
  wb.close()
  exp_f, exp_v = {("Summary", "B1"): "NORM.S.DIST", ("Summary", "B2"): "A1*3"}, {("Summary", "B1"): 0.975, ("Summary", "B2"): 30}
  assert evaluate_p3_oracle(good_xlsx, exp_f, exp_v, set(), ["audit pass"], "pass") is True

  stripped_xlsx = tmp_path / "stripped.xlsx"
  wb_strip = openpyxl.load_workbook(good_xlsx)
  wb_strip["Summary"]["A1"] = 10
  wb_strip.save(stripped_xlsx)
  assert evaluate_p3_oracle(stripped_xlsx, exp_f, exp_v, set(), ["audit pass"], "pass") is False

  wrong_v_xlsx = tmp_path / "wrong_v.xlsx"
  wb2 = xlsxwriter.Workbook(str(wrong_v_xlsx))
  ws2 = wb2.add_worksheet("Summary")
  ws2.write_number("A1", 10)
  ws2.write_formula("B1", "=NORM.S.DIST(1.96,TRUE)", None, 0.975)
  ws2.write_formula("B2", "=A1*3", None, 999)
  wb2.close()
  assert evaluate_p3_oracle(wrong_v_xlsx, exp_f, exp_v, set(), ["audit pass"], "pass") is False

  unflagged_err = tmp_path / "err.xlsx"
  wb3 = xlsxwriter.Workbook(str(unflagged_err))
  ws3 = wb3.add_worksheet("Summary")
  ws3.write_formula("B1", "=1/0", None, "#DIV/0!")
  wb3.close()
  assert evaluate_p3_oracle(unflagged_err, {("Summary", "B1"): "1/0"}, {("Summary", "B1"): "#DIV/0!"}, {"#DIV/0!"}, ["silent"], "pass") is False

  no_calc_xlsx = tmp_path / "no_calc.xlsx"
  with zipfile.ZipFile(good_xlsx, "r") as zin, zipfile.ZipFile(no_calc_xlsx, "w") as zout:
    for item in zin.infolist():
      raw = zin.read(item.filename)
      zout.writestr(item, raw.replace(b'fullCalcOnLoad="1"', b'fullCalcOnLoad="0"') if item.filename == "xl/workbook.xml" else raw)
  assert evaluate_p3_oracle(no_calc_xlsx, exp_f, exp_v, set(), ["audit pass"], "pass") is False
