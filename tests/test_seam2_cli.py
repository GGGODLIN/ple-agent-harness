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

"""Seam 2 subprocess acceptance and Hypothesis P4 property tests for scripts/ple_dev.py."""

from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from typing import Any

from hypothesis import given, settings, strategies as st
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
PLE_DEV = REPO_ROOT / "scripts" / "ple_dev.py"
FORBIDDEN_KEYS = frozenset({"sha" + "256", "md" + "5", "check" + "sum", "dig" + "est"})
EXPECTED_EXPORT_FILES = frozenset({"figure1_pareto.csv", "figure1_pareto.md", "figure2_ablation.csv", "figure2_ablation.md", "figure3_failures.csv", "figure3_failures.md"})
SAFE_ENV_KEYS = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "PYTHONPATH", "VIRTUAL_ENV", "USER", "SYSTEMROOT")


def _has_secret(text: str, secret: str) -> bool:
  return bool(secret) and (secret in text)


def _has_forbidden_key(obj: Any) -> bool:
  if isinstance(obj, dict):
    return any(str(k).strip().lower() in FORBIDDEN_KEYS or _has_forbidden_key(v) for k, v in obj.items())
  if isinstance(obj, list):
    return any(_has_forbidden_key(item) for item in obj)
  return False


def _run_cli(args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
  merged_env = {k: os.environ[k] for k in SAFE_ENV_KEYS if k in os.environ}
  if env:
    merged_env.update(env)
  return subprocess.run([sys.executable, str(PLE_DEV), *args], text=True, capture_output=True, timeout=10, check=False, env=merged_env)


def _snapshot_exports(out_dir: Path) -> dict[str, bytes]:
  return {p.name: p.read_bytes() for p in sorted(out_dir.iterdir()) if p.is_file()} if out_dir.is_dir() else {}


def _write_rollup(log_path: Path, payload: dict[str, Any]) -> None:
  log_path.parent.mkdir(parents=True, exist_ok=True)
  log_path.write_text("[PLE_ROLLUP] " + json.dumps(payload) + "\n", encoding="utf-8")


def evaluate_seam2_p4_oracle(
    *,
    export_snap_1: dict[str, bytes],
    export_snap_2: dict[str, bytes],
    cli_outputs: list[str],
    json_payloads: list[Any],
    ledger_data: dict[str, Any] | None,
    expected_lock_count: int | None,
    fake_secrets: tuple[str, ...],
) -> bool:
  """Independent Seam-2 P4 safety oracle: idempotency, secret redaction, clean schema, lock bounds."""
  if set(export_snap_1.keys()) != EXPECTED_EXPORT_FILES or export_snap_1 != export_snap_2:
    return False
  for name, raw in export_snap_1.items():
    text = raw.decode("utf-8", errors="strict")
    if any(_has_secret(text, sec) for sec in fake_secrets):
      return False
    if name.endswith(".csv"):
      reader = csv.DictReader(io.StringIO(text))
      if not reader.fieldnames or any(col.strip().lower() in FORBIDDEN_KEYS for col in reader.fieldnames):
        return False
      if not list(reader):
        return False
  if any(_has_secret(out, sec) for out in cli_outputs for sec in fake_secrets):
    return False
  for payload in json_payloads:
    if _has_forbidden_key(payload) or any(_has_secret(json.dumps(payload), sec) for sec in fake_secrets):
      return False
  if ledger_data is not None:
    if _has_forbidden_key(ledger_data) or any(_has_secret(json.dumps(ledger_data), sec) for sec in fake_secrets):
      return False
    locks = ledger_data.get("locks")
    if not isinstance(locks, list) or len(locks) > 5:
      return False
    if expected_lock_count is not None and len(locks) != expected_lock_count:
      return False
    if any(not isinstance(item, dict) or float(item.get("mean_score", 0.0)) < 0.138 for item in locks):
      return False
  return True


def _init_temp_git_repo(repo_dir: Path) -> str:
  repo_dir.mkdir(parents=True, exist_ok=True)
  subprocess.run(["git", "-C", str(repo_dir), "init", "-q"], check=True)
  subprocess.run(["git", "-C", str(repo_dir), "config", "user.email", "test@example.com"], check=True)
  subprocess.run(["git", "-C", str(repo_dir), "config", "user.name", "PLE Test"], check=True)
  (repo_dir / "LICENSE").write_text("Apache License 2.0\n", encoding="utf-8")
  (repo_dir / ".gitignore").write_text(".scratch/\n__pycache__/\n", encoding="utf-8")
  (repo_dir / "submission.yaml").write_text(
      "name: ple-clausegate-mirrorir\nmodel_api: google-cloud/glm-5.2\nserve: python3 {src}/serve.py\nenv:\n  COMPACT_AT_TOKENS: \"150000\"\n",
      encoding="utf-8",
  )
  (repo_dir / "serve.py").write_text("print('stub')\n", encoding="utf-8")
  subprocess.run(["git", "-C", str(repo_dir), "add", "."], check=True)
  subprocess.run(["git", "-C", str(repo_dir), "commit", "-q", "-m", "chore: initial fixture"], check=True)
  return subprocess.run(["git", "-C", str(repo_dir), "rev-parse", "HEAD"], text=True, capture_output=True, check=True).stdout.strip()


# --- Role 1: Concrete Capability Examples ---


def test_run_detached_worktree_isolates_main_repo_on_success_and_failure(tmp_path: Path) -> None:
  repo_dir = tmp_path / "main_repo"
  head_sha = _init_temp_git_repo(repo_dir)
  ple_root = tmp_path / "ple_upstream"
  ple_root.mkdir()

  stub_eval = tmp_path / "stub_eval.py"
  stub_eval.write_text(
      "import json, pathlib, sys, yaml\n"
      "wt = pathlib.Path(sys.argv[1]).resolve()\n"
      "assert '--no-export' in sys.argv\n"
      "out = pathlib.Path(sys.argv[sys.argv.index('--out') + 1])\n"
      "sub = yaml.safe_load((wt / 'submission.yaml').read_text(encoding='utf-8'))\n"
      "(wt / 'dirty_untracked.txt').write_text('dirty', encoding='utf-8')\n"
      "(wt / 'artifacts').mkdir(exist_ok=True)\n"
      "(wt / 'artifacts' / 'leak.json').write_text('{}', encoding='utf-8')\n"
      "out.mkdir(parents=True, exist_ok=True)\n"
      "(out / 'observed.json').write_text(json.dumps({'wt': str(wt), 'cwd': str(pathlib.Path.cwd()), 'sub': sub}), encoding='utf-8')\n"
      "sys.exit(7 if ('--tasks' in sys.argv and sys.argv[sys.argv.index('--tasks') + 1] == 'fail-task') else 0)\n",
      encoding="utf-8",
  )
  eval_cmd = f"{sys.executable} {stub_eval}"

  assert _run_cli(["run", "--repo", str(repo_dir), "--out", str(repo_dir / "inside"), "--eval-cmd", eval_cmd]).returncode != 0
  assert _run_cli(["run", "--repo", str(repo_dir), "--out", str(tmp_path / "s1"), "--eval-cmd", eval_cmd, "--tier", "STAGE1_FINAL_EXPORT"]).returncode != 0

  out_ok = tmp_path / "ext_out_ok"
  res_ok = _run_cli([
      "run", "--repo", str(repo_dir), "--ple-root", str(ple_root), "--out", str(out_ok),
      "--model-api", "google-cloud/claude-opus-5-5",
      "--eval-cmd", eval_cmd, "--tier", "LIVE_DOCKER_EVAL",
  ])
  assert res_ok.returncode == 0, res_ok.stderr
  obs = json.loads((out_ok / "observed.json").read_text(encoding="utf-8"))
  assert Path(obs["wt"]) != repo_dir.resolve() and not Path(obs["wt"]).exists()
  assert Path(obs["cwd"]).resolve() == ple_root.resolve()
  assert obs["sub"]["model_api"] == "google-cloud/claude-opus-5-5"
  meta_ok = json.loads((out_ok / "ple_run_meta.json").read_text(encoding="utf-8"))
  assert meta_ok == {"tier": "LIVE_DOCKER_EVAL", "git_rev": head_sha, "model_api": "google-cloud/claude-opus-5-5", "exit_code": 0}
  assert _has_forbidden_key(meta_ok) is False

  res_fail = _run_cli(["run", "--repo", str(repo_dir), "--out", str(tmp_path / "ext_fail"), "--tasks", "fail-task", "--eval-cmd", eval_cmd])
  assert res_fail.returncode == 7
  assert subprocess.run(["git", "-C", str(repo_dir), "status", "--porcelain"], text=True, capture_output=True, check=True).stdout.strip() == ""
  assert not (repo_dir / "artifacts").exists()
  main_sub = yaml.safe_load((repo_dir / "submission.yaml").read_text(encoding="utf-8"))
  assert main_sub["model_api"] == "google-cloud/glm-5.2"
  wt_list = subprocess.run(["git", "-C", str(repo_dir), "worktree", "list", "--porcelain"], text=True, capture_output=True, check=True).stdout
  assert wt_list.count("worktree ") == 1


def test_export_writeup_figures_badges_and_unverified_rubric_handling(tmp_path: Path) -> None:
  fake_secret = "sk-" + "ple-cli-synth-77889900"
  assert _has_secret(f"leak={fake_secret}", fake_secret) is True
  base_dir, cand_dir = tmp_path / "run_baseline", tmp_path / "run_candidate"
  base_dir.mkdir()
  cand_dir.mkdir()

  (base_dir / "results.json").write_text(json.dumps({
      "submission": f"ple-base-{fake_secret}", "model": "google-cloud/glm-5.2", "score": 0.1333, "complete": False,
      "unmeasured": ["rubric-memo-task"], "judge_model": None,
      "tasks": [
          {"id": "mep-routing", "score": 0.4, "reward": 0.4, "measured": True, "kind": "ok", "status": "graded", "seconds": 30.0, "trial": "attempt1/t1"},
          {"id": "loop-sizing", "score": 0.0, "reward": 0.0, "measured": True, "kind": "timeout", "status": "cancelled", "seconds": 60.0, "trial": "attempt1/t2"},
          {"id": "rubric-memo-task", "score": 0.0, "reward": 0.0, "measured": False, "kind": "grader failed", "status": "unmeasured", "seconds": 20.0, "trial": "attempt1/t3"},
      ],
  }), encoding="utf-8")
  _write_rollup(base_dir / "attempt1/t1/agent.txt", {"status": "done", "model": "glm-5.2", "uncached_input_tokens": 1000, "cache_write_tokens": 0, "cache_read_tokens": 4000, "output_tokens": 500, "cost_usd": 0.00416, "summary": "ok", "error": ""})
  _write_rollup(base_dir / "attempt1/t2/agent.txt", {"status": "cancelled", "model": "glm-5.2", "uncached_input_tokens": 2000, "cache_write_tokens": 0, "cache_read_tokens": 0, "output_tokens": 100, "cost_usd": 0.00324, "summary": "", "error": f"timeout {fake_secret}"})
  _write_rollup(base_dir / "attempt1/t3/agent.txt", {"status": "done", "model": "glm-5.2", "uncached_input_tokens": 1000, "cache_write_tokens": 0, "cache_read_tokens": 0, "output_tokens": 100, "cost_usd": 0.00184, "summary": "memo", "error": ""})

  (cand_dir / "results.json").write_text(json.dumps({
      "submission": f"ple-clausegate-mirrorir-{fake_secret}", "model": "google-cloud/glm-5.2", "score": 0.2833, "complete": False,
      "unmeasured": ["rubric-memo-task"], "judge_model": None,
      "tasks": [
          {"id": "mep-routing", "score": 0.85, "reward": 0.85, "measured": True, "kind": "ok", "status": "graded", "seconds": 35.0, "trial": "attempt1/t1"},
          {"id": "loop-sizing", "score": 0.0, "reward": 0.0, "measured": True, "kind": "error", "status": "error", "seconds": 12.0, "trial": "attempt1/t2"},
          {"id": "rubric-memo-task", "score": 0.0, "reward": 0.0, "measured": False, "kind": "grader failed", "status": "unmeasured", "seconds": 22.0, "trial": "attempt1/t3"},
      ],
  }), encoding="utf-8")
  # Omit cost_usd on t1: (1000*1.40 + 4000*0.14 + 300*4.40)/1e6 = 0.00328 USD
  _write_rollup(cand_dir / "attempt1/t1/agent.txt", {"status": "done", "model": "google-cloud/glm-5.2", "uncached_input_tokens": 1000, "cache_write_tokens": 0, "cache_read_tokens": 4000, "output_tokens": 300, "summary": "routed", "error": ""})
  _write_rollup(cand_dir / "attempt1/t2/agent.txt", {"status": "error", "model": "google-cloud/glm-5.2", "uncached_input_tokens": 500, "cache_write_tokens": 0, "cache_read_tokens": 0, "output_tokens": 50, "cost_usd": 0.00092, "summary": "", "error": f"Bearer {fake_secret}"})
  _write_rollup(cand_dir / "attempt1/t3/agent.txt", {"status": "done", "model": "google-cloud/glm-5.2", "uncached_input_tokens": 500, "cache_write_tokens": 0, "cache_read_tokens": 0, "output_tokens": 100, "cost_usd": 0.00114, "summary": "memo", "error": ""})

  assert _run_cli(["export-writeup", "--runs", str(cand_dir), "--out-dir", str(tmp_path / "bad_exp"), "--tier", "BOGUS_TIER"]).returncode != 0

  exp_dir = tmp_path / "writeup_out"
  cmd = ["export-writeup", "--runs", str(base_dir), str(cand_dir), "--baseline-run", str(base_dir), "--out-dir", str(exp_dir), "--tier", "SYNTHETIC_PROTOCOL_TEST"]
  res1 = _run_cli(cmd)
  assert res1.returncode == 0, "export-writeup first pass failed"
  snap1 = _snapshot_exports(exp_dir)
  res2 = _run_cli(cmd)
  assert res2.returncode == 0, "export-writeup second pass failed"
  snap2 = _snapshot_exports(exp_dir)
  p4_ok = evaluate_seam2_p4_oracle(export_snap_1=snap1, export_snap_2=snap2, cli_outputs=[res1.stdout, res1.stderr], json_payloads=[], ledger_data=None, expected_lock_count=None, fake_secrets=(fake_secret,))
  assert p4_ok, "export-writeup P4 oracle failed"

  fig1_rows = list(csv.DictReader(io.StringIO(snap1["figure1_pareto.csv"].decode("utf-8"))))
  cand_row = next(r for r in fig1_rows if "clausegate" in r["config_label"])
  assert cand_row["execution_tier"] == "SYNTHETIC_PROTOCOL_TEST"
  assert int(cand_row["measured_tasks"]) == 2 and int(cand_row["unverified_tasks"]) == 1
  assert abs(float(cand_row["measured_mean_score"]) - 0.425) < 1e-6
  assert abs(float(cand_row["mean_stage2_cost_usd"]) - 0.00178) < 1e-6
  assert "SYNTHETIC_PROTOCOL_TEST" in snap1["figure1_pareto.md"].decode("utf-8")

  fig2_rows = {r["task_id"]: r for r in csv.DictReader(io.StringIO(snap1["figure2_ablation.csv"].decode("utf-8")))}
  assert fig2_rows["mep-routing"]["verification_status"] == "VERIFIED"
  assert abs(float(fig2_rows["mep-routing"]["score_delta"]) - 0.45) < 1e-6
  assert fig2_rows["rubric-memo-task"]["baseline_score"] == "" and fig2_rows["rubric-memo-task"]["candidate_score"] == ""
  assert fig2_rows["rubric-memo-task"]["score_delta"] == "" and "UNVERIFIED" in fig2_rows["rubric-memo-task"]["verification_status"]
  assert "N/A" in snap1["figure2_ablation.md"].decode("utf-8")

  fig3_rows = list(csv.DictReader(io.StringIO(snap1["figure3_failures.csv"].decode("utf-8"))))
  cand_buckets = {r["bucket"]: int(r["count"]) for r in fig3_rows if "clausegate" in r["run_label"]}
  assert cand_buckets["done_pass"] == 1 and cand_buckets["error"] == 1 and cand_buckets["unverified_judge"] == 1


def test_lock_submission_guards_floor_and_lifetime_cap_and_hygiene_delegation(tmp_path: Path) -> None:
  fake_secret = "sk-" + "ple-cli-synth-77889900"
  assert _has_secret(fake_secret, fake_secret) is True
  ledger_path = tmp_path / "submission_locks.json"

  assert _run_cli(["lock-submission", "--ledger", str(ledger_path), "--git-rev", "111", "--model-api", "glm-5.2", "--mean-score", "0.1379"]).returncode != 0
  assert not ledger_path.exists()

  for idx, sc in enumerate(["0.138", "0.210", "0.350", "0.480", "0.620"], start=1):
    ok = _run_cli(["lock-submission", "--ledger", str(ledger_path), "--git-rev", f"rev{idx}", "--model-api", "google-cloud/glm-5.2", "--mean-score", sc, "--notes", f"lock {idx} {fake_secret}"])
    assert ok.returncode == 0, "lock-submission failed unexpectedly"
    if idx == 2:
      snap_two = ledger_path.read_bytes()
      assert _run_cli(["lock-submission", "--ledger", str(ledger_path), "--git-rev", "bad", "--model-api", "glm-5.2", "--mean-score", "0.100"]).returncode != 0
      assert ledger_path.read_bytes() == snap_two

  snap_five = ledger_path.read_bytes()
  assert _run_cli(["lock-submission", "--ledger", str(ledger_path), "--git-rev", "rev6", "--model-api", "glm-5.2", "--mean-score", "0.800"]).returncode != 0
  assert ledger_path.read_bytes() == snap_five
  ledger_data = json.loads(ledger_path.read_text(encoding="utf-8"))
  assert len(ledger_data["locks"]) == 5 and _has_forbidden_key(ledger_data) is False
  leaked = _has_secret(ledger_path.read_text(encoding="utf-8"), fake_secret)
  assert not leaked, "synthetic secret leaked into submission ledger"

  clean_repo = tmp_path / "clean_repo"
  _init_temp_git_repo(clean_repo)
  stub_hygiene = tmp_path / "stub_hygiene.py"
  stub_hygiene.write_text("import sys; sys.exit(0)\n", encoding="utf-8")
  assert _run_cli(["hygiene", "--repo", str(clean_repo), "--hygiene-script", str(stub_hygiene), "--skip-kit"]).returncode == 0

  (clean_repo / "artifacts").mkdir()
  (clean_repo / "artifacts" / "marker.txt").write_text("ok\n", encoding="utf-8")
  subprocess.run(["git", "-C", str(clean_repo), "add", "artifacts/marker.txt"], check=True)
  subprocess.run(["git", "-C", str(clean_repo), "commit", "-q", "-m", "chore: add artifacts marker"], check=True)

  bin_dir, kit_log, ple_dir = tmp_path / "stub_bin", tmp_path / "kit_calls.jsonl", tmp_path / "ple_kit_root"
  bin_dir.mkdir()
  ple_dir.mkdir()
  env_file = tmp_path / "proxy.env"
  env_file.write_text("MODEL_PROXY_URL=http://127.0.0.1:8000/v1\n", encoding="utf-8")
  uv_shim = bin_dir / "uv"
  uv_shim.write_text(
      f"#!{sys.executable}\nimport json, os, pathlib, sys\n"
      f"with pathlib.Path({str(kit_log)!r}).open('a', encoding='utf-8') as fh:\n"
      "  fh.write(json.dumps({'argv': sys.argv[1:]}) + '\\n')\n"
      "sys.exit(4 if (os.environ.get('STUB_KIT_FAIL') == '1' and 'check' in sys.argv) else 0)\n",
      encoding="utf-8",
  )
  uv_shim.chmod(uv_shim.stat().st_mode | stat.S_IEXEC)
  env_uv = {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}

  assert _run_cli(["hygiene", "--repo", str(clean_repo), "--ple-root", str(ple_dir), "--hygiene-script", str(stub_hygiene)], env=env_uv).returncode == 0
  assert _run_cli(["hygiene", "--repo", str(clean_repo), "--ple-root", str(ple_dir), "--env-file", str(env_file), "--hygiene-script", str(stub_hygiene)], env=env_uv).returncode == 0
  calls = [json.loads(line)["argv"] for line in kit_log.read_text(encoding="utf-8").splitlines()]
  assert ["run", "python", "-m", "kit", "artifacts", str(clean_repo.resolve())] in calls
  assert ["run", "python", "-m", "kit", "check", str(clean_repo.resolve())] in calls
  assert ["run", "python", "-m", "kit", "check", "--env-file", str(env_file.resolve()), str(clean_repo.resolve())] in calls
  assert _run_cli(["hygiene", "--repo", str(clean_repo), "--ple-root", str(ple_dir), "--hygiene-script", str(stub_hygiene)], env={**env_uv, "STUB_KIT_FAIL": "1"}).returncode == 4


def test_official_tokens_fallback_retry_dedup_and_non_judge_failure_buckets(tmp_path: Path) -> None:
  repo_dir = tmp_path / "repo_nonempty"
  _init_temp_git_repo(repo_dir)
  nonempty_out = tmp_path / "already_populated"
  nonempty_out.mkdir()
  (nonempty_out / "stale.txt").write_text("stale", encoding="utf-8")
  bad_run = _run_cli(["run", "--repo", str(repo_dir), "--out", str(nonempty_out), "--eval-cmd", "python3 -c 'pass'"])
  assert bad_run.returncode == 2 and "empty" in bad_run.stderr

  base_dir = tmp_path / "official_base"
  cand_dir = tmp_path / "retry_cand"
  base_dir.mkdir()
  cand_dir.mkdir()

  # Official baseline format: tokens dict, no [PLE_ROLLUP], plus decoy rollups in artifacts/ and tasks/
  # t1 cost on glm-5.2: input=5000, cache=4000 -> ui=1000, cr=4000, out=300 => (1000*1.4 + 4000*0.14 + 300*4.4)/1e6 = 0.003280
  (base_dir / "results.json").write_text(json.dumps({
      "submission": "official-openai-base",
      "model": "google-cloud/glm-5.2",
      "score": 0.125,
      "complete": False,
      "unmeasured": ["eval-crash-task", "judge-missing-task"],
      "judge_model": "gpt-5.4",
      "tasks": [
          {"id": "pipe-sizing", "score": 0.5, "reward": 0.5, "measured": True, "kind": "ok", "status": "ok", "trial": "attempt-1/pipe-sizing__a1", "tokens": {"input": 5000, "cache": 4000, "output": 300}},
          {"id": "eval-crash-task", "score": 0.0, "reward": None, "measured": False, "kind": "evaluator", "status": "evaluator: RuntimeError", "trial": "attempt-1/eval-crash-task__a1"},
          {"id": "judge-missing-task", "score": 0.0, "reward": None, "measured": False, "kind": "grader failed", "status": "grader failed: missing key", "trial": "attempt-1/judge-missing-task__a1"},
          {"id": "timed-out-task", "score": 0.0, "reward": 0.0, "measured": True, "kind": "harness", "status": "harness: AgentTimeoutError", "trial": "attempt-1/timed-out-task__a1"},
      ],
  }), encoding="utf-8")
  _write_rollup(base_dir / "artifacts/pipe-sizing/decoy.log", {"status": "done", "model": "glm-5.2", "uncached_input_tokens": 999999, "cache_write_tokens": 0, "cache_read_tokens": 0, "output_tokens": 999999, "cost_usd": 99.0})
  _write_rollup(base_dir / "tasks/pipe-sizing/decoy.txt", {"status": "done", "model": "glm-5.2", "uncached_input_tokens": 999999, "cache_write_tokens": 0, "cache_read_tokens": 0, "output_tokens": 999999, "cost_usd": 99.0})

  # Candidate run with discarded attempt-1 retry and selected attempt-2 trial
  (cand_dir / "results.json").write_text(json.dumps({
      "submission": "ple-candidate",
      "model": "google-cloud/glm-5.2",
      "score": 0.225,
      "complete": False,
      "unmeasured": ["eval-crash-task", "judge-missing-task"],
      "judge_model": "gpt-5.4",
      "tasks": [
          {"id": "pipe-sizing", "score": 0.9, "reward": 0.9, "measured": True, "kind": "ok", "status": "ok", "trial": "attempt-2/pipe-sizing__b2"},
          {"id": "eval-crash-task", "score": 0.0, "reward": None, "measured": False, "kind": "evaluator", "status": "evaluator: RuntimeError", "trial": "attempt-1/eval-crash-task__b1"},
          {"id": "judge-missing-task", "score": 0.0, "reward": None, "measured": False, "kind": "grader failed", "status": "grader failed: missing key", "trial": "attempt-1/judge-missing-task__b1"},
          {"id": "timed-out-task", "score": 0.0, "reward": 0.0, "measured": True, "kind": "harness", "status": "harness: RuntimeError", "trial": "attempt-1/timed-out-task__b1"},
      ],
  }), encoding="utf-8")
  _write_rollup(cand_dir / "attempt-1/pipe-sizing__old/serve.log", {"status": "error", "model": "glm-5.2", "uncached_input_tokens": 500000, "cache_write_tokens": 0, "cache_read_tokens": 0, "output_tokens": 50000, "cost_usd": 0.92})
  _write_rollup(cand_dir / "attempt-2/pipe-sizing__b2/serve.log", {"status": "done", "model": "glm-5.2", "uncached_input_tokens": 2000, "cache_write_tokens": 0, "cache_read_tokens": 0, "output_tokens": 200, "cost_usd": 0.00368})

  out_dir = tmp_path / "figures_out"
  res = _run_cli(["export-writeup", "--runs", str(base_dir), str(cand_dir), "--baseline-run", str(base_dir), "--out-dir", str(out_dir), "--tier", "LIVE_DOCKER_EVAL"])
  assert res.returncode == 0, res.stderr

  fig1 = {r["config_label"]: r for r in csv.DictReader(io.StringIO((out_dir / "figure1_pareto.csv").read_text(encoding="utf-8")))}
  base_row = next(v for k, v in fig1.items() if "official-openai-base" in k)
  cand_row = next(v for k, v in fig1.items() if "ple-candidate" in k)
  # Base mean cost across 4 executed tasks = 0.003280 / 4 = 0.000820
  assert abs(float(base_row["mean_stage2_cost_usd"]) - 0.00082) < 1e-6
  assert int(base_row["total_uncached_input_tokens"]) == 1000
  assert int(base_row["total_cache_read_tokens"]) == 4000
  # Cand mean cost across 4 executed tasks = 0.00368 / 4 = 0.000920 (attempt-1 0.92 NOT summed!)
  assert abs(float(cand_row["mean_stage2_cost_usd"]) - 0.00092) < 1e-6
  assert int(cand_row["total_uncached_input_tokens"]) == 2000

  fig2 = {r["task_id"]: r for r in csv.DictReader(io.StringIO((out_dir / "figure2_ablation.csv").read_text(encoding="utf-8")))}
  assert fig2["eval-crash-task"]["verification_status"] == "UNVERIFIED"
  assert fig2["judge-missing-task"]["verification_status"] == "UNVERIFIED_MISSING_JUDGE"

  fig3 = list(csv.DictReader(io.StringIO((out_dir / "figure3_failures.csv").read_text(encoding="utf-8"))))
  base_b = {r["bucket"]: int(r["count"]) for r in fig3 if "official-openai-base" in r["run_label"]}
  cand_b = {r["bucket"]: int(r["count"]) for r in fig3 if "ple-candidate" in r["run_label"]}
  assert base_b == {"done_pass": 1, "done_zero_score": 0, "cancelled": 1, "error": 1, "unverified_judge": 1}
  assert cand_b == {"done_pass": 1, "done_zero_score": 0, "cancelled": 0, "error": 2, "unverified_judge": 1}


# --- Role 2: Hypothesis P4 Safety Property Guardian ---


@settings(max_examples=12, deadline=None)
@given(
    noise=st.text(alphabet="abcXYZ09 \n\r\t\x07\x1b|,:\"'\\", min_size=1, max_size=25),
    score_a=st.floats(min_value=0.14, max_value=1.0, allow_nan=False, allow_infinity=False),
    unmeasured_b=st.booleans(),
    tok_in=st.integers(min_value=100, max_value=20_000),
    tok_out=st.integers(min_value=10, max_value=5_000),
)
def test_pbt_p4_cli_export_and_ledger_safety_guardian(
    noise: str, score_a: float, unmeasured_b: bool, tok_in: int, tok_out: int, tmp_path_factory: pytest.TempPathFactory
) -> None:
  case_dir = tmp_path_factory.mktemp("p4_seam2")
  fake_sk, fake_hf, fake_ai = "sk-" + "ple-cli-synth-77889900", "hf_" + "pleCliSynthToken99887766", "AIza" + "SyPleCliSynthKey1234567890"
  dirty_blob = f"{noise}{fake_sk} Bearer {fake_hf} key={fake_ai}\nsecond_line"

  run_dir = case_dir / "run_one"
  run_dir.mkdir()
  (run_dir / "results.json").write_text(json.dumps({
      "submission": f"sub-{noise[:4]}-{fake_sk}", "model": "google-cloud/glm-5.2", "score": score_a / 2.0,
      "complete": not unmeasured_b, "unmeasured": ["task-b"] if unmeasured_b else [],
      "judge_model": None if unmeasured_b else "claude-opus-5-5",
      "tasks": [
          {"id": "task-a", "score": score_a, "reward": score_a, "measured": True, "kind": "ok", "status": "graded", "seconds": 10.0, "trial": "t_a"},
          {"id": "task-b", "score": 0.0, "reward": 0.0, "measured": not unmeasured_b, "kind": "grader failed" if unmeasured_b else "ok", "status": "graded", "seconds": 12.0, "trial": "t_b"},
      ],
  }), encoding="utf-8")
  _write_rollup(run_dir / "t_a/serve.log", {"status": "done", "model": "glm-5.2", "uncached_input_tokens": tok_in, "cache_write_tokens": 0, "cache_read_tokens": 0, "output_tokens": tok_out, "summary": dirty_blob, "error": ""})
  _write_rollup(run_dir / "t_b/serve.log", {"status": "error", "model": "glm-5.2", "uncached_input_tokens": tok_in, "cache_write_tokens": 0, "cache_read_tokens": 0, "output_tokens": tok_out, "summary": "", "error": dirty_blob})

  exp1_dir, exp2_dir = case_dir / "exp1", case_dir / "exp2"
  r1 = _run_cli(["export-writeup", "--runs", str(run_dir), "--out-dir", str(exp1_dir), "--tier", "SYNTHETIC_PROTOCOL_TEST"], env={"OPENAI_API_KEY": fake_sk})
  r2 = _run_cli(["export-writeup", "--runs", str(run_dir), "--out-dir", str(exp2_dir), "--tier", "SYNTHETIC_PROTOCOL_TEST"], env={"OPENAI_API_KEY": fake_sk})
  assert r1.returncode == 0 and r2.returncode == 0

  ledger_path = case_dir / "ledger.json"
  rl = _run_cli(["lock-submission", "--ledger", str(ledger_path), "--git-rev", "abc1234", "--model-api", "google-cloud/glm-5.2", "--mean-score", f"{score_a:.4f}", "--notes", dirty_blob], env={"MODEL_API_KEY": fake_sk})
  assert rl.returncode == 0
  ledger_data = json.loads(ledger_path.read_text(encoding="utf-8"))

  p4_ok = evaluate_seam2_p4_oracle(
      export_snap_1=_snapshot_exports(exp1_dir), export_snap_2=_snapshot_exports(exp2_dir),
      cli_outputs=[r1.stdout, r1.stderr, r2.stdout, r2.stderr, rl.stdout, rl.stderr],
      json_payloads=[ledger_data], ledger_data=ledger_data, expected_lock_count=1, fake_secrets=(fake_sk, fake_hf, fake_ai),
  )
  assert p4_ok, "PBT Seam-2 P4 safety oracle failed"


# --- Role 3: Test-local Oracle Calibration ---


def test_seam2_p4_oracle_calibration() -> None:
  fake_secret = "sk-" + "ple-cli-synth-77889900"
  good_snap = {
      "figure1_pareto.csv": b"config_label,execution_tier,measured_mean_score\ncfg,LIVE_DOCKER_EVAL,0.5\n",
      "figure1_pareto.md": b"# Figure 1 [LIVE_DOCKER_EVAL]\n",
      "figure2_ablation.csv": b"task_id,execution_tier,verification_status\nt1,LIVE_DOCKER_EVAL,VERIFIED\n",
      "figure2_ablation.md": b"# Figure 2 [LIVE_DOCKER_EVAL]\n",
      "figure3_failures.csv": b"run_label,execution_tier,bucket,count,share\ncfg,LIVE_DOCKER_EVAL,done_pass,1,1.0\n",
      "figure3_failures.md": b"# Figure 3 [LIVE_DOCKER_EVAL]\n",
  }
  good_ledger = {"locks": [{"lock_index": 1, "git_rev": "abc", "model_api": "glm-5.2", "mean_score": 0.25, "notes": "clean"}]}
  cal_good = evaluate_seam2_p4_oracle(export_snap_1=good_snap, export_snap_2=dict(good_snap), cli_outputs=["ok"], json_payloads=[{"tier": "LIVE_DOCKER_EVAL"}], ledger_data=good_ledger, expected_lock_count=1, fake_secrets=(fake_secret,))
  assert cal_good is True, "good calibration baseline must pass"

  bad_sec = {**good_snap, "figure1_pareto.md": f"leak {fake_secret}".encode("utf-8")}
  cal_sec_md = evaluate_seam2_p4_oracle(export_snap_1=bad_sec, export_snap_2=dict(bad_sec), cli_outputs=["ok"], json_payloads=[], ledger_data=good_ledger, expected_lock_count=1, fake_secrets=(fake_secret,))
  assert cal_sec_md is False, "secret in markdown export must fail"
  cal_sec_out = evaluate_seam2_p4_oracle(export_snap_1=good_snap, export_snap_2=dict(good_snap), cli_outputs=[f"err {fake_secret}"], json_payloads=[], ledger_data=good_ledger, expected_lock_count=1, fake_secrets=(fake_secret,))
  assert cal_sec_out is False, "secret in CLI output must fail"
  cal_diff = evaluate_seam2_p4_oracle(export_snap_1=good_snap, export_snap_2={**good_snap, "figure1_pareto.md": b"diff\n"}, cli_outputs=["ok"], json_payloads=[], ledger_data=good_ledger, expected_lock_count=1, fake_secrets=(fake_secret,))
  assert cal_diff is False, "non-idempotent export must fail"

  for bad_key in sorted(FORBIDDEN_KEYS):
    cal_key = evaluate_seam2_p4_oracle(export_snap_1=good_snap, export_snap_2=dict(good_snap), cli_outputs=["ok"], json_payloads=[{"nested": {bad_key: "1"}}], ledger_data=good_ledger, expected_lock_count=1, fake_secrets=(fake_secret,))
    assert cal_key is False, "forbidden key in JSON must fail"
  bad_col = "sha" + "256"
  bad_csv = {**good_snap, "figure1_pareto.csv": f"config_label,{bad_col}\ncfg,abc\n".encode("utf-8")}
  cal_csv = evaluate_seam2_p4_oracle(export_snap_1=bad_csv, export_snap_2=dict(bad_csv), cli_outputs=["ok"], json_payloads=[], ledger_data=good_ledger, expected_lock_count=1, fake_secrets=(fake_secret,))
  assert cal_csv is False, "forbidden column in CSV must fail"

  cal_cnt = evaluate_seam2_p4_oracle(export_snap_1=good_snap, export_snap_2=dict(good_snap), cli_outputs=["ok"], json_payloads=[], ledger_data=good_ledger, expected_lock_count=2, fake_secrets=(fake_secret,))
  assert cal_cnt is False, "mismatched lock count must fail"
  cal_floor = evaluate_seam2_p4_oracle(export_snap_1=good_snap, export_snap_2=dict(good_snap), cli_outputs=["ok"], json_payloads=[], ledger_data={"locks": [{"mean_score": 0.137}]}, expected_lock_count=1, fake_secrets=(fake_secret,))
  assert cal_floor is False, "below-floor lock must fail"
  cal_cap = evaluate_seam2_p4_oracle(export_snap_1=good_snap, export_snap_2=dict(good_snap), cli_outputs=["ok"], json_payloads=[], ledger_data={"locks": [{"mean_score": 0.5}] * 6}, expected_lock_count=6, fake_secrets=(fake_secret,))
  assert cal_cap is False, "above-cap lock must fail"
