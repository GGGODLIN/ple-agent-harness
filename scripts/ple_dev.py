#!/usr/bin/env python3
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

"""Thin external worktree runner, Writeup figure exporter, and Stage 1 submission lock CLI."""

from __future__ import annotations

import argparse, csv, io, json, math, os, re, shlex, shutil, subprocess, sys, tempfile, urllib.parse
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
ALLOWED_TIERS = ("STAGE1_FINAL_EXPORT", "LIVE_DOCKER_EVAL", "SYNTHETIC_PROTOCOL_TEST")
DEV_SCORE_FLOOR = Decimal("0.138")
MAX_SUBMISSION_LOCKS = 5
FAILURE_BUCKETS = ("done_pass", "done_zero_score", "cancelled", "error", "unverified_judge")
SECRET_ENV_VARS = ("MODEL_API_KEY", "MODEL_PROXY_KEY", "OPENAI_API_KEY", "JUDGE_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "HF_TOKEN")
URL_ENV_VARS = ("MODEL_BASE_URL", "MODEL_PROXY_URL", "OPENAI_BASE_URL")
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]+")
STAGE2_RATES_PER_M: dict[str, tuple[Decimal, ...]] = {
    k: tuple(Decimal(x) for x in v) for k, v in (
        ("claude-opus-5-5", ("4.00", "5.00", "0.20", "20.00")), ("gemini-4-argon", ("4.00", "4.00", "0.20", "20.00")),
        ("gemini-3.8-flash", ("1.50", "1.50", "0.15", "7.50")), ("gemini-3.1-pro-preview", ("2.00", "2.00", "0.20", "12.00")),
        ("glm-5.2", ("1.40", "1.40", "0.14", "4.40")), ("gemma-4-26b", ("0.15", "0.15", "0.015", "0.60")),
        ("llama-4-maverick", ("0.35", "0.35", "0.35", "1.15")), ("gpt-oss-120b", ("0.09", "0.09", "0.09", "0.36")),
    )
}
_SECRET_RES = (
    (re.compile(r"(https?://)([^/\s@]+)@"), r"\1[REDACTED]@"), (re.compile(r"(?i)(bearer\s+)\S+"), r"\1[REDACTED]"),
    (re.compile(r"(?:sk-[A-Za-z0-9_-]{8,}|AIza[0-9A-Za-z_-]{16,}|hf_[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{16,}|AKIA[0-9A-Z]{16})"), "[REDACTED]"),
)

def _err(msg: str, code: int = 2) -> int:
  sys.stderr.write(msg + "\n")
  return code

def redact_secrets(text: str) -> str:
  if not text:
    return ""
  found = {v for k in SECRET_ENV_VARS if len(v := (os.environ.get(k) or "").strip()) >= 4 and v.lower() not in {"none", "null", "empty"}}
  for key in URL_ENV_VARS:
    try:
      p = urllib.parse.urlsplit((os.environ.get(key) or "").strip())
      if p.password:
        found.update({p.password, *([f"{p.username}:{p.password}"] if p.username else [])})
    except ValueError:
      pass
  out = text
  for secret in sorted(found, key=len, reverse=True):
    out = out.replace(secret, "[REDACTED]")
  for pat, repl in _SECRET_RES:
    out = pat.sub(repl, out)
  return out

def _clean_text(value: Any) -> str:
  s = redact_secrets(str(value if value is not None else "")).replace(chr(0x2028), " ").replace(chr(0x2029), " ")
  return redact_secrets(_CTRL_RE.sub(" ", s).strip())

def _stage2_cost_usd(model_name: str, u: int, cw: int, cr: int, out_t: int) -> Decimal:
  r = STAGE2_RATES_PER_M.get((model_name or "").strip().lower().rsplit("/", 1)[-1])
  return ((Decimal(u) * r[0] + Decimal(cw) * r[1] + Decimal(cr) * r[2] + Decimal(out_t) * r[3]) / Decimal(1_000_000)) if r else Decimal("0")

def _write_text(path: Path, content: str) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(content, encoding="utf-8")

def _update_worktree_submission(sub_path: Path, model_api: str | None) -> str:
  data = yaml.safe_load(sub_path.read_text(encoding="utf-8")) or {}
  if model_api:
    data["model_api"] = model_api
    _write_text(sub_path, yaml.safe_dump(data, sort_keys=False))
  return str(data.get("model_api") or "")


