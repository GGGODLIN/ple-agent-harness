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

"""Task-side deliverable audit, stdlib OOXML <v> patcher, and optimization classifier."""

from __future__ import annotations

import contextlib
import json
import math
import os
from pathlib import Path
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any
import xml.etree.ElementTree as ET
import zipfile

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

EXCEL_ERRORS = frozenset({"#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#NUM!", "#N/A", "#NULL!"})
SKIP_DIRS = frozenset({".git", "__pycache__", ".venv", "node_modules", ".pytest_cache", ".mypy_cache"})

_PARAM_RE = re.compile(
  r"\b(?:siz(?:e|ing)|select(?:ion)?|parameters?|diameter|thickness|section|schedule|"
  r"routing|layout|capacity|configuration|stiffeners?|beams?|pipes?|vessels?|tubes?|"
  r"heat\s+exchanger|gains?|tolerances?|dimensions?)\b",
  re.IGNORECASE,
)
_OBJ_RE = re.compile(
  r"\b(?:minimi[sz]e|maximi[sz]e|optimal|optimi[sz](?:e|ation)|"
  r"lowest\s+(?:total\s+|capital\s+|life[-\s]?cycle\s+)?cost|life[-\s]?cycle\s+cost|"
  r"minimum\s+(?:weight|mass|cost|volume|area|loss|power)|least[-\s]?cost|pareto|paper_score)\b",
  re.IGNORECASE,
)
_QUAL_ONLY_RE = re.compile(
  r"\bqualitative\s+(?:engineering\s+)?(?:memo|memorandum|review|assessment|analysis|report)\b",
  re.IGNORECASE,
)
_CELL_PART_RE = re.compile(r"^(\$?)([A-Za-z]{1,3})(\$?)([1-9]\d*)$")
_NUM_SCAN_RE = re.compile(r"(?<![A-Za-z0-9_])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?")
_SCRATCH_PATH_RE = re.compile(r"^/(?:private/)?tmp/\.ple_work_[^/]+(?:/|$)")

for _pfx, _uri in (
  ("", MAIN_NS),
  ("r", REL_NS),
  ("mc", "http://schemas.openxmlformats.org/markup-compatibility/2006"),
  ("x14ac", "http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac"),
  ("xr", "http://schemas.microsoft.com/office/spreadsheetml/2014/revision"),
  ("xr2", "http://schemas.microsoft.com/office/spreadsheetml/2015/revision2"),
  ("xr3", "http://schemas.microsoft.com/office/spreadsheetml/2016/revision3"),
):
  ET.register_namespace(_pfx, _uri)


def is_quantitative_optimization_task(instruction: str) -> bool:
  """Returns True when `instruction` specifies adjustable design parameters and an optimization objective."""
  text = (instruction or "").strip()
  if len(text) < 25 or _QUAL_ONLY_RE.search(text):
    return False
  return bool(_PARAM_RE.search(text) and _OBJ_RE.search(text))


def _col_to_idx(col: str) -> int:
  idx = 0
  for ch in col.upper():
    idx = idx * 26 + (ord(ch) - 64)
  return idx


def _idx_to_col(idx: int) -> str:
  out: list[str] = []
  while idx > 0:
    idx, rem = divmod(idx - 1, 26)
    out.append(chr(65 + rem))
  return "".join(reversed(out))


def _norm_coord(coord: str) -> str:
  m = _CELL_PART_RE.match(coord.strip())
  return f"{m.group(2).upper()}{int(m.group(4))}" if m else coord.upper().replace("$", "")


def _expand_range_2d(c1: str, c2: str) -> list[list[str]]:
  m1, m2 = _CELL_PART_RE.match(c1), _CELL_PART_RE.match(c2)
  if not m1 or not m2:
    return [[_norm_coord(c1)]]
  col1, row1 = _col_to_idx(m1.group(2)), int(m1.group(4))
  col2, row2 = _col_to_idx(m2.group(2)), int(m2.group(4))
  ca, cb = min(col1, col2), max(col1, col2)
  ra, rb = min(row1, row2), max(row1, row2)
  if (rb - ra + 1) * (cb - ca + 1) > 10_000:
    return []
  return [[f"{_idx_to_col(c)}{r}" for c in range(ca, cb + 1)] for r in range(ra, rb + 1)]


