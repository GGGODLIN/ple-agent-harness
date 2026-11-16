# ple-clausegate-mirrorir

Competition agent harness entry for **Google — Agent Harness on Physical-Engineering's Last Exam (PLE)** (`physical-engineerings-last-exam`).

## Overview & Repository Provenance

This repository is a clean, standalone competition entry created after rules acceptance and licensed under `Apache-2.0` (see `LICENSE`). All model credentials and judge keys stay strictly outside the repository (`--env-file <path-to-env-file>`), and all exploratory dev-set probes write outside the repository via `--no-export` so `artifacts/` is reserved exclusively for official `eval/run.py` Stage-1 exports.

## Upstream Attribution (`Apache-2.0`)

Portions of this repository are vendored or adapted from [google-research/ple](https://github.com/google-research/ple) (`Copyright 2026 Google LLC`, licensed under `Apache-2.0`):

- `taskbridge.py`: Vendored and trimmed WebSocket Protocol v1 server bridge from `google-research/ple` (`Copyright 2026 Google LLC`, `Apache-2.0`).
- `harness.py` & `serve.py`: Adapted from the upstream `sample_submissions/custom-openai` and `sample_submissions/plan-verify` reference harnesses (`Copyright 2026 Google LLC`, `Apache-2.0`), extended with immutable-prefix caching discipline, static family-aware reasoning effort, atomic file staging, secret redaction, task-side deliverable auditing, and Stage-2 cost telemetry.

`requirements.txt` pins the two Serve-container runtime packages (`openai`, `websockets`) alongside six permissively licensed verification and reference packages (`XlsxWriter`, `openpyxl`, `python-docx`, `pdfplumber`, `scipy`, `pint`) under `Apache-2.0`, `BSD-3-Clause`, `BSD-2-Clause`, and `MIT` licenses.

## Architecture

- **`submission.yaml` & `serve.py` (WebSocket v1 Entrypoint)**: Installs a self-contained Python virtual environment under `/opt/harness/venv` inside `plebench-builder` (supporting both `uv` Python 3.12 and `debian:bookworm` Python 3.11 fallback) and starts `taskbridge.run(harness.solve)` over WebSocket Protocol v1 with zero extra network egress hosts (`allowed_hosts` omitted).
- **`harness.py` (Immutable-Prefix Static-Effort Loop)**:
  - **Prompt-Cache Discipline & Static Effort**: Preserves byte-identical `messages[:2]` (`system` + initial `user` instruction) across turns and resolves static per-family `reasoning_effort` (`max` for Claude, GLM, GPT-6, DeepSeek-V4; `high` for Gemini and GPT-OSS; omitted for Gemma and Llama).
  - **Full-Output Tee & Atomic Staging**: Tees every `bash` command output to `/tmp/.ple_work_<session>/cmd_XXXX.log` inside the task container before middle-clipping prompt context, and stages `write_file` / `edit_file` mutations through same-directory `._ple_stage_*` files committed via atomic `os.replace`.
  - **Zero-I/O Cancel & Secret Redaction**: Immediately raises `taskbridge.Cancelled` with zero extra model or container calls when `cancel` arrives, and scrubs active credentials/URLs from all log and error frames.
  - **January-2027 Stage-2 Telemetry**: Emits a single sanitized `[PLE_ROLLUP]` JSON record per task computing exact `Decimal` Stage-2 list USD cost across uncached input, cache-write, cache-read, and output tokens.
- **`deliverable_audit.py` (Task-Side Deliverable Audit & OOXML Patcher)**:
  - **Pure-Stdlib OOXML `<v>` Patcher**: Audits produced or modified `.xlsx` workbooks directly as ZIP/XML archives (across `workdir` and sibling `/filesystem` roots) without `openpyxl.save()` round-trip corruption, leaving untouched baseline `.xlsx` fixtures and unchanged `TODAY()`/`NOW()` cached `<v>` tags intact while topologically evaluating dirty formula cells (`SUM`, `AVERAGE`, `MIN`, `MAX`, `COUNT`, `ABS`, `ROUND`, `SQRT`, `IF`, `IFERROR`, `AND`, `OR`, `NOT`) and flagging Excel error tokens (`#REF!`, `#DIV/0!`, `#VALUE!`, `#NAME?`, `#NUM!`, `#N/A`, `#NULL!`).
  - **Cross-Document Consistency & Conditional Optimization**: Validates `.pdf` deliverables for non-empty `%PDF-` headers, cross-checks `.xlsx`, `.docx`, `.json`, and UTF-8 text deliverables (`.csv`, `.md`, up to 2 MiB) against canonical `facts.json` quantities, gates `<= 3` bounded numerical optimization rounds via `is_quantitative_optimization_task`, and keeps the optional read-only second-pass auditor OFF by default (`PLE_ENABLE_VERIFIER=0`).
- **`scripts/ple_dev.py` (External Worktree Runner & Writeup Exporter)**:
  - Runs `eval/run.py --no-export` from a detached temporary `git worktree` writing to a fresh external `--out` directory so the main checkout stays untouched.
  - Exports deterministic CSV and Markdown tables for Writeup Figures 1–3 (`figure1_pareto`, `figure2_ablation`, `figure3_failures`) stamped with explicit execution-tier badges (`STAGE1_FINAL_EXPORT`, `LIVE_DOCKER_EVAL`, `SYNTHETIC_PROTOCOL_TEST`), valuing both `[PLE_ROLLUP]` telemetry and official `results.json` baseline `tokens` counts while deriving `UNVERIFIED_MISSING_JUDGE` vs `UNVERIFIED` status directly from `results.json` judge and grader fields.
  - Enforces the `mean_score >= 0.138` dev-set floor and `<= 5` lifetime cap for Stage-1 submission locks (`lock-submission`).

## Exact Reproduction Commands

### 1. Run Unit, Integration & Property Tests (`P1..P4`)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt PyYAML==6.0.3 pytest hypothesis
.venv/bin/pytest tests -v
```

### 2. Cleanroom Container Smoke, MCP & Cancel Check (`kit check`)

From an official [google-research/ple](https://github.com/google-research/ple) checkout (`<path-to-ple>`) with out-of-repo proxy credentials (`<path-to-env-file>`):

```bash
uv run --directory <path-to-ple> python -m kit check --rebuild --cancel-test \
  --env-file <path-to-env-file> <path-to-repo>
```

### 3. External-Worktree Paired Dev-Set Evaluation (`--no-export`)

```bash
python3 scripts/ple_dev.py run \
  --repo <path-to-repo> \
  --ple-root <path-to-ple> \
  --env-file <path-to-env-file> \
  --model-api google-cloud/glm-5.2 \
  --tasks <task-ids> \
  --out <external-out-dir>/run_candidate \
  --tier LIVE_DOCKER_EVAL
```

### 4. Export Writeup Figures 1–3 & Lock Candidate Submission

```bash
python3 scripts/ple_dev.py export-writeup \
  --runs <external-out-dir>/run_baseline <external-out-dir>/run_candidate \
  --baseline-run <external-out-dir>/run_baseline \
  --out-dir <external-out-dir>/figures \
  --tier LIVE_DOCKER_EVAL

python3 scripts/ple_dev.py lock-submission \
  --ledger <external-out-dir>/submission_locks.json \
  --git-rev <commit-sha> \
  --model-api google-cloud/glm-5.2 \
  --mean-score <dev-mean-score> \
  --notes "Stage-1 verified candidate"

python3 scripts/ple_dev.py hygiene --repo <path-to-repo> --ple-root <path-to-ple> --env-file <path-to-env-file>
```