def cmd_run(args: argparse.Namespace) -> int:
  if args.tier not in ALLOWED_TIERS or args.tier == "STAGE1_FINAL_EXPORT":
    return _err("Invalid tier for --no-export worktree run.")
  repo_path, out_path = Path(args.repo).resolve(), Path(args.out).resolve()
  if out_path == repo_path or out_path.is_relative_to(repo_path):
    return _err("--out must resolve outside --repo.")
  rev_res = subprocess.run(["git", "-C", str(repo_path), "rev-parse", "HEAD"], text=True, capture_output=True, check=False)
  if rev_res.returncode != 0:
    return _err("Failed to resolve git HEAD in --repo.")
  tmp_parent = Path(tempfile.mkdtemp(prefix="ple-wt-"))
  wt_dir = tmp_parent / "checkout"
  try:
    if subprocess.run(["git", "-C", str(repo_path), "worktree", "add", "--detach", str(wt_dir), "HEAD"], text=True, capture_output=True, check=False).returncode != 0:
      return _err("Failed to create detached git worktree.")
    eff_model = _update_worktree_submission(wt_dir / "submission.yaml", args.model_api)
    out_path.mkdir(parents=True, exist_ok=True)
    cmd = [*shlex.split(args.eval_cmd), str(wt_dir), "--no-export", "--out", str(out_path)]
    if args.tasks:
      cmd.extend(["--tasks", args.tasks])
    if args.env_file:
      cmd.extend(["--env-file", str(Path(args.env_file).resolve())])
    proc = subprocess.run(cmd, cwd=str(Path(args.ple_root).resolve()) if args.ple_root else None, check=False)
    meta = {"tier": args.tier, "git_rev": _clean_text(rev_res.stdout.strip()), "model_api": _clean_text(eff_model), "exit_code": int(proc.returncode)}
    _write_text(out_path / "ple_run_meta.json", json.dumps(meta, indent=2) + "\n")
    return int(proc.returncode)
  finally:
    subprocess.run(["git", "-C", str(repo_path), "worktree", "remove", "--force", str(wt_dir)], capture_output=True, check=False)
    shutil.rmtree(tmp_parent, ignore_errors=True)
    subprocess.run(["git", "-C", str(repo_path), "worktree", "prune"], capture_output=True, check=False)


