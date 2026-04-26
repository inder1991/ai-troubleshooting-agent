# Harness Sprint H.1a — Per-Task Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship the ten backend basic checks (`backend_async_correctness`, `backend_db_layer`, `backend_testing`, `backend_validation_contracts`, `dependency_policy`, `performance_budgets`, `audit_emission`, `contract_typed`, `todo_in_prod`, `storage_isolation`) so every backend rule from Q7–Q12 plus four self-learning-spine invariants becomes deterministically enforceable through `make validate-fast`.

**Architecture:** Each check is a standalone Python script under `.harness/checks/<rule_id>.py` that walks the repo (or a `--target`-supplied path), emits structured findings on stdout per H-16/H-23 (`[SEVERITY] file=… rule=… message="…" suggestion="…"`), and exits non-zero on any `ERROR`. Checks share helpers from `.harness/checks/_common.py` (already created in H.0a). Every story follows TDD discipline with paired violation + compliant fixtures (H-24) under `tests/harness/fixtures/<rule_id>/{violation,compliant}/`.

**Tech Stack:** Python 3.14, ast (stdlib), pathlib (stdlib), tomllib (stdlib), PyYAML (already a dep), pytest (already configured in H.0a/H.0b).

**Reference docs:**
- [Consolidated harness plan](./2026-04-26-ai-harness.md) — locked decisions Q7–Q12, H-16/H-23/H-24/H-25.
- [Sprint H.0a per-task plan](./2026-04-26-harness-sprint-h0a-tasks.md) — substrate (`Makefile`, loader, `run_validate.py` orchestrator that auto-discovers `.harness/checks/*.py`, `tests/harness/_helpers.py` with `assert_check_fires` / `assert_check_silent`).
- [Sprint H.0b per-task plan](./2026-04-26-harness-sprint-h0b-tasks.md) — config files (`dependencies.yaml`, `performance_budgets.yaml`) the H.1a checks parse.

**Prerequisites:** Sprints H.0a + H.0b complete and committed. In particular this sprint assumes:
- `tools/run_validate.py` glob-discovers every `.harness/checks/*.py` (added in H.0a Story 4).
- `.harness/checks/_common.py` exposes `Finding`, `Severity`, `emit(Finding)`, `walk_python_files(root, exclude=())`, `walk_text_files(root, exts, exclude=())` (added in H.0a Story 1).
- `tests/harness/_helpers.py` exposes `assert_check_fires(check_name, fixture, expected_rule)` and `assert_check_silent(check_name, fixture)` (added in H.0a Story 8).
- `.harness/dependencies.yaml` exists with seeded spine whitelist + global blacklist (added in H.0b Story 4).
- `.harness/performance_budgets.yaml` exists with seeded `agent_budgets`, `db_query_max_ms`, `bundle_kb` sections (added in H.0b Story 5).

---

## Story map for Sprint H.1a

| Story | Title | Tasks | Pts |
|---|---|---|---|
| H.1a.1 | `backend_async_correctness.py` (Q7) — async-strict at I/O, no asyncio.run in handlers | 1.1 – 1.10 | 5 |
| H.1a.2 | `backend_db_layer.py` (Q8) — gateway quarantine + model separation + raw-SQL discipline | 2.1 – 2.10 | 5 |
| H.1a.3 | `backend_testing.py` (Q9) — Hypothesis-required paths + no live LLM/telemetry | 3.1 – 3.10 | 5 |
| H.1a.4 | `backend_validation_contracts.py` (Q10) — Pydantic strict at boundaries | 4.1 – 4.10 | 5 |
| H.1a.5 | `dependency_policy.py` (Q11) — spine whitelist + global blacklist | 5.1 – 5.10 | 5 |
| H.1a.6 | `performance_budgets.py` (Q12) — agent + DB + bundle hard gates | 6.1 – 6.8 | 3 |
| H.1a.7 | `audit_emission.py` — every gateway write calls `_audit` | 7.1 – 7.6 | 2 |
| H.1a.8 | `contract_typed.py` — no `Optional[Any]` / bare `Any` in spine sidecar models | 8.1 – 8.6 | 2 |
| H.1a.9 | `todo_in_prod.py` — no `# TODO` outside `tests/` and `docs/` | 9.1 – 9.5 | 1 |
| H.1a.10 | `storage_isolation.py` — `cursor.execute` / `session.execute` only inside `storage/` | 10.1 – 10.6 | 2 |

**Total: 10 stories, ~35 points, 2 weeks** (capacity 26 ± buffer; tight but achievable because all checks share a single template and helper module).

---

## Story-template recap (all ten share this shape)

Per Sprint H.1a §5.3 of the master plan, every check story carries the same seven acceptance criteria:

- **AC-1:** Check exists at `.harness/checks/<rule_id>.py`.
- **AC-2:** Output conforms to H-16 + H-23 (`[SEVERITY] file=… rule=… message="…" suggestion="…"`).
- **AC-3:** Violation fixture causes the check to emit ≥ 1 `[ERROR]` line and exit non-zero.
- **AC-4:** Compliant fixture is silent (zero `[ERROR]` lines, exit 0).
- **AC-5:** Wired into `make validate-fast` (automatic via the `*.py` glob in `tools/run_validate.py`).
- **AC-6:** Completes on the full repo in < 2s (each check; total fast budget < 30s, H-17).
- **AC-7:** H-25 docstring present — answers "missing input?", "malformed input?", "upstream failed?".

Common task pattern per story (red → green → refactor):

1. Write paired fixtures under `tests/harness/fixtures/<rule_id>/{violation,compliant}/`.
2. Write the failing test in `tests/harness/checks/test_<rule_id>.py` using `assert_check_fires` / `assert_check_silent` helpers.
3. Run the test → expect failure (`FileNotFoundError` or no findings emitted).
4. `git commit -m "test(red): H.1a.<n> — fixtures + assertions for <rule>"`.
5. Implement `.harness/checks/<rule_id>.py` with the H-25 docstring + structured emit.
6. Re-run the test → expect pass.
7. `git commit -m "feat(green): H.1a.<n> — <rule> check enforces Q<n>"`.
8. Run `python tools/run_validate.py --fast` → confirm new check is discovered + emits no spurious errors against the live repo (or only emits errors on known pre-existing violations, in which case follow the **baseline-or-fix** flow described per story).
9. `git commit -m "chore: H.1a.<n> — wire <rule> into validate-fast"` (only if a config update was needed — usually not, since the orchestrator globs).

---

# Story H.1a.1 — `backend_async_correctness.py` (Q7)

**Rule families enforced (6):**
1. No `requests` import (sync HTTP client banned). Use `httpx.AsyncClient`.
2. No `aiohttp` import (alternative async HTTP banned).
3. No `asyncio.run(` inside `backend/src/api/` (handler files must not start a new loop).
4. No `httpx.Client(` inside `backend/src/` (sync httpx banned; only `AsyncClient`).
5. CPU-bound `time.sleep(` inside `async def` flagged (must use `await asyncio.sleep` or `await asyncio.to_thread(time.sleep, …)`).
6. Plain `def` route handler that calls `await` flagged (sync def cannot await; SyntaxError-adjacent).

**Files:**
- Create: `.harness/checks/backend_async_correctness.py`
- Create: `tests/harness/fixtures/backend_async_correctness/violation/uses_requests.py`
- Create: `tests/harness/fixtures/backend_async_correctness/violation/uses_aiohttp.py`
- Create: `tests/harness/fixtures/backend_async_correctness/violation/asyncio_run_in_handler.py`
- Create: `tests/harness/fixtures/backend_async_correctness/violation/sync_httpx_client.py`
- Create: `tests/harness/fixtures/backend_async_correctness/violation/blocking_sleep_in_async.py`
- Create: `tests/harness/fixtures/backend_async_correctness/compliant/clean.py`
- Create: `tests/harness/fixtures/backend_async_correctness/compliant/async_with_to_thread.py`
- Create: `tests/harness/checks/test_backend_async_correctness.py`

### Task 1.1: Create the violation fixture directory + the five violation files

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
mkdir -p tests/harness/fixtures/backend_async_correctness/violation
mkdir -p tests/harness/fixtures/backend_async_correctness/compliant
```

Create `tests/harness/fixtures/backend_async_correctness/violation/uses_requests.py`:

```python
"""Q7 violation — bans the sync `requests` library."""
import requests

def fetch(url: str) -> str:
    return requests.get(url).text
```

Create `tests/harness/fixtures/backend_async_correctness/violation/uses_aiohttp.py`:

```python
"""Q7 violation — bans `aiohttp`; only httpx.AsyncClient permitted."""
import aiohttp

async def fetch(url: str) -> str:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.text()
```

Create `tests/harness/fixtures/backend_async_correctness/violation/asyncio_run_in_handler.py`:

```python
"""Q7 violation — handler files must not invoke asyncio.run().

This file simulates living under backend/src/api/ — the check uses path
match (`api/` segment) to scope the rule.
"""
# pretend-path: backend/src/api/routes_v4.py
import asyncio

async def _do_work() -> None:
    pass

def handler() -> None:
    asyncio.run(_do_work())
```

Create `tests/harness/fixtures/backend_async_correctness/violation/sync_httpx_client.py`:

```python
"""Q7 violation — sync httpx.Client banned in backend/src/.

Only AsyncClient is permitted on the backend spine.
"""
import httpx

def fetch(url: str) -> str:
    with httpx.Client() as client:
        return client.get(url).text
```

Create `tests/harness/fixtures/backend_async_correctness/violation/blocking_sleep_in_async.py`:

```python
"""Q7 violation — time.sleep inside async def is a blocking syscall.

Use `await asyncio.sleep(...)` or `await asyncio.to_thread(time.sleep, ...)`.
"""
import time

async def slow() -> None:
    time.sleep(0.5)
```

### Task 1.2: Create the two compliant fixtures

Create `tests/harness/fixtures/backend_async_correctness/compliant/clean.py`:

```python
"""Q7 compliant — async httpx + asyncio.sleep + no banned imports."""
import asyncio
import httpx

async def fetch(url: str) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        return resp.text

async def patient(seconds: float) -> None:
    await asyncio.sleep(seconds)
```

Create `tests/harness/fixtures/backend_async_correctness/compliant/async_with_to_thread.py`:

```python
"""Q7 compliant — CPU-bound work delegated to to_thread."""
import asyncio
import time

def cpu_bound(n: int) -> int:
    time.sleep(0.01)  # OK: this is sync def, not async def
    return n * n

async def runner() -> int:
    return await asyncio.to_thread(cpu_bound, 5)
```

### Task 1.3: Write the failing test

Create `tests/harness/checks/__init__.py` (empty) if it does not yet exist.

Create `tests/harness/checks/test_backend_async_correctness.py`:

```python
"""H.1a.1 — backend_async_correctness check tests.

Each violation fixture must produce ≥ 1 ERROR with the matching rule id.
Each compliant fixture must produce zero ERRORs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness._helpers import assert_check_fires, assert_check_silent

CHECK = "backend_async_correctness"
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / CHECK


@pytest.mark.parametrize(
    "fixture_name,expected_rule",
    [
        ("uses_requests.py", "Q7.no-requests"),
        ("uses_aiohttp.py", "Q7.no-aiohttp"),
        ("asyncio_run_in_handler.py", "Q7.no-asyncio-run-in-handler"),
        ("sync_httpx_client.py", "Q7.no-sync-httpx"),
        ("blocking_sleep_in_async.py", "Q7.no-blocking-sleep-in-async"),
    ],
)
def test_violation_fixture_fires(fixture_name: str, expected_rule: str) -> None:
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / fixture_name,
        expected_rule=expected_rule,
    )


@pytest.mark.parametrize(
    "fixture_name",
    [
        "clean.py",
        "async_with_to_thread.py",
    ],
)
def test_compliant_fixture_silent(fixture_name: str) -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / fixture_name,
    )
```

### Task 1.4: Run the failing test

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
python -m pytest tests/harness/checks/test_backend_async_correctness.py -v
```

Expected: all 7 cases fail with `FileNotFoundError: .harness/checks/backend_async_correctness.py` (or equivalent — the helper subprocesses the script).

### Task 1.5: Commit the red

```bash
git add tests/harness/fixtures/backend_async_correctness tests/harness/checks/test_backend_async_correctness.py tests/harness/checks/__init__.py
git commit -m "$(cat <<'EOF'
test(red): H.1a.1 — backend_async_correctness fixtures + assertions

Five violation fixtures (requests/aiohttp imports, asyncio.run in
handler, sync httpx.Client, blocking sleep in async def) plus two
compliant fixtures (clean async httpx, to_thread for CPU-bound). Tests
fail because the check itself is not yet implemented.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 1.6: Implement the check

Create `.harness/checks/backend_async_correctness.py`:

```python
#!/usr/bin/env python3
"""Q7 — backend async-strict correctness check.

Six rules enforced:
  Q7.no-requests              — `requests` module banned everywhere on backend spine.
  Q7.no-aiohttp               — `aiohttp` banned (use httpx.AsyncClient).
  Q7.no-asyncio-run-in-handler— `asyncio.run(...)` banned inside files whose path contains `api/`.
  Q7.no-sync-httpx            — `httpx.Client(...)` banned (only AsyncClient on backend).
  Q7.no-blocking-sleep-in-async — `time.sleep(...)` inside an `async def` body.
  Q7.no-await-in-sync-def     — `await` token inside a plain `def` (syntactically suspect).

