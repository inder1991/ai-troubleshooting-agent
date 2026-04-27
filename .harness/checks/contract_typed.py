#!/usr/bin/env python3
"""SL — no Any escape hatches on contract surfaces.

One rule:
  SL.contract-typed — fields of classes under backend/src/models/api/,
                      backend/src/models/agent/, or backend/src/learning/sidecars/
                      may not be annotated `Any`, `Optional[Any]`, or `dict[str, Any]`.

H-25 — same defaults as siblings.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / ".harness/checks"))

from _common import emit, load_baseline, normalize_path, spine_paths  # noqa: E402

DEFAULT_ROOTS = (
    spine_paths("backend_models_api", ("backend/src/models/api",))
    + spine_paths("backend_models_agent", ("backend/src/models/agent",))
    + spine_paths("backend_learning_sidecars", ("backend/src/learning/sidecars",))
)
EXCLUDE = (
    "__pycache__", ".venv", "/venv/", "node_modules",
    "tests/harness/fixtures", "site-packages", ".git", ".pytest_cache",
)
GUARDED_PREFIXES = (
    "backend/src/models/api/",
    "backend/src/models/agent/",
    "backend/src/learning/sidecars/",
)
BASELINE = load_baseline("contract_typed")


def _emit(path: Path, rule: str, msg: str, suggestion: str, line: int) -> bool:
    sig = (normalize_path(path), int(line), rule)
    if sig in BASELINE:
        return False
    emit("ERROR", path, rule, msg, suggestion, line=line)
    return True


def _is_any(node: ast.AST | None) -> bool:
    if node is None:
        return False
    if isinstance(node, ast.Name) and node.id == "Any":
        return True
    if isinstance(node, ast.Attribute) and node.attr == "Any":
        return True
    return False


def _is_none(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _is_optional_any(node: ast.AST | None) -> bool:
    if (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id == "Optional"
        and _is_any(node.slice)
    ):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return (_is_any(node.left) and _is_none(node.right)) or (_is_any(node.right) and _is_none(node.left))
    return False


def _is_dict_str_any(node: ast.AST | None) -> bool:
    if not isinstance(node, ast.Subscript):
        return False
    base = node.value
    if not (
        (isinstance(base, ast.Name) and base.id in {"dict", "Dict"})
        or (isinstance(base, ast.Attribute) and base.attr in {"dict", "Dict"})
    ):
        return False
    s = node.slice
    if isinstance(s, ast.Tuple) and len(s.elts) == 2:
        return _is_any(s.elts[1])
    return False


def _scan_file(path: Path, virtual: str) -> int:
    if not any(virtual.startswith(p) for p in GUARDED_PREFIXES):
        return 0
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, UnicodeDecodeError):
        return 0
    except SyntaxError:
        emit("WARN", path, "harness.unparseable",
             f"could not parse {path.name}", "fix syntax", line=1)
        return 0
    errors = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    ann = stmt.annotation
                    if _is_any(ann) or _is_optional_any(ann) or _is_dict_str_any(ann):
                        if _emit(path, "SL.contract-typed",
                                 f"field `{stmt.target.id}` annotated with Any-shaped type",
                                 "declare a concrete type or a specific union",
                                 stmt.lineno):
                            errors += 1
    return errors


def _walk_python(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*.py")):
        if any(tok in str(path) for tok in EXCLUDE):
            continue
        yield path


def scan(roots: Iterable[Path], pretend_path: str | None) -> int:
    total_errors = 0
    for root in roots:
        if not root.exists():
            continue
        if root.is_file() and root.suffix == ".py":
            virtual = pretend_path or (
                str(root.relative_to(REPO_ROOT))
                if root.is_relative_to(REPO_ROOT) else root.name
            )
            total_errors += _scan_file(root, virtual)
        else:
            for path in _walk_python(root):
                virtual = (
                    str(path.relative_to(REPO_ROOT))
                    if path.is_relative_to(REPO_ROOT) else path.name
                )
                total_errors += _scan_file(path, virtual)
    return 1 if total_errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, action="append")
    parser.add_argument("--pretend-path", type=str)
    args = parser.parse_args(argv)
    roots = tuple(args.target) if args.target else DEFAULT_ROOTS
    return scan(roots, args.pretend_path)


if __name__ == "__main__":
    sys.exit(main())
