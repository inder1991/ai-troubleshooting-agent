#!/usr/bin/env python3
"""Q7 — backend async-strict correctness check.

Six rules enforced:
  Q7.no-requests              — `requests` module banned everywhere on backend spine.
  Q7.no-aiohttp               — `aiohttp` banned (use httpx.AsyncClient).
  Q7.no-asyncio-run-in-handler— `asyncio.run(...)` banned inside files whose path contains `api/`.
  Q7.no-sync-httpx            — `httpx.Client(...)` banned (only AsyncClient on backend).
  Q7.no-blocking-sleep-in-async — `time.sleep(...)` inside an `async def` body.

H-25 contract:
  Missing input    : if --target points at a non-existent path, exit 2 and
                     emit ERROR rule=harness.target-missing.
  Malformed input  : if a Python file fails to parse, emit WARN
                     rule=harness.unparseable and skip it.
  Upstream failed  : the check reads only the filesystem; no upstream services.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / ".harness/checks"))

from _common import emit, load_baseline, spine_paths  # noqa: E402

DEFAULT_ROOTS = spine_paths("backend_src", ("backend/src",))
EXCLUDE = (
    "__pycache__", ".venv", "/venv/", "node_modules",
    "tests/harness/fixtures", "site-packages", ".git", ".pytest_cache",
)
BASELINE = load_baseline("backend_async_correctness")


def _emit_unless_baselined(path: Path, rule: str, msg: str, suggestion: str, line: int) -> bool:
    """Emit ERROR unless (file, line, rule) is in the baseline. Returns True
    iff a real ERROR was emitted (caller increments error counter on True)."""
    sig = (str(path), int(line), rule)
    if sig in BASELINE:
        return False
    emit("ERROR", path, rule, msg, suggestion, line=line)
    return True


def _is_handler_path(virtual: str) -> bool:
    return "/api/" in virtual or virtual.startswith("api/")


def _scan_file(path: Path, virtual: str) -> int:
    """Returns number of ERROR findings emitted."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        emit("WARN", path, "harness.unparseable",
             f"could not parse {path.name} as Python",
             "fix the syntax error or exclude the file",
             line=1)
        return 0

    errors = 0
    for node in ast.walk(tree):
        # Imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "requests":
                    if _emit_unless_baselined(path, "Q7.no-requests",
                            "sync `requests` is banned on the backend spine",
                            "use httpx.AsyncClient (see backend/src/utils/http.py)",
                            node.lineno):
                        errors += 1
                if alias.name == "aiohttp":
                    if _emit_unless_baselined(path, "Q7.no-aiohttp",
                            "`aiohttp` is banned; only httpx.AsyncClient permitted",
                            "replace aiohttp.ClientSession with httpx.AsyncClient",
                            node.lineno):
                        errors += 1
        if isinstance(node, ast.ImportFrom) and node.module in {"requests", "aiohttp"}:
            if _emit_unless_baselined(path, f"Q7.no-{node.module}",
                    f"`{node.module}` is banned on the backend spine",
                    "use httpx.AsyncClient",
                    node.lineno):
                errors += 1

        # asyncio.run(...) in handler files
        if (
            _is_handler_path(virtual)
            and isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "asyncio"
            and node.func.attr == "run"
        ):
            if _emit_unless_baselined(path, "Q7.no-asyncio-run-in-handler",
                    "asyncio.run() inside an api/ handler",
                    "handlers run inside FastAPI's loop; declare `async def` instead",
                    node.lineno):
                errors += 1

        # sync httpx.Client(...)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "httpx"
            and node.func.attr == "Client"
        ):
            if _emit_unless_baselined(path, "Q7.no-sync-httpx",
                    "httpx.Client() is sync; backend spine requires AsyncClient",
                    "use httpx.AsyncClient inside an `async with` block",
                    node.lineno):
                errors += 1

        # time.sleep inside async def
        if isinstance(node, ast.AsyncFunctionDef):
            for sub in ast.walk(node):
                if (
                    isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)
                    and isinstance(sub.func.value, ast.Name)
                    and sub.func.value.id == "time"
                    and sub.func.attr == "sleep"
                ):
                    if _emit_unless_baselined(path, "Q7.no-blocking-sleep-in-async",
                            "time.sleep() inside async def blocks the event loop",
                            "use `await asyncio.sleep(...)` or `await asyncio.to_thread(time.sleep, ...)`",
                            sub.lineno):
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
            emit("ERROR", root, "harness.target-missing",
                 f"target path does not exist: {root}",
                 "pass an existing file or directory via --target",
                 line=0)
            return 2
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
    parser.add_argument("--target", type=Path, action="append",
                        help="File or directory to scan (default: backend/src/).")
    parser.add_argument("--pretend-path", type=str, default=None)
    args = parser.parse_args(argv)
    roots = tuple(args.target) if args.target else DEFAULT_ROOTS
    return scan(roots, args.pretend_path)


if __name__ == "__main__":
    sys.exit(main())
