#!/usr/bin/env python3
"""Q10 — Pydantic strict at boundaries.

Eight rules:
  Q10.api-request-needs-forbid       — request models missing extra="forbid".
  Q10.api-response-needs-frozen      — response models missing frozen=True.
  Q10.agent-needs-forbid-and-frozen  — agent models missing both.
  Q10.probability-needs-bounds       — fields named confidence/probability/*_score/*_ratio
                                       must declare ge=0/le=1.
  Q10.no-extra-allow-in-boundary     — extra="allow" banned in api/agent.

H-25:
  Missing input    — exit 2.
  Malformed input  — WARN harness.unparseable.
  Upstream failed  — none.
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

DEFAULT_ROOTS = spine_paths("backend_models", ("backend/src/models",))
EXCLUDE = (
    "__pycache__", ".venv", "/venv/", "node_modules",
    "tests/harness/fixtures", "site-packages", ".git", ".pytest_cache",
)
BASELINE = load_baseline("backend_validation_contracts")

PROBABILITY_NAMES = {"confidence", "probability"}
PROBABILITY_SUFFIXES = ("_score", "_ratio", "_probability")


def _emit(path: Path, rule: str, msg: str, suggestion: str, line: int) -> bool:
    sig = (normalize_path(path), int(line), rule)
    if sig in BASELINE:
        return False
    emit("ERROR", path, rule, msg, suggestion, line=line)
    return True


def _is_request(virtual: str, class_name: str) -> bool:
    return virtual.endswith("_request.py") or class_name.endswith("Request")


def _is_response(virtual: str, class_name: str) -> bool:
    return virtual.endswith("_response.py") or class_name.endswith("Response")


def _config_dict_kwargs(class_node: ast.ClassDef) -> dict[str, ast.AST]:
    out: dict[str, ast.AST] = {}
    for stmt in class_node.body:
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and stmt.targets[0].id == "model_config"
        ):
            value = stmt.value
            if isinstance(value, ast.Call):
                for kw in value.keywords:
                    if kw.arg:
                        out[kw.arg] = kw.value
    return out


def _is_const(node: ast.AST, expected) -> bool:
    return isinstance(node, ast.Constant) and node.value == expected


def _field_call_kwargs(call: ast.Call) -> dict[str, ast.AST]:
    return {kw.arg: kw.value for kw in call.keywords if kw.arg}


def _scan_class(class_node: ast.ClassDef, path: Path, virtual: str) -> int:
    in_api = "/models/api/" in virtual or virtual.startswith("backend/src/models/api/")
    in_agent = "/models/agent/" in virtual or virtual.startswith("backend/src/models/agent/")
    if not (in_api or in_agent):
        return 0

    config = _config_dict_kwargs(class_node)
    is_request = _is_request(virtual, class_node.name)
    is_response = _is_response(virtual, class_node.name)

    extra = config.get("extra")
    frozen = config.get("frozen")

    errors = 0

    if extra is not None and _is_const(extra, "allow"):
        if _emit(path, "Q10.no-extra-allow-in-boundary",
                 f"`extra='allow'` on boundary class {class_node.name}",
                 'set ConfigDict(extra="forbid") and add the missing fields explicitly',
                 class_node.lineno):
            errors += 1

    if in_agent:
        forbid_ok = extra is not None and _is_const(extra, "forbid")
        frozen_ok = frozen is not None and _is_const(frozen, True)
        if not (forbid_ok and frozen_ok):
            if _emit(path, "Q10.agent-needs-forbid-and-frozen",
                     f"agent schema {class_node.name} missing forbid+frozen",
                     'add model_config = ConfigDict(extra="forbid", frozen=True)',
                     class_node.lineno):
                errors += 1
    elif in_api:
        if is_request:
            forbid_ok = extra is not None and _is_const(extra, "forbid")
            if not forbid_ok:
                if _emit(path, "Q10.api-request-needs-forbid",
                         f"request model {class_node.name} missing extra='forbid'",
                         'add model_config = ConfigDict(extra="forbid")',
                         class_node.lineno):
                    errors += 1
        if is_response:
            frozen_ok = frozen is not None and _is_const(frozen, True)
            if not frozen_ok:
                if _emit(path, "Q10.api-response-needs-frozen",
                         f"response model {class_node.name} missing frozen=True",
                         'add model_config = ConfigDict(extra="forbid", frozen=True)',
                         class_node.lineno):
                    errors += 1

    # field-level bounds
    for stmt in class_node.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            field_name = stmt.target.id
            is_probability = (
                field_name in PROBABILITY_NAMES
                or any(field_name.endswith(suf) for suf in PROBABILITY_SUFFIXES)
            )
            if (
                is_probability
                and isinstance(stmt.value, ast.Call)
                and isinstance(stmt.value.func, ast.Name)
                and stmt.value.func.id == "Field"
            ):
                kwargs = _field_call_kwargs(stmt.value)
                if "ge" not in kwargs or "le" not in kwargs:
                    if _emit(path, "Q10.probability-needs-bounds",
                             f"field `{field_name}` is a probability but lacks ge/le",
                             "declare Field(..., ge=0.0, le=1.0)",
                             stmt.lineno):
                        errors += 1
    return errors


def _scan_file(path: Path, virtual: str) -> int:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        emit("WARN", path, "harness.unparseable",
             f"could not parse {path.name}", "fix syntax", line=1)
        return 0
    errors = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            errors += _scan_class(node, path, virtual)
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
            # Models dir may not exist; that's not an error worth shouting about.
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
    parser.add_argument("--pretend-path", type=str, default=None)
    args = parser.parse_args(argv)
    roots = tuple(args.target) if args.target else DEFAULT_ROOTS
    return scan(roots, args.pretend_path)


if __name__ == "__main__":
    sys.exit(main())