def _tokenize_expr(expr: str, default_sheet: str) -> list[tuple[str, Any]]:
  s = expr.strip().lstrip("=")
  n = len(s)
  i = 0
  toks: list[tuple[str, Any]] = []
  while i < n:
    ch = s[i]
    if ch.isspace():
      i += 1
      continue
    if ch == "#":
      matched_err = next((e for e in EXCEL_ERRORS if s[i:].upper().startswith(e)), None)
      if matched_err:
        toks.append(("ERR", matched_err))
        i += len(matched_err)
        continue
      toks.append(("ERR", "#VALUE!"))
      break
    if ch == '"':
      i += 1
      buf: list[str] = []
      while i < n:
        if s[i] == '"':
          if i + 1 < n and s[i + 1] == '"':
            buf.append('"')
            i += 2
            continue
          i += 1
          break
        buf.append(s[i])
        i += 1
      toks.append(("STR", "".join(buf)))
      continue
    if ch == "'":
      i += 1
      sh_buf: list[str] = []
      while i < n:
        if s[i] == "'":
          if i + 1 < n and s[i + 1] == "'":
            sh_buf.append("'")
            i += 2
            continue
          i += 1
          break
        sh_buf.append(s[i])
        i += 1
      if i < n and s[i] == "!":
        i += 1
        sh_name = "".join(sh_buf)
        m_ref = re.match(r"(\$?[A-Za-z]{1,3}\$?[1-9]\d*)(?::(\$?[A-Za-z]{1,3}\$?[1-9]\d*))?", s[i:])
        if m_ref:
          i += m_ref.end()
          if m_ref.group(2):
            toks.append(("RANGE", (sh_name, m_ref.group(1), m_ref.group(2))))
          else:
            toks.append(("CELL", (sh_name, _norm_coord(m_ref.group(1)))))
          continue
      toks.append(("ERR", "#REF!"))
      continue
    m_num = re.match(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", s[i:])
    if m_num and (ch.isdigit() or ch == "."):
      toks.append(("NUM", float(m_num.group(0))))
      i += m_num.end()
      continue
    if s[i : i + 2] in ("<=", ">=", "<>"):
      toks.append(("OP", s[i : i + 2]))
      i += 2
      continue
    if ch in "+-*/^&=<>(),%":
      toks.append(("OP", ch))
      i += 1
      continue
    m_sh = re.match(r"([A-Za-z_][A-Za-z0-9_.]*)!", s[i:])
    if m_sh:
      sh_name = m_sh.group(1)
      i += m_sh.end()
      m_ref = re.match(r"(\$?[A-Za-z]{1,3}\$?[1-9]\d*)(?::(\$?[A-Za-z]{1,3}\$?[1-9]\d*))?", s[i:])
      if m_ref:
        i += m_ref.end()
        if m_ref.group(2):
          toks.append(("RANGE", (sh_name, m_ref.group(1), m_ref.group(2))))
        else:
          toks.append(("CELL", (sh_name, _norm_coord(m_ref.group(1)))))
        continue
      toks.append(("ERR", "#REF!"))
      continue
    m_id = re.match(r"\$?[A-Za-z_][A-Za-z0-9_.$]*", s[i:])
    if m_id:
      ident = m_id.group(0)
      j = i + m_id.end()
      k = j
      while k < n and s[k].isspace():
        k += 1
      if k < n and s[k] == "(":
        fn_name = ident.upper()
        if fn_name.startswith("_XLFN."):
          fn_name = fn_name[6:]
        toks.append(("FUNC", fn_name))
        i = j
        continue
      if ident.upper() in ("TRUE", "FALSE"):
        toks.append(("BOOL", ident.upper() == "TRUE"))
        i = j
        continue
      if _CELL_PART_RE.match(ident):
        if j < n and s[j] == ":":
          m_c2 = re.match(r"\$?[A-Za-z]{1,3}\$?[1-9]\d*", s[j + 1 :])
          if m_c2:
            toks.append(("RANGE", (default_sheet, ident, m_c2.group(0))))
            i = j + 1 + m_c2.end()
            continue
        toks.append(("CELL", (default_sheet, _norm_coord(ident))))
        i = j
        continue
      toks.append(("ERR", "#NAME?"))
      i = j
      continue
    toks.append(("ERR", "#VALUE!"))
    break
  return toks


def _to_num(v: Any) -> float | str:
  if isinstance(v, str) and v in EXCEL_ERRORS:
    return v
  if v is None:
    return 0.0
  if isinstance(v, bool):
    return 1.0 if v else 0.0
  if isinstance(v, (int, float)):
    return float(v)
  try:
    return float(str(v).strip())
  except ValueError:
    return "#VALUE!"


def _to_bool(v: Any) -> bool | str:
  if isinstance(v, str) and v in EXCEL_ERRORS:
    return v
  if isinstance(v, bool):
    return v
  if v is None:
    return False
  if isinstance(v, (int, float)):
    return v != 0
  u = str(v).strip().upper()
  if u in ("TRUE", "FALSE"):
    return u == "TRUE"
  return "#VALUE!"


def _flatten_nums(val: Any) -> list[float] | str:
  if isinstance(val, list):
    out: list[float] = []
    for row in val:
      sub = _flatten_nums(row)
      if isinstance(sub, str):
        return sub
      out.extend(sub)
    return out
  if isinstance(val, str) and val in EXCEL_ERRORS:
    return val
  if isinstance(val, (int, float)) and not isinstance(val, bool):
    return [float(val)]
  return []


def _cmp_key(v: Any) -> tuple[int, Any]:
  if isinstance(v, bool):
    return (2, v)
  if isinstance(v, str):
    return (1, v.lower())
  if isinstance(v, (int, float)):
    return (0, float(v))
  return (1, str(v).lower())


class _FormulaEvaluator:
  """Recursive-descent evaluator over tokenized OOXML cell expressions."""

  def __init__(self, toks: list[tuple[str, Any]], get_cell: Any, known_sheets: set[str]):
    self.toks = toks
    self.pos = 0
    self.get_cell = get_cell
    self.known_sheets = known_sheets

  def _peek(self) -> tuple[str, Any] | None:
    return self.toks[self.pos] if self.pos < len(self.toks) else None

  def _eat(self) -> tuple[str, Any]:
    t = self.toks[self.pos]
    self.pos += 1
    return t

  def parse(self) -> Any:
    if not self.toks:
      return 0.0
    val = self._cmp()
    if isinstance(val, list):
      return val[0][0] if val and val[0] else 0.0
    return val

  def _cmp(self) -> Any:
    left = self._concat()
    while (p := self._peek()) and p[0] == "OP" and p[1] in ("=", "<>", "<", "<=", ">", ">="):
      op = self._eat()[1]
      right = self._concat()
      if isinstance(left, list):
        left = left[0][0] if left and left[0] else None
      if isinstance(right, list):
        right = right[0][0] if right and right[0] else None
      if isinstance(left, str) and left in EXCEL_ERRORS:
        return left
      if isinstance(right, str) and right in EXCEL_ERRORS:
        return right
      if left is None and right is None:
        lv_raw: Any = 0.0
        rv_raw: Any = 0.0
      elif left is None:
        lv_raw = "" if isinstance(right, str) else (False if isinstance(right, bool) else 0.0)
        rv_raw = right
      elif right is None:
        lv_raw = left
        rv_raw = "" if isinstance(left, str) else (False if isinstance(left, bool) else 0.0)
      else:
        lv_raw, rv_raw = left, right
      lk, rk = _cmp_key(lv_raw), _cmp_key(rv_raw)
      if op == "=":
        left = lk == rk
      elif op == "<>":
        left = lk != rk
      elif op == "<":
        left = lk < rk
      elif op == "<=":
        left = lk <= rk
      elif op == ">":
        left = lk > rk
      else:
        left = lk >= rk
    return left

  def _concat(self) -> Any:
    left = self._add()
    while (p := self._peek()) and p == ("OP", "&"):
      self._eat()
      right = self._add()
      if isinstance(left, str) and left in EXCEL_ERRORS:
        return left
      if isinstance(right, str) and right in EXCEL_ERRORS:
        return right
      left = ("" if left is None else str(left)) + ("" if right is None else str(right))
    return left

  def _add(self) -> Any:
    left = self._mul()
    while (p := self._peek()) and p[0] == "OP" and p[1] in ("+", "-"):
      op = self._eat()[1]
      right = self._mul()
      ln, rn = _to_num(left), _to_num(right)
      if isinstance(ln, str):
        return ln
      if isinstance(rn, str):
        return rn
      left = ln + rn if op == "+" else ln - rn
    return left

  def _mul(self) -> Any:
    left = self._pow()
    while (p := self._peek()) and p[0] == "OP" and p[1] in ("*", "/"):
      op = self._eat()[1]
      right = self._pow()
      ln, rn = _to_num(left), _to_num(right)
      if isinstance(ln, str):
        return ln
      if isinstance(rn, str):
        return rn
      if op == "/":
        if rn == 0.0:
          return "#DIV/0!"
        left = ln / rn
      else:
        left = ln * rn
    return left

  def _pow(self) -> Any:
    left = self._unary()
    while (p := self._peek()) and p == ("OP", "^"):
      self._eat()
      right = self._unary()
      ln, rn = _to_num(left), _to_num(right)
      if isinstance(ln, str):
        return ln
      if isinstance(rn, str):
        return rn
      try:
        left = math.pow(ln, rn)
      except (ValueError, OverflowError):
        return "#NUM!"
    return left

  def _unary(self) -> Any:
    p = self._peek()
    if p and p[0] == "OP" and p[1] in ("+", "-"):
      op = self._eat()[1]
      v = _to_num(self._unary())
      if isinstance(v, str):
        return v
      return -v if op == "-" else v
    val = self._primary()
    while (p2 := self._peek()) and p2 == ("OP", "%"):
      self._eat()
      vn = _to_num(val)
      if isinstance(vn, str):
        return vn
      val = vn / 100.0
    return val

  def _skip_arg_tokens(self) -> list[tuple[str, Any]]:
    depth = 0
    sub: list[tuple[str, Any]] = []
    while self.pos < len(self.toks):
      t = self.toks[self.pos]
      if t == ("OP", "("):
        depth += 1
      elif t == ("OP", ")"):
        if depth == 0:
          break
        depth -= 1
      elif t == ("OP", ",") and depth == 0:
        break
      sub.append(t)
      self.pos += 1
    return sub

  def _eval_sub(self, sub_toks: list[tuple[str, Any]]) -> Any:
    return _FormulaEvaluator(sub_toks, self.get_cell, self.known_sheets)._cmp()

  def _primary(self) -> Any:
    t = self._peek()
    if t is None:
      return "#VALUE!"
    kind, val = self._eat()
    if kind in ("NUM", "STR", "BOOL", "ERR"):
      return val
    if kind == "CELL":
      sh, coord = val
      if sh not in self.known_sheets:
        return "#REF!"
      return self.get_cell(sh, coord)
    if kind == "RANGE":
      sh, c1, c2 = val
      if sh not in self.known_sheets:
        return "#REF!"
      grid = _expand_range_2d(c1, c2)
      return [[self.get_cell(sh, c) for c in row] for row in grid]
    if kind == "OP" and val == "(":
      inner = self._cmp()
      if self._peek() == ("OP", ")"):
        self._eat()
      return inner
    if kind == "FUNC":
      if self._peek() == ("OP", "("):
        self._eat()
      raw_args: list[list[tuple[str, Any]]] = []
      if self._peek() != ("OP", ")"):
        while True:
          raw_args.append(self._skip_arg_tokens())
          if self._peek() == ("OP", ","):
            self._eat()
            continue
          break
      if self._peek() == ("OP", ")"):
        self._eat()
      return self._call_func(val, raw_args)
    return "#VALUE!"

  def _call_func(self, fn: str, raw_args: list[list[tuple[str, Any]]]) -> Any:
    if fn == "IF":
      if not raw_args:
        return "#VALUE!"
      cond = _to_bool(self._eval_sub(raw_args[0]))
      if isinstance(cond, str):
        return cond
      if cond:
        return self._eval_sub(raw_args[1]) if len(raw_args) >= 2 else True
      return self._eval_sub(raw_args[2]) if len(raw_args) >= 3 else False
    if fn == "IFERROR":
      if len(raw_args) < 2:
        return "#VALUE!"
      v = self._eval_sub(raw_args[0])
      if isinstance(v, str) and v in EXCEL_ERRORS:
        return self._eval_sub(raw_args[1])
      return v
    args = [self._eval_sub(a) for a in raw_args]
    for a in args:
      if isinstance(a, str) and a in EXCEL_ERRORS:
        return a
    if fn in ("TRUE", "FALSE"):
      return fn == "TRUE"
    if fn in ("SUM", "AVERAGE", "MIN", "MAX", "COUNT"):
      nums: list[float] = []
      for a in args:
        if isinstance(a, list):
          sub = _flatten_nums(a)
          if isinstance(sub, str):
            return sub
          nums.extend(sub)
        elif a is not None:
          na = _to_num(a)
          if isinstance(na, str):
            return na
          nums.append(na)
      if fn == "SUM":
        return sum(nums)
      if fn == "COUNT":
        return float(len(nums))
      if fn == "AVERAGE":
        return sum(nums) / len(nums) if nums else "#DIV/0!"
      if fn == "MIN":
        return min(nums) if nums else 0.0
      return max(nums) if nums else 0.0
    if fn in ("AND", "OR"):
      bvals: list[bool] = []
      for a in args:
        items = [x for row in a for x in row] if isinstance(a, list) else [a]
        for it in items:
          if it is None:
            continue
          b = _to_bool(it)
          if isinstance(b, str):
            return b
          bvals.append(b)
      return all(bvals) if fn == "AND" else any(bvals)
    if fn == "NOT":
      b = _to_bool(args[0] if args else False)
      return b if isinstance(b, str) else (not b)
    if fn == "ROUND":
      if not args:
        return "#VALUE!"
      x = _to_num(args[0])
      nd = _to_num(args[1]) if len(args) > 1 else 0.0
      if isinstance(x, str):
        return x
      if isinstance(nd, str):
        return nd
      return round(x, int(nd))
    if fn in ("ABS", "SQRT"):
      if not args:
        return "#VALUE!"
      x = _to_num(args[0])
      if isinstance(x, str):
        return x
      if fn == "ABS":
        return abs(x)
      return math.sqrt(x) if x >= 0 else "#NUM!"
    return "#NAME?"


def _read_shared_strings(zf: zipfile.ZipFile) -> list[str]:
  if "xl/sharedStrings.xml" not in zf.namelist():
    return []
  root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
  return ["".join(t.text or "" for t in si.iter(f"{{{MAIN_NS}}}t")) for si in root.findall(f"{{{MAIN_NS}}}si")]


def _sheet_targets(zf: zipfile.ZipFile) -> list[tuple[str, str]]:
  wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
  rels_map: dict[str, str] = {}
  if "xl/_rels/workbook.xml.rels" in zf.namelist():
    rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    for rel in rels_root:
      rid, tgt = rel.attrib.get("Id", ""), rel.attrib.get("Target", "")
      if rid and tgt:
        arc = tgt.lstrip("/") if tgt.startswith("/") else (tgt if tgt.startswith("xl/") else posixpath.normpath(posixpath.join("xl", tgt)))
        rels_map[rid] = arc
  out: list[tuple[str, str]] = []
  for sh in wb_root.iter(f"{{{MAIN_NS}}}sheet"):
    name = sh.attrib.get("name", "")
    rid = sh.attrib.get(f"{{{REL_NS}}}id") or sh.attrib.get("id", "")
    arc = rels_map.get(rid, "")
    if name and arc and arc in zf.namelist():
      out.append((name, arc))
  return out


def _decode_scalar(c_t: str, raw_v: str | None, inline_s: str | None, shared: list[str]) -> Any:
  if c_t == "inlineStr":
    return inline_s or ""
  if raw_v is None or raw_v == "":
    return None
  if c_t == "s":
    idx = int(raw_v)
    return shared[idx] if 0 <= idx < len(shared) else ""
  if c_t == "str" or c_t == "e":
    return raw_v
  if c_t == "b":
    return raw_v.strip() in ("1", "true", "TRUE")
  try:
    fv = float(raw_v)
    return int(fv) if fv.is_integer() and "." not in raw_v and "e" not in raw_v.lower() else fv
  except ValueError:
    return raw_v


def _parse_cell_xml(c_el: ET.Element, shared: list[str]) -> tuple[str, dict[str, Any]] | None:
  coord = _norm_coord(c_el.attrib.get("r", ""))
  if not coord:
    return None
  c_t = c_el.attrib.get("t", "")
  f_el = c_el.find(f"{{{MAIN_NS}}}f")
  v_el = c_el.find(f"{{{MAIN_NS}}}v")
  is_el = c_el.find(f"{{{MAIN_NS}}}is")
  f_txt = (f_el.text or "").strip() if f_el is not None else None
  raw_v = v_el.text if v_el is not None else None
  inline_s = "".join(t.text or "" for t in is_el.iter(f"{{{MAIN_NS}}}t")) if is_el is not None else None
  return coord, {"f": f_txt, "v": raw_v, "t": c_t, "val": _decode_scalar(c_t, raw_v, inline_s, shared)}


def _extract_xlsx_state(xlsx_path: Path) -> dict[str, Any]:
  if not zipfile.is_zipfile(xlsx_path):
    return {}
  with zipfile.ZipFile(xlsx_path, "r") as zf:
    if "xl/workbook.xml" not in zf.namelist():
      return {}
    shared = _read_shared_strings(zf)
    sheets_out: dict[str, dict[str, Any]] = {}
    for sh_name, arc in _sheet_targets(zf):
      root = ET.fromstring(zf.read(arc))
      cells_out: dict[str, Any] = {}
      for c_el in root.iter(f"{{{MAIN_NS}}}c"):
        parsed = _parse_cell_xml(c_el, shared)
        if parsed is not None:
          cells_out[parsed[0]] = parsed[1]
      sheets_out[sh_name] = cells_out
    return {"sheets": sheets_out}


def _active_extra_roots(workdir: Path, extra_roots: list[Path] | None) -> list[Path]:
  w_res = workdir.resolve()
  if extra_roots is None:
    fs_dir = Path("/filesystem")
    raw_roots = [fs_dir] if fs_dir.is_dir() else []
  else:
    raw_roots = [Path(r) for r in extra_roots]
  seen: set[Path] = {w_res}
  out: list[Path] = []
  for cand in raw_roots:
    rp = cand.resolve()
    if rp not in seen:
      seen.add(rp)
      out.append(rp)
  return out


def _scan_files(workdir: Path, state_dir: Path, *, absolute_keys: bool = False) -> dict[str, list[int]]:
  out: dict[str, list[int]] = {}
  if not workdir.is_dir():
    return out
  state_res = state_dir.resolve()
  for root_s, dirs, files in os.walk(workdir):
    root_p = Path(root_s)
    dirs[:] = [
      d for d in dirs
      if d not in SKIP_DIRS and not d.startswith(".ple_") and (root_p / d).resolve() != state_res
    ]
    for fn in files:
      if fn.startswith("._ple_stage_"):
        continue
      full = root_p / fn
      try:
        st_info = full.stat()
      except OSError:
        continue
      key = full.resolve().as_posix() if absolute_keys else full.relative_to(workdir).as_posix()
      out[key] = [int(st_info.st_size), int(st_info.st_mtime_ns)]
  return out


def _scan_all_files(workdir: Path, state_dir: Path, extra_roots: list[Path] | None) -> dict[str, list[int]]:
  merged = _scan_files(workdir, state_dir, absolute_keys=False)
  for eroot in _active_extra_roots(workdir, extra_roots):
    merged.update(_scan_files(eroot, state_dir, absolute_keys=True))
  return merged


def snapshot_workdir(
  workdir: Path, state_dir: Path, extra_roots: list[Path] | None = None
) -> dict[str, Any]:
  """Records pre-mutation file metadata and existing `.xlsx` `<v>` baselines in `state_dir/init.json`."""
  state_dir.mkdir(parents=True, exist_ok=True)
  init_file = state_dir / "init.json"
  if init_file.is_file():
    with contextlib.suppress(OSError, ValueError):
      loaded = json.loads(init_file.read_text(encoding="utf-8"))
      if isinstance(loaded, dict):
        return loaded
  files = _scan_all_files(workdir, state_dir, extra_roots)
  xlsx_base: dict[str, Any] = {}
  for rel in files:
    if rel.lower().endswith(".xlsx"):
      fpath = Path(rel) if rel.startswith("/") else (workdir / rel)
      try:
        xlsx_base[rel] = _extract_xlsx_state(fpath)
      except (zipfile.BadZipFile, ET.ParseError, KeyError, ValueError, OSError):
        xlsx_base[rel] = {}
  data = {"files": files, "xlsx": xlsx_base}
  init_file.write_text(json.dumps(data), encoding="utf-8")
  return data


def is_workdir_dirty(
  workdir: Path, state_dir: Path, extra_roots: list[Path] | None = None
) -> bool:
  """Returns True when any deliverable or `facts.json` exists or changed across active roots."""
  if (state_dir / "facts.json").is_file() or (workdir / "facts.json").is_file():
    return True
  init_file = state_dir / "init.json"
  cur = _scan_all_files(workdir, state_dir, extra_roots)
  if not init_file.is_file():
    return bool(cur)
  try:
    init_obj = json.loads(init_file.read_text(encoding="utf-8"))
    base = init_obj.get("files", {}) if isinstance(init_obj, dict) else {}
  except (OSError, ValueError):
    return True
  return cur != base


def _referenced_cells(expr: str, default_sheet: str, known_sheets: set[str]) -> list[tuple[str, str]] | None:
  toks = _tokenize_expr(expr, default_sheet)
  refs: list[tuple[str, str]] = []
  for kind, val in toks:
    if kind == "CELL":
      refs.append(val)
    elif kind == "RANGE":
      sh, c1, c2 = val
      if sh not in known_sheets:
        return None
      grid = _expand_range_2d(c1, c2)
      if not grid:
        return None
      for row in grid:
        for c in row:
          refs.append((sh, c))
  return refs


def _set_cell_cached_xml(c_el: ET.Element, res: Any, raw_override: tuple[str, str] | None = None) -> Any:
  for child in list(c_el):
    if child.tag == f"{{{MAIN_NS}}}is":
      c_el.remove(child)
  v_el = c_el.find(f"{{{MAIN_NS}}}v")
  if v_el is None:
    v_el = ET.Element(f"{{{MAIN_NS}}}v")
    children = list(c_el)
    f_idx = next((idx for idx, ch in enumerate(children) if ch.tag == f"{{{MAIN_NS}}}f"), -1)
    c_el.insert(f_idx + 1 if f_idx >= 0 else len(children), v_el)

  if raw_override is not None:
    b_t, b_v = raw_override
    if b_t in ("", "n"):
      c_el.attrib.pop("t", None)
    else:
      c_el.set("t", b_t)
    v_el.text = b_v
    return res

  if isinstance(res, str) and res in EXCEL_ERRORS:
    c_el.set("t", "e")
    v_el.text = res
    return res
  if isinstance(res, bool):
    c_el.set("t", "b")
    v_el.text = "1" if res else "0"
    return res
  if isinstance(res, (int, float)):
    fv = float(res)
    if math.isnan(fv) or math.isinf(fv):
      c_el.set("t", "e")
      v_el.text = "#NUM!"
      return "#NUM!"
    c_el.attrib.pop("t", None)
    v_el.text = str(int(fv)) if fv.is_integer() and abs(fv) < 1e15 else repr(round(fv, 12))
    return int(fv) if fv.is_integer() and abs(fv) < 1e15 else round(fv, 12)
  sval = "" if res is None else str(res)
  c_el.set("t", "str")
  v_el.text = sval
  return sval


def _patch_xlsx_file(
  xlsx_path: Path, rel_path: str, baseline_book: dict[str, Any] | None
) -> tuple[list[str], list[float], str]:
  findings: list[str] = []
  nums: list[float] = []
  texts: list[str] = []

  if not zipfile.is_zipfile(xlsx_path):
    return [f"{rel_path}: invalid xlsx archive"], nums, ""

  if shutil.which("soffice"):
    stage_so = xlsx_path.parent / f"._ple_stage_soffice_{os.getpid()}"
    try:
      with tempfile.TemporaryDirectory() as tmp_d:
        proc = subprocess.run(
          ["soffice", "--headless", "--convert-to", "xlsx", "--outdir", tmp_d, str(xlsx_path)],
          capture_output=True,
          timeout=30,
        )
        cand = Path(tmp_d) / xlsx_path.name
        if proc.returncode == 0 and cand.is_file() and zipfile.is_zipfile(cand):
          shutil.copyfile(cand, stage_so)
          os.replace(stage_so, xlsx_path)
    except (subprocess.SubprocessError, OSError):
      pass
    finally:
      if stage_so.exists():
        with contextlib.suppress(OSError):
          stage_so.unlink()

  stage_path = xlsx_path.parent / f"._ple_stage_audit_{os.getpid()}"
  try:
    with zipfile.ZipFile(xlsx_path, "r") as zin:
      if "xl/workbook.xml" not in zin.namelist():
        return [f"{rel_path}: missing xl/workbook.xml"], nums, ""
      archive_bytes = {name: zin.read(name) for name in zin.namelist()}
      shared = _read_shared_strings(zin)
      targets = _sheet_targets(zin)

    wb_root = ET.fromstring(archive_bytes["xl/workbook.xml"])
    calc_pr = wb_root.find(f"{{{MAIN_NS}}}calcPr")
    if calc_pr is None:
      calc_pr = ET.SubElement(wb_root, f"{{{MAIN_NS}}}calcPr")
    calc_pr.set("fullCalcOnLoad", "1")
    archive_bytes["xl/workbook.xml"] = ET.tostring(wb_root, encoding="utf-8", xml_declaration=True)

    known_sheets = {name for name, _ in targets}
    sheet_trees: dict[str, tuple[str, ET.Element]] = {}
    cells: dict[tuple[str, str], dict[str, Any]] = {}

    for sh_name, arc in targets:
      root = ET.fromstring(archive_bytes[arc])
      sheet_trees[sh_name] = (arc, root)
      for c_el in root.iter(f"{{{MAIN_NS}}}c"):
        parsed = _parse_cell_xml(c_el, shared)
        if parsed is not None:
          coord, info = parsed
          cells[(sh_name, coord)] = {"el": c_el, **info, "ready": info["f"] is None}

    base_sheets = (baseline_book or {}).get("sheets", {})
    dirty_memo: dict[tuple[str, str], bool] = {}
    dirty_visiting: set[tuple[str, str]] = set()

    def _is_cell_dirty(sh: str, coord: str) -> bool:
      key = (sh, coord)
      if key in dirty_memo:
        return dirty_memo[key]
      if key in dirty_visiting:
        return True
      dirty_visiting.add(key)
      try:
        b_cell = base_sheets.get(sh, {}).get(coord)
        cur_cell = cells.get(key)
        if b_cell is None and cur_cell is None:
          res_d = False
        elif b_cell is None or cur_cell is None:
          res_d = True
        elif cur_cell["f"] is None:
          res_d = b_cell.get("f") is not None or cur_cell["val"] != b_cell.get("val")
        else:
          bf = b_cell.get("f")
          if bf is None or cur_cell["f"].strip().lstrip("=") != bf.strip().lstrip("="):
            res_d = True
          else:
            refs = _referenced_cells(cur_cell["f"], sh, known_sheets)
            res_d = True if refs is None else any(_is_cell_dirty(rsh, rc) for rsh, rc in refs)
        dirty_memo[key] = res_d
        return res_d
      finally:
        dirty_visiting.discard(key)

    eval_visiting: set[tuple[str, str]] = set()

    def _eval_cell(sh: str, coord: str) -> Any:
      key = (sh, coord)
      info = cells.get(key)
      if info is None:
        return None
      if info["ready"]:
        return info["val"]
      if key in eval_visiting:
        return "#REF!"
      eval_visiting.add(key)
      try:
        f_expr = info["f"]
        assert f_expr is not None
        if not _is_cell_dirty(sh, coord):
          if info["v"] not in (None, ""):
            info["ready"] = True
            return info["val"]
          b_cell = base_sheets.get(sh, {}).get(coord, {})
          if b_cell.get("v") not in (None, ""):
            b_t = b_cell.get("t") or ""
            b_val = b_cell.get("val")
            override = ("str", str(b_val)) if b_t == "s" else (b_t, str(b_cell["v"]))
            info["val"] = _set_cell_cached_xml(info["el"], b_val, raw_override=override)
            info["ready"] = True
            return info["val"]
        toks = _tokenize_expr(f_expr, sh)
        computed = _FormulaEvaluator(toks, _eval_cell, known_sheets).parse()
        info["val"] = _set_cell_cached_xml(info["el"], computed)
        info["ready"] = True
        return info["val"]
      finally:
        eval_visiting.discard(key)

    for sh_name, coord in list(cells.keys()):
      val = _eval_cell(sh_name, coord)
      if isinstance(val, str) and val in EXCEL_ERRORS:
        findings.append(f"{rel_path}!{sh_name}!{coord}: formula error {val}")
      elif isinstance(val, (int, float)) and not isinstance(val, bool):
        nums.append(float(val))
      elif isinstance(val, str) and val:
        texts.append(val)
        nums.extend(_extract_nums_from_text(val))

    for sh_name, (arc, root) in sheet_trees.items():
      archive_bytes[arc] = ET.tostring(root, encoding="utf-8", xml_declaration=True)

    with zipfile.ZipFile(stage_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
      for name, raw in archive_bytes.items():
        zout.writestr(name, raw)
    os.replace(stage_path, xlsx_path)
  except (zipfile.BadZipFile, ET.ParseError, KeyError, ValueError, RecursionError, OSError) as exc:
    if stage_path.exists():
      with contextlib.suppress(OSError):
        stage_path.unlink()
    return [f"{rel_path}: xlsx audit error ({type(exc).__name__})"], nums, ""
  return findings, nums, "\n".join(texts)


def _extract_nums_from_text(text: str) -> list[float]:
  out: list[float] = []
  for m in _NUM_SCAN_RE.finditer(text):
    try:
      out.append(float(m.group(0).replace(",", "")))
    except ValueError:
      continue
  return out


def audit_workdir(
  workdir: Path,
  state_dir: Path,
  delivered_paths: list[str] | None = None,
  extra_roots: list[Path] | None = None,
) -> dict[str, Any]:
  """Audits produced deliverables, patches `.xlsx` `<v>` caches, and cross-checks `facts.json`."""
  init_file = state_dir / "init.json"
  init_data: dict[str, Any] = {"files": {}, "xlsx": {}}
  if init_file.is_file():
    with contextlib.suppress(OSError, ValueError):
      parsed_init = json.loads(init_file.read_text(encoding="utf-8"))
      if isinstance(parsed_init, dict):
        init_data = parsed_init
  base_files: dict[str, list[int]] = init_data.get("files", {}) if isinstance(init_data.get("files"), dict) else {}
  base_xlsx: dict[str, Any] = init_data.get("xlsx", {}) if isinstance(init_data.get("xlsx"), dict) else {}
  cur_files = _scan_all_files(workdir, state_dir, extra_roots)

  candidate_rels: set[str] = set()
  alias_paths: dict[str, list[str]] = {}
  for rel, meta in cur_files.items():
    if rel not in base_files or base_files[rel] != meta:
      candidate_rels.add(rel)

  w_res = workdir.resolve()
  s_res = state_dir.resolve()
  for p_str in delivered_paths or []:
    norm_raw = posixpath.normpath(p_str)
    if _SCRATCH_PATH_RE.match(norm_raw):
      continue
    p = Path(p_str) if Path(p_str).is_absolute() else (workdir / p_str)
    try:
      p_res = p.resolve()
    except OSError:
      continue
    if p_res == s_res or p_res.is_relative_to(s_res) or _SCRATCH_PATH_RE.match(p_res.as_posix()):
      continue
    try:
      rel = p_res.relative_to(w_res).as_posix()
    except ValueError:
      rel = p_res.as_posix()
    if rel and rel != ".":
      candidate_rels.add(rel)
      alias_paths.setdefault(rel, []).append(p_str)

  findings: list[str] = []
  doc_records: list[tuple[str, list[float], str]] = []
  sizes: dict[str, int] = {}

  for rel in sorted(candidate_rels):
    if rel == "facts.json":
      continue
    fpath = Path(rel) if rel.startswith("/") else (workdir / rel)
    if not fpath.is_file():
      findings.append(f"{rel}: missing deliverable file")
      continue
    try:
      sz = fpath.stat().st_size
    except OSError as exc:
      findings.append(f"{rel}: stat failed ({type(exc).__name__})")
      continue
    if sz == 0:
      findings.append(f"{rel}: empty deliverable (0 bytes)")
      continue
    low = rel.lower()
    final_sz = sz
    if low.endswith(".xlsx"):
      f_errs, nums, txts = _patch_xlsx_file(fpath, rel, base_xlsx.get(rel))
      findings.extend(f_errs)
      doc_records.append((rel, nums, txts))
      with contextlib.suppress(OSError):
        final_sz = fpath.stat().st_size
    elif low.endswith(".docx"):
      if not zipfile.is_zipfile(fpath):
        findings.append(f"{rel}: invalid docx archive")
      else:
        try:
          with zipfile.ZipFile(fpath, "r") as zf:
            if "word/document.xml" not in zf.namelist():
              findings.append(f"{rel}: missing word/document.xml")
            else:
              wroot = ET.fromstring(zf.read("word/document.xml"))
              wtxt = " ".join(t.text or "" for t in wroot.iter(f"{{{WORD_NS}}}t"))
              doc_records.append((rel, _extract_nums_from_text(wtxt), wtxt))
        except (zipfile.BadZipFile, ET.ParseError, KeyError, OSError) as exc:
          findings.append(f"{rel}: docx audit error ({type(exc).__name__})")
    elif low.endswith(".pdf"):
      head_b = fpath.read_bytes()[:1024]
      if b"%PDF-" not in head_b:
        findings.append(f"{rel}: invalid PDF header")
    elif low.endswith(".json"):
      raw_t = fpath.read_text(encoding="utf-8", errors="replace")
      try:
        json.loads(raw_t)
      except ValueError as exc:
        findings.append(f"{rel}: invalid JSON ({exc})")
      if sz <= 2 * 1024 * 1024:
        doc_records.append((rel, _extract_nums_from_text(raw_t), raw_t))
    else:
      if sz <= 2 * 1024 * 1024:
        raw_b = fpath.read_bytes()
        if b"\0" not in raw_b[:4096]:
          raw_t = raw_b.decode("utf-8", errors="replace")
          doc_records.append((rel, _extract_nums_from_text(raw_t), raw_t))
    sizes[str(fpath)] = final_sz
    for orig_p in alias_paths.get(rel, ()):
      sizes[orig_p] = final_sz

  facts_file = state_dir / "facts.json"
  if not facts_file.is_file() and (workdir / "facts.json").is_file():
    facts_file = workdir / "facts.json"
  if facts_file.is_file() and doc_records:
    try:
      raw_facts = json.loads(facts_file.read_text(encoding="utf-8"))
      facts_map = raw_facts.get("facts") if isinstance(raw_facts, dict) and isinstance(raw_facts.get("facts"), dict) else raw_facts
      if isinstance(facts_map, dict):
        for fk, fv in facts_map.items():
          fk_str = str(fk)
          fk_spaced = fk_str.lower().replace("_", " ")
          if isinstance(fv, (int, float)) and not isinstance(fv, bool):
            target_f = float(fv)
            tol = max(1e-6, abs(target_f) * 2e-3) if abs(target_f) < 1.0 else max(0.02, abs(target_f) * 2e-3)
            any_hit = False
            for d_rel, d_nums, d_txt in doc_records:
              hit = any(abs(x - target_f) <= tol for x in d_nums)
              if hit:
                any_hit = True
              d_low = d_txt.lower()
              if (fk_str.lower() in d_low or fk_spaced in d_low) and not hit:
                findings.append(f"{d_rel}: facts.json mismatch for {fk_str}={fv}")
            if not any_hit:
              findings.append(f"facts.json quantity {fk_str}={fv} missing across deliverables")
          elif isinstance(fv, str) and fv:
            for d_rel, _, d_txt in doc_records:
              d_low = d_txt.lower()
              if (fk_str.lower() in d_low or fk_spaced in d_low) and fv.lower() not in d_low:
                findings.append(f"{d_rel}: facts.json mismatch for {fk_str}={fv!r}")
    except (OSError, ValueError) as exc:
      findings.append(f"facts.json: unreadable ({exc})")

  outcome = "not_run" if not candidate_rels and not facts_file.is_file() else ("flagged" if findings else "pass")
  return {"outcome": outcome, "findings": findings, "sizes": sizes}


def _cli() -> int:
  if len(sys.argv) < 4:
    return 2
  mode = sys.argv[1]
  workdir = Path(sys.argv[2])
  state_dir = Path(sys.argv[3])
  if mode == "hook-pre":
    snapshot_workdir(workdir, state_dir)
    return 0
  if mode == "hook-post":
    if is_workdir_dirty(workdir, state_dir):
      sys.stdout.write("\n__PLE_DIRTY__")
    return 0
  if mode == "audit":
    delivered = json.loads(sys.argv[4]) if len(sys.argv) > 4 else []
    res = audit_workdir(workdir, state_dir, delivered)
    sys.stdout.write("__PLE_AUDIT_JSON__:" + json.dumps(res, separators=(",", ":")))
    return 0
  return 1


if __name__ == "__main__":
  raise SystemExit(_cli())
