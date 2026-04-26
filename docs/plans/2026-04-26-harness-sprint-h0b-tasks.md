# Harness Sprint H.0b — Per-Task Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Wire up every config + helper module that the Q5–Q19 stack-decision checks (Sprint H.1a–H.1d) will need to operate. Twelve small, mostly-tactical stories. No business logic, no rule enforcement yet — just the scaffolding that the checks will plug into.

**Architecture:** Each story stands up one piece of foundational infrastructure: a config file, a third-party tool installed and minimally configured, a Python helper module wired with skeleton functions and unit tests. Together they form the substrate the H.1 sprints assume exists.

**Tech Stack:** Python 3.14, PyYAML (already a dep), pytest + Hypothesis, mypy, structlog + opentelemetry-api/sdk + opentelemetry-instrumentation-{fastapi,httpx,sqlalchemy}, tenacity, alembic, slowapi, gitleaks (binary), eslint-plugin-jsx-a11y + vitest-axe + @axe-core/playwright + @commitlint/cli + @commitlint/config-conventional + eslint-plugin-import + eslint-plugin-jsdoc.

**Reference docs:**
- [Consolidated harness plan](./2026-04-26-ai-harness.md) — locked decisions Q5–Q19.
- [Sprint H.0a per-task plan](./2026-04-26-harness-sprint-h0a-tasks.md) — substrate that H.0b builds on.

**Prerequisites:** Sprint H.0a complete and committed (Makefile, loader, root CLAUDE.md, harness self-checks all present).

---

## Story map for Sprint H.0b

| Story | Title | Tasks | Pts |
|---|---|---|---|
| H.0b.1 | Vitest config (Q5) — coverage thresholds + Playwright project | 1.1 – 1.6 | 2 |
| H.0b.2 | Alembic init + baseline migration (Q8) | 2.1 – 2.7 | 3 |
| H.0b.3 | pytest-cov + diff-cover + Hypothesis (Q9) | 3.1 – 3.5 | 2 |
| H.0b.4 | `.harness/dependencies.yaml` (Q11) seeded + schema validator | 4.1 – 4.6 | 2 |
| H.0b.5 | `.harness/performance_budgets.yaml` (Q12) + `@timed_query` + `assert_within_budget` | 5.1 – 5.8 | 3 |
| H.0b.6 | gitleaks installed + `.gitleaks.toml` + slowapi installed (Q13) | 6.1 – 6.5 | 3 |
| H.0b.7 | eslint-plugin-jsx-a11y + vitest-axe + @axe-core/playwright (Q14) | 7.1 – 7.5 | 2 |
| H.0b.8 | `docs/decisions/_TEMPLATE.md` + ruff D-class + eslint-plugin-jsdoc (Q15) | 8.1 – 8.6 | 2 |
| H.0b.9 | structlog + OpenTelemetry SDKs + observability/{logging,tracing}.py + frontend errorReporter (Q16) | 9.1 – 9.10 | 5 |
| H.0b.10 | `src/errors/Result.py` + `src/utils/http.py` (`with_retry`) + `src/api/problem.py` + `<ErrorBoundary>` + tenacity (Q17) | 10.1 – 10.10 | 5 |
| H.0b.11 | eslint + commitlint + ruff isort + tsconfig path alias + vite alias (Q18) | 11.1 – 11.7 | 3 |
| H.0b.12 | mypy strict per-module config + tsconfig strict + initial baselines (Q19) | 12.1 – 12.6 | 3 |

**Total: 12 stories, ~30 points, 2 weeks.**

---

# Story H.0b.1 — Vitest config + Playwright project skeleton (Q5)

**Files:**
- Modify: `frontend/vitest.config.ts` (or create if missing)
- Create: `frontend/playwright.config.ts` (if missing)
- Create: `frontend/e2e/.gitkeep`
- Create: `frontend/e2e/a11y/.gitkeep`
- Test: `tests/harness/configs/test_vitest_config.py`

### Task 1.1: Write the failing test

Create `tests/harness/configs/__init__.py` (empty) and `tests/harness/configs/test_vitest_config.py`:

```python
"""Sprint H.0b Story 1 — vitest.config.ts must declare per-path coverage
thresholds matching Q5 of the harness plan."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
VITEST_CONFIG = REPO_ROOT / "frontend/vitest.config.ts"
PLAYWRIGHT_CONFIG = REPO_ROOT / "frontend/playwright.config.ts"


def test_vitest_config_exists() -> None:
    assert VITEST_CONFIG.is_file()


def test_vitest_config_declares_coverage() -> None:
    text = VITEST_CONFIG.read_text()
    assert "coverage" in text, "vitest config must enable coverage"
    # Thresholds keyed by glob; per Q5 services/api ≥ 90%, hooks ≥ 85%
    assert re.search(r"frontend/src/services/api", text), (
        "coverage thresholds must target services/api"
    )
    assert re.search(r"frontend/src/hooks", text), (
        "coverage thresholds must target hooks"
    )


def test_vitest_config_threshold_for_services_api_is_90() -> None:
    text = VITEST_CONFIG.read_text()
    # Loose check: a `0.9` or `90` near the services/api path
    section = text[text.index("services/api"):text.index("services/api") + 400]
    assert "0.9" in section or "90" in section


def test_vitest_config_threshold_for_hooks_is_85() -> None:
    text = VITEST_CONFIG.read_text()
    section = text[text.index("hooks"):text.index("hooks") + 400]
    assert "0.85" in section or "85" in section


def test_playwright_config_exists() -> None:
    assert PLAYWRIGHT_CONFIG.is_file()


def test_playwright_quarantines_e2e_dir() -> None:
    text = PLAYWRIGHT_CONFIG.read_text()
    assert "frontend/e2e" in text or "./e2e" in text or "'e2e'" in text, (
        "playwright config must point at the frontend/e2e directory"
    )
```

### Task 1.2: Run tests to verify they fail

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
python -m pytest ../tests/harness/configs/test_vitest_config.py -v
```

Expected: every test fails with `vitest.config.ts` missing or assertion errors.

### Task 1.3: Commit failing tests

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
git add tests/harness/configs/__init__.py tests/harness/configs/test_vitest_config.py
git commit -m "test(red): H.0b.1 — vitest + playwright config contract (Q5)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 1.4: Write `vitest.config.ts`

Create or replace `frontend/vitest.config.ts`:

```typescript
/// <reference types="vitest" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Q5 — Vitest for unit/integration. Per-path hard coverage gate:
//   services/api/ ≥ 90%   (the contract layer; silent breakage = bugs)
//   hooks/        ≥ 85%   (the orchestrators)
// Other paths report coverage but don't gate.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    // Q5: e2e tests live under frontend/e2e/ and are run by Playwright.
    // Vitest must not pick them up.
    exclude: [
      "node_modules/**",
      "dist/**",
      "e2e/**",
      ".idea",
      ".git",
      ".cache",
    ],
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "html"],
      // Locked Q5 path-targeted thresholds. Files outside these globs
      // still report coverage but don't gate.
      thresholds: {
        "frontend/src/services/api/**": {
          branches: 0.9,
          functions: 0.9,
          lines: 0.9,
          statements: 0.9,
        },
        "frontend/src/hooks/**": {
          branches: 0.85,
          functions: 0.85,
          lines: 0.85,
          statements: 0.85,
        },
      },
    },
  },
});
```

### Task 1.5: Write `playwright.config.ts` and quarantine directories

Create `frontend/playwright.config.ts`:

```typescript
import { defineConfig, devices } from "@playwright/test";

// Q5 — Playwright e2e specs are quarantined under frontend/e2e/.
// Vitest excludes this directory; Playwright owns it exclusively.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: "html",
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:5173",
    trace: "on-first-retry",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
```

Create the quarantine directories:

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
mkdir -p frontend/e2e/a11y
touch frontend/e2e/.gitkeep frontend/e2e/a11y/.gitkeep
```

### Task 1.6: Run tests to verify they pass, then commit

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
python -m pytest ../tests/harness/configs/test_vitest_config.py -v
```

Expected: all 6 tests pass.

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
git add frontend/vitest.config.ts frontend/playwright.config.ts \
        frontend/e2e/.gitkeep frontend/e2e/a11y/.gitkeep
git commit -m "feat(green): H.0b.1 — vitest path-targeted coverage + playwright e2e dir

Coverage gates: services/api ≥ 90%, hooks ≥ 85% (Q5). Vitest excludes
frontend/e2e/, Playwright owns it. e2e/a11y/ scaffolded for Q14
accessibility specs.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

# Story H.0b.2 — Alembic init + baseline migration (Q8)

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/.gitkeep`
- Create: `backend/alembic/versions/<timestamp>_baseline.py`
- Test: `tests/harness/configs/test_alembic.py`

### Task 2.1: Add alembic to backend deps

Modify `backend/requirements.txt` (append):

```
alembic>=1.13.0
```

Install:

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
pip install -q alembic
```

### Task 2.2: Write the failing test

Create `tests/harness/configs/test_alembic.py`:

```python
"""Sprint H.0b Story 2 — Alembic scaffolded for Q8 migrations."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "backend/alembic.ini"
ENV_PY = REPO_ROOT / "backend/alembic/env.py"
VERSIONS_DIR = REPO_ROOT / "backend/alembic/versions"


def test_alembic_ini_exists() -> None:
    assert ALEMBIC_INI.is_file()


def test_alembic_env_exists() -> None:
    assert ENV_PY.is_file()


def test_alembic_versions_dir_exists() -> None:
    assert VERSIONS_DIR.is_dir()


def test_alembic_baseline_migration_exists() -> None:
    """At least one migration file under versions/ named *_baseline.py."""
    candidates = list(VERSIONS_DIR.glob("*_baseline.py"))
    assert candidates, "expected a baseline migration in alembic/versions/"


def test_alembic_history_runs_cleanly() -> None:
    """`alembic history` exits 0 once env.py is wired correctly."""
    result = subprocess.run(
        ["alembic", "history"],
        cwd=REPO_ROOT / "backend",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"alembic history failed: stderr={result.stderr}"
    )
```

### Task 2.3: Run tests to confirm they fail

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
python -m pytest ../tests/harness/configs/test_alembic.py -v
```

Expected: every test fails (alembic not initialized).

### Task 2.4: Commit failing tests

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
git add tests/harness/configs/test_alembic.py backend/requirements.txt
git commit -m "test(red): H.0b.2 — alembic scaffolding contract (Q8)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 2.5: Initialize alembic

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
alembic init alembic
```

This creates `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/`, and `alembic/README` (delete the README).

```bash
rm alembic/README
touch alembic/versions/.gitkeep
```

### Task 2.6: Configure async + sqlite + first baseline

Edit `backend/alembic.ini` — change the `sqlalchemy.url` line:

```
sqlalchemy.url = sqlite+aiosqlite:///./data/learning.db
```

(Or whatever your real DB URL is once the learning DB is wired; for Sprint H.0b a placeholder pointed at the existing data dir is enough.)

Edit `backend/alembic/env.py` — replace contents:

```python
"""Alembic env — async-aware, reads the URL from alembic.ini and
runs against the learning DB (Q8)."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import models so autogenerate sees them. For now, target_metadata is
# None — we'll wire it once Sprint H.0a's models/db/ exists. Migrations
# remain hand-written until then.
target_metadata = None


