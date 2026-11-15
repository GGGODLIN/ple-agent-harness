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

"""Seam 2 cleanroom clone, root README contract, and pre-submit hygiene tests."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
HYGIENE_SCRIPT = Path.home() / ".claude/skills/hackathon/scripts/pre-submit-hygiene.py"
CUSTOM_HARNESS_FILES = ("serve.py", "harness.py", "deliverable_audit.py", "scripts/ple_dev.py")
FORBIDDEN_HASH_TERMS = ("sha256", "md5", "checksum", "digest")


def test_readme_documents_architecture_attributions_and_reproduction() -> None:
  readme_path = REPO_ROOT / "README.md"
  assert readme_path.is_file(), "missing root README.md"
  readme = readme_path.read_text(encoding="utf-8")

  for required_arch in ("serve.py", "harness.py", "deliverable_audit.py", "scripts/ple_dev.py"):
    assert required_arch in readme, f"README.md missing architecture module: {required_arch}"

  for required_attr in (
      "Apache-2.0",
      "Copyright 2026 Google LLC",
      "google-research/ple",
      "taskbridge.py",
      "custom-openai",
      "plan-verify",
  ):
    assert required_attr in readme, f"README.md missing attribution token: {required_attr}"

  for required_cmd in (
      "kit check --rebuild --cancel-test",
      "scripts/ple_dev.py run",
      "scripts/ple_dev.py export-writeup",
      "scripts/ple_dev.py lock-submission",
      "pytest",
  ):
    assert required_cmd in readme, f"README.md missing reproduction command: {required_cmd}"

  users_prefix = "/" + "Users/"
  home_prefix = "/" + "home/"
  assert (users_prefix in f"sample {users_prefix}dev") and (home_prefix in f"sample {home_prefix}dev")
  has_home_path = (users_prefix in readme) or (home_prefix in readme)
  assert not has_home_path, "README.md contains machine-local home path"

  secret_prefixes = ("sk-live-", "sk-proj-", "sk-or-v1-", "ghp_", "github_pat_", "AKIA", "AIza")
  has_secret = any(pfx in readme for pfx in secret_prefixes)
  assert not has_secret, "README.md contains secret literal prefix"


def test_cleanroom_clone_passes_pre_submit_hygiene(tmp_path: Path) -> None:
  assert HYGIENE_SCRIPT.is_file(), "missing pre-submit-hygiene.py script"
  status_res = subprocess.run(
      ["git", "-C", str(REPO_ROOT), "status", "--porcelain"],
      text=True, capture_output=True, check=True,
  )
  is_clean = status_res.stdout.strip() == ""
  if is_clean:
    target = tmp_path / "cleanroom"
    subprocess.run(["git", "clone", str(REPO_ROOT), str(target)], capture_output=True, check=True)
    assert not (target / ".scratch").exists()
    assert not list(target.glob(".env*"))
  else:
    target = REPO_ROOT

  res = subprocess.run(
      [sys.executable, str(HYGIENE_SCRIPT), "--repo", str(target)],
      cwd=str(tmp_path), text=True, capture_output=True, timeout=15, check=False,
  )
  if is_clean:
    assert res.returncode == 0, f"pre-submit-hygiene failed:\n{res.stdout}\n{res.stderr}"
    assert "SUMMARY: PASS" in res.stdout
  else:
    bad = [
        ln for ln in res.stdout.splitlines()
        if ln.startswith("FAIL ") and not ln.startswith(("FAIL [GIT_CLEAN_LOCAL]", "FAIL [GIT_CLEAN_AND_PUSHED]"))
    ]
    assert not bad, f"pre-submit-hygiene failed:\n{res.stdout}\n{res.stderr}"
    for chk in ("LICENSE_PRESENT", "NO_TRACKED_SCRATCH", "NO_LOCAL_HOME_PATHS", "NO_SECRET_LITERALS", "PORTAL_LINKS_ABSOLUTE"):
      assert f"PASS [{chk}]" in res.stdout, f"missing PASS [{chk}]:\n{res.stdout}"

  for p in target.rglob("*"):
    if any(part in {".git", ".scratch", ".pytest_cache", "__pycache__"} for part in p.parts):
      continue
    assert not p.is_symlink(), f"unexpected symlink: {p.relative_to(target)}"
    if p.is_file():
      head = p.read_bytes()[:128]
      assert not head.startswith(b"version https://git-lfs.github.com/spec/v1"), "Git LFS pointer forbidden"

  for rel in CUSTOM_HARNESS_FILES:
    low = (target / rel).read_text(encoding="utf-8").lower()
    has_hash = any(term in low for term in FORBIDDEN_HASH_TERMS)
    assert not has_hash, f"custom harness file {rel} contains forbidden hash term"
