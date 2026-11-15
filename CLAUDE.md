# ple-agent-harness

Competition entry repository for **Google — Agent Harness on Physical-Engineering's Last Exam (PLE)** (`physical-engineerings-last-exam` on Kaggle).

## Hard Competition & Local Rules

- **No API keys or secrets in repository**: `submission.yaml` and all tracked files must never contain API keys, tokens, or machine-local home-directory paths. Keep local proxy/judge environment files strictly outside this repository.
- **Fair play**: Never hard-code task answers, never detect task IDs to branch on them, never read `artifacts/` or public dev-set graders at build or runtime, and never bypass the evaluation egress proxy.
- **Artifacts contract**: Official `artifacts/` is exported exclusively by `google-research/ple`'s `uv run python eval/run.py` and verified via `uv run python -m kit artifacts` and `uv run python -m kit check` (no Git LFS, no symlinks, `<= 512 MiB`, `<= 10,000` files, repo + `.git` history `<= 1 GiB`). Note: gitignore rules must never ignore `artifacts/`.
- **Custom harness state**: Do not compute, store, or compare content hashes (`sha256` / `md5` / `checksum` / `digest`) in our own custom harness scripts or state files; official `kit/artifacts.py` `manifest.json` is generated untouched by the official evaluator CLI.
- **Secret-free test assertions**: In tests verifying redaction or absence of secrets, bind a boolean (`leaked = fake_secret in output; assert not leaked, "secret leaked"`) — never use `assertNotIn` or echo raw output on failure.