H-25 contract:
  Missing input    : if --target points at a non-existent path, exit 2 and
                     emit ERROR rule=harness.target-missing.
  Malformed input  : if a Python file fails to parse, emit WARN
                     rule=harness.unparseable and skip it (do not exit non-zero
                     for a parse error — that is `ruff`'s job, not ours).
  Upstream failed  : the check reads only the filesystem; no upstream services.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from .harness.checks._common import Finding, Severity, emit, walk_python_files  # noqa: E402

DEFAULT_ROOTS = (REPO_ROOT / "backend" / "src",)
EXCLUDE = ("__pycache__", ".venv", "node_modules", "tests/harness/fixtures")


def _is_handler_path(path: Path) -> bool:
    return "api" in path.parts


def _scan_file(path: Path) -> Iterable[Finding]:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        yield Finding(
            severity=Severity.WARN,
            file=path,
            line=1,
            rule="harness.unparseable",
            message=f"could not parse {path.name} as Python",
            suggestion="fix the syntax error or exclude the file",
        )
        return

    for node in ast.walk(tree):
        # Imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "requests":
                    yield Finding(
                        severity=Severity.ERROR,
                        file=path,
                        line=node.lineno,
                        rule="Q7.no-requests",
                        message="sync `requests` is banned on the backend spine",
                        suggestion="use httpx.AsyncClient (see backend/src/utils/http.py)",
                    )
                if alias.name == "aiohttp":
                    yield Finding(
                        severity=Severity.ERROR,
                        file=path,
                        line=node.lineno,
                        rule="Q7.no-aiohttp",
                        message="`aiohttp` is banned; only httpx.AsyncClient permitted",
                        suggestion="replace aiohttp.ClientSession with httpx.AsyncClient",
                    )
        if isinstance(node, ast.ImportFrom) and node.module in {"requests", "aiohttp"}:
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=node.lineno,
                rule=f"Q7.no-{node.module}",
                message=f"`{node.module}` is banned on the backend spine",
                suggestion="use httpx.AsyncClient",
            )

        # asyncio.run(...) in handler files
        if (
            _is_handler_path(path)
            and isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "asyncio"
            and node.func.attr == "run"
        ):
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=node.lineno,
                rule="Q7.no-asyncio-run-in-handler",
                message="asyncio.run() inside an api/ handler",
                suggestion="handlers run inside FastAPI's loop; declare `async def` instead",
            )

        # sync httpx.Client(...)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "httpx"
            and node.func.attr == "Client"
        ):
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=node.lineno,
                rule="Q7.no-sync-httpx",
                message="httpx.Client() is sync; backend spine requires AsyncClient",
                suggestion="use httpx.AsyncClient inside an `async with` block",
            )

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
                    yield Finding(
                        severity=Severity.ERROR,
                        file=path,
                        line=sub.lineno,
                        rule="Q7.no-blocking-sleep-in-async",
                        message="time.sleep() inside async def blocks the event loop",
                        suggestion="use `await asyncio.sleep(...)` or `await asyncio.to_thread(time.sleep, ...)`",
                    )


def scan(roots: Iterable[Path]) -> int:
    total_errors = 0
    for root in roots:
        if not root.exists():
            emit(Finding(
                severity=Severity.ERROR,
                file=root,
                line=0,
                rule="harness.target-missing",
                message=f"target path does not exist: {root}",
                suggestion="pass an existing file or directory via --target",
            ))
            return 2
        if root.is_file() and root.suffix == ".py":
            files = [root]
        else:
            files = list(walk_python_files(root, exclude=EXCLUDE))
        for path in files:
            for finding in _scan_file(path):
                emit(finding)
                if finding.severity == Severity.ERROR:
                    total_errors += 1
    return 1 if total_errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        type=Path,
        action="append",
        help="File or directory to scan (default: backend/src/).",
    )
    args = parser.parse_args(argv)
    roots = tuple(args.target) if args.target else DEFAULT_ROOTS
    return scan(roots)


if __name__ == "__main__":
    sys.exit(main())
```

### Task 1.7: Run tests — expect green

```bash
python -m pytest tests/harness/checks/test_backend_async_correctness.py -v
```

Expected: all 7 parametrized cases pass.

### Task 1.8: Run the check against the real backend, triage results

```bash
python .harness/checks/backend_async_correctness.py
```

Expected outcomes (handle whichever applies):

- **Clean exit 0** → ideal; the backend is already async-strict.
- **Some `[ERROR]` lines** → triage:
  - If the violation is a real bug → fix it in a follow-up commit (separate from this story).
  - If the file is legitimately exempt → add it to `EXCLUDE` with a comment, OR add an inline `# harness:allow Q7.<rule>` directive (not yet supported in H.1a — defer that file to the H.1d baseline buffer).
  - If the volume is large (≥ 5 files) → record the violations in `.harness/baselines/Q7_baseline.json` (create the file, listing `path:line:rule`) and add a baseline-aware filter to the check (consult H.1d.1 for the pattern). Then file a tracking ticket.

### Task 1.9: Run the full validate-fast

```bash
python tools/run_validate.py --fast
```

Expected: orchestrator picks up the new check via its glob; total wall time < 30s; exit 0 if backend is clean (or matches baseline).

### Task 1.10: Commit the green

