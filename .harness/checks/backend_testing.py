#!/usr/bin/env python3
"""Q9 — backend testing discipline.

Six rules:
  Q9.learning-needs-hypothesis    — every backend/src/learning/*.py needs a
                                     paired test under backend/tests/learning/
                                     that imports `hypothesis`.
  Q9.parser-needs-hypothesis      — every backend/src/**/parsers/*.py needs same.
  Q9.extractor-needs-hypothesis   — top-level def matching extract_*/parse_*/
                                     resolve_*/calibrate_*/score_* must have a
                                     paired Hypothesis-decorated test (function
                                     name reference inside any hypothesis test
                                     file).
  Q9.no-live-llm                  — test files must not import openai/anthropic.
  Q9.no-live-otlp-exporter        — test files must not import opentelemetry-
                                     exporter-otlp.
  Q9.test-raw-sql-justification-banned — `RAW-SQL-JUSTIFIED:` token banned in
                                          test files.

H-25:
  Missing input    — exit 2 (target path missing).
  Malformed input  — WARN harness.unparseable; skip.
  Upstream failed  — none.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / ".harness/checks"))

from _common import emit, load_baseline, normalize_path, spine_paths  # noqa: E402

DEFAULT_ROOTS = spine_paths("backend_src", ("backend/src",)) + spine_paths("backend_tests", ("backend/tests",))
EXCLUDE = (
    "__pycache__", ".venv", "/venv/", "node_modules",
    "tests/harness/fixtures", "site-packages", ".git", ".pytest_cache",
)
BASELINE = load_baseline("backend_testing")

EXTRACTOR_PREFIXES = ("extract_", "parse_", "resolve_", "calibrate_", "score_")
LIVE_LLM_MODULES = {"openai", "anthropic"}
LIVE_OTLP_MODULES = {
    "opentelemetry.exporter.otlp",
    "opentelemetry.exporter.otlp.proto.grpc",
}


def _emit(path: Path, rule: str, msg: str, suggestion: str, line: int) -> bool:
    sig = (normalize_path(path), int(line), rule)
    if sig in BASELINE:
        return False
    emit("ERROR", path, rule, msg, suggestion, line=line)
    return True


def _is_test_file(virtual: str) -> bool:
    return (
        "/tests/" in virtual
        or virtual.startswith("tests/")
        or Path(virtual).name.startswith("test_")
    )


def _is_learning_source(virtual: str) -> bool:
    name = Path(virtual).name
    return (
        virtual.startswith("backend/src/learning/")
        and virtual.endswith(".py")
        and not name.startswith("test_")
        and name != "__init__.py"
    )


def _is_parser_source(virtual: str) -> bool:
    name = Path(virtual).name
    return (
        "/parsers/" in virtual
        and virtual.startswith("backend/src/")
        and not name.startswith("test_")
        and name != "__init__.py"
    )


def _imports(tree: ast.AST) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.add(alias.name)
        if isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def _scan_test_file(path: Path, virtual: str, source: str, tree: ast.AST) -> int:
    errors = 0
    imports = _imports(tree)
    for live in LIVE_LLM_MODULES:
        for imp in imports:
            if imp == live or imp.startswith(live + "."):
                if _emit(path, "Q9.no-live-llm",
                         f"test file imports `{live}`",
                         f"mock {live} via pytest-mock or respx", 1):
                    errors += 1
                break
    for live in LIVE_OTLP_MODULES:
        for imp in imports:
            if imp == live:
                if _emit(path, "Q9.no-live-otlp-exporter",
                         "test file imports a live OTLP exporter",
                         "use ConsoleSpanExporter or in-memory span recorder", 1):
                    errors += 1
                break
    if "RAW-SQL-JUSTIFIED:" in source:
        if _emit(path, "Q9.test-raw-sql-justification-banned",
                 "`RAW-SQL-JUSTIFIED:` comment present inside a test file",
                 "raw SQL belongs in storage/analytics.py, not tests", 1):
            errors += 1
    return errors


def _collect_extractor_names(tree: ast.AST) -> set[str]:
    out: set[str] = set()
    body = getattr(tree, "body", None)
    nodes = body if body is not None else list(ast.walk(tree))
    for node in nodes:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for prefix in EXTRACTOR_PREFIXES:
                if node.name.startswith(prefix):
                    out.add(node.name)
                    break
    return out


def _walk_python(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*.py")):
        if any(tok in str(path) for tok in EXCLUDE):
            continue
        yield path


def _hypothesis_referenced_names_in_dir(test_dir: Path) -> set[str]:
    """Coarse: any identifier appearing in a test file that imports hypothesis
    is treated as 'covered'. H.2 will replace with a real call-graph analyzer."""
    refs: set[str] = set()
    if not test_dir.exists():
        return refs
    for f in _walk_python(test_dir):
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "from hypothesis" not in text and "import hypothesis" not in text:
            continue
        refs.update(re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", text))
    return refs


def _hypothesis_referenced_names_in_paths(paths: Iterable[Path]) -> set[str]:
    """Same as _hypothesis_referenced_names_in_dir but accepts a flat list of
    file paths. Used when scanning a fixture directory passed as --target."""
    refs: set[str] = set()
    for f in paths:
        if not f.is_file() or f.suffix != ".py":
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "from hypothesis" not in text and "import hypothesis" not in text:
            continue
        refs.update(re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", text))
    return refs


def _scan_source_file(path: Path, virtual: str, tree: ast.AST,
                       hypothesis_refs: set[str]) -> int:
    errors = 0
    if _is_learning_source(virtual):
        stem = path.stem
        repo_test = (spine_paths("backend_tests_learning", ("backend/tests/learning",))[0])
        candidates = list(repo_test.glob(f"test_{stem}*.py")) if repo_test.exists() else []
        ok = False
        for cand in candidates:
            try:
                ctxt = cand.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if "hypothesis" in ctxt:
                ok = True
                break
        if not ok and stem not in hypothesis_refs:
            if _emit(path, "Q9.learning-needs-hypothesis",
                     f"learning module {path.name} has no Hypothesis-using paired test",
                     f"add backend/tests/learning/test_{stem}.py with `from hypothesis import given`",
                     1):
                errors += 1

    if _is_parser_source(virtual):
        stem = path.stem
        any_test_root = (spine_paths("backend_tests", ("backend/tests",))[0])
        ok = False
        if any_test_root.exists():
            for cand in any_test_root.rglob(f"test_{stem}*.py"):
                try:
                    ctxt = cand.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                if "hypothesis" in ctxt:
                    ok = True
                    break
        if not ok and stem not in hypothesis_refs:
            if _emit(path, "Q9.parser-needs-hypothesis",
                     f"parser {path.name} has no Hypothesis-using paired test",
                     "add a Hypothesis property test under backend/tests/", 1):
                errors += 1

    if virtual.startswith("backend/src/"):
        names = _collect_extractor_names(tree)
        if names:
            for name in sorted(names):
                if name not in hypothesis_refs:
                    if _emit(path, "Q9.extractor-needs-hypothesis",
                             f"function `{name}` matches extract_*/parse_*/resolve_*/calibrate_*/score_* but no Hypothesis test references it",
                             f"add `from hypothesis import given` test that calls {name}", 1):
                        errors += 1
    return errors


def _scan_file(path: Path, virtual: str, hypothesis_refs: set[str]) -> int:
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
    if _is_test_file(virtual):
        return _scan_test_file(path, virtual, source, tree)
    return _scan_source_file(path, virtual, tree, hypothesis_refs)


def scan(roots: Iterable[Path], pretend_path: str | None) -> int:
    total_errors = 0
    for root in roots:
        if not root.exists():
            emit("ERROR", root, "harness.target-missing",
                 f"target path does not exist: {root}",
                 "pass an existing file or directory via --target", line=0)
            return 2
        # Cache: when scanning the live repo (or any dir containing backend/tests/),
        # collect hypothesis refs once across the canonical test roots.
        cached_refs: set[str] = set()
        live_test_root = (spine_paths("backend_tests", ("backend/tests",))[0])
        if live_test_root.exists() and root.is_dir() and (
            root == REPO_ROOT or root == REPO_ROOT / "backend"
            or live_test_root.is_relative_to(root) if hasattr(Path, "is_relative_to") else False
        ):
            cached_refs = _hypothesis_referenced_names_in_dir(live_test_root)

        if root.is_file() and root.suffix == ".py":
            virtual = pretend_path or (
                str(root.relative_to(REPO_ROOT))
                if root.is_relative_to(REPO_ROOT) else root.name
            )
            # For single-file mode, also scan sibling files for hypothesis refs
            # plus the cached canonical test-root refs.
            sibling_refs = _hypothesis_referenced_names_in_paths(root.parent.iterdir())
            total_errors += _scan_file(root, virtual, sibling_refs | cached_refs)
        else:
            # Directory mode — collect hypothesis refs from all .py under this root first.
            local_refs = _hypothesis_referenced_names_in_paths(_walk_python(root)) | cached_refs
            for path in _walk_python(root):
                virtual = (
                    str(path.relative_to(REPO_ROOT))
                    if path.is_relative_to(REPO_ROOT) else path.name
                )
                # When the dir is a fixture directory passed as --target, infer
                # virtual paths from the pretend_path's parent if provided.
                if pretend_path and not path.is_relative_to(REPO_ROOT):
                    pretend_parent = str(Path(pretend_path).parent)
                    virtual = f"{pretend_parent}/{path.name}"
                total_errors += _scan_file(path, virtual, local_refs)
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