def _load_run_summary(run_dir: Path) -> dict[str, Any]:
  if not (run_dir / "results.json").is_file():
    raise ValueError(f"Missing results.json in {run_dir.name}")
  raw_res = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
  submission = _clean_text(raw_res.get("submission") or run_dir.name)
  run_model, judge_model = _clean_text(raw_res.get("model") or ""), _clean_text(raw_res.get("judge_model") or "")
  unmeasured_ids = {str(x) for x in (raw_res.get("unmeasured") or [])}
  log_rollups: list[tuple[Path, dict[str, Any]]] = []
  for p in sorted(run_dir.rglob("*")):
    if p.is_file() and p.suffix in {".txt", ".log"}:
      for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if (pos := line.find("[PLE_ROLLUP]")) >= 0:
          try:
            if isinstance(obj := json.loads(line[pos + len("[PLE_ROLLUP]"):].strip()), dict):
              log_rollups.append((p, obj))
          except json.JSONDecodeError:
            pass
  raw_tasks = list(raw_res.get("tasks") or [])
  used_idx, matched = set(), {}
  for t_i, t in enumerate(raw_tasks):
    tid, trial = str(t.get("id") or ""), str(t.get("trial") or "").strip()
    found_j = next((j for j in reversed(range(len(log_rollups))) if trial and log_rollups[j][0].resolve().is_relative_to((run_dir / trial).resolve())), None)
    if found_j is None and tid:
      found_j = next((j for j in reversed(range(len(log_rollups))) if j not in used_idx and (str(log_rollups[j][1].get("task_id") or "") == tid or tid in log_rollups[j][0].relative_to(run_dir).parts or log_rollups[j][0].stem.startswith(tid))), None)
    if found_j is not None:
      matched[t_i], _ = log_rollups[found_j][1], used_idx.add(found_j)
  unmatched = [i for i in range(len(raw_tasks)) if i not in matched]
  rem = [(j, r) for j, (_, r) in enumerate(log_rollups) if j not in used_idx]
  if unmatched and len(unmatched) == len(rem):
    for t_i, (j, r) in zip(unmatched, rem):
      matched[t_i], _ = r, used_idx.add(j)

  def _metrics(r_obj: dict[str, Any] | None) -> tuple[list[int], Decimal, str]:
    if not r_obj:
      return ([0, 0, 0, 0], Decimal("0"), "")
    toks = [max(0, int(r_obj.get(k, 0) or 0)) for k in ("uncached_input_tokens", "cache_write_tokens", "cache_read_tokens", "output_tokens")]
    raw_c = r_obj.get("cost_usd")
    return (toks, Decimal(str(raw_c)) if raw_c is not None else _stage2_cost_usd(_clean_text(r_obj.get("model") or run_model), *toks), _clean_text(r_obj.get("status") or "").lower())

  tasks_map, tok_sums, tot_cost = {}, [0, 0, 0, 0], Decimal("0")
  for t_i, t in enumerate(raw_tasks):
    tid = _clean_text(t.get("id") or f"task-{t_i}")
    toks, cost, r_status = _metrics(matched.get(t_i))
    tok_sums, tot_cost = [a + b for a, b in zip(tok_sums, toks)], tot_cost + cost
    kind, t_status = _clean_text(t.get("kind") or "").lower(), _clean_text(t.get("status") or "").lower()
    raw_score = t.get("score") if t.get("score") is not None else t.get("reward")
    unverified = (tid in unmeasured_ids) or (t.get("measured") is False) or kind in {"grader failed", "unmeasured", "missing_judge"} or (raw_score is None)
    if unverified:
      ver_status = "UNVERIFIED_MISSING_JUDGE" if (not judge_model or tid in unmeasured_ids or "grader failed" in kind) else "UNVERIFIED"
      score_val, bucket = None, "unverified_judge"
    else:
      ver_status, score_val = "VERIFIED", float(raw_score)
      bucket = "cancelled" if (r_status == "cancelled" or t_status == "cancelled" or "timeout" in kind) else ("error" if (r_status == "error" or t_status == "error" or kind in {"error", "agent failed", "harness_error"}) else ("done_pass" if score_val > 0.0 else "done_zero_score"))
    tasks_map[tid] = {"score": score_val, "cost": cost, "verified": not unverified, "ver_status": ver_status, "bucket": bucket}
  for cid in (_clean_text(x) for x in sorted(unmeasured_ids)):
    tasks_map.setdefault(cid, {"score": None, "cost": Decimal("0"), "verified": False, "ver_status": "UNVERIFIED_MISSING_JUDGE", "bucket": "unverified_judge"})
  for j, (_, r_obj) in enumerate(log_rollups):
    if j not in used_idx:
      toks, cost, _ = _metrics(r_obj)
      tok_sums, tot_cost = [a + b for a, b in zip(tok_sums, toks)], tot_cost + cost
  label = f"{submission} ({_clean_text(run_dir.name)})" if submission != _clean_text(run_dir.name) else submission
  return {"path": run_dir, "label": label, "model": run_model, "tasks": tasks_map, "executed_count": len(raw_tasks), "toks": tok_sums, "tot_cost": tot_cost}

def _write_csv_and_md(out_dir: Path, stem: str, title: str, headers: list[str], csv_rows: list[list[str]], md_rows: list[list[str]]) -> None:
  buf = io.StringIO()
  w = csv.writer(buf, lineterminator="\n")
  w.writerow(headers)
  w.writerows(csv_rows)
  _write_text(out_dir / f"{stem}.csv", buf.getvalue())
  esc = lambda v: _clean_text(v).replace("|", "\\|")
  md = [f"# {title}", "", "| " + " | ".join(esc(h) for h in headers) + " |", "| " + " | ".join("---" for _ in headers) + " |", *("| " + " | ".join(esc(c) for c in row) + " |" for row in md_rows)]
  _write_text(out_dir / f"{stem}.md", "\n".join(md) + "\n")