```bash
git add .harness/checks/backend_async_correctness.py
git commit -m "$(cat <<'EOF'
feat(green): H.1a.1 — backend_async_correctness enforces Q7

AST-based check enforcing six Q7 sub-rules: no `requests`/`aiohttp`
imports, no `asyncio.run` in api/ handlers, no sync `httpx.Client`,
no `time.sleep` inside `async def`. H-25 docstring covers missing
target, unparseable file, no upstream calls. Auto-discovered by
tools/run_validate.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Story H.1a.2 — `backend_db_layer.py` (Q8)

**Rule families enforced (8):**
1. `from sqlmodel import` (or `import sqlmodel`) banned outside `backend/src/storage/` and `backend/src/models/db/`.
2. `AsyncSession` import banned outside `backend/src/storage/`.
3. `from sqlalchemy.ext.asyncio import` banned outside `backend/src/storage/`.
4. `models/db/*.py` files must declare `table=True` (otherwise misplaced).
5. `models/api/*.py` and `models/agent/*.py` must NOT have `table=True`.
6. Raw SQL strings (containing `SELECT `, `INSERT `, `UPDATE `, `DELETE ` as f-string or string-literal substring) banned outside `backend/src/storage/analytics.py` unless the file contains a `# RAW-SQL-JUSTIFIED:` comment.
7. `cursor.execute(` / `connection.execute(` banned outside `backend/src/storage/`.
8. Top-level `text("...")` calls (sqlalchemy.text) outside `storage/analytics.py` flagged.

**Files:**
- Create: `.harness/checks/backend_db_layer.py`
- Create: `tests/harness/fixtures/backend_db_layer/violation/sqlmodel_outside_storage.py`
- Create: `tests/harness/fixtures/backend_db_layer/violation/asyncsession_outside_storage.py`
- Create: `tests/harness/fixtures/backend_db_layer/violation/raw_sql_unjustified.py`
- Create: `tests/harness/fixtures/backend_db_layer/violation/api_model_with_table.py`
- Create: `tests/harness/fixtures/backend_db_layer/violation/cursor_execute_outside_storage.py`
- Create: `tests/harness/fixtures/backend_db_layer/compliant/storage_gateway.py`
- Create: `tests/harness/fixtures/backend_db_layer/compliant/api_model.py`
- Create: `tests/harness/fixtures/backend_db_layer/compliant/raw_sql_justified.py`
- Create: `tests/harness/checks/test_backend_db_layer.py`

### Task 2.1: Write violation fixtures

```bash
mkdir -p tests/harness/fixtures/backend_db_layer/{violation,compliant}
```

Create `tests/harness/fixtures/backend_db_layer/violation/sqlmodel_outside_storage.py`:

```python
"""Q8 violation — SQLModel imported outside storage/ or models/db/.

Pretend-path: backend/src/agents/learning/runner.py
"""
from sqlmodel import SQLModel

class Foo(SQLModel):
    name: str
```

Create `tests/harness/fixtures/backend_db_layer/violation/asyncsession_outside_storage.py`:

```python
"""Q8 violation — AsyncSession leaked beyond storage/."""
from sqlalchemy.ext.asyncio import AsyncSession

async def use(session: AsyncSession) -> None:
    pass
```

Create `tests/harness/fixtures/backend_db_layer/violation/raw_sql_unjustified.py`:

```python
"""Q8 violation — raw SELECT in non-analytics file with no justification."""

def report() -> str:
    return "SELECT id, name FROM customers WHERE deleted_at IS NULL"
```

Create `tests/harness/fixtures/backend_db_layer/violation/api_model_with_table.py`:

```python
"""Q8 violation — api boundary model accidentally declared table=True.

Pretend-path: backend/src/models/api/incident_response.py
"""
from sqlmodel import SQLModel

class IncidentResponse(SQLModel, table=True):
    id: int
```

Create `tests/harness/fixtures/backend_db_layer/violation/cursor_execute_outside_storage.py`:

```python
"""Q8 violation — cursor.execute outside the gateway."""
import sqlite3

def hack() -> None:
    cursor = sqlite3.connect(":memory:").cursor()
    cursor.execute("SELECT 1")
```

### Task 2.2: Write compliant fixtures

Create `tests/harness/fixtures/backend_db_layer/compliant/storage_gateway.py`:

```python
"""Q8 compliant — gateway file may import SQLModel + AsyncSession.

Pretend-path: backend/src/storage/gateway.py
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel, select

async def fetch(session: AsyncSession) -> None:
    await session.execute(select(SQLModel))
```

Create `tests/harness/fixtures/backend_db_layer/compliant/api_model.py`:

```python
"""Q8 compliant — pure API model, no table=True, no SQLModel inheritance.

Pretend-path: backend/src/models/api/incident_response.py
"""
from pydantic import BaseModel, Field

class IncidentResponse(BaseModel):
    incident_id: str = Field(..., min_length=1, max_length=64)
```

Create `tests/harness/fixtures/backend_db_layer/compliant/raw_sql_justified.py`:

```python
"""Q8 compliant — analytics file with raw SQL + justification comment.

Pretend-path: backend/src/storage/analytics.py
"""

# RAW-SQL-JUSTIFIED: aggregations cannot be expressed via SQLModel safely.

def cohort_sql() -> str:
    return "SELECT COUNT(*), strftime('%Y-%m', created_at) FROM incidents GROUP BY 2"
```

### Task 2.3: Write the failing test

Create `tests/harness/checks/test_backend_db_layer.py`:

```python
"""H.1a.2 — backend_db_layer check tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness._helpers import assert_check_fires, assert_check_silent

CHECK = "backend_db_layer"
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / CHECK


@pytest.mark.parametrize(
    "fixture_name,expected_rule,pretend_path",
    [
        ("sqlmodel_outside_storage.py", "Q8.sqlmodel-quarantine", "backend/src/agents/learning/runner.py"),
        ("asyncsession_outside_storage.py", "Q8.asyncsession-quarantine", "backend/src/api/routes_v4.py"),
        ("raw_sql_unjustified.py", "Q8.raw-sql-unjustified", "backend/src/services/report.py"),
        ("api_model_with_table.py", "Q8.api-model-no-table", "backend/src/models/api/incident_response.py"),
        ("cursor_execute_outside_storage.py", "Q8.execute-quarantine", "backend/src/services/migrate.py"),
    ],
)
def test_violation_fixture_fires(fixture_name: str, expected_rule: str, pretend_path: str) -> None:
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / fixture_name,
        expected_rule=expected_rule,
        pretend_path=pretend_path,
    )


@pytest.mark.parametrize(
    "fixture_name,pretend_path",
    [
        ("storage_gateway.py", "backend/src/storage/gateway.py"),
        ("api_model.py", "backend/src/models/api/incident_response.py"),
        ("raw_sql_justified.py", "backend/src/storage/analytics.py"),
    ],
)
def test_compliant_fixture_silent(fixture_name: str, pretend_path: str) -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / fixture_name,
        pretend_path=pretend_path,
    )
```

> The `pretend_path` argument is required because Q8's quarantine rules depend on file location. The `_helpers.py` already supports `pretend_path` (added in H.0a Story 8): the helper invokes the check with `--pretend-path <virtual-path>` so path-dependent rules see the right context. If your H.0a helper does not yet support this, add support as a 5-line patch under H.0a (or extend it as part of Task 2.6 below) before continuing.

### Task 2.4: Run failing test + commit red

```bash
python -m pytest tests/harness/checks/test_backend_db_layer.py -v
```

Expected: all 8 cases fail (`FileNotFoundError`).

```bash
git add tests/harness/fixtures/backend_db_layer tests/harness/checks/test_backend_db_layer.py
git commit -m "$(cat <<'EOF'
test(red): H.1a.2 — backend_db_layer fixtures + assertions

Five violation fixtures (sqlmodel/AsyncSession quarantine breach, raw SQL
unjustified, api-model-with-table, cursor.execute outside storage/) plus
three compliant fixtures (gateway file, pure api model, justified raw
SQL in analytics). Tests fail because the check is not yet implemented.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 2.5: Implement the check

Create `.harness/checks/backend_db_layer.py`:

```python
#!/usr/bin/env python3
"""Q8 — backend DB layer (gateway quarantine + model separation + raw-SQL).

Eight rules:
  Q8.sqlmodel-quarantine     — `sqlmodel` import outside storage/ or models/db/.
  Q8.asyncsession-quarantine — `AsyncSession` import outside storage/.
  Q8.execute-quarantine      — `cursor.execute` / `session.execute` / `connection.execute`
                                outside storage/ (text-based fallback for cursor/connection).
  Q8.api-model-no-table      — file under models/api|agent contains `table=True`.
  Q8.db-model-needs-table    — file under models/db lacks any `table=True`.
  Q8.raw-sql-unjustified     — raw SQL keyword in source string outside storage/analytics.py
                                unless `# RAW-SQL-JUSTIFIED:` comment present.
  Q8.text-call-outside-analytics — `text("…")` call outside storage/analytics.py.
  Q8.alembic-rev-append-only — alembic revision file deletes lines from earlier rev (nag-warn only).

H-25:
  Missing input   — exit 2 with harness.target-missing.
  Malformed input — WARN harness.unparseable; skip file.
  Upstream failed — none; pure filesystem.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from .harness.checks._common import Finding, Severity, emit, walk_python_files  # noqa: E402

DEFAULT_ROOTS = (REPO_ROOT / "backend" / "src",)
EXCLUDE = ("__pycache__", ".venv", "node_modules", "tests/harness/fixtures")

RAW_SQL_RE = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE)\s+\w", re.IGNORECASE)
JUSTIFICATION_TOKEN = "RAW-SQL-JUSTIFIED:"

STORAGE_PREFIX = "backend/src/storage"
MODELS_DB_PREFIX = "backend/src/models/db"
MODELS_API_PREFIX = "backend/src/models/api"
MODELS_AGENT_PREFIX = "backend/src/models/agent"
ANALYTICS_FILE = "backend/src/storage/analytics.py"


def _path_starts_with(virtual_path: str, prefix: str) -> bool:
    return virtual_path.startswith(prefix + "/") or virtual_path == prefix


def _scan_file(path: Path, virtual: str) -> Iterable[Finding]:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        yield Finding(
            severity=Severity.WARN,
            file=path,
            line=1,
            rule="harness.unparseable",
            message=f"could not parse {path.name}",
            suggestion="fix syntax or exclude from harness scope",
        )
        return

    in_storage = _path_starts_with(virtual, STORAGE_PREFIX)
    in_models_db = _path_starts_with(virtual, MODELS_DB_PREFIX)
    in_models_api = _path_starts_with(virtual, MODELS_API_PREFIX) or _path_starts_with(virtual, MODELS_AGENT_PREFIX)
    is_analytics = virtual == ANALYTICS_FILE
    has_justification = JUSTIFICATION_TOKEN in source

    for node in ast.walk(tree):
        # SQLModel quarantine
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
                    yield Finding(
                        severity=Severity.ERROR,
                        file=path,
                        line=node.lineno,
                        rule="Q8.sqlmodel-quarantine",
                        message="`sqlmodel` imported outside storage/ or models/db/",
                        suggestion="move ORM access behind StorageGateway methods",
                    )
                if name in {"sqlalchemy.ext.asyncio", "sqlalchemy.orm.session"} and not in_storage:
                    yield Finding(
                        severity=Severity.ERROR,
                        file=path,
                        line=node.lineno,
                        rule="Q8.asyncsession-quarantine",
                        message=f"`{name}` imported outside storage/",
                        suggestion="only StorageGateway may hold AsyncSession references",
                    )

        # api/agent model with table=True
        if (
            in_models_api
            and isinstance(node, ast.ClassDef)
        ):
            for keyword in getattr(node, "keywords", []):
                if (
                    keyword.arg == "table"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is True
                ):
                    yield Finding(
                        severity=Severity.ERROR,
                        file=path,
                        line=node.lineno,
                        rule="Q8.api-model-no-table",
                        message=f"`{node.name}` declared `table=True` in api/agent boundary",
                        suggestion="split DB persistence into models/db/, keep boundary models pure pydantic",
                    )

        # text("...") outside analytics
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "text"
            and not is_analytics
        ):
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=node.lineno,
                rule="Q8.text-call-outside-analytics",
                message="sqlalchemy `text(...)` call outside storage/analytics.py",
                suggestion="route raw SQL through storage/analytics.py with a justification comment",
            )

        # cursor.execute / session.execute (textual fallback for non-storage files)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in {"cursor", "connection"}
            and not in_storage
        ):
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=node.lineno,
                rule="Q8.execute-quarantine",
                message=f"`{node.func.value.id}.execute(...)` outside storage/",
                suggestion="add a method to StorageGateway and call that instead",
            )

    # raw SQL string scan (text-based, line-aware)
    if not is_analytics:
        for lineno, line in enumerate(source.splitlines(), 1):
            if RAW_SQL_RE.search(line) and not has_justification:
                # ignore comments and docstrings/triple-quoted-only lines superficially
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                yield Finding(
                    severity=Severity.ERROR,
                    file=path,
                    line=lineno,
                    rule="Q8.raw-sql-unjustified",
                    message="raw SQL keyword in source outside storage/analytics.py",
                    suggestion="move query to analytics.py with `# RAW-SQL-JUSTIFIED: <reason>`",
                )

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
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=1,
                rule="Q8.db-model-needs-table",
                message=f"{path.name} lives under models/db/ but no class declares `table=True`",
                suggestion="add `table=True` or move the file out of models/db/",
            )


def scan(roots: Iterable[Path], pretend_path: str | None) -> int:
    total_errors = 0
    for root in roots:
        if not root.exists():
            emit(Finding(
                severity=Severity.ERROR,
                file=root,
                line=0,
                rule="harness.target-missing",
                message=f"target path does not exist: {root}",
                suggestion="pass an existing file or directory via --target",
            ))
            return 2
        if root.is_file() and root.suffix == ".py":
            files = [(root, pretend_path or str(root.relative_to(REPO_ROOT)))]
        else:
            files = [
                (p, str(p.relative_to(REPO_ROOT)))
                for p in walk_python_files(root, exclude=EXCLUDE)
            ]
        for path, virtual in files:
            for finding in _scan_file(path, virtual):
                emit(finding)
                if finding.severity == Severity.ERROR:
                    total_errors += 1
    return 1 if total_errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, action="append", help="File or dir.")
    parser.add_argument(
        "--pretend-path",
        type=str,
        help="Override virtual path for a single --target file (testing aid).",
    )
    args = parser.parse_args(argv)
    roots = tuple(args.target) if args.target else DEFAULT_ROOTS
    return scan(roots, args.pretend_path)


if __name__ == "__main__":
    sys.exit(main())
```

### Task 2.6: (If needed) extend `_helpers.py` with `pretend_path` support

If `tests/harness/_helpers.py` does not yet pass `--pretend-path` to checks, add it now. Read the file first to confirm the current API, then patch `assert_check_fires` and `assert_check_silent` to accept `pretend_path: str | None = None` and append `["--pretend-path", pretend_path]` to the subprocess argv when set. Skip this step if H.0a Story 8 already added it.

### Task 2.7: Run tests, expect green

```bash
python -m pytest tests/harness/checks/test_backend_db_layer.py -v
```

Expected: all 8 cases pass.

### Task 2.8: Triage live-repo run

```bash
python .harness/checks/backend_db_layer.py
```

Expected outcomes — same triage flow as Task 1.8 (clean, fix, exclude, or baseline).

### Task 2.9: Run full validate-fast

```bash
python tools/run_validate.py --fast
```

Expected: < 30s, exit code consistent with triage.

### Task 2.10: Commit green

```bash
git add .harness/checks/backend_db_layer.py
git commit -m "$(cat <<'EOF'
feat(green): H.1a.2 — backend_db_layer enforces Q8

AST + textual check enforcing eight Q8 sub-rules: sqlmodel quarantine,
AsyncSession quarantine, execute-call quarantine, api/agent model has
no table=True, models/db file must declare table=True, raw SQL banned
outside storage/analytics.py without justification, sqlalchemy text()
banned outside analytics. H-25 docstring covers missing/malformed/no
upstream. Auto-discovered by tools/run_validate.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Story H.1a.3 — `backend_testing.py` (Q9)

**Rule families enforced (6):**
1. Files under `backend/src/learning/` MUST have a paired test file under `backend/tests/learning/` containing at least one `from hypothesis import` (or `import hypothesis`) usage.
2. Files matching `backend/src/**/parsers/*.py` MUST have at least one Hypothesis-decorated test in the corresponding test path.
3. Functions named `extract_*`, `parse_*`, `resolve_*`, `calibrate_*`, `score_*` in `backend/src/` MUST have a paired Hypothesis-decorated test (function-name match in any test file).
4. Test files under `backend/tests/` MUST NOT import `openai`, `anthropic`, real telemetry SDKs (`opentelemetry-exporter-otlp` direct), or contact live HTTP (no `httpx.AsyncClient` instantiation in tests without `respx`).
5. `from learning.gateway import` (or any `storage.gateway` direct import) inside test files must be paired with a fixture or `respx`/`pytest-mock` import in the same file.
6. `# RAW-SQL-JUSTIFIED` token banned in test files (tests must not whitelist raw SQL).

**Files:**
- Create: `.harness/checks/backend_testing.py`
- Create: `tests/harness/fixtures/backend_testing/violation/learning_module_no_hypothesis_test.py`
- Create: `tests/harness/fixtures/backend_testing/violation/test_uses_real_openai.py`
- Create: `tests/harness/fixtures/backend_testing/violation/extract_function_no_hypothesis.py`
- Create: `tests/harness/fixtures/backend_testing/violation/test_imports_openai.py`
- Create: `tests/harness/fixtures/backend_testing/compliant/learning_module.py`
- Create: `tests/harness/fixtures/backend_testing/compliant/test_learning_module.py`
- Create: `tests/harness/fixtures/backend_testing/compliant/test_with_respx.py`
- Create: `tests/harness/checks/test_backend_testing.py`

### Task 3.1: Write violation fixtures

```bash
mkdir -p tests/harness/fixtures/backend_testing/{violation,compliant}
```

Create `tests/harness/fixtures/backend_testing/violation/learning_module_no_hypothesis_test.py`:

```python
"""Q9 violation — learning/ source file with no paired Hypothesis test.

Pretend-path: backend/src/learning/calibrator.py
"""
def calibrate(score: float) -> float:
    return max(0.0, min(1.0, score))
```

Create `tests/harness/fixtures/backend_testing/violation/test_uses_real_openai.py`:

```python
"""Q9 violation — test file imports openai (real LLM call risk).

Pretend-path: backend/tests/test_routes.py
"""
import openai

def test_completion() -> None:
    openai.ChatCompletion.create(model="gpt-4", messages=[])
```

Create `tests/harness/fixtures/backend_testing/violation/extract_function_no_hypothesis.py`:

```python
"""Q9 violation — `extract_*` function without paired Hypothesis test.

Pretend-path: backend/src/agents/log_agent.py
"""
def extract_severity(line: str) -> str:
    return "ERROR" if "error" in line.lower() else "INFO"
```

Create `tests/harness/fixtures/backend_testing/violation/test_imports_openai.py`:

```python
"""Q9 violation — test file imports anthropic (real LLM call risk)."""
import anthropic

def test_call() -> None:
    anthropic.Anthropic().messages.create(model="claude-3", messages=[])
```

### Task 3.2: Write compliant fixtures

Create `tests/harness/fixtures/backend_testing/compliant/learning_module.py`:

```python
"""Q9 compliant source — paired Hypothesis test exists in same fixture set.

Pretend-path: backend/src/learning/calibrator.py
"""
def calibrate(score: float) -> float:
    return max(0.0, min(1.0, score))
```

Create `tests/harness/fixtures/backend_testing/compliant/test_learning_module.py`:

```python
"""Q9 compliant — Hypothesis-decorated test covering calibrate.

Pretend-path: backend/tests/learning/test_calibrator.py
"""
from hypothesis import given, strategies as st

from .learning_module import calibrate


@given(st.floats(allow_nan=False, allow_infinity=False))
def test_calibrate_in_range(score: float) -> None:
    assert 0.0 <= calibrate(score) <= 1.0
```

Create `tests/harness/fixtures/backend_testing/compliant/test_with_respx.py`:

```python
"""Q9 compliant — test makes outbound calls, but they are mocked via respx."""
import httpx
import respx

@respx.mock
async def test_outbound() -> None:
    respx.get("https://example.com").respond(200, json={"ok": True})
    async with httpx.AsyncClient() as client:
        resp = await client.get("https://example.com")
        assert resp.json() == {"ok": True}
```

### Task 3.3: Write the failing test

Create `tests/harness/checks/test_backend_testing.py`:

```python
"""H.1a.3 — backend_testing check tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness._helpers import assert_check_fires, assert_check_silent

CHECK = "backend_testing"
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / CHECK


@pytest.mark.parametrize(
    "fixture_name,expected_rule,pretend_path",
    [
        ("learning_module_no_hypothesis_test.py", "Q9.learning-needs-hypothesis", "backend/src/learning/calibrator.py"),
        ("test_uses_real_openai.py", "Q9.no-live-llm", "backend/tests/test_routes.py"),
        ("extract_function_no_hypothesis.py", "Q9.extractor-needs-hypothesis", "backend/src/agents/log_agent.py"),
        ("test_imports_openai.py", "Q9.no-live-llm", "backend/tests/test_call.py"),
    ],
)
def test_violation_fixture_fires(fixture_name: str, expected_rule: str, pretend_path: str) -> None:
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / fixture_name,
        expected_rule=expected_rule,
        pretend_path=pretend_path,
    )


@pytest.mark.parametrize(
    "fixture_dir,pretend_path",
    [
        # Test-pair compliance is checked at the directory level: learning_module.py
        # has a sibling test_learning_module.py that imports hypothesis.
        ("compliant", "backend/src/learning/calibrator.py"),
    ],
)
def test_compliant_directory_silent(fixture_dir: str, pretend_path: str) -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / fixture_dir,
        pretend_path=pretend_path,
    )
```

### Task 3.4: Run failing test + commit red

```bash
python -m pytest tests/harness/checks/test_backend_testing.py -v
```

Expected: failures.

```bash
git add tests/harness/fixtures/backend_testing tests/harness/checks/test_backend_testing.py
git commit -m "$(cat <<'EOF'
test(red): H.1a.3 — backend_testing fixtures + assertions

Four violation fixtures (learning module without hypothesis test, test
files importing openai/anthropic, extract_* function without hypothesis)
plus a compliant directory pairing source with a hypothesis-decorated
test and a respx-mocked outbound HTTP test. Tests fail because the check
is not yet implemented.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 3.5: Implement the check

Create `.harness/checks/backend_testing.py`:

```python
#!/usr/bin/env python3
"""Q9 — backend testing discipline.

Six rules:
  Q9.learning-needs-hypothesis    — every backend/src/learning/*.py needs a paired test
                                     under backend/tests/learning/ that imports `hypothesis`.
  Q9.parser-needs-hypothesis      — every backend/src/**/parsers/*.py needs same.
  Q9.extractor-needs-hypothesis   — every `extract_*|parse_*|resolve_*|calibrate_*|score_*`
                                     top-level def needs a paired Hypothesis-decorated test.
  Q9.no-live-llm                  — test files must not import `openai` / `anthropic`.
  Q9.no-live-otlp-exporter        — test files must not import opentelemetry-exporter-otlp.
  Q9.test-raw-sql-justification-banned — `RAW-SQL-JUSTIFIED:` token banned in test files.

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
sys.path.insert(0, str(REPO_ROOT))

from .harness.checks._common import Finding, Severity, emit, walk_python_files  # noqa: E402

DEFAULT_ROOTS = (REPO_ROOT / "backend",)
EXCLUDE = ("__pycache__", ".venv", "node_modules", "tests/harness/fixtures")

EXTRACTOR_PREFIXES = ("extract_", "parse_", "resolve_", "calibrate_", "score_")
LIVE_LLM_MODULES = {"openai", "anthropic"}
LIVE_OTLP_MODULES = {"opentelemetry.exporter.otlp", "opentelemetry.exporter.otlp.proto.grpc"}


def _is_test_file(virtual: str) -> bool:
    return "/tests/" in virtual or virtual.startswith("tests/") or Path(virtual).name.startswith("test_")


def _is_learning_source(virtual: str) -> bool:
    return virtual.startswith("backend/src/learning/") and virtual.endswith(".py") and not Path(virtual).name.startswith("test_")


def _is_parser_source(virtual: str) -> bool:
    return "/parsers/" in virtual and virtual.startswith("backend/src/") and not Path(virtual).name.startswith("test_")


def _imports(tree: ast.AST) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.add(alias.name)
        if isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def _has_hypothesis_decorator(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                src = ast.dump(dec)
                if "given" in src or "hypothesis" in src.lower():
                    return True
    return False


def _scan_test_file(path: Path, virtual: str, source: str, tree: ast.AST) -> Iterable[Finding]:
    imports = _imports(tree)
    for live in LIVE_LLM_MODULES:
        for imp in imports:
            if imp == live or imp.startswith(live + "."):
                yield Finding(
                    severity=Severity.ERROR,
                    file=path,
                    line=1,
                    rule="Q9.no-live-llm",
                    message=f"test file imports `{live}`",
                    suggestion=f"mock {live} via pytest-mock or respx",
                )
                break
    for live in LIVE_OTLP_MODULES:
        for imp in imports:
            if imp == live:
                yield Finding(
                    severity=Severity.ERROR,
                    file=path,
                    line=1,
                    rule="Q9.no-live-otlp-exporter",
                    message="test file imports a live OTLP exporter",
                    suggestion="use ConsoleSpanExporter or in-memory span recorder",
                )
                break
    if "RAW-SQL-JUSTIFIED:" in source:
        yield Finding(
            severity=Severity.ERROR,
            file=path,
            line=1,
            rule="Q9.test-raw-sql-justification-banned",
            message="`RAW-SQL-JUSTIFIED:` comment present inside a test file",
            suggestion="raw SQL belongs in storage/analytics.py, not tests",
        )


def _collect_extractor_names(tree: ast.AST) -> set[str]:
    out: set[str] = set()
    for node in tree.body if hasattr(tree, "body") else ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for prefix in EXTRACTOR_PREFIXES:
                if node.name.startswith(prefix):
                    out.add(node.name)
                    break
    return out


def _hypothesis_referenced_names_in_dir(test_dir: Path) -> set[str]:
    """Return the set of identifiers that appear next to a Hypothesis decorator
    or `given` reference anywhere under `test_dir`. We use a coarse text match:
    any function in any test file whose definition is decorated with `@given`."""
    refs: set[str] = set()
    if not test_dir.exists():
        return refs
    for f in walk_python_files(test_dir, exclude=EXCLUDE):
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "from hypothesis" not in text and "import hypothesis" not in text:
            continue
        # any identifier appearing in the file is "covered" — coarse but enough
        # at this stage; H.2 will replace with a real call-graph generator.
        refs.update(re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", text))
    return refs


def _scan_source_file(path: Path, virtual: str, tree: ast.AST) -> Iterable[Finding]:
    if _is_learning_source(virtual):
        # paired test path: backend/tests/learning/test_<stem>.py
        stem = path.stem
        repo_test = REPO_ROOT / "backend" / "tests" / "learning"
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
        if not ok:
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=1,
                rule="Q9.learning-needs-hypothesis",
                message=f"learning module {path.name} has no Hypothesis-using paired test",
                suggestion=f"add backend/tests/learning/test_{stem}.py with `from hypothesis import given`",
            )

    if _is_parser_source(virtual):
        # paired test in any tests/ subtree that mentions hypothesis and the parser stem
        stem = path.stem
        any_test_root = REPO_ROOT / "backend" / "tests"
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
        if not ok:
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=1,
                rule="Q9.parser-needs-hypothesis",
                message=f"parser {path.name} has no Hypothesis-using paired test",
                suggestion="add a Hypothesis property test under backend/tests/",
            )

    if virtual.startswith("backend/src/"):
        names = _collect_extractor_names(tree)
        if names:
            test_root = REPO_ROOT / "backend" / "tests"
            referenced = _hypothesis_referenced_names_in_dir(test_root)
            for name in sorted(names):
                if name not in referenced:
                    yield Finding(
                        severity=Severity.ERROR,
                        file=path,
                        line=1,
                        rule="Q9.extractor-needs-hypothesis",
                        message=f"function `{name}` matches extract_*/parse_*/resolve_*/calibrate_*/score_* but no Hypothesis test references it",
                        suggestion=f"add `from hypothesis import given` test that calls {name}",
                    )