def run_migrations_offline() -> None:
    """Generate SQL without a live connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

Generate the baseline migration:

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
alembic revision -m "baseline"
```

This produces `backend/alembic/versions/<rev>_baseline.py`. The body is empty — that's correct for v1; tables get added in subsequent migrations.

### Task 2.7: Run tests, then commit

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
python -m pytest ../tests/harness/configs/test_alembic.py -v
```

Expected: all 5 tests pass.

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
git add backend/alembic.ini backend/alembic/env.py backend/alembic/script.py.mako \
        backend/alembic/versions/
git commit -m "feat(green): H.0b.2 — alembic init + baseline migration (Q8)

Async-aware env.py reads URL from alembic.ini, runs against the
learning DB. Baseline revision is empty — concrete tables are added
by future migrations as models/db/ fills in.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

# Story H.0b.3 — pytest-cov + diff-cover + Hypothesis (Q9)

**Files:**
- Modify: `backend/requirements.txt` (or `requirements-dev.txt`)
- Modify: `backend/pyproject.toml`
- Test: `tests/harness/configs/test_pytest_config.py`

### Task 3.1: Write the failing test

Create `tests/harness/configs/test_pytest_config.py`:

```python
"""Sprint H.0b Story 3 — pytest + Hypothesis + coverage tooling per Q9."""

from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PYPROJECT = REPO_ROOT / "backend/pyproject.toml"


def _pyproject() -> dict:
    return tomllib.loads(PYPROJECT.read_text())


def test_pyproject_pytest_section_exists() -> None:
    cfg = _pyproject()
    assert "tool" in cfg
    assert "pytest" in cfg["tool"]


def test_pytest_asyncio_mode_strict() -> None:
    cfg = _pyproject()
    inicfg = cfg["tool"]["pytest"]["ini_options"]
    assert inicfg.get("asyncio_mode") in ("strict", "auto"), (
        "asyncio_mode must be set"
    )


def test_pytest_marks_property_and_slow_registered() -> None:
    cfg = _pyproject()
    marks = cfg["tool"]["pytest"]["ini_options"].get("markers", [])
    marks_text = "\n".join(marks) if isinstance(marks, list) else str(marks)
    for tag in ("property:", "slow:"):
        assert tag in marks_text, f"pytest marker `{tag}` must be registered"


def test_hypothesis_importable() -> None:
    """Hypothesis library is installed."""
    result = subprocess.run(
        ["python", "-c", "import hypothesis; print(hypothesis.__version__)"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, "hypothesis must be installed"


def test_pytest_cov_importable() -> None:
    result = subprocess.run(
        ["python", "-c", "import pytest_cov"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, "pytest-cov must be installed"


def test_diff_cover_importable() -> None:
    result = subprocess.run(
        ["python", "-c", "import diff_cover"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, "diff-cover must be installed"
```

### Task 3.2: Run tests to verify they fail

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
python -m pytest ../tests/harness/configs/test_pytest_config.py -v
```

Expected: failures for missing pytest config and (depending on local environment) missing libraries.

### Task 3.3: Install deps + configure pyproject.toml

Append to `backend/requirements.txt` (or your dev-deps file):

```
pytest-cov>=4.1.0
diff-cover>=8.0.0
hypothesis>=6.92.0
respx>=0.20.0
```

Install:

```bash
pip install -q pytest-cov diff-cover hypothesis respx
```

Add or modify `[tool.pytest.ini_options]` in `backend/pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "strict"
testpaths = ["backend/tests", "tests/harness"]
markers = [
    "property: Hypothesis property-based test (slower; skip with -m 'not property').",
    "slow: integration / slow test (skip with -m 'not slow').",
]
addopts = [
    "--strict-markers",
    "-q",
]
```

### Task 3.4: Commit failing tests, then green

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
git add tests/harness/configs/test_pytest_config.py backend/requirements.txt
git commit -m "test(red): H.0b.3 — pytest + Hypothesis + coverage tooling contract (Q9)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"

git add backend/pyproject.toml
git commit -m "feat(green): H.0b.3 — pytest config with property/slow marks + Hypothesis + diff-cover

asyncio_mode strict; markers registered; pytest-cov, diff-cover,
hypothesis, respx installed. Q9 patch-coverage gate (≥90%) is enforced
later by tools/run_validate.py wiring (Sprint H.1a).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 3.5: Verify pytest still finds harness tests

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
python -m pytest ../tests/harness/ -q
```

Expected: every harness test still passes (we didn't change any test, just the config).

---

# Story H.0b.4 — `.harness/dependencies.yaml` (Q11) seeded + schema validator

**Files:**
- Create: `.harness/dependencies.yaml`
- Create: `tools/validate_dependencies_yaml.py`
- Test: `tests/harness/configs/test_dependencies_yaml.py`

### Task 4.1: Write the failing test

Create `tests/harness/configs/test_dependencies_yaml.py`:

```python
"""Sprint H.0b Story 4 — .harness/dependencies.yaml seeded + valid (Q11)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
DEPS_YAML = REPO_ROOT / ".harness/dependencies.yaml"
VALIDATOR = REPO_ROOT / "tools/validate_dependencies_yaml.py"


def test_dependencies_yaml_exists() -> None:
    assert DEPS_YAML.is_file()


def test_dependencies_yaml_loads() -> None:
    yaml.safe_load(DEPS_YAML.read_text())


def test_dependencies_yaml_has_required_top_level() -> None:
    data = yaml.safe_load(DEPS_YAML.read_text())
    for key in ("version", "spine_paths", "whitelist", "blacklist", "audit"):
        assert key in data, f"dependencies.yaml missing top-level `{key}`"


def test_dependencies_yaml_blacklist_includes_known_banned() -> None:
    data = yaml.safe_load(DEPS_YAML.read_text())
    banned = data["blacklist"]["global"]
    for must in ("requests", "axios", "redux", "jest", "moment"):
        assert must in banned, f"global blacklist should include `{must}` (Q1/Q2/Q5/Q7)"


def test_validator_exists() -> None:
    assert VALIDATOR.is_file()


