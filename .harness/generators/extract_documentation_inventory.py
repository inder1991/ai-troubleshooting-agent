#!/usr/bin/env python3
"""Generator — documentation inventory.

Walks .harness/documentation_policy.yaml.spine_python_paths (AST: per public
function/class, has_docstring flag), then frontend_jsdoc_paths (regex: per
top-level export, has_jsdoc flag), and emits both surfaces plus the list of
ADRs under docs/decisions/*.md.

Output: .harness/generated/documentation_inventory.json
Schema: .harness/schemas/generated/documentation_inventory.schema.json

H-25:
  Missing input    — exit 0 with empty arrays.
  Malformed input  — skip silently.
  Upstream failed  — none.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / ".harness/generators"))

from _common import iter_python_files, iter_tsx_files, write_generated  # noqa: E402

JSDOC_RE = re.compile(r'/\*\*[\s\S]*?\*/')
EXPORT_DECL_RE = re.compile(
    r'^\s*export\s+(const|function|class|async\s+function)\s+(\w+)', re.MULTILINE,
)
ADR_HEADER_RE = re.compile(r'^# (?P<title>.+)$', re.MULTILINE)


def _glob_to_root(glob: str) -> str:
    parts = []
    for seg in glob.split("/"):
        if any(c in seg for c in "*?["):
            break
        parts.append(seg)
    return "/".join(parts)


def _scan_python_symbols(root: Path, globs: list[str]) -> list[dict]:
    out: list[dict] = []
    for glob in globs:
        prefix = _glob_to_root(glob)
        if not prefix:
            continue
        scan_root = root / prefix
        if not scan_root.exists():
            continue
        for path in iter_python_files(scan_root, exclude=("__pycache__", "/venv/", ".venv")):
            virtual = str(path.relative_to(root))
            if not any(fnmatch.fnmatchcase(virtual, g) for g in globs):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (OSError, UnicodeDecodeError, SyntaxError):
                continue
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                if node.name.startswith("_"):
                    continue
                doc = ast.get_docstring(node, clean=False)
                out.append({
                    "file": virtual,
                    "symbol": node.name,
                    "kind": type(node).__name__,
                    "line": node.lineno,
                    "has_docstring": bool(doc and doc.strip()),
                })
    out.sort(key=lambda e: (e["file"], e["line"], e["symbol"]))
    return out


def _scan_jsdoc_exports(root: Path, globs: list[str]) -> list[dict]:
    out: list[dict] = []
    for glob in globs:
        prefix = _glob_to_root(glob)
        if not prefix:
            continue
        scan_root = root / prefix
        if not scan_root.exists():
            continue
        for path in iter_tsx_files(scan_root, exclude=("node_modules", "dist")):
            virtual = str(path.relative_to(root))
            if not any(fnmatch.fnmatchcase(virtual, g) for g in globs):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for m in EXPORT_DECL_RE.finditer(text):
                decl_start = m.start()
                window = text[max(0, decl_start - 400):decl_start]
                has_jsdoc = bool(list(JSDOC_RE.finditer(window)))
                line = text[:decl_start].count("\n") + 1
                out.append({
                    "file": virtual,
                    "symbol": m.group(2),
                    "kind": "export",
                    "line": line,
                    "has_jsdoc": has_jsdoc,
                })
    out.sort(key=lambda e: (e["file"], e["line"], e["symbol"]))
    return out


def _scan_adrs(root: Path) -> list[dict]:
    decisions_dir = root / "docs" / "decisions"
    if not decisions_dir.exists():
        return []
    out: list[dict] = []
    for path in sorted(decisions_dir.glob("*.md")):
        if path.name == "_TEMPLATE.md":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        m = ADR_HEADER_RE.search(text)
        title = m.group("title").strip() if m else path.stem
        out.append({"file": str(path.relative_to(root)), "title": title})
    return out


def _scan(root: Path) -> dict:
    """Read documentation_policy.yaml; project per-symbol presence + ADR list."""
    policy_path = root / ".harness" / "documentation_policy.yaml"
    if policy_path.exists():
        try:
            policy = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            policy = {}
    else:
        policy = {}
    py_globs = policy.get("spine_python_paths") or []
    js_globs = policy.get("frontend_jsdoc_paths") or []
    return {
        "python_symbols": _scan_python_symbols(root, py_globs),
        "frontend_exports": _scan_jsdoc_exports(root, js_globs),
        "adrs": _scan_adrs(root),
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args(argv)
    payload = _scan(args.root)
    if args.print:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    out_path = write_generated("documentation_inventory", payload)
    print(
        f"[INFO] wrote {len(payload['python_symbols'])} py + "
        f"{len(payload['frontend_exports'])} fe + "
        f"{len(payload['adrs'])} ADRs → {out_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