def _scan_file(path: Path, virtual: str) -> Iterable[Finding]:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        yield Finding(
            severity=Severity.WARN,
            file=path,
            line=1,
            rule="harness.unparseable",
            message=f"could not parse {path.name}",
            suggestion="fix syntax",
        )
        return
    if _is_test_file(virtual):
        yield from _scan_test_file(path, virtual, source, tree)
    else:
        yield from _scan_source_file(path, virtual, tree)


def scan(roots: Iterable[Path], pretend_path: str | None) -> int:
    total_errors = 0
    for root in roots:
        if not root.exists():
            emit(Finding(
                severity=Severity.ERROR,
                file=root,
                line=0,
                rule="harness.target-missing",
                message=f"target path does not exist: {root}",
                suggestion="pass an existing file or directory via --target",
            ))
            return 2
        if root.is_file() and root.suffix == ".py":
            files = [(root, pretend_path or str(root.relative_to(REPO_ROOT)))]
        else:
            files = [
                (p, str(p.relative_to(REPO_ROOT)))
                for p in walk_python_files(root, exclude=EXCLUDE)
            ]
        for path, virtual in files:
            for finding in _scan_file(path, virtual):
                emit(finding)
                if finding.severity == Severity.ERROR:
                    total_errors += 1
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
```

### Task 3.6: Run tests, expect green

```bash
python -m pytest tests/harness/checks/test_backend_testing.py -v
```

Expected: pass.

### Task 3.7: Triage live-repo run

```bash
python .harness/checks/backend_testing.py
```

Expect a non-trivial number of `Q9.extractor-needs-hypothesis` findings; this is normal because the codebase has many `extract_*` helpers. Triage:

- Pick the top 3 most-critical extractors → write Hypothesis tests for them (separate commits).
- Add the rest to `.harness/baselines/Q9_baseline.json` (path:rule) and load it in the check (defer baseline loader to H.1d.1).

### Task 3.8: Run full validate-fast, commit

```bash
python tools/run_validate.py --fast
```

```bash
git add .harness/checks/backend_testing.py
git commit -m "$(cat <<'EOF'
feat(green): H.1a.3 — backend_testing enforces Q9

Six rules: learning/parsers/extractor functions require Hypothesis-using
paired tests; test files banned from importing openai/anthropic/live OTLP
exporters; `RAW-SQL-JUSTIFIED:` banned in tests. H-25 docstring covers
missing/malformed/no-upstream. Auto-discovered.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 3.9: (Optional, time-permitting) write Hypothesis tests for top-3 extractors

Pick three top-level extractors that surface as `Q9.extractor-needs-hypothesis` and write minimal property tests. Commit each as `test(green): H.1a.3 — Hypothesis test for <fn>`.

### Task 3.10: Re-run validate-fast

Confirm the count of `Q9.extractor-needs-hypothesis` findings drops by at least three.

---

# Story H.1a.4 — `backend_validation_contracts.py` (Q10)

**Rule families enforced (8):**
1. Pydantic models in `backend/src/models/api/` MUST set `model_config = ConfigDict(extra="forbid")` for request models (file naming convention `*_request.py` or class with `Request` suffix).
2. Pydantic models in `backend/src/models/api/` MUST set `model_config = ConfigDict(frozen=True)` for response models (`*_response.py` or class with `Response` suffix).
3. Models in `backend/src/models/agent/` MUST set both `extra="forbid"` AND `frozen=True`.
4. Numeric fields named `confidence`, `probability`, `*_score`, `*_ratio` MUST use `Field(..., ge=0, le=1)`.
5. String fields in api/agent boundary models MUST set `max_length` via `Field`.
6. Global `BaseModel.model_config` configurations setting `strict=True` outside of `models/` BANNED (must be per-model, opt-in).
7. `extra="allow"` BANNED in api/agent boundary models.
8. `Field(...)` without bounds on `int`/`float` boundary fields → WARN (not ERROR; many legitimate cases).

**Files:**
- Create: `.harness/checks/backend_validation_contracts.py`
- Create: `tests/harness/fixtures/backend_validation_contracts/violation/api_request_no_forbid.py`
- Create: `tests/harness/fixtures/backend_validation_contracts/violation/api_response_not_frozen.py`
- Create: `tests/harness/fixtures/backend_validation_contracts/violation/agent_missing_strict.py`
- Create: `tests/harness/fixtures/backend_validation_contracts/violation/confidence_no_bounds.py`
- Create: `tests/harness/fixtures/backend_validation_contracts/violation/extra_allow_in_api.py`
- Create: `tests/harness/fixtures/backend_validation_contracts/compliant/clean_api_request.py`
- Create: `tests/harness/fixtures/backend_validation_contracts/compliant/clean_api_response.py`
- Create: `tests/harness/fixtures/backend_validation_contracts/compliant/clean_agent_schema.py`
- Create: `tests/harness/checks/test_backend_validation_contracts.py`

### Task 4.1: Write violation fixtures

```bash
mkdir -p tests/harness/fixtures/backend_validation_contracts/{violation,compliant}
```

Create `tests/harness/fixtures/backend_validation_contracts/violation/api_request_no_forbid.py`:

```python
"""Q10 violation — request model missing extra='forbid'.

Pretend-path: backend/src/models/api/incident_request.py
"""
from pydantic import BaseModel, Field

class IncidentRequest(BaseModel):
    incident_id: str = Field(..., max_length=64)
```

Create `tests/harness/fixtures/backend_validation_contracts/violation/api_response_not_frozen.py`:

```python
"""Q10 violation — response model not frozen.

Pretend-path: backend/src/models/api/incident_response.py
"""
from pydantic import BaseModel, ConfigDict, Field

class IncidentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    incident_id: str = Field(..., max_length=64)
```

Create `tests/harness/fixtures/backend_validation_contracts/violation/agent_missing_strict.py`:

```python
"""Q10 violation — agent schema missing both forbid and frozen.

Pretend-path: backend/src/models/agent/log_finding.py
"""
from pydantic import BaseModel, Field

class LogFinding(BaseModel):
    severity: str = Field(..., max_length=16)
```

Create `tests/harness/fixtures/backend_validation_contracts/violation/confidence_no_bounds.py`:

```python
"""Q10 violation — confidence field without ge/le bounds.

Pretend-path: backend/src/models/agent/score.py
"""
from pydantic import BaseModel, ConfigDict, Field

class Score(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    confidence: float = Field(...)
```

Create `tests/harness/fixtures/backend_validation_contracts/violation/extra_allow_in_api.py`:

```python
"""Q10 violation — extra='allow' inside api boundary.

Pretend-path: backend/src/models/api/loose_request.py
"""
from pydantic import BaseModel, ConfigDict

class LooseRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    foo: str
```

### Task 4.2: Write compliant fixtures

Create `tests/harness/fixtures/backend_validation_contracts/compliant/clean_api_request.py`:

```python
"""Q10 compliant — request with extra='forbid', bounds, max_length.

Pretend-path: backend/src/models/api/incident_request.py
"""
from pydantic import BaseModel, ConfigDict, Field

class IncidentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    incident_id: str = Field(..., min_length=1, max_length=64)
    confidence: float = Field(..., ge=0.0, le=1.0)
```

Create `tests/harness/fixtures/backend_validation_contracts/compliant/clean_api_response.py`:

```python
"""Q10 compliant — response frozen + forbid + bounds.

Pretend-path: backend/src/models/api/incident_response.py
"""
from pydantic import BaseModel, ConfigDict, Field

class IncidentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    incident_id: str = Field(..., min_length=1, max_length=64)
    score_total: float = Field(..., ge=0.0, le=1.0)
```

Create `tests/harness/fixtures/backend_validation_contracts/compliant/clean_agent_schema.py`:

```python
"""Q10 compliant — agent schema with both forbid and frozen.

Pretend-path: backend/src/models/agent/log_finding.py
"""
from pydantic import BaseModel, ConfigDict, Field

class LogFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    severity: str = Field(..., min_length=1, max_length=16)
    confidence: float = Field(..., ge=0.0, le=1.0)
```

### Task 4.3: Write the failing test

Create `tests/harness/checks/test_backend_validation_contracts.py`:

```python
"""H.1a.4 — backend_validation_contracts check tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness._helpers import assert_check_fires, assert_check_silent

CHECK = "backend_validation_contracts"
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / CHECK


@pytest.mark.parametrize(
    "fixture_name,expected_rule,pretend_path",
    [
        ("api_request_no_forbid.py", "Q10.api-request-needs-forbid", "backend/src/models/api/incident_request.py"),
        ("api_response_not_frozen.py", "Q10.api-response-needs-frozen", "backend/src/models/api/incident_response.py"),
        ("agent_missing_strict.py", "Q10.agent-needs-forbid-and-frozen", "backend/src/models/agent/log_finding.py"),
        ("confidence_no_bounds.py", "Q10.probability-needs-bounds", "backend/src/models/agent/score.py"),
        ("extra_allow_in_api.py", "Q10.no-extra-allow-in-boundary", "backend/src/models/api/loose_request.py"),
    ],
)
def test_violation_fires(fixture_name: str, expected_rule: str, pretend_path: str) -> None:
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / fixture_name,
        expected_rule=expected_rule,
        pretend_path=pretend_path,
    )


@pytest.mark.parametrize(
    "fixture_name,pretend_path",
    [
        ("clean_api_request.py", "backend/src/models/api/incident_request.py"),
        ("clean_api_response.py", "backend/src/models/api/incident_response.py"),
        ("clean_agent_schema.py", "backend/src/models/agent/log_finding.py"),
    ],
)
def test_compliant_silent(fixture_name: str, pretend_path: str) -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / fixture_name,
        pretend_path=pretend_path,
    )
```

### Task 4.4: Run failing test + commit red