def test_validator_passes_on_seeded_yaml() -> None:
    result = subprocess.run(
        ["python", str(VALIDATOR)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"validator should pass on seeded yaml: {result.stderr}"
    )
```

### Task 4.2: Run, commit failing tests

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
python -m pytest ../tests/harness/configs/test_dependencies_yaml.py -v
```

Expected: all fail.

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
git add tests/harness/configs/test_dependencies_yaml.py
git commit -m "test(red): H.0b.4 — dependencies.yaml + validator contract (Q11)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 4.3: Write the seeded `.harness/dependencies.yaml`

Use the canonical config from the harness plan §2 Q11 — paste verbatim from `docs/plans/2026-04-26-ai-harness.md` Q11 section into `.harness/dependencies.yaml`. (Reproduce the YAML there exactly: `version: 1`, `spine_paths`, `whitelist.backend_spine`, `whitelist.frontend_spine`, `blacklist.global`, `audit`.)

### Task 4.4: Write the schema validator

Create `tools/validate_dependencies_yaml.py`:

```python
#!/usr/bin/env python3
"""Schema-validate .harness/dependencies.yaml.

Runs in `make validate-fast` (wired by Sprint H.1a). Catches malformed
YAML or missing required keys at PR time, not at the moment a check
tries to read it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEPS_YAML = REPO_ROOT / ".harness/dependencies.yaml"

REQUIRED_TOP_LEVEL = ["version", "spine_paths", "whitelist", "blacklist", "audit"]
REQUIRED_SPINE_PATHS = ["backend", "frontend"]
REQUIRED_WHITELIST_SECTIONS = ["backend_spine", "frontend_spine"]
REQUIRED_BLACKLIST_SECTIONS = ["global"]
REQUIRED_AUDIT_KEYS = [
    "trigger_paths", "backend_command", "frontend_command", "block_on", "warn_on",
]


def _err(msg: str) -> None:
    print(f"[ERROR] file={DEPS_YAML.relative_to(REPO_ROOT)} "
          f'rule=dependencies_yaml_schema message="{msg}" '
          f'suggestion="See docs/plans/2026-04-26-ai-harness.md §2 Q11 for the canonical shape."',
          file=sys.stderr)


def main() -> int:
    if not DEPS_YAML.exists():
        _err("dependencies.yaml missing")
        return 1
    try:
        data = yaml.safe_load(DEPS_YAML.read_text())
    except yaml.YAMLError as e:
        _err(f"invalid YAML: {e}")
        return 1

    if not isinstance(data, dict):
        _err("top-level YAML must be a mapping")
        return 1

    for key in REQUIRED_TOP_LEVEL:
        if key not in data:
            _err(f"missing top-level key: {key}")
            return 1

    if not isinstance(data["spine_paths"], dict):
        _err("spine_paths must be a mapping")
        return 1
    for key in REQUIRED_SPINE_PATHS:
        if key not in data["spine_paths"]:
            _err(f"spine_paths missing key: {key}")
            return 1

    for key in REQUIRED_WHITELIST_SECTIONS:
        if key not in data["whitelist"]:
            _err(f"whitelist missing section: {key}")
            return 1

    for key in REQUIRED_BLACKLIST_SECTIONS:
        if key not in data["blacklist"]:
            _err(f"blacklist missing section: {key}")
            return 1

    for key in REQUIRED_AUDIT_KEYS:
        if key not in data["audit"]:
            _err(f"audit missing key: {key}")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### Task 4.5: Run tests, commit green

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
python -m pytest ../tests/harness/configs/test_dependencies_yaml.py -v
```

Expected: all pass.

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
git add .harness/dependencies.yaml tools/validate_dependencies_yaml.py
git commit -m "feat(green): H.0b.4 — dependencies.yaml seeded + schema validator (Q11)

Spine whitelist + global blacklist (axios, redux, jest, requests, moment,
django, flask, etc.). Validator runs in make validate-fast (wired in H.1a).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 4.6: Sanity-check via the orchestrator

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
python tools/validate_dependencies_yaml.py
```

Expected: exit 0, no output.

---

# Story H.0b.5 — `.harness/performance_budgets.yaml` (Q12) + `@timed_query` + `assert_within_budget`

**Files:**
- Create: `.harness/performance_budgets.yaml`
- Create: `backend/src/storage/_timing.py`
- Create: `backend/src/agents/_budget.py`
- Test: `tests/harness/configs/test_performance_budgets.py`
- Test: `backend/tests/storage/test_timing.py`
- Test: `backend/tests/agents/test_budget.py`

### Task 5.1: Write the failing test for the YAML

Create `tests/harness/configs/test_performance_budgets.py`:

```python
"""Sprint H.0b Story 5 — performance_budgets.yaml seeded with Q12 hard + soft gates."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
PERF_YAML = REPO_ROOT / ".harness/performance_budgets.yaml"


def test_perf_yaml_exists() -> None:
    assert PERF_YAML.is_file()


def test_perf_yaml_has_hard_gates() -> None:
    data = yaml.safe_load(PERF_YAML.read_text())
    assert "hard" in data
    for key in ("agent_budgets", "database", "frontend_bundle"):
        assert key in data["hard"], f"hard gate missing: {key}"


def test_perf_yaml_has_soft_gates() -> None:
    data = yaml.safe_load(PERF_YAML.read_text())
    assert "soft" in data
    for key in ("api_latency", "frontend_rendering"):
        assert key in data["soft"], f"soft gate missing: {key}"


def test_perf_yaml_db_query_budget_is_100ms() -> None:
    data = yaml.safe_load(PERF_YAML.read_text())
    assert data["hard"]["database"]["single_query_max_ms"] == 100


def test_perf_yaml_default_agent_budgets_are_sensible() -> None:
    defaults = yaml.safe_load(PERF_YAML.read_text())["hard"]["agent_budgets"]["default"]
    assert defaults["tool_calls_max"] == 20
    assert defaults["tokens_max"] == 20000
    assert defaults["wall_clock_max_s"] == 30


def test_perf_yaml_bundle_budgets() -> None:
    bundle = yaml.safe_load(PERF_YAML.read_text())["hard"]["frontend_bundle"]
    assert bundle["initial_js_kb_gzipped"] == 220
    assert bundle["per_route_chunk_kb_gzipped"] == 100
    assert bundle["total_css_kb_gzipped"] == 50
```

### Task 5.2: Write the failing tests for `_timing.py` and `_budget.py`

Create `backend/tests/storage/__init__.py` if missing, then `backend/tests/storage/test_timing.py`:

```python
"""Sprint H.0b Story 5 — @timed_query decorator (Q12 hard gate on DB queries)."""

from __future__ import annotations

import asyncio
import time

import pytest


@pytest.mark.asyncio
async def test_timed_query_passes_under_budget() -> None:
    from src.storage._timing import timed_query, QueryBudgetExceeded

    @timed_query(max_ms=100)
    async def fast_query() -> int:
        await asyncio.sleep(0.001)
        return 42

    assert await fast_query() == 42


@pytest.mark.asyncio
async def test_timed_query_raises_over_budget() -> None:
    from src.storage._timing import timed_query, QueryBudgetExceeded

    @timed_query(max_ms=10)
    async def slow_query() -> int:
        await asyncio.sleep(0.05)  # 50ms > 10ms budget
        return 42

    with pytest.raises(QueryBudgetExceeded):
        await slow_query()
```

Create `backend/tests/agents/__init__.py` if missing, then `backend/tests/agents/test_budget.py`:

```python
"""Sprint H.0b Story 5 — assert_within_budget helper (Q12 agent budgets)."""

from __future__ import annotations

import pytest


def test_assert_within_budget_passes_when_under() -> None:
    from src.agents._budget import assert_within_budget, BudgetSnapshot

    snapshot = BudgetSnapshot(tool_calls_used=10, tokens_used=5000, wall_clock_s=15.0)
    # Should not raise
    assert_within_budget("default", snapshot)


def test_assert_within_budget_raises_when_over() -> None:
    from src.agents._budget import assert_within_budget, BudgetSnapshot, BudgetExceeded

    snapshot = BudgetSnapshot(tool_calls_used=25, tokens_used=21000, wall_clock_s=35.0)
    with pytest.raises(BudgetExceeded):
        assert_within_budget("default", snapshot)


def test_assert_within_budget_uses_workflow_override_if_present() -> None:
    """Per Q12 + E-11 of the perf budgets: overrides via YAML."""
    from src.agents._budget import assert_within_budget, BudgetSnapshot, BudgetExceeded

    # Default is 20 tool_calls; if workflow `wide_investigation` overrides
    # to 40, then 30 should pass.
    snapshot = BudgetSnapshot(tool_calls_used=30, tokens_used=10000, wall_clock_s=20.0)
    # Overridden workflow won't exist in the seeded yaml; the test just
    # confirms the override mechanism handles unknown workflows gracefully
    # by falling back to default.
    with pytest.raises(BudgetExceeded):
        assert_within_budget("nonexistent_workflow", snapshot)
```

### Task 5.3: Run tests to confirm they fail, commit

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
python -m pytest ../tests/harness/configs/test_performance_budgets.py tests/storage/test_timing.py tests/agents/test_budget.py -v
```

Expected: all fail (yaml missing, modules don't exist).

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
git add tests/harness/configs/test_performance_budgets.py \
        backend/tests/storage/__init__.py backend/tests/storage/test_timing.py \
        backend/tests/agents/__init__.py backend/tests/agents/test_budget.py
git commit -m "test(red): H.0b.5 — perf_budgets.yaml + @timed_query + assert_within_budget contract (Q12)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 5.4: Seed `.harness/performance_budgets.yaml`

Paste the canonical YAML from the harness plan §2 Q12 into `.harness/performance_budgets.yaml`. Reproduce verbatim: `version: 1`, `hard.agent_budgets.default + overrides`, `hard.database.single_query_max_ms: 100`, `hard.frontend_bundle.initial_js_kb_gzipped: 220` etc., `soft.api_latency.p99_ms_per_class`, `soft.frontend_rendering`.

### Task 5.5: Implement `backend/src/storage/_timing.py`

```python
"""Q12 hard gate: every StorageGateway method must complete in
≤ single_query_max_ms (default 100ms in test fixtures)."""

from __future__ import annotations

import functools
import time
from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar("T")


class QueryBudgetExceeded(Exception):
    """Raised when a @timed_query exceeds its declared budget."""


def timed_query(max_ms: int = 100) -> Callable[
    [Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]
]:
    """Decorator. Wraps an async gateway method; raises QueryBudgetExceeded
    if elapsed exceeds max_ms.

    H-25: works on async-only methods (gateway is async per Q7); calling
    on a sync function is a programmer error and surfaces immediately
    via TypeError when the decorated function is awaited.
    """

    def deco(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(fn)
        async def wrapped(*args: Any, **kwargs: Any) -> T:
            start = time.perf_counter()
            result = await fn(*args, **kwargs)
            elapsed_ms = (time.perf_counter() - start) * 1000
            if elapsed_ms > max_ms:
                raise QueryBudgetExceeded(
                    f"{fn.__qualname__} took {elapsed_ms:.1f}ms "
                    f"(budget: {max_ms}ms)"
                )
            return result

        return wrapped

    return deco
```

### Task 5.6: Implement `backend/src/agents/_budget.py`

```python
"""Q12 hard gate: agent runs must stay within budget.

assert_within_budget(workflow_id, snapshot) raises BudgetExceeded if
the snapshot violates the budget for that workflow. Workflow overrides
in .harness/performance_budgets.yaml; unknown workflows fall back to
default."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
PERF_YAML = REPO_ROOT / ".harness/performance_budgets.yaml"


class BudgetExceeded(Exception):
    """Raised when an agent run exceeds its budget."""


@dataclass(frozen=True)
class BudgetSnapshot:
    tool_calls_used: int
    tokens_used: int
    wall_clock_s: float


@lru_cache(maxsize=1)
def _load_budgets() -> dict[str, dict[str, Any]]:
    """Load + cache the budget table. Reload by clearing the cache."""
    if not PERF_YAML.exists():
        return {"default": {"tool_calls_max": 20, "tokens_max": 20000, "wall_clock_max_s": 30}}
    data = yaml.safe_load(PERF_YAML.read_text())
    agent_budgets = data.get("hard", {}).get("agent_budgets", {})
    table = {"default": agent_budgets.get(
        "default",
        {"tool_calls_max": 20, "tokens_max": 20000, "wall_clock_max_s": 30},
    )}
    table.update(agent_budgets.get("overrides", {}) or {})
    return table


def assert_within_budget(workflow_id: str, snapshot: BudgetSnapshot) -> None:
    table = _load_budgets()
    budget = table.get(workflow_id, table["default"])
    breaches: list[str] = []
    if snapshot.tool_calls_used > budget["tool_calls_max"]:
        breaches.append(
            f"tool_calls: {snapshot.tool_calls_used} > {budget['tool_calls_max']}"
        )
    if snapshot.tokens_used > budget["tokens_max"]:
        breaches.append(
            f"tokens: {snapshot.tokens_used} > {budget['tokens_max']}"
        )
    if snapshot.wall_clock_s > budget["wall_clock_max_s"]:
        breaches.append(
            f"wall_clock: {snapshot.wall_clock_s:.1f}s > {budget['wall_clock_max_s']}s"
        )
    if breaches:
        raise BudgetExceeded(
            f"workflow `{workflow_id}` exceeded budget: " + "; ".join(breaches)
        )
```

### Task 5.7: Run tests to verify they pass

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
python -m pytest ../tests/harness/configs/test_performance_budgets.py tests/storage/test_timing.py tests/agents/test_budget.py -v
```

Expected: all pass.

### Task 5.8: Commit green

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
git add .harness/performance_budgets.yaml \
        backend/src/storage/_timing.py \
        backend/src/agents/_budget.py
git commit -m "feat(green): H.0b.5 — perf_budgets.yaml + @timed_query + assert_within_budget (Q12)

Hard gates: agent budgets (20 tool calls / 20K tokens / 30s wall clock),
DB single-query 100ms, bundle 220KB initial / 100KB per-route / 50KB CSS.
Soft gates: API p99 + Lighthouse FCP/TTI/CLS.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

# Story H.0b.6 — gitleaks + .gitleaks.toml + slowapi (Q13)

**Files:**
- Create: `.gitleaks.toml`
- Modify: `backend/requirements.txt` (add `slowapi`)
- Test: `tests/harness/configs/test_security_tooling.py`

### Task 6.1: Write the failing test

Create `tests/harness/configs/test_security_tooling.py`:

```python
"""Sprint H.0b Story 6 — gitleaks + .gitleaks.toml + slowapi (Q13)."""

from __future__ import annotations

import shutil
import subprocess
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
GITLEAKS_TOML = REPO_ROOT / ".gitleaks.toml"


def test_gitleaks_toml_exists() -> None:
    assert GITLEAKS_TOML.is_file()


def test_gitleaks_toml_loads() -> None:
    tomllib.loads(GITLEAKS_TOML.read_text())


def test_gitleaks_toml_has_default_rules_inherited() -> None:
    """We don't redefine the world; we extend gitleaks defaults."""
    text = GITLEAKS_TOML.read_text()
    assert "[extend]" in text or "useDefault" in text


def test_gitleaks_binary_available_or_skipped() -> None:
    """gitleaks may not be on every dev box; this test documents that it's
    expected on CI but not blocking locally."""
    if shutil.which("gitleaks") is None:
        import pytest
        pytest.skip("gitleaks not installed locally; will run in CI")
    result = subprocess.run(["gitleaks", "version"], capture_output=True, text=True)
    assert result.returncode == 0


def test_slowapi_importable() -> None:
    result = subprocess.run(
        ["python", "-c", "import slowapi"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, "slowapi must be installed"
```

### Task 6.2: Run, commit failing tests

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
python -m pytest ../tests/harness/configs/test_security_tooling.py -v
```

Expected: failures.

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
git add tests/harness/configs/test_security_tooling.py
git commit -m "test(red): H.0b.6 — gitleaks + slowapi tooling contract (Q13)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 6.3: Create `.gitleaks.toml`

```toml
# Q13 — secret scanning. Extend gitleaks default rules; don't redefine.
# Custom allowlist captures fixture files where AKIA000... patterns are
# intentionally fake (Q13 `gitleaks:allow` comment convention).

title = "DebugDuck gitleaks config"

[extend]
useDefault = true

[allowlist]
description = "Allowlist for documented test fixtures"
paths = [
    '''tests/harness/fixtures/.*''',
    '''backend/tests/fixtures/.*''',
    '''docs/.*''',
]
regexes = [
    '''AKIA0{16}''',  # canonical "obviously fake" placeholder
]
```

### Task 6.4: Add slowapi

Append to `backend/requirements.txt`:

```
slowapi>=0.1.9
```

Install:

```bash
pip install -q slowapi
```

### Task 6.5: Run tests, commit green

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
python -m pytest ../tests/harness/configs/test_security_tooling.py -v
```

Expected: all pass (gitleaks-binary test may skip if gitleaks isn't installed locally — that's fine; CI will verify).

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
git add .gitleaks.toml backend/requirements.txt
git commit -m "feat(green): H.0b.6 — .gitleaks.toml + slowapi installed (Q13)

Extends gitleaks default rules; allowlist for test fixtures.
slowapi available for rate-limit middleware (mutating-endpoint
auth-and-rate-limit gate from Q13 lands in Sprint H.1c).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

# Story H.0b.7 — eslint-plugin-jsx-a11y + vitest-axe + @axe-core/playwright (Q14)

**Files:**
- Modify: `frontend/package.json` (add deps)
- Create: `frontend/eslint.config.js` (or modify existing)
- Test: `tests/harness/configs/test_a11y_tooling.py`

### Task 7.1: Write the failing test

Create `tests/harness/configs/test_a11y_tooling.py`:

```python
"""Sprint H.0b Story 7 — a11y tooling installed and configured (Q14)."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_JSON = REPO_ROOT / "frontend/package.json"
ESLINT_CFG = REPO_ROOT / "frontend/eslint.config.js"


def _deps() -> dict[str, str]:
    pkg = json.loads(PACKAGE_JSON.read_text())
    return {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}


def test_eslint_jsx_a11y_installed() -> None:
    assert "eslint-plugin-jsx-a11y" in _deps()


def test_vitest_axe_installed() -> None:
    assert "vitest-axe" in _deps()


def test_axe_core_playwright_installed() -> None:
    assert "@axe-core/playwright" in _deps()


def test_eslint_config_extends_jsx_a11y() -> None:
    text = ESLINT_CFG.read_text()
    assert "jsx-a11y" in text, "eslint config must reference jsx-a11y"
```

### Task 7.2: Run tests to fail, commit

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
python -m pytest ../tests/harness/configs/test_a11y_tooling.py -v
```

Expected: failures.

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
git add tests/harness/configs/test_a11y_tooling.py
git commit -m "test(red): H.0b.7 — a11y tooling contract (Q14)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 7.3: Install deps

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend
npm install --save-dev eslint-plugin-jsx-a11y vitest-axe @axe-core/playwright
```

### Task 7.4: Wire eslint config

Create or modify `frontend/eslint.config.js`:

```javascript
// Q14 — WCAG 2.2 AA gate via jsx-a11y at error level.
// Q18 — import/order + import/no-default-export + alias enforcement
//       (the import-rule wiring lands in Sprint H.0b.11).
import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";
import jsxA11y from "eslint-plugin-jsx-a11y";

export default tseslint.config(
  { ignores: ["dist", "node_modules", "e2e"] },
  {
    files: ["src/**/*.{ts,tsx}"],
    extends: [
      js.configs.recommended,
      ...tseslint.configs.recommended,
    ],
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
      "jsx-a11y": jsxA11y,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": "warn",
      // Q14: jsx-a11y recommended rules at error level.
      ...jsxA11y.configs.recommended.rules,
    },
  },
);
```

### Task 7.5: Run tests, commit

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
python -m pytest ../tests/harness/configs/test_a11y_tooling.py -v
```

Expected: all pass.

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
git add frontend/package.json frontend/package-lock.json frontend/eslint.config.js
git commit -m "feat(green): H.0b.7 — a11y tooling + eslint jsx-a11y at error level (Q14)

eslint-plugin-jsx-a11y, vitest-axe, @axe-core/playwright installed.
ESLint config extends recommended + jsx-a11y/recommended at error level.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

# Story H.0b.8 — `docs/decisions/_TEMPLATE.md` + ruff D-class + eslint-plugin-jsdoc (Q15)

**Files:**
- Create: `docs/decisions/_TEMPLATE.md`
- Create: `docs/api.md` (stub)
- Modify: `backend/pyproject.toml` (ruff `D` rules on contract surfaces)
- Modify: `frontend/package.json` (add `eslint-plugin-jsdoc`)
- Test: `tests/harness/configs/test_documentation_tooling.py`

### Task 8.1: Write the failing test

Create `tests/harness/configs/test_documentation_tooling.py`:

```python
"""Sprint H.0b Story 8 — documentation infrastructure (Q15)."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ADR_TEMPLATE = REPO_ROOT / "docs/decisions/_TEMPLATE.md"
API_MD = REPO_ROOT / "docs/api.md"
PYPROJECT = REPO_ROOT / "backend/pyproject.toml"
PACKAGE_JSON = REPO_ROOT / "frontend/package.json"


def test_adr_template_exists() -> None:
    assert ADR_TEMPLATE.is_file()


def test_adr_template_has_required_sections() -> None:
    text = ADR_TEMPLATE.read_text()
    for section in ("Status:", "Date:", "## Context", "## Decision", "## Consequences"):
        assert section in text, f"ADR template missing: {section}"


def test_api_md_stub_exists() -> None:
    assert API_MD.is_file()


def test_ruff_select_includes_D() -> None:
    cfg = tomllib.loads(PYPROJECT.read_text())
    ruff = cfg.get("tool", {}).get("ruff", {})
    select = ruff.get("lint", {}).get("select", []) or ruff.get("select", [])
    assert "D" in select, "ruff lint.select must include D (pydocstyle) for Q15"


def test_eslint_plugin_jsdoc_installed() -> None:
    pkg = json.loads(PACKAGE_JSON.read_text())
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    assert "eslint-plugin-jsdoc" in deps
```

### Task 8.2: Run, commit failing tests

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
python -m pytest ../tests/harness/configs/test_documentation_tooling.py -v
```

Expected: failures.

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
git add tests/harness/configs/test_documentation_tooling.py
git commit -m "test(red): H.0b.8 — ADR template + ruff D + eslint jsdoc contract (Q15)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 8.3: Create the ADR template + api.md stub

Create `docs/decisions/_TEMPLATE.md`:

```markdown
# <Short Title — imperative, e.g., "Pin React Router to v6 (avoid TanStack Router)">

Status: Proposed | Accepted | Deprecated | Superseded by <ADR-link>
Date: YYYY-MM-DD
Owner: @your-handle

## Context

What problem are we solving? What constraints, goals, history matter?
2–6 sentences usually.

## Decision

What did we decide? Be unambiguous. Future readers should be able to
implement this without re-deriving the reasoning.

## Consequences

- Positive — what becomes easier, safer, faster.
- Negative — what becomes harder, slower, more brittle.
- Neutral — what changes shape but isn't strictly better or worse.

## Alternatives considered

Optional. List the 1–3 alternatives we rejected and why each was
rejected. Keeps future maintainers from re-debating the same options.
```

Create `docs/api.md`:

```markdown
# DebugDuck API — operator guide

This is the human-curated companion to the auto-generated OpenAPI spec
at `/openapi.json`. The OpenAPI is the source of truth for shapes;
this document explains *how to use* the API end-to-end.

## Sections (to be filled in as endpoints stabilize)

- Authentication
- Starting an investigation
- Polling status + findings
- Approval gates (the ledger flow)
- Error responses (RFC 7807, Q17)
- Rate limits (per Q13)

This file is a placeholder; concrete sections land in Sprint H.1c when
documentation_policy is enforced.
```

### Task 8.4: Update ruff config

Modify `backend/pyproject.toml` — add a `[tool.ruff.lint]` section (or extend the existing one) with the D rules:

```toml
[tool.ruff.lint]
select = ["E", "F", "I", "B", "D"]
ignore = [
    "D100",  # Missing docstring in public module — too noisy for v1
    "D104",  # Missing docstring in public package
    "D203",  # 1 blank line required before docstring (conflicts with D211)
    "D213",  # Multi-line docstring summary should start at the second line
]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["D"]                  # tests don't need docstrings
"backend/tests/**" = ["D"]
"backend/src/**/_*.py" = ["D"]      # private helpers exempt
```

### Task 8.5: Install eslint-plugin-jsdoc

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend
npm install --save-dev eslint-plugin-jsdoc
```

(The actual rule wiring lands in Sprint H.1c when `documentation_policy.py` enforces JSDoc on hooks.)

### Task 8.6: Run tests, commit

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
python -m pytest ../tests/harness/configs/test_documentation_tooling.py -v
```

Expected: all pass.

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
git add docs/decisions/_TEMPLATE.md docs/api.md backend/pyproject.toml \
        frontend/package.json frontend/package-lock.json
git commit -m "feat(green): H.0b.8 — ADR template + ruff D + eslint-plugin-jsdoc (Q15)

ADR template at docs/decisions/_TEMPLATE.md with Status/Date/Owner/Context/
Decision/Consequences/Alternatives. docs/api.md stub. ruff D-class enabled
with sensible per-file ignores. eslint-plugin-jsdoc installed (rule wiring
lands in Sprint H.1c).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

# Story H.0b.9 — structlog + OpenTelemetry + observability + frontend errorReporter (Q16)

**Files:**
- Modify: `backend/requirements.txt` (structlog + OpenTelemetry SDKs)
- Create: `backend/src/observability/__init__.py`
- Create: `backend/src/observability/logging.py`
- Create: `backend/src/observability/tracing.py`
- Create: `backend/src/observability/_redactor.py`
- Create: `frontend/src/lib/errorReporter.ts`
- Test: `tests/harness/configs/test_observability_setup.py`
- Test: `backend/tests/observability/test_logging.py`
- Test: `backend/tests/observability/test_tracing.py`
- Test: `backend/tests/observability/test_redactor.py`

### Task 9.1: Write the failing tests

Create `backend/tests/observability/__init__.py` (empty), then `backend/tests/observability/test_logging.py`:

```python
"""Sprint H.0b Story 9 — structlog configured per Q16 discipline."""

from __future__ import annotations


def test_logger_returns_structlog_bound_logger() -> None:
    from src.observability.logging import get_logger
    log = get_logger("test")
    # Bound loggers expose .info/.warning/.error/etc.
    assert hasattr(log, "info")
    assert hasattr(log, "error")
    assert hasattr(log, "exception")


def test_processor_chain_includes_redactor() -> None:
    from src.observability.logging import _processor_names
    names = _processor_names()
    assert any("redactor" in n.lower() for n in names), (
        "Q16 mandates secret-redaction processor in the chain"
    )


def test_logger_event_field_carried() -> None:
    """Smoke: emitting a log call doesn't crash and renders to JSON."""
    import io, structlog
    from src.observability.logging import configure_for_test_capture, get_logger

    buf = io.StringIO()
    configure_for_test_capture(buf)
    log = get_logger("test")
    log.info("event_under_test", session_id="sess-1")
    output = buf.getvalue()
    assert "event_under_test" in output
    assert "sess-1" in output
```

Create `backend/tests/observability/test_tracing.py`:

```python
"""Sprint H.0b Story 9 — OpenTelemetry tracer initialized."""

from __future__ import annotations


def test_get_tracer_returns_a_tracer() -> None:
    from src.observability.tracing import get_tracer
    tracer = get_tracer("test")
    # OpenTelemetry tracers expose start_as_current_span.
    assert hasattr(tracer, "start_as_current_span")


def test_span_creation_does_not_crash() -> None:
    from src.observability.tracing import get_tracer
    tracer = get_tracer("test")
    with tracer.start_as_current_span("test.span", attributes={"k": "v"}):
        pass
```

Create `backend/tests/observability/test_redactor.py`:

```python
"""Sprint H.0b Story 9 — secret redaction processor (Q16 γ + Q13)."""

from __future__ import annotations


def test_redactor_replaces_aws_key() -> None:
    from src.observability._redactor import redact_secrets
    out = redact_secrets("AWS_KEY=AKIAIOSFODNN7EXAMPLE in config")
    assert "AKIAIOSFODNN7EXAMPLE" not in out
    assert "[REDACTED]" in out


def test_redactor_replaces_jwt() -> None:
    from src.observability._redactor import redact_secrets
    jwt = "eyJ0eXAi.eyJzdWIi.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    out = redact_secrets(f"token={jwt}")
    assert jwt not in out
    assert "[REDACTED]" in out


def test_redactor_no_op_on_clean_text() -> None:
    from src.observability._redactor import redact_secrets
    out = redact_secrets("nothing sensitive here")
    assert out == "nothing sensitive here"
```

Create `tests/harness/configs/test_observability_setup.py`:

```python
"""Sprint H.0b Story 9 — observability dependencies installed; frontend
errorReporter wrapper exists."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ERROR_REPORTER = REPO_ROOT / "frontend/src/lib/errorReporter.ts"


def test_structlog_installed() -> None:
    r = subprocess.run(["python", "-c", "import structlog"], capture_output=True, text=True)
    assert r.returncode == 0


def test_opentelemetry_api_installed() -> None:
    r = subprocess.run(
        ["python", "-c", "from opentelemetry import trace"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0


def test_frontend_error_reporter_exists() -> None:
    assert ERROR_REPORTER.is_file()
    text = ERROR_REPORTER.read_text()
    assert "captureMessage" in text or "captureException" in text
```

### Task 9.2: Run, commit failing tests

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
python -m pytest tests/observability/ ../tests/harness/configs/test_observability_setup.py -v
```

Expected: failures.

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
git add backend/tests/observability/ tests/harness/configs/test_observability_setup.py
git commit -m "test(red): H.0b.9 — structlog + OTel + redactor + errorReporter contract (Q16)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 9.3: Install backend dependencies

Append to `backend/requirements.txt`:

```
structlog>=24.0.0
opentelemetry-api>=1.27.0
opentelemetry-sdk>=1.27.0
opentelemetry-instrumentation-fastapi>=0.48b0
opentelemetry-instrumentation-httpx>=0.48b0
opentelemetry-instrumentation-sqlalchemy>=0.48b0
```

Install:

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
pip install -q structlog opentelemetry-api opentelemetry-sdk \
                opentelemetry-instrumentation-fastapi \
                opentelemetry-instrumentation-httpx \
                opentelemetry-instrumentation-sqlalchemy
```

### Task 9.4: Implement `_redactor.py`

Create `backend/src/observability/__init__.py` (empty), then `backend/src/observability/_redactor.py`:

```python
"""Q16 γ + Q13 — secret redaction in log output.

Pattern catalogue mirrors .harness/security_policy.yaml's transport.log_redaction.patterns.
Single source of truth lives in security_policy.yaml; this module is the
runtime applier for backend logs."""

from __future__ import annotations

import re
from typing import Pattern

# Q13 — pattern set. Keep in sync with security_policy.yaml.
_PATTERNS: list[tuple[str, Pattern[str]]] = [
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")),
    (
        "generic_secret",
        re.compile(
            r"(?i)(api[_-]?key|secret|password|token)[\"']?\s*[:=]\s*[\"']([^\"']{8,})[\"']",
        ),
    ),
]


def redact_secrets(text: str) -> str:
    """Replace any matched secret with [REDACTED]. Idempotent."""
    if not isinstance(text, str):
        return text
    for _name, pattern in _PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text
```

### Task 9.5: Implement `logging.py`

Create `backend/src/observability/logging.py`:

```python
"""Q16 — structlog backend with mandatory event field, redaction processor,
and OpenTelemetry context injection.

Production renders JSON to stdout; dev pretty-prints. Test mode (used by
the harness's own tests) writes to an injectable buffer for inspection."""

from __future__ import annotations

import io
import logging
import sys
from typing import Any, IO, Iterable

import structlog

from src.observability._redactor import redact_secrets


def _redact_processor(_logger, _method, event_dict: dict[str, Any]) -> dict[str, Any]:
    """structlog processor: apply secret_redactor to every string value."""
    for key, value in list(event_dict.items()):
        if isinstance(value, str):
            event_dict[key] = redact_secrets(value)
    return event_dict


def _otel_context_processor(_logger, _method, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Inject trace_id + span_id from the current OpenTelemetry context."""
    try:
        from opentelemetry import trace
        span = trace.get_current_span()
        ctx = span.get_span_context() if span is not None else None
        if ctx and ctx.is_valid:
            event_dict.setdefault("trace_id", format(ctx.trace_id, "032x"))
            event_dict.setdefault("span_id", format(ctx.span_id, "016x"))
    except Exception:
        # H-25: tracing being unavailable must not crash logging.
        pass
    return event_dict


_DEFAULT_PROCESSORS = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    _redact_processor,
    _otel_context_processor,
    structlog.processors.JSONRenderer(sort_keys=True),
]


def _processor_names() -> list[str]:
    """For introspection by tests."""
    return [getattr(p, "__qualname__", getattr(p, "__class__", type(p)).__name__)
            for p in _DEFAULT_PROCESSORS]


def configure_default(stream: IO[str] | None = None) -> None:
    """Wire structlog with the default processor chain."""
    structlog.configure(
        processors=_DEFAULT_PROCESSORS,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=stream or sys.stdout),
        cache_logger_on_first_use=True,
    )


def configure_for_test_capture(buf: IO[str]) -> None:
    """Used by tests to assert log output."""
    configure_default(stream=buf)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    if not structlog.is_configured():
        configure_default()
    return structlog.get_logger(name) if name else structlog.get_logger()
```

### Task 9.6: Implement `tracing.py`

Create `backend/src/observability/tracing.py`:

```python
"""Q16 ε — OpenTelemetry tracer initialization.

Auto-instruments fastapi/httpx/sqlalchemy when their modules are imported.
Manual span requirement on agent runners + workflow steps lives in the
agent code itself; this module just provides the tracer factory."""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)

_initialized = False


def configure_default(service_name: str = "debugduck") -> None:
    global _initialized
    if _initialized:
        return
    resource = Resource(attributes={"service.name": service_name})
    provider = TracerProvider(resource=resource)
    # In dev / test, write spans to console. Production wires an OTLP
    # exporter (deferred to a follow-up sprint when prod telemetry is wired).
    provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    _initialized = True


def get_tracer(name: str = "debugduck"):
    if not _initialized:
        configure_default()
    return trace.get_tracer(name)
```

### Task 9.7: Implement `frontend/src/lib/errorReporter.ts`

```typescript
// Q16 — frontend error reporter wrapper.
//
// Today: thin wrapper around console.warn/error with a beforeSend hook
// that scrubs secret-shaped strings (Q13). Production deployment swaps
// the backend transport for Sentry/Rollbar/etc. without touching call
// sites.

const SECRET_PATTERNS: RegExp[] = [
  /AKIA[0-9A-Z]{16}/g,
  /eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/g,
  /(api[_-]?key|secret|password|token)["']?\s*[:=]\s*["']([^"']{8,})["']/gi,
];

function redact(text: string): string {
  let out = text;
  for (const pattern of SECRET_PATTERNS) {
    out = out.replace(pattern, "[REDACTED]");
  }
  return out;
}

export interface ErrorReportContext {
  event: string;
  route?: string;
  session_id?: string;
  [key: string]: unknown;
}

export const errorReporter = {
  captureMessage(message: string, context: ErrorReportContext): void {
    const safe = redact(message);
    // Until a real SDK lands, emit to console.warn — but ESLint
    // no-console rule is configured to allow console.warn/error
    // when called via this wrapper (see Q16 logging policy).
    // eslint-disable-next-line no-console
    console.warn(JSON.stringify({ level: "WARN", message: safe, ...context }));
  },

  captureException(err: unknown, context: ErrorReportContext): void {
    const message = err instanceof Error ? err.message : String(err);
    const safe = redact(message);
    // eslint-disable-next-line no-console
    console.error(
      JSON.stringify({
        level: "ERROR",
        message: safe,
        stack: err instanceof Error ? err.stack : undefined,
        ...context,
      }),
    );
  },
};
```

### Task 9.8: Run tests to verify they pass

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
python -m pytest tests/observability/ ../tests/harness/configs/test_observability_setup.py -v
```

Expected: all pass.

### Task 9.9: Commit green

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
git add backend/requirements.txt \
        backend/src/observability/__init__.py \
        backend/src/observability/logging.py \
        backend/src/observability/tracing.py \
        backend/src/observability/_redactor.py \
        frontend/src/lib/errorReporter.ts
git commit -m "feat(green): H.0b.9 — structlog + OTel + redactor + frontend errorReporter (Q16)

Backend: structlog with mandatory event field + secret redaction
processor + OTel context injection. OpenTelemetry tracer factory
(console exporter for dev; OTLP exporter wiring deferred to a follow-up
sprint when prod telemetry is wired).
Frontend: thin errorReporter wrapper with secret-shaped-string redaction
in beforeSend; backend transport swappable for Sentry/Rollbar later.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 9.10: Smoke-check via the orchestrator

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
python tools/run_validate.py --fast
```

Expected: still PASS (we haven't added any check yet that would gate on observability code; this just confirms nothing broke).

---

# Story H.0b.10 — `Result.py` + `with_retry` + `problem.py` + `<ErrorBoundary>` + tenacity (Q17)

**Files:**
- Modify: `backend/requirements.txt` (`tenacity`)
- Create: `backend/src/errors/__init__.py`
- Create: `backend/src/errors/result.py`
- Create: `backend/src/utils/__init__.py` (if missing)
- Create: `backend/src/utils/http.py`
- Create: `backend/src/api/problem.py`
- Create: `frontend/src/components/ui/error-boundary.tsx`
- Test: `backend/tests/errors/test_result.py`
- Test: `backend/tests/utils/test_http.py`
- Test: `backend/tests/api/test_problem.py`
- Test: `tests/harness/configs/test_error_handling_helpers.py`

### Task 10.1: Write the failing tests for `Result`

Create `backend/tests/errors/__init__.py`, then `backend/tests/errors/test_result.py`:

```python
"""Sprint H.0b Story 10 — Result[T, E] for expected outcomes (Q17 C)."""

from __future__ import annotations


def test_ok_holds_value() -> None:
    from src.errors.result import Ok
    r = Ok(42)
    assert r.is_ok()
    assert not r.is_err()
    assert r.unwrap() == 42


def test_err_holds_error() -> None:
    from src.errors.result import Err
    err_obj = ValueError("nope")
    r = Err(err_obj)
    assert r.is_err()
    assert not r.is_ok()
    assert r.unwrap_err() is err_obj


def test_ok_unwrap_err_raises() -> None:
    from src.errors.result import Ok
    r = Ok(1)
    import pytest
    with pytest.raises(Exception):
        r.unwrap_err()


def test_err_unwrap_raises() -> None:
    from src.errors.result import Err
    r = Err("oops")
    import pytest
    with pytest.raises(Exception):
        r.unwrap()


def test_result_pattern_match() -> None:
    """Idiomatic match-statement use."""
    from src.errors.result import Ok, Err, Result

    def classify(r: Result[int, str]) -> str:
        match r:
            case Ok(value=v):
                return f"got {v}"
            case Err(error=e):
                return f"failed: {e}"

    assert classify(Ok(7)) == "got 7"
    assert classify(Err("boom")) == "failed: boom"
```

### Task 10.2: Write the failing tests for `with_retry`

Create `backend/tests/utils/__init__.py`, then `backend/tests/utils/test_http.py`:

```python
"""Sprint H.0b Story 10 — with_retry decorator (Q17 P)."""

from __future__ import annotations

import asyncio
import pytest


@pytest.mark.asyncio
async def test_with_retry_succeeds_first_attempt() -> None:
    from src.utils.http import with_retry

    counter = {"calls": 0}

    @with_retry()
    async def fn() -> int:
        counter["calls"] += 1
        return 1

    assert await fn() == 1
    assert counter["calls"] == 1


@pytest.mark.asyncio
async def test_with_retry_retries_on_transient_failure() -> None:
    import httpx
    from src.utils.http import with_retry

    counter = {"calls": 0}

    @with_retry()
    async def fn() -> int:
        counter["calls"] += 1
        if counter["calls"] < 3:
            raise httpx.NetworkError("boom")
        return 42

    assert await fn() == 42
    assert counter["calls"] == 3


@pytest.mark.asyncio
async def test_with_retry_gives_up_after_max_attempts() -> None:
    import httpx
    from src.utils.http import with_retry

    counter = {"calls": 0}

    @with_retry()
    async def fn() -> int:
        counter["calls"] += 1
        raise httpx.NetworkError("always boom")

    with pytest.raises(httpx.NetworkError):
        await fn()
    assert counter["calls"] == 3   # max_attempts default = 3
```

### Task 10.3: Write the failing tests for `problem_response`

Create `backend/tests/api/test_problem.py`:

```python
"""Sprint H.0b Story 10 — RFC 7807 helper (Q17 i)."""

from __future__ import annotations


def test_problem_response_includes_required_fields() -> None:
    from src.api.problem import problem_response

    resp = problem_response(
        type_="https://debugduck.dev/errors/budget-exceeded",
        title="Budget exceeded",
        status=400,
        detail="Tool call budget reached",
        instance="/api/v4/x",
    )
    body = resp.body.decode()
    for required in ("type", "title", "status", "detail", "instance"):
        assert f'"{required}"' in body


def test_problem_response_content_type_is_problem_json() -> None:
    from src.api.problem import problem_response
    resp = problem_response(type_="x", title="y", status=400, detail="z", instance="/")
    assert resp.media_type == "application/problem+json"


def test_problem_response_extensions_passthrough() -> None:
    from src.api.problem import problem_response
    resp = problem_response(
        type_="x", title="y", status=400, detail="z", instance="/",
        code="BUDGET_EXCEEDED",
        retry_after=30,
    )
    body = resp.body.decode()
    assert '"code":"BUDGET_EXCEEDED"' in body
    assert '"retry_after":30' in body
```

Create `tests/harness/configs/test_error_handling_helpers.py`:

```python
"""Sprint H.0b Story 10 — frontend ErrorBoundary primitive + tenacity installed."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ERROR_BOUNDARY = REPO_ROOT / "frontend/src/components/ui/error-boundary.tsx"


def test_error_boundary_primitive_exists() -> None:
    assert ERROR_BOUNDARY.is_file()


def test_error_boundary_exports_named() -> None:
    text = ERROR_BOUNDARY.read_text()
    assert "export class ErrorBoundary" in text or "export function ErrorBoundary" in text


def test_tenacity_installed() -> None:
    r = subprocess.run(["python", "-c", "import tenacity"], capture_output=True, text=True)
    assert r.returncode == 0
```

### Task 10.4: Run, commit failing tests

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
python -m pytest tests/errors/ tests/utils/ tests/api/test_problem.py \
                  ../tests/harness/configs/test_error_handling_helpers.py -v
```

Expected: failures.

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
git add backend/tests/errors/ backend/tests/utils/ backend/tests/api/test_problem.py \
        tests/harness/configs/test_error_handling_helpers.py
git commit -m "test(red): H.0b.10 — Result + with_retry + problem_response + ErrorBoundary contract (Q17)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 10.5: Install tenacity

Append to `backend/requirements.txt`:

```
tenacity>=8.2.0
```

```bash
pip install -q tenacity
```

### Task 10.6: Implement `Result`

Create `backend/src/errors/__init__.py`:

```python
"""Q17 — typed Result for expected outcomes; raise for unexpected."""
from src.errors.result import Result, Ok, Err  # re-export

__all__ = ["Result", "Ok", "Err"]
```

Create `backend/src/errors/result.py`:

```python
"""Result[T, E] for expected business outcomes (Q17 C).

Pattern: services return Result; route handlers map Err variants to
RFC 7807 problem+json (Q17 i)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, NoReturn, TypeVar, Union

T = TypeVar("T")
E = TypeVar("E")


@dataclass(frozen=True, slots=True)
class Ok(Generic[T]):
    value: T

    def is_ok(self) -> bool:
        return True

    def is_err(self) -> bool:
        return False

    def unwrap(self) -> T:
        return self.value

    def unwrap_err(self) -> NoReturn:
        raise RuntimeError("Called unwrap_err on Ok")


@dataclass(frozen=True, slots=True)
class Err(Generic[E]):
    error: E

    def is_ok(self) -> bool:
        return False

    def is_err(self) -> bool:
        return True

    def unwrap(self) -> NoReturn:
        raise RuntimeError(f"Called unwrap on Err: {self.error!r}")

    def unwrap_err(self) -> E:
        return self.error


# Convenience alias: Result[T, E] = Ok[T] | Err[E]
Result = Union[Ok[T], Err[E]]
```

### Task 10.7: Implement `with_retry`

Create `backend/src/utils/__init__.py` (empty if missing), then `backend/src/utils/http.py`:

```python
"""Q17 P — mandatory retry + timeout on outbound httpx.

Every outbound call goes through a `with_retry`-decorated helper.
Bare httpx.AsyncClient().get() is banned (the dependency_policy check
in Sprint H.1a enforces). This module provides the canonical decorator
and a couple of pre-wrapped helpers."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, TypeVar

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    retry_if_result,
    stop_after_attempt,
    wait_exponential_jitter,
)

T = TypeVar("T")

DEFAULT_TIMEOUT_S = 10.0
DEFAULT_MAX_ATTEMPTS = 3
RETRYABLE_STATUSES = {502, 503, 504, 408, 429}


def _retryable_response(response: Any) -> bool:
    """Retry if httpx.Response with retryable status."""
    return (
        isinstance(response, httpx.Response)
        and response.status_code in RETRYABLE_STATUSES
    )


def with_retry(
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    initial_delay: float = 0.5,
    max_delay: float = 8.0,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Decorator. Wraps an async function in tenacity retry with
    exponential jitter. Retries on httpx.NetworkError + httpx.TimeoutException
    by default."""

    def deco(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        async def wrapped(*args: Any, **kwargs: Any) -> T:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(max_attempts),
                wait=wait_exponential_jitter(initial=initial_delay, max=max_delay),
                retry=retry_if_exception_type((
                    httpx.NetworkError, httpx.TimeoutException,
                )),
                reraise=True,
            ):
                with attempt:
                    return await fn(*args, **kwargs)
            raise RuntimeError("unreachable")  # safety net for type-checkers

        return wrapped

    return deco


# Pre-wrapped helpers — the canonical safe outbound primitives.

@with_retry()
async def http_get(url: str, *, timeout: float = DEFAULT_TIMEOUT_S, **kwargs: Any) -> httpx.Response:
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
        response = await client.get(url, **kwargs)
        response.raise_for_status()
        return response


@with_retry()
async def http_post(
    url: str, *, json: Any = None, timeout: float = DEFAULT_TIMEOUT_S, **kwargs: Any
) -> httpx.Response:
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
        response = await client.post(url, json=json, **kwargs)
        response.raise_for_status()
        return response
```

### Task 10.8: Implement `problem_response`

Create `backend/src/api/problem.py`:

```python
"""Q17 i — RFC 7807 problem+json helper.

Every error response from a route uses this. Content-Type is
`application/problem+json`. Extensions (code, retry_after, etc.) pass
through as additional JSON fields."""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

PROBLEM_JSON = "application/problem+json"


def problem_response(
    *,
    type_: str,
    title: str,
    status: int,
    detail: str,
    instance: str,
    **extensions: Any,
) -> JSONResponse:
    """Construct an RFC 7807 problem+json response.

    Args:
      type_: a URI identifying the problem class
        (e.g., "https://debugduck.dev/errors/budget-exceeded").
      title: short human-readable summary.
      status: HTTP status code.
      detail: human-readable explanation specific to this occurrence.
      instance: URI reference identifying the specific occurrence
        (typically request.url.path).
      **extensions: additional JSON fields for machine-actionable context
        (e.g., code="BUDGET_EXCEEDED", retry_after=30).
    """
    body: dict[str, Any] = {
        "type": type_,
        "title": title,
        "status": status,
        "detail": detail,
        "instance": instance,
    }
    body.update(extensions)
    return JSONResponse(content=body, status_code=status, media_type=PROBLEM_JSON)
```

### Task 10.9: Implement frontend `<ErrorBoundary>`

Create `frontend/src/components/ui/error-boundary.tsx`:

```typescript
// Q17 α — every route wrapped in <ErrorBoundary>; per-card boundaries
// inside the war room. Errors propagate to the error reporter (Q16).

import { Component, type ErrorInfo, type ReactNode } from "react";

import { errorReporter } from "@/lib/errorReporter";

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback: ReactNode | ((error: Error, reset: () => void) => ReactNode);
  scope?: string;
}

interface ErrorBoundaryState {
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    errorReporter.captureException(error, {
      event: "react_render_error",
      route: typeof window !== "undefined" ? window.location.pathname : undefined,
      scope: this.props.scope,
      componentStack: info.componentStack ?? undefined,
    });
  }

  reset = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    if (this.state.error) {
      const { fallback } = this.props;
      return typeof fallback === "function"
        ? fallback(this.state.error, this.reset)
        : fallback;
    }
    return this.props.children;
  }
}
```

### Task 10.10: Run tests, commit

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
python -m pytest tests/errors/ tests/utils/ tests/api/test_problem.py \
                  ../tests/harness/configs/test_error_handling_helpers.py -v
```

Expected: all pass.

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
git add backend/requirements.txt \
        backend/src/errors/ backend/src/utils/ backend/src/api/problem.py \
        frontend/src/components/ui/error-boundary.tsx
git commit -m "feat(green): H.0b.10 — Result + with_retry + problem_response + ErrorBoundary (Q17)

Backend: Result[T, E] + Ok/Err with pattern-match support; with_retry
async decorator (tenacity-backed, exponential jitter, 3 attempts);
http_get/http_post pre-wrapped helpers; RFC 7807 problem_response with
application/problem+json content type.
Frontend: ErrorBoundary primitive that forwards render errors to the
errorReporter wrapper (Q16). Per-route + per-card boundary use ships
in Sprint H.1c when error_handling_policy.py enforces.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

# Story H.0b.11 — eslint + commitlint + ruff isort + tsconfig path alias + vite alias (Q18)

**Files:**
- Modify: `backend/pyproject.toml` (ruff isort)
- Modify: `frontend/package.json` (commitlint + eslint-plugin-import)
- Create: `frontend/.commitlintrc.json` (or `commitlint.config.cjs`)
- Modify: `frontend/eslint.config.js` (add import rules)
- Modify: `frontend/tsconfig.json` (path alias)
- Modify: `frontend/vite.config.ts` (alias resolution)
- Test: `tests/harness/configs/test_conventions_setup.py`

### Task 11.1: Write the failing test

Create `tests/harness/configs/test_conventions_setup.py`:

```python
"""Sprint H.0b Story 11 — Q18 conventions infrastructure."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PYPROJECT = REPO_ROOT / "backend/pyproject.toml"
TSCONFIG = REPO_ROOT / "frontend/tsconfig.json"
VITE_CFG = REPO_ROOT / "frontend/vite.config.ts"
ESLINT_CFG = REPO_ROOT / "frontend/eslint.config.js"
PACKAGE_JSON = REPO_ROOT / "frontend/package.json"
COMMITLINT_CFG_CJS = REPO_ROOT / "frontend/commitlint.config.cjs"
COMMITLINT_CFG_JSON = REPO_ROOT / "frontend/.commitlintrc.json"


def _strip_jsonc(text: str) -> str:
    """Strip line + block comments so we can json-parse tsconfig.json."""
    import re
    text = re.sub(r"//.*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return text


def test_ruff_isort_force_sort_within_sections() -> None:
    cfg = tomllib.loads(PYPROJECT.read_text())
    isort = cfg.get("tool", {}).get("ruff", {}).get("lint", {}).get("isort", {}) \
            or cfg.get("tool", {}).get("ruff", {}).get("isort", {})
    assert isort.get("force-sort-within-sections") is True
    known_first = isort.get("known-first-party", [])
    assert "src" in known_first


def test_tsconfig_has_path_alias() -> None:
    raw = TSCONFIG.read_text()
    data = json.loads(_strip_jsonc(raw))
    paths = data.get("compilerOptions", {}).get("paths", {})
    assert "@/*" in paths


def test_vite_alias_present() -> None:
    text = VITE_CFG.read_text()
    assert "@" in text and "src" in text and "alias" in text


def test_eslint_import_plugin_configured() -> None:
    text = ESLINT_CFG.read_text()
    for rule in ("import/order", "import/no-default-export", "import/no-relative-parent-imports"):
        assert rule in text, f"eslint rule `{rule}` not configured"


def test_commitlint_config_present() -> None:
    assert COMMITLINT_CFG_CJS.exists() or COMMITLINT_CFG_JSON.exists()


def test_commitlint_dep_installed() -> None:
    pkg = json.loads(PACKAGE_JSON.read_text())
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    assert "@commitlint/cli" in deps
    assert "@commitlint/config-conventional" in deps
```

### Task 11.2: Run, commit failing tests

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
python -m pytest ../tests/harness/configs/test_conventions_setup.py -v
```

Expected: failures.

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
git add tests/harness/configs/test_conventions_setup.py
git commit -m "test(red): H.0b.11 — conventions infrastructure contract (Q18)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 11.3: Configure ruff isort

Add to `backend/pyproject.toml` (under existing `[tool.ruff]` / `[tool.ruff.lint]`):

```toml
[tool.ruff.lint.isort]
force-single-line = false
force-sort-within-sections = true
known-first-party = ["src"]
```

### Task 11.4: Add tsconfig + vite path alias

Modify `frontend/tsconfig.json` `compilerOptions.paths` (preserve all other settings):

```json
"baseUrl": "./",
"paths": {
  "@/*": ["src/*"]
}
```

Modify `frontend/vite.config.ts` to resolve `@`:

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
```

(If your existing `vite.config.ts` has more configuration, merge — don't overwrite.)

### Task 11.5: Wire eslint-plugin-import

Install:

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend
npm install --save-dev eslint-plugin-import @commitlint/cli @commitlint/config-conventional
```

Extend `frontend/eslint.config.js` (add the plugin and rules):

```javascript
import importPlugin from "eslint-plugin-import";

// Inside the existing tseslint.config({ ... }, { ... }) array, add a new
// block after the React block:
{
  files: ["src/**/*.{ts,tsx}"],
  plugins: { import: importPlugin },
  rules: {
    "import/order": ["error", {
      groups: ["builtin", "external", "parent", "sibling", "index"],
      "newlines-between": "always",
      alphabetize: { order: "asc", caseInsensitive: true },
    }],
    "import/no-default-export": "error",
    "import/no-relative-parent-imports": "error",
  },
},
{
  // pages/ + config files exception for default exports.
  files: ["src/pages/**/*.tsx", "*.config.{ts,js,cjs}", "playwright.config.ts"],
  rules: {
    "import/no-default-export": "off",
  },
},
```

### Task 11.6: Add commitlint config

Create `frontend/commitlint.config.cjs`:

```javascript
// Q18 — Conventional Commits enforcement.
module.exports = {
  extends: ["@commitlint/config-conventional"],
  rules: {
    "header-max-length": [2, "always", 72],
    "type-enum": [2, "always", [
      "feat", "fix", "docs", "refactor", "test",
      "chore", "perf", "style", "build", "ci",
    ]],
    "subject-case": [0],   // disable; we want flexibility for proper nouns
  },
};
```

(commitlint runs from the frontend dir but governs commits across the repo; since Sprint H.0a.7 already wired pre-commit, commit-msg hook wiring is added by Sprint H.1b.7 when conventions_policy lands. Today this story just installs + configures.)

### Task 11.7: Run tests, commit

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
python -m pytest ../tests/harness/configs/test_conventions_setup.py -v
```

Expected: all pass.

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
git add backend/pyproject.toml frontend/tsconfig.json frontend/vite.config.ts \
        frontend/eslint.config.js frontend/commitlint.config.cjs \
        frontend/package.json frontend/package-lock.json
git commit -m "feat(green): H.0b.11 — eslint import + commitlint + ruff isort + alias resolution (Q18)

Backend: ruff isort force-sort-within-sections + known-first-party=src.
Frontend: tsconfig path alias @/ → src/, vite alias resolution to match,
eslint-plugin-import with import/order + no-default-export + no-relative-parent-imports
(pages/ + config exceptions). commitlint configured for Conventional
Commits with 72-char header cap.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

# Story H.0b.12 — mypy strict per-module + tsconfig strict + initial baselines (Q19)

**Files:**
- Modify: `backend/pyproject.toml` (mypy per-module)
- Modify: `frontend/tsconfig.json` (`strict`, `noUncheckedIndexedAccess`)
- Create: `.harness/baselines/mypy_baseline.json`
- Create: `.harness/baselines/tsc_baseline.json`
- Create: `tools/generate_typecheck_baseline.py`
- Modify: `Makefile` (add `harness-typecheck-baseline` target)
- Test: `tests/harness/configs/test_typecheck_setup.py`

### Task 12.1: Write the failing test

Create `tests/harness/configs/test_typecheck_setup.py`:

```python
"""Sprint H.0b Story 12 — mypy strict per-module + tsc strict + baselines (Q19)."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PYPROJECT = REPO_ROOT / "backend/pyproject.toml"
TSCONFIG = REPO_ROOT / "frontend/tsconfig.json"
MYPY_BASELINE = REPO_ROOT / ".harness/baselines/mypy_baseline.json"
TSC_BASELINE = REPO_ROOT / ".harness/baselines/tsc_baseline.json"
BASELINE_GEN = REPO_ROOT / "tools/generate_typecheck_baseline.py"


def _strip_jsonc(text: str) -> str:
    text = re.sub(r"//.*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return text


def test_mypy_strict_overrides_present_for_locked_paths() -> None:
    cfg = tomllib.loads(PYPROJECT.read_text())
    overrides = cfg.get("tool", {}).get("mypy", {}).get("overrides", [])
    text = json.dumps(overrides)
    for spine in ("src.storage", "src.learning", "src.models", "src.api"):
        assert spine in text, f"mypy strict override missing for {spine}"


def test_tsconfig_strict_and_unchecked_indexed_access() -> None:
    raw = TSCONFIG.read_text()
    data = json.loads(_strip_jsonc(raw))
    co = data.get("compilerOptions", {})
    assert co.get("strict") is True
    assert co.get("noUncheckedIndexedAccess") is True


def test_mypy_baseline_exists() -> None:
    assert MYPY_BASELINE.is_file()


def test_tsc_baseline_exists() -> None:
    assert TSC_BASELINE.is_file()


def test_baseline_files_have_required_schema() -> None:
    for path in (MYPY_BASELINE, TSC_BASELINE):
        data = json.loads(path.read_text())
        for required in ("generated_at", "tool_version", "violations"):
            assert required in data, f"{path.name} missing required field {required}"
        assert isinstance(data["violations"], list)


def test_baseline_generator_exists() -> None:
    assert BASELINE_GEN.is_file()
```

### Task 12.2: Run, commit failing tests

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
python -m pytest ../tests/harness/configs/test_typecheck_setup.py -v
```

Expected: failures.

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
git add tests/harness/configs/test_typecheck_setup.py
git commit -m "test(red): H.0b.12 — typecheck baselines + strict configs contract (Q19)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 12.3: Configure mypy strict per-module

Append to `backend/pyproject.toml`:

```toml
[tool.mypy]
python_version = "3.14"
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = ["src.storage.*", "src.learning.*", "src.models.*", "src.api.*"]
strict = true

[[tool.mypy.overrides]]
module = "src.agents.*.runners.*"
strict = true
```

### Task 12.4: Configure tsconfig strict

Modify `frontend/tsconfig.json` `compilerOptions` — add or update:

```json
"strict": true,
"noUncheckedIndexedAccess": true
```

(Preserve all other compiler options.)

### Task 12.5: Write the baseline generator

Create `tools/generate_typecheck_baseline.py`:

```python
#!/usr/bin/env python3
"""Generate baseline files for mypy and tsc.

Per Q19 β — existing violations grandfathered into a baseline; new
violations block merge. Regenerating the baseline grows the snapshot
of allowed violations and requires an ADR (Q15) — except when
violations *shrink* (errors fixed), which is always allowed.

Invoked via `make harness-typecheck-baseline`."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINES_DIR = REPO_ROOT / ".harness/baselines"
MYPY_OUT = BASELINES_DIR / "mypy_baseline.json"
TSC_OUT = BASELINES_DIR / "tsc_baseline.json"


def _run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


def collect_mypy() -> dict:
    """Walk mypy across the strict paths; collect violations."""
    if shutil.which("mypy") is None:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "tool_version": "unavailable",
            "violations": [],
            "_note": "mypy not on PATH at baseline generation time",
        }
    code, out = _run(
        ["mypy", "--no-color-output", "--show-column-numbers", "--strict",
         "src/storage/", "src/learning/", "src/models/", "src/api/"],
        cwd=REPO_ROOT / "backend",
    )
    violations = []
    pattern = re.compile(r"^(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+): error: (?P<msg>.+)$")
    for line in out.splitlines():
        if m := pattern.match(line):
            violations.append({
                "file": m.group("file"),
                "line": int(m.group("line")),
                "column": int(m.group("col")),
                "message": m.group("msg"),
            })
    version_code, version_out = _run(["mypy", "--version"], cwd=REPO_ROOT)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tool_version": version_out.strip(),
        "violations": violations,
    }


def collect_tsc() -> dict:
    if shutil.which("npx") is None:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "tool_version": "unavailable",
            "violations": [],
            "_note": "npx not on PATH",
        }
    code, out = _run(
        ["npx", "tsc", "--noEmit", "-p", "tsconfig.json"],
        cwd=REPO_ROOT / "frontend",
    )
    violations = []
    pattern = re.compile(r"^(?P<file>[^()]+)\((?P<line>\d+),(?P<col>\d+)\): error TS(?P<code>\d+): (?P<msg>.+)$")
    for line in out.splitlines():
        if m := pattern.match(line):
            violations.append({
                "file": m.group("file"),
                "line": int(m.group("line")),
                "column": int(m.group("col")),
                "code": int(m.group("code")),
                "message": m.group("msg"),
            })
    version_code, version_out = _run(["npx", "tsc", "--version"], cwd=REPO_ROOT / "frontend")
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tool_version": version_out.strip(),
        "violations": violations,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true",
                        help="Don't write; print summary and exit.")
    args = parser.parse_args(argv)

    BASELINES_DIR.mkdir(parents=True, exist_ok=True)

    mypy_data = collect_mypy()
    tsc_data = collect_tsc()

    if not args.check_only:
        MYPY_OUT.write_text(json.dumps(mypy_data, indent=2, sort_keys=True) + "\n")
        TSC_OUT.write_text(json.dumps(tsc_data, indent=2, sort_keys=True) + "\n")

    print(f"mypy_baseline: {len(mypy_data['violations'])} violations")
    print(f"tsc_baseline:  {len(tsc_data['violations'])} violations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### Task 12.6: Generate baselines, wire Makefile target, run tests, commit

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
python tools/generate_typecheck_baseline.py
```

Expected: prints `mypy_baseline: <N> violations` and `tsc_baseline: <N> violations`. Creates `.harness/baselines/mypy_baseline.json` and `tsc_baseline.json`.

Append to the `Makefile`:

```make
# Q19 — regenerate the type-check baselines. Required after a path is
# promoted from non-strict to strict; otherwise generally not run.
.PHONY: harness-typecheck-baseline
harness-typecheck-baseline:
	@python tools/generate_typecheck_baseline.py
```

Run the harness tests:

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
python -m pytest ../tests/harness/configs/test_typecheck_setup.py -v
```

Expected: all pass.

Commit:

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
git add backend/pyproject.toml frontend/tsconfig.json \
        tools/generate_typecheck_baseline.py Makefile \
        .harness/baselines/mypy_baseline.json .harness/baselines/tsc_baseline.json
git commit -m "feat(green): H.0b.12 — mypy strict + tsc strict + initial baselines (Q19)

Backend: mypy strict per-module overrides for src.storage/learning/
models/api/agents.runners + src.observability. Frontend: tsconfig
strict + noUncheckedIndexedAccess.
Baselines: tools/generate_typecheck_baseline.py generates
.harness/baselines/{mypy,tsc}_baseline.json. Makefile target
harness-typecheck-baseline regenerates explicitly. Drift detection
(no new errors allowed; growth requires ADR) lands in Sprint H.1d.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

# Sprint H.0b — Acceptance verification

After all 12 stories ship, run this end-to-end sequence:

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm

# 1. Every config file is present
test -f frontend/vitest.config.ts
test -f frontend/playwright.config.ts
test -f backend/alembic.ini
test -f .harness/dependencies.yaml
test -f .harness/performance_budgets.yaml
test -f .gitleaks.toml
test -f docs/decisions/_TEMPLATE.md
test -f docs/api.md
test -f .harness/baselines/mypy_baseline.json
test -f .harness/baselines/tsc_baseline.json
echo "All configs present ✅"

# 2. Every helper module imports cleanly
cd backend
python -c "
import structlog
from src.observability.logging import get_logger
from src.observability.tracing import get_tracer
from src.observability._redactor import redact_secrets
from src.errors.result import Ok, Err, Result
from src.utils.http import with_retry, http_get, http_post
from src.api.problem import problem_response, PROBLEM_JSON
from src.storage._timing import timed_query, QueryBudgetExceeded
from src.agents._budget import assert_within_budget, BudgetSnapshot, BudgetExceeded
print('All helpers importable ✅')
"
cd ..

# 3. Validators pass
python tools/validate_dependencies_yaml.py
echo "dependencies.yaml validator passes ✅"

# 4. Harness tests still green
cd backend && python -m pytest ../tests/harness/ -q && cd ..
echo "Harness tests green ✅"

# 5. New backend tests green (observability + errors + utils + api + storage + agents helpers)
cd backend && python -m pytest tests/observability/ tests/errors/ tests/utils/ \
                              tests/api/test_problem.py tests/storage/test_timing.py \
                              tests/agents/test_budget.py -q && cd ..
echo "Backend helper tests green ✅"

# 6. Orchestrator still under budget
time python tools/run_validate.py --fast
echo "validate-fast still under 30s ✅"

# 7. Baselines have stable byte output (regenerating produces identical bytes
#    if no source changed)
python tools/generate_typecheck_baseline.py
git diff --quiet .harness/baselines/ && echo "Baselines deterministic ✅" \
  || echo "WARN: regenerating produced a diff — investigate"
```

If every step passes, **Sprint H.0b is done**. Move to:

- **Sprint H.1a — Backend basic checks** (next plan to write).
- Or stop and verify the consolidated state to `main`.

## Execution Handoff

Plan complete and saved to `docs/plans/2026-04-26-harness-sprint-h0b-tasks.md`. Two execution options:

**1. Subagent-Driven (this session)** — fresh subagent per task/story, review between checkpoints.

**2. Parallel Session (separate)** — open new session with executing-plans, batch execution with checkpoints.

**Which approach?** Or hold and confirm before I author Sprint H.1a.