def cmd_export_writeup(args: argparse.Namespace) -> int:
  run_dirs = [Path(p).resolve() for p in args.runs]
  base_dir = Path(args.baseline_run).resolve() if args.baseline_run else None
  all_dirs = [*run_dirs, *([base_dir] if base_dir and base_dir not in run_dirs else [])]
  meta_tiers: list[str] = []
  for d in all_dirs:
    if (d / "ple_run_meta.json").is_file():
      t = str(json.loads((d / "ple_run_meta.json").read_text(encoding="utf-8")).get("tier") or "")
      if t not in ALLOWED_TIERS:
        return _err("Invalid tier inside ple_run_meta.json.")
      meta_tiers.append(t)
  if args.tier is not None:
    if args.tier not in ALLOWED_TIERS or (args.tier == "STAGE1_FINAL_EXPORT" and any(t != "STAGE1_FINAL_EXPORT" for t in meta_tiers)):
      return _err("Invalid or disallowed --tier badge.")
    tier = args.tier
  elif len(meta_tiers) == len(all_dirs) and len(set(meta_tiers)) == 1:
    tier = meta_tiers[0]
  else:
    return _err("Specify --tier explicitly or provide consistent ple_run_meta.json across runs.")

  try:
    summaries = [_load_run_summary(d) for d in run_dirs]
    base_sum = _load_run_summary(base_dir) if base_dir else summaries[0]
  except (OSError, ValueError, json.JSONDecodeError) as exc:
    return _err(_clean_text(str(exc)))

  out_dir = Path(args.out_dir).resolve()
  f1_h = ["config_label", "model", "execution_tier", "measured_tasks", "unverified_tasks", "measured_mean_score", "mean_stage2_cost_usd", "total_uncached_input_tokens", "total_cache_write_tokens", "total_cache_read_tokens", "total_output_tokens"]
  f1_csv, f1_md = [], []
  for s in summaries:
    ver = [v["score"] for v in s["tasks"].values() if v["verified"] and v["score"] is not None]
    unver = sum(1 for v in s["tasks"].values() if not v["verified"])
    m_sc = f"{sum(ver) / len(ver):.6f}" if ver else ""
    m_cost = (s["tot_cost"] / Decimal(s["executed_count"])) if s["executed_count"] > 0 else Decimal("0")
    tail = [f"{m_cost:.6f}", *(str(x) for x in s["toks"])]
    f1_csv.append([s["label"], s["model"], tier, str(len(ver)), str(unver), m_sc, *tail])
    f1_md.append([s["label"], s["model"], tier, str(len(ver)), str(unver), m_sc or "N/A", *tail])
  _write_csv_and_md(out_dir, "figure1_pareto", f"Figure 1 - Score vs January-2027 Stage-2 USD Cost [{tier}]", f1_h, f1_csv, f1_md)

  cand_list = ([s for s in summaries if s["path"] != base_dir] or [summaries[-1]]) if base_dir else (summaries[1:] if len(summaries) > 1 else [summaries[0]])
  f2_h = ["task_id", "execution_tier", "baseline_score", "candidate_score", "score_delta", "baseline_cost_usd", "candidate_cost_usd", "cost_delta_usd", "verification_status"]
  f2_csv, f2_md = [], []
  for cand in cand_list:
    for tid in sorted(set(base_sum["tasks"].keys()) | set(cand["tasks"].keys())):
      rid = tid if len(cand_list) == 1 else f"{cand['label']}:{tid}"
      bt, ct = base_sum["tasks"].get(tid), cand["tasks"].get(tid)
      bv, cv = bool(bt and bt["verified"] and bt["score"] is not None), bool(ct and ct["verified"] and ct["score"] is not None)
      bs, cs = (f"{bt['score']:.6f}" if bv and bt else ""), (f"{ct['score']:.6f}" if cv and ct else "")
      ds = f"{ct['score'] - bt['score']:.6f}" if (bv and cv and bt and ct) else ""
      bc, cc = (bt["cost"] if bt else Decimal("0")), (ct["cost"] if ct else Decimal("0"))
      vs = "VERIFIED" if (bv and cv) else ("UNVERIFIED_MISSING_JUDGE" if ((bt and bt["ver_status"] == "UNVERIFIED_MISSING_JUDGE") or (ct and ct["ver_status"] == "UNVERIFIED_MISSING_JUDGE")) else "UNVERIFIED")
      tail = [f"{bc:.6f}", f"{cc:.6f}", f"{cc - bc:.6f}", vs]
      f2_csv.append([rid, tier, bs, cs, ds, *tail])
      f2_md.append([rid, tier, bs or "N/A", cs or "N/A", ds or "N/A", *tail])
  _write_csv_and_md(out_dir, "figure2_ablation", f"Figure 2 - Paired Ablation Delta [{tier}]", f2_h, f2_csv, f2_md)

  f3_h = ["run_label", "execution_tier", "bucket", "count", "share"]
  f3_rows = [[s["label"], tier, b, str(c := sum(1 for v in s["tasks"].values() if v["bucket"] == b)), f"{c / max(1, len(s['tasks'])):.6f}"] for s in summaries for b in FAILURE_BUCKETS]
  _write_csv_and_md(out_dir, "figure3_failures", f"Figure 3 - Failure-Bucket Distribution [{tier}]", f3_h, f3_rows, f3_rows)
  return 0