```bash
python -m pytest tests/harness/checks/test_backend_validation_contracts.py -v
git add tests/harness/fixtures/backend_validation_contracts tests/harness/checks/test_backend_validation_contracts.py
git commit -m "$(cat <<'EOF'
test(red): H.1a.4 — backend_validation_contracts fixtures + assertions

Five violation fixtures (api request without extra=forbid; response not
frozen; agent schema missing both; confidence field without ge/le; extra
=allow in api boundary) plus three compliant counterparts.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 4.5: Implement the check

Create `.harness/checks/backend_validation_contracts.py`:

```python
#!/usr/bin/env python3
"""Q10 — Pydantic strict at boundaries.

Eight rules:
  Q10.api-request-needs-forbid       — request models missing extra="forbid".
  Q10.api-response-needs-frozen      — response models missing frozen=True.
  Q10.agent-needs-forbid-and-frozen  — agent models missing both.
  Q10.probability-needs-bounds       — fields named confidence/probability/*_score/*_ratio
                                       must declare ge=0/le=1.
  Q10.string-needs-max-length        — boundary string field without max_length (WARN).
  Q10.no-extra-allow-in-boundary     — extra="allow" banned in api/agent.
  Q10.no-global-strict               — module-level strict=True outside of models/.
  Q10.no-untyped-base-model          — `class X(BaseModel):` without model_config inside boundary (WARN).

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
sys.path.insert(0, str(REPO_ROOT))

from .harness.checks._common import Finding, Severity, emit, walk_python_files  # noqa: E402

DEFAULT_ROOTS = (REPO_ROOT / "backend" / "src" / "models",)
EXCLUDE = ("__pycache__", ".venv", "node_modules", "tests/harness/fixtures")

PROBABILITY_NAMES = {"confidence", "probability"}
PROBABILITY_SUFFIXES = ("_score", "_ratio", "_probability")


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


def _scan_class(class_node: ast.ClassDef, path: Path, virtual: str) -> Iterable[Finding]:
    in_api = "/models/api/" in virtual or virtual.startswith("backend/src/models/api/")
    in_agent = "/models/agent/" in virtual or virtual.startswith("backend/src/models/agent/")
    if not (in_api or in_agent):
        return

    config = _config_dict_kwargs(class_node)
    is_request = _is_request(virtual, class_node.name)
    is_response = _is_response(virtual, class_node.name)

    extra = config.get("extra")
    frozen = config.get("frozen")

    if extra is not None and _is_const(extra, "allow"):
        yield Finding(
            severity=Severity.ERROR,
            file=path,
            line=class_node.lineno,
            rule="Q10.no-extra-allow-in-boundary",
            message=f"`extra='allow'` on boundary class {class_node.name}",
            suggestion='set ConfigDict(extra="forbid") and add the missing fields explicitly',
        )

    if in_agent:
        forbid_ok = extra is not None and _is_const(extra, "forbid")
        frozen_ok = frozen is not None and _is_const(frozen, True)
        if not (forbid_ok and frozen_ok):
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=class_node.lineno,
                rule="Q10.agent-needs-forbid-and-frozen",
                message=f"agent schema {class_node.name} missing forbid+frozen",
                suggestion='add model_config = ConfigDict(extra="forbid", frozen=True)',
            )
    elif in_api:
        if is_request:
            forbid_ok = extra is not None and _is_const(extra, "forbid")
            if not forbid_ok:
                yield Finding(
                    severity=Severity.ERROR,
                    file=path,
                    line=class_node.lineno,
                    rule="Q10.api-request-needs-forbid",
                    message=f"request model {class_node.name} missing extra='forbid'",
                    suggestion='add model_config = ConfigDict(extra="forbid")',
                )
        if is_response:
            frozen_ok = frozen is not None and _is_const(frozen, True)
            if not frozen_ok:
                yield Finding(
                    severity=Severity.ERROR,
                    file=path,
                    line=class_node.lineno,
                    rule="Q10.api-response-needs-frozen",
                    message=f"response model {class_node.name} missing frozen=True",
                    suggestion='add model_config = ConfigDict(extra="forbid", frozen=True)',
                )

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
                    yield Finding(
                        severity=Severity.ERROR,
                        file=path,
                        line=stmt.lineno,
                        rule="Q10.probability-needs-bounds",
                        message=f"field `{field_name}` is a probability but lacks ge/le",
                        suggestion="declare Field(..., ge=0.0, le=1.0)",
                    )


def _scan_file(path: Path, virtual: str) -> Iterable[Finding]:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        yield Finding(
            severity=Severity.WARN,
            file=path,
            line=1,
            rule="harness.unparseable",
            message=f"could not parse {path.name}",
            suggestion="fix syntax",
        )
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            yield from _scan_class(node, path, virtual)


def scan(roots: Iterable[Path], pretend_path: str | None) -> int:
    total_errors = 0
    for root in roots:
        if not root.exists():
            emit(Finding(
                severity=Severity.ERROR,
                file=root,
                line=0,
                rule="harness.target-missing",
                message=f"target path does not exist: {root}",
                suggestion="pass an existing file or directory via --target",
            ))
            return 2
        if root.is_file() and root.suffix == ".py":
            files = [(root, pretend_path or str(root.relative_to(REPO_ROOT)))]
        else:
            files = [
                (p, str(p.relative_to(REPO_ROOT)))
                for p in walk_python_files(root, exclude=EXCLUDE)
            ]
        for path, virtual in files:
            for finding in _scan_file(path, virtual):
                emit(finding)
                if finding.severity == Severity.ERROR:
                    total_errors += 1
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
```

### Task 4.6: Run tests, expect green

```bash
python -m pytest tests/harness/checks/test_backend_validation_contracts.py -v
```

### Task 4.7: Triage live-repo run

```bash
python .harness/checks/backend_validation_contracts.py
```

Likely findings: missing-forbid on a few request files, missing-frozen on responses. Fix the highest-impact ones; baseline the rest.

### Task 4.8: Run validate-fast

```bash
python tools/run_validate.py --fast
```

### Task 4.9: Commit green

```bash
git add .harness/checks/backend_validation_contracts.py
git commit -m "$(cat <<'EOF'
feat(green): H.1a.4 — backend_validation_contracts enforces Q10

AST scan of backend/src/models/{api,agent}/. Eight rules: api request
needs extra='forbid'; response needs frozen=True; agent needs both;
probability-shaped fields need ge=0/le=1; extra='allow' banned in
boundaries; module-level strict=True banned; missing model_config in
boundary (WARN); string fields without max_length (WARN). H-25
docstring covers missing/malformed/no-upstream.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 4.10: Verify discovery

```bash
python tools/run_validate.py --fast | grep "check:backend_validation_contracts"
```

Expected: orchestrator label printed; check ran.

---

# Story H.1a.5 — `dependency_policy.py` (Q11)

**Rule families enforced (5):**
1. New entry in `backend/pyproject.toml [project.dependencies]` not present in `.harness/dependencies.yaml.python.allowed` → ERROR.
2. New entry in `frontend/package.json dependencies` not present in `.harness/dependencies.yaml.npm.allowed` → ERROR.
3. Any dep matching `.harness/dependencies.yaml.global_blacklist` → ERROR (regardless of path).
4. Spine paths (`backend/src/{api,storage,models,agents}`, `frontend/src/{services/api,hooks}`) `import`ing a module not listed in `.harness/dependencies.yaml.python.allowed_on_spine` → ERROR.
5. Lockfiles (`backend/poetry.lock` or `backend/uv.lock`, `frontend/package-lock.json`) missing while their manifest exists → ERROR.

**Files:**
- Create: `.harness/checks/dependency_policy.py`
- Create: `tests/harness/fixtures/dependency_policy/violation/pyproject_unlisted.toml`
- Create: `tests/harness/fixtures/dependency_policy/violation/package_unlisted.json`
- Create: `tests/harness/fixtures/dependency_policy/violation/spine_imports_unlisted.py`
- Create: `tests/harness/fixtures/dependency_policy/violation/blacklisted_dep.toml`
- Create: `tests/harness/fixtures/dependency_policy/compliant/pyproject_clean.toml`
- Create: `tests/harness/fixtures/dependency_policy/compliant/package_clean.json`
- Create: `tests/harness/fixtures/dependency_policy/compliant/spine_imports_clean.py`
- Create: `tests/harness/fixtures/dependency_policy/_test_dependencies.yaml`
- Create: `tests/harness/checks/test_dependency_policy.py`

### Task 5.1: Write the per-fixture mini-policy

Create `tests/harness/fixtures/dependency_policy/_test_dependencies.yaml`:

```yaml
# Mini policy used only by the H.1a.5 fixtures via --policy override.
python:
  allowed:
    - fastapi
    - httpx
    - sqlmodel
    - pydantic
    - structlog
    - opentelemetry-api
  allowed_on_spine:
    - fastapi
    - httpx
    - sqlmodel
    - pydantic

npm:
  allowed:
    - react
    - "@tanstack/react-query"
    - "react-router-dom"

global_blacklist:
  - "left-pad"
  - "evil-package"
```

### Task 5.2: Write violation fixtures

```bash
mkdir -p tests/harness/fixtures/dependency_policy/{violation,compliant}
```

Create `tests/harness/fixtures/dependency_policy/violation/pyproject_unlisted.toml`:

```toml
[project]
name = "x"
version = "0.0.0"
dependencies = [
  "fastapi",
  "some-unlisted-pkg",
]
```

Create `tests/harness/fixtures/dependency_policy/violation/package_unlisted.json`:

```json
{
  "name": "x",
  "version": "0.0.0",
  "dependencies": {
    "react": "18.0.0",
    "ungoverned-lib": "1.0.0"
  }
}
```

Create `tests/harness/fixtures/dependency_policy/violation/spine_imports_unlisted.py`:

```python
"""Q11 violation — spine file imports an off-list dep.

Pretend-path: backend/src/api/routes_v4.py
"""
import some_unlisted_pkg

def handler() -> None:
    some_unlisted_pkg.do()
```

Create `tests/harness/fixtures/dependency_policy/violation/blacklisted_dep.toml`:

```toml
[project]
name = "x"
version = "0.0.0"
dependencies = ["fastapi", "left-pad"]
```

### Task 5.3: Write compliant fixtures

Create `tests/harness/fixtures/dependency_policy/compliant/pyproject_clean.toml`:

```toml
[project]
name = "x"
version = "0.0.0"
dependencies = [
  "fastapi",
  "httpx",
  "sqlmodel",
  "pydantic",
]
```

Create `tests/harness/fixtures/dependency_policy/compliant/package_clean.json`:

```json
{
  "name": "x",
  "version": "0.0.0",
  "dependencies": {
    "react": "18.0.0",
    "@tanstack/react-query": "5.0.0",
    "react-router-dom": "6.0.0"
  }
}
```

Create `tests/harness/fixtures/dependency_policy/compliant/spine_imports_clean.py`:

```python
"""Q11 compliant — spine file imports only allowed deps.

Pretend-path: backend/src/api/routes_v4.py
"""
import fastapi
import httpx

def handler() -> None:
    pass
```

### Task 5.4: Write the failing test

Create `tests/harness/checks/test_dependency_policy.py`:

```python
"""H.1a.5 — dependency_policy check tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness._helpers import assert_check_fires, assert_check_silent

CHECK = "dependency_policy"
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / CHECK
POLICY = FIXTURE_ROOT / "_test_dependencies.yaml"


@pytest.mark.parametrize(
    "fixture_name,expected_rule,extra_args",
    [
        ("pyproject_unlisted.toml", "Q11.python-unlisted", ["--policy", str(POLICY)]),
        ("package_unlisted.json", "Q11.npm-unlisted", ["--policy", str(POLICY)]),
        ("spine_imports_unlisted.py", "Q11.spine-import-unlisted", ["--policy", str(POLICY), "--pretend-path", "backend/src/api/routes_v4.py"]),
        ("blacklisted_dep.toml", "Q11.blacklisted", ["--policy", str(POLICY)]),
    ],
)
def test_violation_fires(fixture_name: str, expected_rule: str, extra_args: list[str]) -> None:
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / fixture_name,
        expected_rule=expected_rule,
        extra_args=extra_args,
    )


@pytest.mark.parametrize(
    "fixture_name,extra_args",
    [
        ("pyproject_clean.toml", ["--policy", str(POLICY)]),
        ("package_clean.json", ["--policy", str(POLICY)]),
        ("spine_imports_clean.py", ["--policy", str(POLICY), "--pretend-path", "backend/src/api/routes_v4.py"]),
    ],
)
def test_compliant_silent(fixture_name: str, extra_args: list[str]) -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / fixture_name,
        extra_args=extra_args,
    )
```

> **`extra_args` support**: `_helpers.py` (added in H.0a Story 8) accepts `extra_args` to forward arbitrary flags to the check subprocess. If your H.0a helper does not yet accept it, add the parameter as a small patch (5 lines) before continuing. The same parameter is reused by H.1a.6 and H.1a.7 below.

### Task 5.5: Run failing test + commit red

```bash
python -m pytest tests/harness/checks/test_dependency_policy.py -v
git add tests/harness/fixtures/dependency_policy tests/harness/checks/test_dependency_policy.py
git commit -m "$(cat <<'EOF'
test(red): H.1a.5 — dependency_policy fixtures + assertions

Four violation fixtures (unlisted python dep, unlisted npm dep, spine
file importing off-list module, blacklisted dep) plus three compliant
counterparts. Mini policy yaml under fixtures/ is forwarded via
--policy flag.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 5.6: Implement the check

Create `.harness/checks/dependency_policy.py`:

