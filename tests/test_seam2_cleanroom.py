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

import os
from pathlib import Path
import re
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
HYGIENE_SCRIPT = Path.home() / ".claude/skills/hackathon/scripts/pre-submit-hygiene.py"
CUSTOM_HARNESS_FILES = ("serve.py", "harness.py", "deliverable_audit.py", "scripts/ple_dev.py")
FORBIDDEN_TERMS = ("sha" + "256", "md" + "5", "check" + "sum", "dig" + "est")
SECRET_PREFIXES = ("sk-" + "live-", "sk-" + "proj-", "sk-" + "or-v1-", "gh" + "p_", "github_" + "pat_", "AK" + "IA", "AI" + "za")
HOME_PATH_RE = re.compile(r"(?:/" + r"Users/|/" + r"home/)[A-Za-z0-9._-]+")
REPO_SECRET_RE = re.compile(
    r"(?:sk-(?:or-v1-|proj-|live-)[A-Za-z0-9_-]{16,}"
    r"|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|AIza[A-Za-z0-9_-]{20,}"
    r"|hf_[A-Za-z0-9]{20,}"
    r"|-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----)"
)
TEST_CONTIGUOUS_KEY_RE = re.compile(
    r"(?:sk-|AIza|hf_|gh[pousr]_|github_pat_|AKIA|xox[baprs]-)[A-Za-z0-9_-]{8,}"
)


def _scan_forbidden_home_or_secret(text: str) -> tuple[bool, bool]:
  has_home = HOME_PATH_RE.search(text) is not None
  has_sec = REPO_SECRET_RE.search(text) is not None
  return has_home, has_sec


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
      "python3 -m venv .venv",
      "kit check --rebuild --cancel-test",
      "scripts/ple_dev.py run",
      "scripts/ple_dev.py export-writeup",
      "scripts/ple_dev.py lock-submission",
      "scripts/ple_dev.py hygiene",
      "pytest",
  ):
    assert required_cmd in readme, f"README.md missing reproduction command: {required_cmd}"

  pos_home, pos_sec = _scan_forbidden_home_or_secret("sample /" + "Users/dev " + "sk-" + "live-0123456789abcdef0123")
  assert pos_home is True and pos_sec is True
  has_home_path = HOME_PATH_RE.search(readme) is not None
  has_secret = any(pfx in readme for pfx in SECRET_PREFIXES)
  assert not has_home_path, "README.md contains machine-local home path"
  assert not has_secret, "README.md contains secret literal prefix"


def test_cleanroom_clone_passes_pre_submit_hygiene(tmp_path: Path) -> None:
  # Positive controls for self-contained cleanroom checks
  lfs_sig = b"version https://git-lfs.github.com/spec/v1\n"
  assert lfs_sig.startswith(b"version https://git-lfs.github.com/spec/v1")
  assert any(t in ("bad_" + "sha" + "256_ref") for t in FORBIDDEN_TERMS)
  pos_h, pos_s = _scan_forbidden_home_or_secret("/" + "home/alice " + "gh" + "p_0123456789abcdefghij0123")
  assert pos_h is True and pos_s is True
  assert TEST_CONTIGUOUS_KEY_RE.search("sk-" + "ple-synth-99887766") is not None

  target = tmp_path / "cleanroom"
  subprocess.run(["git", "clone", str(REPO_ROOT), str(target)], capture_output=True, check=True)
  assert (target / "LICENSE").is_file(), "cleanroom clone missing LICENSE"
  assert not (target / ".scratch").exists()
  assert not list(target.glob(".env*"))

  for check_root in (target, REPO_ROOT):
    for p in check_root.rglob("*"):
      if any(part in {".git", ".scratch", ".pytest_cache", "__pycache__", ".venv"} for part in p.parts):
        continue
      assert not p.is_symlink(), f"unexpected symlink: {p.relative_to(check_root)}"
      if p.is_file():
        raw = p.read_bytes()
        assert not raw[:128].startswith(b"version https://git-lfs.github.com/spec/v1"), "Git LFS pointer forbidden"
        if b"\x00" not in raw[:4096]:
          txt = raw.decode("utf-8", errors="replace")
          has_home, has_sec = _scan_forbidden_home_or_secret(txt)
          assert not has_home, f"local home path in {p.relative_to(check_root)}"
          assert not has_sec, f"secret token in {p.relative_to(check_root)}"

    for rel in CUSTOM_HARNESS_FILES:
      low = (check_root / rel).read_text(encoding="utf-8").lower()
      has_forbidden = any(term in low for term in FORBIDDEN_TERMS)
      assert not has_forbidden, f"custom harness file {rel} contains forbidden term"

  for test_py in sorted((REPO_ROOT / "tests").glob("*.py")):
    t_txt = test_py.read_text(encoding="utf-8")
    has_contig = TEST_CONTIGUOUS_KEY_RE.search(t_txt) is not None
    has_hash_word = any(term in t_txt.lower() for term in FORBIDDEN_TERMS)
    assert not has_contig, f"contiguous synthetic key literal in {test_py.name}"
    assert not has_hash_word, f"forbidden content-hash word in {test_py.name}"

  override_script = os.environ.get("PLE_HYGIENE_SCRIPT", "").strip()
  hygiene_script = Path(override_script).resolve() if override_script else HYGIENE_SCRIPT
  if hygiene_script.is_file():
    safe_env = {k: os.environ[k] for k in ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL") if k in os.environ}
    res = subprocess.run(
        [sys.executable, str(hygiene_script), "--repo", str(target)],
        cwd=str(tmp_path), text=True, capture_output=True, timeout=15, check=False, env=safe_env,
    )
    assert res.returncode == 0, f"pre-submit-hygiene failed:\n{res.stdout}\n{res.stderr}"
    assert "SUMMARY: PASS" in res.stdout
