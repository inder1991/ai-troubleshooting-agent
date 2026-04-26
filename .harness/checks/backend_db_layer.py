#!/usr/bin/env python3
"""Q8 — backend DB layer (gateway quarantine + model separation + raw-SQL).

Eight rules:
  Q8.sqlmodel-quarantine     — `sqlmodel` import outside storage/ or models/db/.
  Q8.asyncsession-quarantine — `AsyncSession` import outside storage/.
  Q8.execute-quarantine      — `cursor.execute` / `connection.execute`
                                outside storage/ (text-based fallback for
                                cursor/connection).
  Q8.api-model-no-table      — file under models/api|agent contains `table=True`.
  Q8.db-model-needs-table    — file under models/db lacks any `table=True`.
  Q8.raw-sql-unjustified     — raw SQL keyword in source string outside
                                storage/analytics.py unless a
                                `# RAW-SQL-JUSTIFIED:` comment is present.
  Q8.text-call-outside-analytics — `text("…")` call outside storage/analytics.py.

H-25:
  Missing input    — exit 2 with harness.target-missing.
  Malformed input  — WARN harness.unparseable; skip file.
  Upstream failed  — none; pure filesystem.
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

from _common import emit, load_baseline  # noqa: E402

DEFAULT_ROOTS = (REPO_ROOT / "backend" / "src",)
EXCLUDE = ("__pycache__", ".venv", "node_modules", "tests/harness/fixtures")
BASELINE = load_baseline("backend_db_layer")

RAW_SQL_RE = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE)\s+\w", re.IGNORECASE)
JUSTIFICATION_TOKEN = "RAW-SQL-JUSTIFIED:"

STORAGE_PREFIX = "backend/src/storage"
MODELS_DB_PREFIX = "backend/src/models/db"
MODELS_API_PREFIX = "backend/src/models/api"
MODELS_AGENT_PREFIX = "backend/src/models/agent"
ANALYTICS_FILE = "backend/src/storage/analytics.py"


def _emit(path: Path, rule: str, msg: str, suggestion: str, line: int) -> bool:
    """Emit ERROR unless baselined. Returns True if real ERROR was emitted."""
    sig = (str(path), int(line), rule)
    if sig in BASELINE:
        return False
    emit("ERROR", path, rule, msg, suggestion, line=line)
    return True


def _path_starts_with(virtual: str, prefix: str) -> bool:
    return virtual.startswith(prefix + "/") or virtual == prefix


def _scan_file(path: Path, virtual: str) -> int:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        emit("WARN", path, "harness.unparseable",
             f"could not parse {path.name}",
             "fix syntax or exclude from harness scope", line=1)
        return 0

    in_storage = _path_starts_with(virtual, STORAGE_PREFIX)
    in_models_db = _path_starts_with(virtual, MODELS_DB_PREFIX)
    in_models_api = (
        _path_starts_with(virtual, MODELS_API_PREFIX)
        or _path_starts_with(virtual, MODELS_AGENT_PREFIX)
    )
    is_analytics = virtual == ANALYTICS_FILE
    has_justification = JUSTIFICATION_TOKEN in source

    errors = 0

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module_names: list[str] = []
            if isinstance(node, ast.Import):
                module_names = [alias.name for alias in node.names]
            else:
                if node.module:
                    module_names = [node.module]
            for name in module_names:
                root = name.split(".")[0]
                if root == "sqlmodel" and not (in_storage or in_models_db):
                    if _emit(path, "Q8.sqlmodel-quarantine",
                             "`sqlmodel` imported outside storage/ or models/db/",
                             "move ORM access behind StorageGateway methods",
                             node.lineno):
                        errors += 1
                if name in {"sqlalchemy.ext.asyncio", "sqlalchemy.orm.session"} and not in_storage:
                    if _emit(path, "Q8.asyncsession-quarantine",
                             f"`{name}` imported outside storage/",
                             "only StorageGateway may hold AsyncSession references",
                             node.lineno):
                        errors += 1

        # api/agent model with table=True
        if in_models_api and isinstance(node, ast.ClassDef):
            for keyword in getattr(node, "keywords", []):
                if (
                    keyword.arg == "table"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is True
                ):
                    if _emit(path, "Q8.api-model-no-table",
                             f"`{node.name}` declared `table=True` in api/agent boundary",
                             "split DB persistence into models/db/, keep boundary models pure pydantic",
                             node.lineno):
                        errors += 1

        # text("...") outside analytics
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "text"
            and not is_analytics
        ):
            if _emit(path, "Q8.text-call-outside-analytics",
                     "sqlalchemy `text(...)` call outside storage/analytics.py",
                     "route raw SQL through storage/analytics.py with a justification comment",
                     node.lineno):
                errors += 1

        # cursor.execute / connection.execute (textual fallback for non-storage files)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in {"cursor", "connection"}
            and not in_storage
        ):
            if _emit(path, "Q8.execute-quarantine",
                     f"`{node.func.value.id}.execute(...)` outside storage/",
                     "add a method to StorageGateway and call that instead",
                     node.lineno):
                errors += 1

    # raw SQL string scan (text-based, line-aware)
    if not is_analytics and not has_justification:
        for lineno, line in enumerate(source.splitlines(), 1):
            if RAW_SQL_RE.search(line):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if _emit(path, "Q8.raw-sql-unjustified",
                         "raw SQL keyword in source outside storage/analytics.py",
                         "move query to analytics.py with `# RAW-SQL-JUSTIFIED: <reason>`",
                         lineno):
                    errors += 1

    # models/db/ files must declare at least one table=True
    if in_models_db and path.name not in {"__init__.py"}:
        any_table = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for keyword in getattr(node, "keywords", []):
                    if (
                        keyword.arg == "table"
                        and isinstance(keyword.value, ast.Constant)
                        and keyword.value.value is True
                    ):
                        any_table = True
                        break
            if any_table:
                break
        if not any_table:
            if _emit(path, "Q8.db-model-needs-table",
                     f"{path.name} lives under models/db/ but no class declares `table=True`",
                     "add `table=True` or move the file out of models/db/",
                     1):
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
    parser.add_argument("--target", type=Path, action="append")
    parser.add_argument("--pretend-path", type=str, default=None)
    args = parser.parse_args(argv)
    roots = tuple(args.target) if args.target else DEFAULT_ROOTS
    return scan(roots, args.pretend_path)


if __name__ == "__main__":
    sys.exit(main())