```python
#!/usr/bin/env python3
"""Q11 — hybrid dependency policy.

Five rules:
  Q11.python-unlisted        — entry in pyproject.toml not in policy.python.allowed.
  Q11.npm-unlisted           — entry in package.json not in policy.npm.allowed.
  Q11.spine-import-unlisted  — backend spine file imports module not in policy.python.allowed_on_spine.
  Q11.blacklisted            — any dep on policy.global_blacklist.
  Q11.lockfile-missing       — manifest present without committed lockfile.

H-25:
  Missing input    — exit 2 if --target missing or --policy missing.
  Malformed input  — WARN harness.unparseable; skip file.
  Upstream failed  — none (no network).
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
import tomllib
from pathlib import Path
from typing import Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from .harness.checks._common import Finding, Severity, emit, walk_python_files  # noqa: E402

DEFAULT_POLICY = REPO_ROOT / ".harness" / "dependencies.yaml"
SPINE_PREFIXES = (
    "backend/src/api/",
    "backend/src/storage/",
    "backend/src/models/",
    "backend/src/agents/",
    "frontend/src/services/api/",
    "frontend/src/hooks/",
)


def _load_policy(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _parse_pyproject_deps(path: Path) -> list[str]:
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    deps = data.get("project", {}).get("dependencies", [])
    out = []
    for dep in deps:
        # take name before any version spec (>=, ==, ~=, <, >, [)
        name = dep
        for sep in (">=", "==", "~=", "<=", ">", "<", "[", " "):
            idx = name.find(sep)
            if idx != -1:
                name = name[:idx]
        out.append(name.strip().lower())
    return out


def _parse_package_deps(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    deps = list(data.get("dependencies", {}).keys()) + list(data.get("devDependencies", {}).keys())
    return [d.strip().lower() for d in deps]


def _scan_pyproject(path: Path, policy: dict) -> Iterable[Finding]:
    try:
        deps = _parse_pyproject_deps(path)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        yield Finding(
            severity=Severity.WARN,
            file=path,
            line=1,
            rule="harness.unparseable",
            message=f"could not parse {path.name}: {exc}",
            suggestion="fix TOML syntax",
        )
        return
    allowed = {x.lower() for x in (policy.get("python") or {}).get("allowed", [])}
    blacklist = {x.lower() for x in policy.get("global_blacklist", [])}
    for dep in deps:
        if dep in blacklist:
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=1,
                rule="Q11.blacklisted",
                message=f"`{dep}` is globally blacklisted",
                suggestion=f"remove {dep} from pyproject dependencies",
            )
        elif dep not in allowed:
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=1,
                rule="Q11.python-unlisted",
                message=f"python dep `{dep}` not in .harness/dependencies.yaml allow-list",
                suggestion=f"add {dep} to python.allowed (with ADR justification)",
            )


def _scan_package_json(path: Path, policy: dict) -> Iterable[Finding]:
    try:
        deps = _parse_package_deps(path)
    except (OSError, json.JSONDecodeError) as exc:
        yield Finding(
            severity=Severity.WARN,
            file=path,
            line=1,
            rule="harness.unparseable",
            message=f"could not parse {path.name}: {exc}",
            suggestion="fix JSON syntax",
        )
        return
    allowed = {x.lower() for x in (policy.get("npm") or {}).get("allowed", [])}
    blacklist = {x.lower() for x in policy.get("global_blacklist", [])}
    for dep in deps:
        if dep in blacklist:
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=1,
                rule="Q11.blacklisted",
                message=f"`{dep}` is globally blacklisted",
                suggestion=f"remove {dep} from package.json",
            )
        elif dep not in allowed:
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=1,
                rule="Q11.npm-unlisted",
                message=f"npm dep `{dep}` not in .harness/dependencies.yaml allow-list",
                suggestion=f"add {dep} to npm.allowed (with ADR justification)",
            )


def _scan_python_for_spine_imports(path: Path, virtual: str, policy: dict) -> Iterable[Finding]:
    if not any(virtual.startswith(prefix) for prefix in SPINE_PREFIXES):
        return
    allowed = {x.lower() for x in (policy.get("python") or {}).get("allowed_on_spine", [])}
    if not allowed:
        return
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return
    seen: set[str] = set()
    for node in ast.walk(tree):
        roots: list[tuple[str, int]] = []
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.append((alias.name.split(".")[0], node.lineno))
        if isinstance(node, ast.ImportFrom) and node.module:
            roots.append((node.module.split(".")[0], node.lineno))
        for root, lineno in roots:
            r = root.lower()
            if r in seen:
                continue
            seen.add(r)
            # ignore stdlib + first-party (heuristic: starts with "backend" or "src")
            if r in {"asyncio", "json", "logging", "os", "re", "sys", "typing", "pathlib", "datetime", "collections", "functools", "itertools", "uuid", "enum", "dataclasses", "abc", "hashlib"}:
                continue
            if r in {"backend", "src", "tests", "frontend"}:
                continue
            if r not in allowed:
                yield Finding(
                    severity=Severity.ERROR,
                    file=path,
                    line=lineno,
                    rule="Q11.spine-import-unlisted",
                    message=f"spine file imports `{r}` (not in allowed_on_spine)",
                    suggestion=f"add {r} to python.allowed_on_spine + ADR, OR move usage off spine",
                )


def scan(targets: list[Path], policy_path: Path, pretend_path: str | None) -> int:
    if not policy_path.exists():
        emit(Finding(
            severity=Severity.ERROR,
            file=policy_path,
            line=0,
            rule="harness.target-missing",
            message=f"policy file does not exist: {policy_path}",
            suggestion="seed .harness/dependencies.yaml (Sprint H.0b Story 4)",
        ))
        return 2
    policy = _load_policy(policy_path)
    total_errors = 0
    for target in targets:
        if not target.exists():
            emit(Finding(
                severity=Severity.ERROR,
                file=target,
                line=0,
                rule="harness.target-missing",
                message=f"target does not exist: {target}",
                suggestion="pass an existing path",
            ))
            return 2
        files: list[tuple[Path, str]]
        if target.is_file():
            files = [(target, pretend_path or str(target.relative_to(REPO_ROOT)) if target.is_absolute() and target.is_relative_to(REPO_ROOT) else pretend_path or target.name)]
        else:
            files = []
            for p in target.rglob("*"):
                if p.is_file() and p.name in {"pyproject.toml", "package.json"} or (p.suffix == ".py"):
                    try:
                        files.append((p, str(p.relative_to(REPO_ROOT))))
                    except ValueError:
                        files.append((p, p.name))
        for path, virtual in files:
            if path.name == "pyproject.toml":
                for finding in _scan_pyproject(path, policy):
                    emit(finding)
                    if finding.severity == Severity.ERROR:
                        total_errors += 1
            elif path.name == "package.json":
                for finding in _scan_package_json(path, policy):
                    emit(finding)
                    if finding.severity == Severity.ERROR:
                        total_errors += 1
            elif path.suffix == ".py":
                for finding in _scan_python_for_spine_imports(path, virtual, policy):
                    emit(finding)
                    if finding.severity == Severity.ERROR:
                        total_errors += 1
    return 1 if total_errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, action="append")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--pretend-path", type=str)
    args = parser.parse_args(argv)
    targets = list(args.target) if args.target else [
        REPO_ROOT / "backend" / "pyproject.toml",
        REPO_ROOT / "frontend" / "package.json",
        REPO_ROOT / "backend" / "src",
    ]
    return scan(targets, args.policy, args.pretend_path)


if __name__ == "__main__":
    sys.exit(main())
```

### Task 5.7: Run tests, expect green

```bash
python -m pytest tests/harness/checks/test_dependency_policy.py -v
```

### Task 5.8: Triage live-repo run

```bash
python .harness/checks/dependency_policy.py
```

Almost certainly fires a few `Q11.python-unlisted` / `Q11.npm-unlisted` findings — the H.0b seed of `.harness/dependencies.yaml` may have missed something. Triage:

- If the dep is legitimate → add to the allow-list (separate commit, with a short ADR rationale appended to `.harness/dependencies.yaml` as a comment).
- If the dep is unused → remove from the manifest.

### Task 5.9: Run validate-fast

```bash
python tools/run_validate.py --fast
```

### Task 5.10: Commit green

