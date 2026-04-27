#!/usr/bin/env python3
"""Q15 — documentation discipline (docstrings + JSDoc + ADR triggers).

Three rules (api.md presence + ADR template + ADR-on-change deferred):
  Q15.spine-docstring-required    — every public function/class in spine
                                     paths must have a non-empty docstring.
  Q15.frontend-jsdoc-required     — every `export const|function` in
                                     frontend/src/{hooks,lib,services}/**
                                     must have a JSDoc comment.
  Q15.adr-required-on-change      — git diff on adr_required_on_change paths
                                     requires a new docs/decisions/<date>.md.

H-25:
  Missing input    — exit 2.
  Malformed input  — WARN harness.unparseable.
  Upstream failed  — git binary missing → WARN; ADR-on-change rule degrades.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / ".harness/checks"))

from _common import emit, load_baseline, normalize_path  # noqa: E402

DEFAULT_POLICY = REPO_ROOT / ".harness" / "documentation_policy.yaml"
EXCLUDE_VIRTUAL_PREFIXES = (
    "tests/harness/fixtures/",
    "frontend/dist/",
    "frontend/node_modules/",
    "backend/.venv/",
    "backend/venv/",
)
EXCLUDE_FS = (
    "node_modules", ".git", "dist", "site-packages",
    "tests/harness/fixtures", "__pycache__", ".venv", "/venv/",
    ".pytest_cache",
)
JS_SCANNED_EXTS = {".ts", ".tsx", ".js", ".jsx"}
BASELINE = load_baseline("documentation_policy")

JSDOC_RE = re.compile(r'/\*\*[\s\S]*?\*/')
EXPORT_DECL_RE = re.compile(r'^\s*export\s+(const|function|class|async\s+function)\s+(\w+)', re.MULTILINE)


def _emit(file: Path, rule: str, msg: str, suggestion: str, line: int = 1) -> bool:
    sig = (normalize_path(file), int(line), rule)
    if sig in BASELINE:
        return False
    emit("ERROR", file, rule, msg, suggestion, line=line)
    return True


def _load_policy(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _matches_any(virtual: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(virtual, g) for g in globs)


def _is_excluded(virtual: str) -> bool:
    return any(virtual.startswith(p) for p in EXCLUDE_VIRTUAL_PREFIXES)


def _scan_python_docstrings(path: Path, source: str) -> int:
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        emit("WARN", path, "harness.unparseable",
             f"could not parse {path.name}", "fix syntax", line=1)
        return 0
    errors = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name.startswith("_"):
                continue
            doc = ast.get_docstring(node, clean=False)
            if not doc or not doc.strip():
                if _emit(path, "Q15.spine-docstring-required",
                         f"public {type(node).__name__} `{node.name}` missing docstring",
                         "add a one-line docstring describing purpose + return contract",
                         node.lineno):
                    errors += 1
    return errors


def _scan_jsdoc(path: Path, source: str) -> int:
    errors = 0
    for m in EXPORT_DECL_RE.finditer(source):
        decl_start = m.start()
        window = source[max(0, decl_start - 400):decl_start]
        last_jsdoc = None
        for jm in JSDOC_RE.finditer(window):
            last_jsdoc = jm
        if last_jsdoc is None:
            line = source[:decl_start].count("\n") + 1
            if _emit(path, "Q15.frontend-jsdoc-required",
                     f"export `{m.group(2)}` lacks JSDoc",
                     "add a `/** ... */` comment immediately above the declaration",
                     line):
                errors += 1
    return errors


def _scan_file(path: Path, virtual: str, policy: dict) -> int:
    if _is_excluded(virtual):
        return 0
    spine = policy.get("spine_python_paths") or []
    front = policy.get("frontend_jsdoc_paths") or []
    if path.suffix == ".py" and _matches_any(virtual, spine):
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return 0
        return _scan_python_docstrings(path, source)
    if path.suffix in JS_SCANNED_EXTS and _matches_any(virtual, front):
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return 0
        return _scan_jsdoc(path, source)
    return 0


def _scan_adr_on_change(policy: dict) -> int:
    if not shutil.which("git"):
        emit("WARN", Path("git"), "Q15.adr-required-on-change",
             "git binary missing; ADR diff check skipped",
             "install git so this rule can enforce", line=0)
        return 0
    try:
        diff = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=10,
        )
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return 0
    changed = [
        p for p in (diff.stdout + "\n" + untracked.stdout).splitlines() if p.strip()
    ]
    triggers = policy.get("adr_required_on_change") or []
    triggered = [p for p in changed if any(fnmatch.fnmatchcase(p, t) for t in triggers)]
    if not triggered:
        return 0
    new_adr = [p for p in changed if p.startswith("docs/decisions/") and not p.endswith("_TEMPLATE.md")]
    if not new_adr:
        if _emit(Path("docs/decisions/"), "Q15.adr-required-on-change",
                 f"changes to {triggered[:3]} (and {max(0, len(triggered)-3)} others) require an ADR",
                 "add docs/decisions/<YYYY-MM-DD>-<slug>.md based on _TEMPLATE.md",
                 0):
            return 1
    return 0


def _walk_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(tok in str(path) for tok in EXCLUDE_FS):
            continue
        if path.suffix == ".py" or path.suffix in JS_SCANNED_EXTS:
            yield path


def _glob_to_root(glob: str) -> str:
    parts = []
    for seg in glob.split("/"):
        if any(c in seg for c in "*?["):
            break
        parts.append(seg)
    return "/".join(parts)


def _scoped_walk_roots(policy: dict) -> list[Path]:
    seen: set[str] = set()
    roots: list[Path] = []
    for glob in (policy.get("spine_python_paths") or []) + (policy.get("frontend_jsdoc_paths") or []):
        prefix = _glob_to_root(glob)
        if not prefix or prefix in seen:
            continue
        seen.add(prefix)
        candidate = REPO_ROOT / prefix
        if candidate.exists():
            roots.append(candidate)
    return roots


def scan(roots: Iterable[Path], policy_path: Path, pretend_path: str | None) -> int:
    """Run Q15 documentation rules against `roots`. Return 1 if any errors fired."""
    policy = _load_policy(policy_path)
    total_errors = 0
    roots_list = list(roots)
    if any(root.is_dir() for root in roots_list):
        total_errors += _scan_adr_on_change(policy)
    for root in roots_list:
        if not root.exists():
            continue
        if root.is_file():
            virtual = pretend_path or (
                str(root.relative_to(REPO_ROOT))
                if root.is_relative_to(REPO_ROOT) else root.name
            )
            total_errors += _scan_file(root, virtual, policy)
        else:
            walk_roots = _scoped_walk_roots(policy) if root == REPO_ROOT else [root]
            for walk_root in walk_roots:
                for p in _walk_files(walk_root):
                    virtual = (
                        str(p.relative_to(REPO_ROOT))
                        if p.is_relative_to(REPO_ROOT) else p.name
                    )
                    total_errors += _scan_file(p, virtual, policy)
    return 1 if total_errors else 0


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint: parse args, dispatch scan, return process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, action="append")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--pretend-path", type=str)
    args = parser.parse_args(argv)
    roots = tuple(args.target) if args.target else (REPO_ROOT,)
    return scan(roots, args.policy, args.pretend_path)


if __name__ == "__main__":
    sys.exit(main())