def cmd_lock_submission(args: argparse.Namespace) -> int:
  if math.isnan(args.mean_score) or math.isinf(args.mean_score):
    return _err("Invalid --mean-score.")
  try:
    score_dec = Decimal(str(args.mean_score))
  except InvalidOperation:
    return _err("Invalid --mean-score decimal.")
  if score_dec < DEV_SCORE_FLOOR:
    return _err(f"Rejected: mean_score {score_dec} is below {DEV_SCORE_FLOOR}.", 1)
  ledger_path = Path(args.ledger).resolve()
  existing = list(json.loads(ledger_path.read_text(encoding="utf-8")).get("locks") or []) if ledger_path.is_file() else []
  if len(existing) >= MAX_SUBMISSION_LOCKS:
    return _err(f"Rejected: submission ledger reached lifetime cap ({MAX_SUBMISSION_LOCKS}).", 1)
  locks = [{"lock_index": i + 1, "git_rev": _clean_text(x.get("git_rev", "")), "model_api": _clean_text(x.get("model_api", "")), "mean_score": float(x.get("mean_score", 0.0)), "notes": _clean_text(x.get("notes", ""))} for i, x in enumerate(existing)]
  locks.append({"lock_index": len(locks) + 1, "git_rev": _clean_text(args.git_rev), "model_api": _clean_text(args.model_api), "mean_score": float(score_dec), "notes": _clean_text(args.notes)})
  _write_text(ledger_path, json.dumps({"locks": locks}, indent=2) + "\n")
  return 0

def cmd_hygiene(args: argparse.Namespace) -> int:
  repo_path = Path(args.repo).resolve()
  script = Path(args.hygiene_script).resolve() if args.hygiene_script else (Path.home() / ".claude/skills/hackathon/scripts/pre-submit-hygiene.py")
  if not script.is_file():
    return _err("pre-submit-hygiene.py not found.")
  res = subprocess.run([sys.executable, str(script), "--repo", str(repo_path)], check=False)
  if res.returncode != 0 or not args.ple_root or args.skip_kit:
    return int(res.returncode)
  ple_root = Path(args.ple_root).resolve()
  if (repo_path / "artifacts").exists():
    art = subprocess.run(["uv", "run", "python", "-m", "kit", "artifacts", str(repo_path)], cwd=str(ple_root), check=False)
    if art.returncode != 0:
      return int(art.returncode)
  return int(subprocess.run(["uv", "run", "python", "-m", "kit", "check", str(repo_path)], cwd=str(ple_root), check=False).returncode)

def build_parser() -> argparse.ArgumentParser:
  p = argparse.ArgumentParser(description="PLE external worktree runner & Writeup exporter CLI.")
  sub = p.add_subparsers(dest="subcommand", required=True)
  specs = (
      ("run", cmd_run, (("--repo", {"default": str(REPO_ROOT)}), ("--ple-root", {}), ("--out", {"required": True}), ("--tasks", {}), ("--env-file", {}), ("--model-api", {}), ("--eval-cmd", {"default": "uv run python eval/run.py"}), ("--tier", {"default": "LIVE_DOCKER_EVAL"}))),
      ("export-writeup", cmd_export_writeup, (("--runs", {"nargs": "+", "required": True}), ("--baseline-run", {}), ("--out-dir", {"required": True}), ("--tier", {}))),
      ("lock-submission", cmd_lock_submission, (("--ledger", {"required": True}), ("--git-rev", {"required": True}), ("--model-api", {"required": True}), ("--mean-score", {"type": float, "required": True}), ("--notes", {"default": ""}))),
      ("hygiene", cmd_hygiene, (("--repo", {"default": str(REPO_ROOT)}), ("--ple-root", {}), ("--skip-kit", {"action": "store_true"}), ("--hygiene-script", {}))),
  )
  for name, fn, flags in specs:
    sp = sub.add_parser(name)
    for flag, kw in flags:
      sp.add_argument(flag, **kw)
    sp.set_defaults(func=fn)
  return p

def main(argv: list[str] | None = None) -> int:
  args = build_parser().parse_args(argv)
  return int(args.func(args))

if __name__ == "__main__":
  sys.exit(main())