```bash
git add .harness/checks/dependency_policy.py
git commit -m "$(cat <<'EOF'
feat(green): H.1a.5 — dependency_policy enforces Q11

Five rules: pyproject deps must be in python.allowed; package.json deps
must be in npm.allowed; backend spine files may only import modules in
python.allowed_on_spine; global_blacklist is hard-banned everywhere;
manifest without committed lockfile flagged. H-25 docstring covers
missing/malformed/no-upstream. Auto-discovered by run_validate.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Story H.1a.6 — `performance_budgets.py` (Q12)

**Rule families enforced (6):**
1. Every agent contract YAML under `backend/src/contracts/*.yaml` MUST declare `cost_hint.tool_calls_max`, `cost_hint.tokens_max`, `cost_hint.wall_clock_max`.
2. Each `cost_hint` value MUST be ≤ the cap declared in `.harness/performance_budgets.yaml.agent_budgets.<field>`.
3. `StorageGateway` methods (in `backend/src/storage/gateway.py`) that lack a `@timed_query` decorator → ERROR.
4. Frontend bundle stats from `frontend/dist/stats.json` (if present): initial chunk ≤ 220 KB gz; per-route chunk ≤ 100 KB gz; CSS ≤ 50 KB gz.
5. Lighthouse soft budgets read from `frontend/lighthouserc.json` exist (presence check, not pass/fail).
6. Per-agent `assert_within_budget` invocation must exist in at least one paired test under `backend/tests/agents/`.

**Files:**
- Create: `.harness/checks/performance_budgets.py`
- Create: `tests/harness/fixtures/performance_budgets/violation/agent_missing_cost_hint.yaml`
- Create: `tests/harness/fixtures/performance_budgets/violation/agent_exceeds_budget.yaml`
- Create: `tests/harness/fixtures/performance_budgets/violation/gateway_no_timed_query.py`
- Create: `tests/harness/fixtures/performance_budgets/compliant/agent_within_budget.yaml`
- Create: `tests/harness/fixtures/performance_budgets/compliant/gateway_with_timed_query.py`
- Create: `tests/harness/fixtures/performance_budgets/_test_budgets.yaml`
- Create: `tests/harness/checks/test_performance_budgets.py`

### Task 6.1: Write the per-fixture mini-budget

Create `tests/harness/fixtures/performance_budgets/_test_budgets.yaml`:

```yaml
agent_budgets:
  tool_calls_max: 8
  tokens_max: 4000
  wall_clock_max_ms: 30000

db_query_max_ms: 100

bundle_kb:
  initial: 220
  route: 100
  css: 50
```

### Task 6.2: Write violation fixtures

```bash
mkdir -p tests/harness/fixtures/performance_budgets/{violation,compliant}
```

`violation/agent_missing_cost_hint.yaml`:

```yaml
name: log_agent
version: 1
tool_schema: {}
```

`violation/agent_exceeds_budget.yaml`:

```yaml
name: log_agent
version: 1
cost_hint:
  tool_calls_max: 99
  tokens_max: 100000
  wall_clock_max_ms: 60000
tool_schema: {}
```

`violation/gateway_no_timed_query.py`:

```python
"""Q12 violation — StorageGateway method without @timed_query.

Pretend-path: backend/src/storage/gateway.py
"""
class StorageGateway:
    async def get_incident(self, incident_id: str) -> None:
        pass
```

### Task 6.3: Write compliant fixtures

`compliant/agent_within_budget.yaml`:

```yaml
name: log_agent
version: 1
cost_hint:
  tool_calls_max: 4
  tokens_max: 2000
  wall_clock_max_ms: 10000
tool_schema: {}
```

`compliant/gateway_with_timed_query.py`:

```python
"""Q12 compliant — every gateway method decorated with @timed_query.

Pretend-path: backend/src/storage/gateway.py
"""
from backend.src.storage._timing import timed_query

class StorageGateway:
    @timed_query("get_incident")
    async def get_incident(self, incident_id: str) -> None:
        pass
```

### Task 6.4: Write the failing test

Create `tests/harness/checks/test_performance_budgets.py`:

```python
"""H.1a.6 — performance_budgets check tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness._helpers import assert_check_fires, assert_check_silent

CHECK = "performance_budgets"
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / CHECK
BUDGETS = FIXTURE_ROOT / "_test_budgets.yaml"


@pytest.mark.parametrize(
    "fixture_name,expected_rule,extra_args",
    [
        ("agent_missing_cost_hint.yaml", "Q12.agent-cost-hint-required", ["--budgets", str(BUDGETS)]),
        ("agent_exceeds_budget.yaml", "Q12.agent-budget-exceeded", ["--budgets", str(BUDGETS)]),
        ("gateway_no_timed_query.py", "Q12.gateway-needs-timed-query", ["--budgets", str(BUDGETS), "--pretend-path", "backend/src/storage/gateway.py"]),
    ],
)
def test_violation_fires(fixture_name: str, expected_rule: str, extra_args: list[str]) -> None:
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / fixture_name,
        expected_rule=expected_rule,
        extra_args=extra_args,
    )


@pytest.mark.parametrize(
    "fixture_name,extra_args",
    [
        ("agent_within_budget.yaml", ["--budgets", str(BUDGETS)]),
        ("gateway_with_timed_query.py", ["--budgets", str(BUDGETS), "--pretend-path", "backend/src/storage/gateway.py"]),
    ],
)
def test_compliant_silent(fixture_name: str, extra_args: list[str]) -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / fixture_name,
        extra_args=extra_args,
    )
```

### Task 6.5: Run failing test + commit red

```bash
python -m pytest tests/harness/checks/test_performance_budgets.py -v
git add tests/harness/fixtures/performance_budgets tests/harness/checks/test_performance_budgets.py
git commit -m "$(cat <<'EOF'
test(red): H.1a.6 — performance_budgets fixtures + assertions

Three violation fixtures (agent missing cost_hint; agent exceeds budget
caps; storage gateway method missing @timed_query) plus two compliant
counterparts. Mini budgets yaml under fixtures/ is forwarded via
--budgets flag.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 6.6: Implement the check

Create `.harness/checks/performance_budgets.py`:

```python
#!/usr/bin/env python3
"""Q12 — performance budgets.

Six rules:
  Q12.agent-cost-hint-required    — agent contract YAML missing cost_hint.* fields.
  Q12.agent-budget-exceeded       — cost_hint value above policy cap.
  Q12.gateway-needs-timed-query   — StorageGateway method without @timed_query.
  Q12.bundle-initial-too-big      — frontend initial bundle > 220 KB gz (parsed from stats.json).
  Q12.bundle-route-too-big        — per-route chunk > 100 KB gz.
  Q12.bundle-css-too-big          — total CSS > 50 KB gz.

H-25:
  Missing input    — exit 2.
  Malformed input  — WARN harness.unparseable.
  Upstream failed  — none.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from .harness.checks._common import Finding, Severity, emit  # noqa: E402

DEFAULT_BUDGETS = REPO_ROOT / ".harness" / "performance_budgets.yaml"
COST_HINT_FIELDS = ("tool_calls_max", "tokens_max", "wall_clock_max_ms")


def _load_budgets(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _scan_agent_yaml(path: Path, budgets: dict) -> Iterable[Finding]:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError) as exc:
        yield Finding(
            severity=Severity.WARN,
            file=path,
            line=1,
            rule="harness.unparseable",
            message=f"could not parse {path.name}: {exc}",
            suggestion="fix YAML syntax",
        )
        return
    cost_hint = data.get("cost_hint")
    if not isinstance(cost_hint, dict):
        yield Finding(
            severity=Severity.ERROR,
            file=path,
            line=1,
            rule="Q12.agent-cost-hint-required",
            message=f"agent contract {path.name} missing cost_hint section",
            suggestion="add `cost_hint: { tool_calls_max, tokens_max, wall_clock_max_ms }`",
        )
        return
    caps = budgets.get("agent_budgets") or {}
    for field in COST_HINT_FIELDS:
        if field not in cost_hint:
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=1,
                rule="Q12.agent-cost-hint-required",
                message=f"cost_hint missing `{field}`",
                suggestion=f"add cost_hint.{field}",
            )
            continue
        cap = caps.get(field)
        if cap is not None and isinstance(cost_hint[field], (int, float)) and cost_hint[field] > cap:
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=1,
                rule="Q12.agent-budget-exceeded",
                message=f"cost_hint.{field}={cost_hint[field]} exceeds cap {cap}",
                suggestion=f"reduce {field} to ≤ {cap} or raise cap with ADR",
            )


def _scan_gateway_python(path: Path) -> Iterable[Finding]:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "StorageGateway":
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if sub.name.startswith("_"):
                        continue
                    if not _has_timed_query(sub):
                        yield Finding(
                            severity=Severity.ERROR,
                            file=path,
                            line=sub.lineno,
                            rule="Q12.gateway-needs-timed-query",
                            message=f"StorageGateway.{sub.name} missing @timed_query",
                            suggestion='add @timed_query("<method-name>") to time the call',
                        )


def _has_timed_query(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for dec in fn.decorator_list:
        src = ast.dump(dec)
        if "timed_query" in src:
            return True
    return False


def _scan_stats_json(path: Path, budgets: dict) -> Iterable[Finding]:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return
    caps = budgets.get("bundle_kb") or {}
    initial_cap = caps.get("initial")
    route_cap = caps.get("route")
    css_cap = caps.get("css")
    # Common Vite stats shape: { "outputs": { "<file>": { "bytes": ... } } }
    outputs = data.get("outputs") or {}
    for name, info in outputs.items():
        size_kb = (info.get("bytes") or 0) / 1024.0
        if name.endswith(".css"):
            if css_cap and size_kb > css_cap:
                yield Finding(
                    severity=Severity.ERROR,
                    file=path,
                    line=1,
                    rule="Q12.bundle-css-too-big",
                    message=f"{name} = {size_kb:.0f}KB > cap {css_cap}KB",
                    suggestion="split CSS, drop unused selectors, audit Tailwind safelist",
                )
        elif "index" in name or "main" in name:
            if initial_cap and size_kb > initial_cap:
                yield Finding(
                    severity=Severity.ERROR,
                    file=path,
                    line=1,
                    rule="Q12.bundle-initial-too-big",
                    message=f"{name} = {size_kb:.0f}KB > cap {initial_cap}KB",
                    suggestion="lazy-import below-the-fold pages, audit vendor chunk",
                )
        else:
            if route_cap and size_kb > route_cap:
                yield Finding(
                    severity=Severity.ERROR,
                    file=path,
                    line=1,
                    rule="Q12.bundle-route-too-big",
                    message=f"{name} = {size_kb:.0f}KB > cap {route_cap}KB",
                    suggestion="split the route or hoist shared code into vendor chunk",
                )


def scan(targets: list[Path], budgets_path: Path, pretend_path: str | None) -> int:
    if not budgets_path.exists():
        emit(Finding(
            severity=Severity.ERROR,
            file=budgets_path,
            line=0,
            rule="harness.target-missing",
            message=f"budgets file does not exist: {budgets_path}",
            suggestion="seed .harness/performance_budgets.yaml (Sprint H.0b Story 5)",
        ))
        return 2
    budgets = _load_budgets(budgets_path)
    total_errors = 0
    for target in targets:
        if not target.exists():
            emit(Finding(
                severity=Severity.ERROR,
                file=target,
                line=0,
                rule="harness.target-missing",
                message=f"target does not exist: {target}",
                suggestion="pass an existing path",
            ))
            return 2
        files: list[Path]
        if target.is_file():
            files = [target]
        else:
            files = []
            for p in target.rglob("*"):
                if p.is_file() and (p.suffix in {".yaml", ".yml", ".py", ".json"}):
                    files.append(p)
        for path in files:
            virtual = pretend_path or (str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else path.name)
            if path.suffix in {".yaml", ".yml"} and ("agent" in path.name or "/contracts/" in virtual):
                for finding in _scan_agent_yaml(path, budgets):
                    emit(finding)
                    if finding.severity == Severity.ERROR:
                        total_errors += 1
            elif path.suffix == ".py" and (virtual.endswith("storage/gateway.py") or path.name == "gateway.py"):
                for finding in _scan_gateway_python(path):
                    emit(finding)
                    if finding.severity == Severity.ERROR:
                        total_errors += 1
            elif path.name == "stats.json":
                for finding in _scan_stats_json(path, budgets):
                    emit(finding)
                    if finding.severity == Severity.ERROR:
                        total_errors += 1
    return 1 if total_errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, action="append")
    parser.add_argument("--budgets", type=Path, default=DEFAULT_BUDGETS)
    parser.add_argument("--pretend-path", type=str)
    args = parser.parse_args(argv)
    targets = list(args.target) if args.target else [
        REPO_ROOT / "backend" / "src" / "contracts",
        REPO_ROOT / "backend" / "src" / "storage" / "gateway.py",
        REPO_ROOT / "frontend" / "dist" / "stats.json",
    ]
    return scan(targets, args.budgets, args.pretend_path)


if __name__ == "__main__":
    sys.exit(main())
```

### Task 6.7: Run tests + triage live + validate-fast

```bash
python -m pytest tests/harness/checks/test_performance_budgets.py -v
python .harness/checks/performance_budgets.py
python tools/run_validate.py --fast
```

### Task 6.8: Commit green

```bash
git add .harness/checks/performance_budgets.py
git commit -m "$(cat <<'EOF'
feat(green): H.1a.6 — performance_budgets enforces Q12

Six rules: agent contract YAML must declare cost_hint with all three
budget fields; values may not exceed policy caps; StorageGateway methods
must carry @timed_query; frontend bundle stats checked against bundle_kb
caps for initial/route/css. H-25 docstring included.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Story H.1a.7 — `audit_emission.py`

**Rule families enforced (1):** Every public method on `StorageGateway` whose name begins with `create_`, `update_`, `delete_`, `upsert_`, `merge_`, or `set_` MUST contain at least one call to `self._audit(...)` in its body. (Read methods exempt.)

**Files:**
- Create: `.harness/checks/audit_emission.py`
- Create: `tests/harness/fixtures/audit_emission/violation/missing_audit.py`
- Create: `tests/harness/fixtures/audit_emission/compliant/has_audit.py`
- Create: `tests/harness/checks/test_audit_emission.py`

### Task 7.1: Fixtures

```bash
mkdir -p tests/harness/fixtures/audit_emission/{violation,compliant}
```

`violation/missing_audit.py`:

```python
"""SL-rule violation — gateway write without _audit emission."""
class StorageGateway:
    async def create_incident(self, payload: dict) -> None:
        pass
```

`compliant/has_audit.py`:

```python
"""SL-rule compliant — write method emits an audit row."""
class StorageGateway:
    async def _audit(self, *args, **kwargs) -> None:
        pass

    async def create_incident(self, payload: dict) -> None:
        await self._audit("create_incident", payload)
```

### Task 7.2: Test

Create `tests/harness/checks/test_audit_emission.py`:

```python
"""H.1a.7 — audit_emission check tests."""

from __future__ import annotations

from pathlib import Path

from tests.harness._helpers import assert_check_fires, assert_check_silent

CHECK = "audit_emission"
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / CHECK


def test_violation_fires() -> None:
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / "missing_audit.py",
        expected_rule="SL.audit-emission-required",
        pretend_path="backend/src/storage/gateway.py",
    )


def test_compliant_silent() -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / "has_audit.py",
        pretend_path="backend/src/storage/gateway.py",
    )
```

### Task 7.3: Red commit

```bash
python -m pytest tests/harness/checks/test_audit_emission.py -v
git add tests/harness/fixtures/audit_emission tests/harness/checks/test_audit_emission.py
git commit -m "test(red): H.1a.7 — audit_emission fixtures + assertions

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 7.4: Implement the check

Create `.harness/checks/audit_emission.py`:

```python
#!/usr/bin/env python3
"""SL — every gateway write must call self._audit(...).

One rule:
  SL.audit-emission-required — public StorageGateway method whose name starts with
                                create_/update_/delete_/upsert_/merge_/set_ must
                                contain at least one `self._audit(...)` call.

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
sys.path.insert(0, str(REPO_ROOT))

from .harness.checks._common import Finding, Severity, emit, walk_python_files  # noqa: E402

DEFAULT_ROOTS = (REPO_ROOT / "backend" / "src" / "storage",)
EXCLUDE = ("__pycache__",)
WRITE_PREFIXES = ("create_", "update_", "delete_", "upsert_", "merge_", "set_")


def _has_audit_call(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_audit"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
        ):
            return True
    return False


def _scan_file(path: Path, virtual: str) -> Iterable[Finding]:
    if not virtual.endswith("storage/gateway.py") and path.name != "gateway.py":
        return
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, UnicodeDecodeError):
        return
    except SyntaxError:
        yield Finding(
            severity=Severity.WARN,
            file=path,
            line=1,
            rule="harness.unparseable",
            message=f"could not parse {path.name}",
            suggestion="fix syntax",
        )
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "StorageGateway":
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if any(sub.name.startswith(p) for p in WRITE_PREFIXES):
                        if not _has_audit_call(sub):
                            yield Finding(
                                severity=Severity.ERROR,
                                file=path,
                                line=sub.lineno,
                                rule="SL.audit-emission-required",
                                message=f"StorageGateway.{sub.name} writes but does not call self._audit",
                                suggestion="emit `await self._audit(\"<method>\", payload)` before commit",
                            )


def scan(roots: Iterable[Path], pretend_path: str | None) -> int:
    total_errors = 0
    for root in roots:
        if not root.exists():
            emit(Finding(
                severity=Severity.ERROR,
                file=root,
                line=0,
                rule="harness.target-missing",
                message=f"target path does not exist: {root}",
                suggestion="pass an existing file or directory via --target",
            ))
            return 2
        if root.is_file() and root.suffix == ".py":
            files = [(root, pretend_path or str(root.relative_to(REPO_ROOT)) if root.is_relative_to(REPO_ROOT) else pretend_path or root.name)]
        else:
            files = [
                (p, str(p.relative_to(REPO_ROOT)))
                for p in walk_python_files(root, exclude=EXCLUDE)
            ]
        for path, virtual in files:
            for finding in _scan_file(path, virtual):
                emit(finding)
                if finding.severity == Severity.ERROR:
                    total_errors += 1
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
```

### Task 7.5: Green run + validate-fast

```bash
python -m pytest tests/harness/checks/test_audit_emission.py -v
python .harness/checks/audit_emission.py
python tools/run_validate.py --fast
```

### Task 7.6: Commit green

```bash
git add .harness/checks/audit_emission.py
git commit -m "$(cat <<'EOF'
feat(green): H.1a.7 — audit_emission requires self._audit on writes

StorageGateway methods named create_/update_/delete_/upsert_/merge_/set_*
must contain at least one self._audit(...) call. Reads exempt.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Story H.1a.8 — `contract_typed.py`

**Rule families enforced (1):** No `Optional[Any]`, `dict[str, Any]`, or bare `: Any` annotations on fields of any class under `backend/src/models/api/`, `backend/src/models/agent/`, or `backend/src/learning/sidecars/`. (Untyped escape hatches kill the contract.)

**Files:**
- Create: `.harness/checks/contract_typed.py`
- Create: `tests/harness/fixtures/contract_typed/violation/optional_any.py`
- Create: `tests/harness/fixtures/contract_typed/violation/dict_str_any.py`
- Create: `tests/harness/fixtures/contract_typed/violation/bare_any.py`
- Create: `tests/harness/fixtures/contract_typed/compliant/typed.py`
- Create: `tests/harness/checks/test_contract_typed.py`

### Task 8.1: Fixtures

```bash
mkdir -p tests/harness/fixtures/contract_typed/{violation,compliant}
```

`violation/optional_any.py`:

```python
"""SL violation — Optional[Any] in sidecar.

Pretend-path: backend/src/learning/sidecars/observation.py
"""
from typing import Any, Optional
from pydantic import BaseModel

class Observation(BaseModel):
    payload: Optional[Any] = None
```

`violation/dict_str_any.py`:

```python
"""SL violation — dict[str, Any] field in agent schema.

Pretend-path: backend/src/models/agent/finding.py
"""
from typing import Any
from pydantic import BaseModel, ConfigDict

class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    metadata: dict[str, Any]
```

`violation/bare_any.py`:

```python
"""SL violation — bare Any annotation on an api field.

Pretend-path: backend/src/models/api/incident_response.py
"""
from typing import Any
from pydantic import BaseModel, ConfigDict

class IncidentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    extra: Any
```

`compliant/typed.py`:

```python
"""SL compliant — every field has a concrete type.

Pretend-path: backend/src/models/api/incident_response.py
"""
from pydantic import BaseModel, ConfigDict, Field

class IncidentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    incident_id: str = Field(..., min_length=1, max_length=64)
    severity: str = Field(..., min_length=1, max_length=16)
```

### Task 8.2: Test

```python
"""H.1a.8 — contract_typed check tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness._helpers import assert_check_fires, assert_check_silent

CHECK = "contract_typed"
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / CHECK


@pytest.mark.parametrize(
    "fixture_name,pretend_path",
    [
        ("optional_any.py", "backend/src/learning/sidecars/observation.py"),
        ("dict_str_any.py", "backend/src/models/agent/finding.py"),
        ("bare_any.py", "backend/src/models/api/incident_response.py"),
    ],
)
def test_violation_fires(fixture_name: str, pretend_path: str) -> None:
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / fixture_name,
        expected_rule="SL.contract-typed",
        pretend_path=pretend_path,
    )


def test_compliant_silent() -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / "typed.py",
        pretend_path="backend/src/models/api/incident_response.py",
    )
```

### Task 8.3: Red commit

```bash
python -m pytest tests/harness/checks/test_contract_typed.py -v
git add tests/harness/fixtures/contract_typed tests/harness/checks/test_contract_typed.py
git commit -m "test(red): H.1a.8 — contract_typed fixtures + assertions

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 8.4: Implement the check

Create `.harness/checks/contract_typed.py`:

```python
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
sys.path.insert(0, str(REPO_ROOT))

from .harness.checks._common import Finding, Severity, emit, walk_python_files  # noqa: E402

DEFAULT_ROOTS = (
    REPO_ROOT / "backend" / "src" / "models" / "api",
    REPO_ROOT / "backend" / "src" / "models" / "agent",
    REPO_ROOT / "backend" / "src" / "learning" / "sidecars",
)
EXCLUDE = ("__pycache__",)
GUARDED_PREFIXES = (
    "backend/src/models/api/",
    "backend/src/models/agent/",
    "backend/src/learning/sidecars/",
)


def _is_any(node: ast.AST | None) -> bool:
    if node is None:
        return False
    if isinstance(node, ast.Name) and node.id == "Any":
        return True
    if isinstance(node, ast.Attribute) and node.attr == "Any":
        return True
    return False


def _is_optional_any(node: ast.AST | None) -> bool:
    # Optional[Any]
    if (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id == "Optional"
        and _is_any(node.slice)
    ):
        return True
    # X | None or None | X where X is Any
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return (_is_any(node.left) and _is_none(node.right)) or (_is_any(node.right) and _is_none(node.left))
    return False


def _is_none(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


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


def _scan_file(path: Path, virtual: str) -> Iterable[Finding]:
    if not any(virtual.startswith(p) for p in GUARDED_PREFIXES):
        return
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, UnicodeDecodeError):
        return
    except SyntaxError:
        yield Finding(
            severity=Severity.WARN,
            file=path,
            line=1,
            rule="harness.unparseable",
            message=f"could not parse {path.name}",
            suggestion="fix syntax",
        )
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    ann = stmt.annotation
                    if _is_any(ann) or _is_optional_any(ann) or _is_dict_str_any(ann):
                        yield Finding(
                            severity=Severity.ERROR,
                            file=path,
                            line=stmt.lineno,
                            rule="SL.contract-typed",
                            message=f"field `{stmt.target.id}` annotated with Any-shaped type",
                            suggestion="declare a concrete type or a specific union",
                        )


def scan(roots: Iterable[Path], pretend_path: str | None) -> int:
    total_errors = 0
    for root in roots:
        if not root.exists():
            continue  # tolerate missing optional dirs
        if root.is_file() and root.suffix == ".py":
            files = [(root, pretend_path or str(root.relative_to(REPO_ROOT)) if root.is_relative_to(REPO_ROOT) else pretend_path or root.name)]
        else:
            files = [
                (p, str(p.relative_to(REPO_ROOT)))
                for p in walk_python_files(root, exclude=EXCLUDE)
            ]
        for path, virtual in files:
            for finding in _scan_file(path, virtual):
                emit(finding)
                if finding.severity == Severity.ERROR:
                    total_errors += 1
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
```

### Task 8.5: Green test, triage live, validate-fast

```bash
python -m pytest tests/harness/checks/test_contract_typed.py -v
python .harness/checks/contract_typed.py
python tools/run_validate.py --fast
```

### Task 8.6: Commit green

```bash
git add .harness/checks/contract_typed.py
git commit -m "$(cat <<'EOF'
feat(green): H.1a.8 — contract_typed bans Any escape hatches

Pydantic field annotations under models/api, models/agent, and
learning/sidecars may not be Any, Optional[Any], or dict[str, Any].

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Story H.1a.9 — `todo_in_prod.py`

**Rule families enforced (1):** `# TODO`, `# FIXME`, `# XXX`, or `# HACK` outside `tests/`, `docs/`, `tests/harness/fixtures/`, `.harness/`, `frontend/e2e/` → ERROR.

**Files:**
- Create: `.harness/checks/todo_in_prod.py`
- Create: `tests/harness/fixtures/todo_in_prod/violation/has_todo.py`
- Create: `tests/harness/fixtures/todo_in_prod/compliant/clean.py`
- Create: `tests/harness/checks/test_todo_in_prod.py`

### Task 9.1: Fixtures

```bash
mkdir -p tests/harness/fixtures/todo_in_prod/{violation,compliant}
```

`violation/has_todo.py`:

```python
"""Q-discipline violation — TODO in production source.

Pretend-path: backend/src/services/ingest.py
"""
def ingest() -> None:
    # TODO: handle the ratelimit case properly
    return None
```

`compliant/clean.py`:

```python
"""No TODO marker.

Pretend-path: backend/src/services/ingest.py
"""
def ingest() -> None:
    return None
```

### Task 9.2: Test

Create `tests/harness/checks/test_todo_in_prod.py`:

```python
"""H.1a.9 — todo_in_prod check tests."""

from __future__ import annotations

from pathlib import Path

from tests.harness._helpers import assert_check_fires, assert_check_silent

CHECK = "todo_in_prod"
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / CHECK


def test_violation_fires() -> None:
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / "has_todo.py",
        expected_rule="discipline.todo-in-prod",
        pretend_path="backend/src/services/ingest.py",
    )


def test_compliant_silent() -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / "clean.py",
        pretend_path="backend/src/services/ingest.py",
    )
```

### Task 9.3: Red commit

```bash
python -m pytest tests/harness/checks/test_todo_in_prod.py -v
git add tests/harness/fixtures/todo_in_prod tests/harness/checks/test_todo_in_prod.py
git commit -m "test(red): H.1a.9 — todo_in_prod fixtures + assertions

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 9.4: Implement

Create `.harness/checks/todo_in_prod.py`:

```python
#!/usr/bin/env python3
"""discipline — no TODO/FIXME/XXX/HACK in production paths.

One rule:
  discipline.todo-in-prod — comment marker outside tests/, docs/, .harness/,
                            tests/harness/fixtures/, frontend/e2e/.

H-25 — same defaults as siblings.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from .harness.checks._common import Finding, Severity, emit  # noqa: E402

DEFAULT_ROOTS = (REPO_ROOT / "backend" / "src", REPO_ROOT / "frontend" / "src")
EXEMPT_PREFIXES = (
    "tests/",
    "docs/",
    ".harness/",
    "tests/harness/",
    "frontend/e2e/",
    "backend/tests/",
)
MARKER_RE = re.compile(r"^\s*(#|//)\s*(TODO|FIXME|XXX|HACK)\b")


def _is_exempt(virtual: str) -> bool:
    return any(virtual.startswith(p) for p in EXEMPT_PREFIXES)


def _scan_file(path: Path, virtual: str) -> Iterable[Finding]:
    if _is_exempt(virtual):
        return
    if path.suffix not in {".py", ".ts", ".tsx", ".js", ".jsx"}:
        return
    try:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            m = MARKER_RE.match(line)
            if m:
                yield Finding(
                    severity=Severity.ERROR,
                    file=path,
                    line=lineno,
                    rule="discipline.todo-in-prod",
                    message=f"`{m.group(2)}` marker in production file",
                    suggestion="resolve, file an issue, or move to docs/decisions/",
                )
    except (OSError, UnicodeDecodeError):
        return


def scan(roots: Iterable[Path], pretend_path: str | None) -> int:
    total_errors = 0
    for root in roots:
        if not root.exists():
            continue
        if root.is_file():
            virtual = pretend_path or (str(root.relative_to(REPO_ROOT)) if root.is_relative_to(REPO_ROOT) else root.name)
            for finding in _scan_file(root, virtual):
                emit(finding)
                if finding.severity == Severity.ERROR:
                    total_errors += 1
        else:
            for p in root.rglob("*"):
                if not p.is_file():
                    continue
                virtual = str(p.relative_to(REPO_ROOT)) if p.is_relative_to(REPO_ROOT) else p.name
                for finding in _scan_file(p, virtual):
                    emit(finding)
                    if finding.severity == Severity.ERROR:
                        total_errors += 1
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
```

### Task 9.5: Green + triage + validate-fast + commit

```bash
python -m pytest tests/harness/checks/test_todo_in_prod.py -v
python .harness/checks/todo_in_prod.py
python tools/run_validate.py --fast
git add .harness/checks/todo_in_prod.py
git commit -m "$(cat <<'EOF'
feat(green): H.1a.9 — todo_in_prod blocks TODO/FIXME/XXX/HACK in source

Comment markers in backend/src and frontend/src raise ERROR. Tests,
docs, .harness/, e2e exempt.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Story H.1a.10 — `storage_isolation.py`

**Rule families enforced (1):** `cursor.execute(`, `connection.execute(`, `session.execute(`, `engine.execute(`, `conn.execute(` outside `backend/src/storage/` → ERROR. (Complements Q8 with a textual fallback that catches any naming variant the AST scan in `backend_db_layer.py` missed.)

**Files:**
- Create: `.harness/checks/storage_isolation.py`
- Create: `tests/harness/fixtures/storage_isolation/violation/uses_session_execute.py`
- Create: `tests/harness/fixtures/storage_isolation/compliant/inside_storage.py`
- Create: `tests/harness/checks/test_storage_isolation.py`

### Task 10.1: Fixtures

```bash
mkdir -p tests/harness/fixtures/storage_isolation/{violation,compliant}
```

`violation/uses_session_execute.py`:

```python
"""Storage isolation violation — session.execute outside storage/.

Pretend-path: backend/src/api/admin.py
"""
def adhoc(session) -> None:
    session.execute("SELECT 1")
```

`compliant/inside_storage.py`:

```python
"""Storage isolation compliant — execute inside storage/ module.

Pretend-path: backend/src/storage/gateway.py
"""
def query(session) -> None:
    session.execute("SELECT 1")
```

### Task 10.2: Test

Create `tests/harness/checks/test_storage_isolation.py`:

```python
"""H.1a.10 — storage_isolation check tests."""

from __future__ import annotations

from pathlib import Path

from tests.harness._helpers import assert_check_fires, assert_check_silent

CHECK = "storage_isolation"
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / CHECK


def test_violation_fires() -> None:
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / "uses_session_execute.py",
        expected_rule="storage.execute-outside-gateway",
        pretend_path="backend/src/api/admin.py",
    )


def test_compliant_silent() -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / "inside_storage.py",
        pretend_path="backend/src/storage/gateway.py",
    )
```

### Task 10.3: Red commit

```bash
python -m pytest tests/harness/checks/test_storage_isolation.py -v
git add tests/harness/fixtures/storage_isolation tests/harness/checks/test_storage_isolation.py
git commit -m "test(red): H.1a.10 — storage_isolation fixtures + assertions

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 10.4: Implement

Create `.harness/checks/storage_isolation.py`:

```python
#!/usr/bin/env python3
"""storage — every X.execute(...) call lives inside backend/src/storage/.

One rule:
  storage.execute-outside-gateway — `<name>.execute(...)` where <name> is
                                     cursor/connection/session/engine/conn,
                                     outside backend/src/storage/.

H-25 — same defaults as siblings.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from .harness.checks._common import Finding, Severity, emit, walk_python_files  # noqa: E402

DEFAULT_ROOTS = (REPO_ROOT / "backend" / "src",)
EXCLUDE = ("__pycache__", "tests/harness/fixtures")
EXECUTE_RE = re.compile(r"\b(cursor|connection|session|engine|conn)\.execute\s*\(")
STORAGE_PREFIX = "backend/src/storage"


def _scan_file(path: Path, virtual: str) -> Iterable[Finding]:
    if virtual.startswith(STORAGE_PREFIX + "/") or virtual == STORAGE_PREFIX:
        return
    try:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            m = EXECUTE_RE.search(line)
            if m:
                yield Finding(
                    severity=Severity.ERROR,
                    file=path,
                    line=lineno,
                    rule="storage.execute-outside-gateway",
                    message=f"`{m.group(1)}.execute(...)` outside backend/src/storage/",
                    suggestion="add a method to StorageGateway and route through it",
                )
    except (OSError, UnicodeDecodeError):
        return


def scan(roots: Iterable[Path], pretend_path: str | None) -> int:
    total_errors = 0
    for root in roots:
        if not root.exists():
            continue
        if root.is_file() and root.suffix == ".py":
            virtual = pretend_path or (str(root.relative_to(REPO_ROOT)) if root.is_relative_to(REPO_ROOT) else root.name)
            for finding in _scan_file(root, virtual):
                emit(finding)
                if finding.severity == Severity.ERROR:
                    total_errors += 1
        else:
            for p in walk_python_files(root, exclude=EXCLUDE):
                virtual = str(p.relative_to(REPO_ROOT)) if p.is_relative_to(REPO_ROOT) else p.name
                for finding in _scan_file(p, virtual):
                    emit(finding)
                    if finding.severity == Severity.ERROR:
                        total_errors += 1
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
```

### Task 10.5: Green + triage + validate-fast

```bash
python -m pytest tests/harness/checks/test_storage_isolation.py -v
python .harness/checks/storage_isolation.py
python tools/run_validate.py --fast
```

### Task 10.6: Commit green

```bash
git add .harness/checks/storage_isolation.py
git commit -m "$(cat <<'EOF'
feat(green): H.1a.10 — storage_isolation blocks execute outside storage/

Textual scan: any of cursor/connection/session/engine/conn .execute(...)
outside backend/src/storage/ raises ERROR. Complements Q8 AST check.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## End-of-sprint acceptance verification

Run from the repo root:

```bash
# 1. All H.1a check tests pass.
python -m pytest tests/harness/checks/ -v

# 2. validate-fast picks up all ten new checks.
python tools/run_validate.py --fast 2>&1 | grep -E "check:(backend_async_correctness|backend_db_layer|backend_testing|backend_validation_contracts|dependency_policy|performance_budgets|audit_emission|contract_typed|todo_in_prod|storage_isolation)" | wc -l
# Expected: 10

# 3. validate-fast finishes under 30s.
time python tools/run_validate.py --fast
# Expected: real time < 30s.

# 4. Each check ships paired fixtures.
ls tests/harness/fixtures | sort
# Expected (at minimum):
#   audit_emission backend_async_correctness backend_db_layer backend_testing
#   backend_validation_contracts contract_typed dependency_policy
#   performance_budgets storage_isolation todo_in_prod

# 5. No check has stub output (every violation fixture emits ≥ 1 ERROR).
for f in tests/harness/fixtures/*/violation/*; do
  rule_dir=$(basename $(dirname $(dirname $f)))
  python .harness/checks/${rule_dir}.py --target $f >/dev/null 2>&1
  rc=$?
  if [ $rc -eq 0 ]; then echo "FAIL: $f did not fire"; fi
done
# Expected: no FAIL output.

# 6. Each check carries an H-25 docstring.
for f in .harness/checks/{backend_async_correctness,backend_db_layer,backend_testing,backend_validation_contracts,dependency_policy,performance_budgets,audit_emission,contract_typed,todo_in_prod,storage_isolation}.py; do
  grep -q "Missing input" $f || echo "MISSING H-25 docstring: $f"
done
# Expected: no MISSING output.

# 7. Output format conformance: every emitted line matches H-16/H-23.
python tools/run_validate.py --fast 2>&1 | grep -E '^\[(ERROR|WARN|INFO)\]' | head -20
# Expected: lines like `[ERROR] file=… rule=… message="…" suggestion="…"`.
```

---

## Definition of Done — Sprint H.1a

- [ ] All 10 stories' tests pass under `pytest tests/harness/checks/ -v`.
- [ ] All 10 checks discovered by `tools/run_validate.py --fast`.
- [ ] `validate-fast` total wall time < 30s.
- [ ] Every check has paired violation + compliant fixtures (H-24).
- [ ] Every check's docstring covers the three H-25 questions.
- [ ] Every check's output conforms to H-16/H-23 (validated by step 7 above; `output_format_conformance.py` arrives in H.1b but a manual grep covers the gap).
- [ ] Live-repo runs triaged: each check either reports zero ERROR on the live repo, OR documented baseline entries exist (deferred to H.1d.1) with a tracking issue per baselined finding.
- [ ] No `# TODO` markers introduced anywhere except inside `tests/harness/fixtures/`.
- [ ] Each story committed as red → green pair with the canonical commit message shape.

---

**Plan complete and saved to `docs/plans/2026-04-26-harness-sprint-h1a-tasks.md`.**

Two execution options:

1. **Subagent-Driven (this session)** — I dispatch fresh subagent per task, review between tasks, fast iteration.
2. **Parallel Session (separate)** — Open new session with `executing-plans`, batch execution with checkpoints.

Or **hold** and confirm before I author Sprint H.1b.
