# Harness Sprint H.2 — Per-Task Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship the eighteen generators that produce machine-readable truth files under `.harness/generated/`, the `run_harness_regen` orchestrator, the Claude Code session-start hook that invokes the loader, the `harness-init` bootstrap that scaffolds the harness into a brand-new repo, and the final onboarding docs (`.harness/README.md` end-user guide, first cut of `docs/api.md`). Together these close the AI-readability loop: every rule that the AI needs to understand the codebase is now derivable from code, regenerated on demand, and surfaced into the IDE on session start.

**Architecture:** Same template as the H.1 sprints — each generator is a standalone Python script under `.harness/generators/<name>.py` that walks the repo, parses the relevant code surfaces (AST for Python, regex/tree-sitter for TS/TSX, YAML for configs), and emits a deterministic JSON file under `.harness/generated/<name>.json`. The orchestrator `tools/run_harness_regen.py` runs every generator in topological order (independent generators run in parallel via `concurrent.futures.ProcessPoolExecutor`). The Claude Code hook is a `.claude/settings.local.json` entry that fires `tools/load_harness.py` on session start with the active file as context. The `harness-init` bootstrap is a one-shot `tools/init_harness.py` that copies the harness skeleton into a target repo, with prompts for owner/scope.

**Tech Stack:** Python 3.14, ast (stdlib), pathlib (stdlib), json (stdlib), concurrent.futures (stdlib), tomllib (stdlib), tree-sitter + tree-sitter-typescript (added in H.1b Story 0), PyYAML (already a dep).

**Reference docs:**
- [Consolidated harness plan](./2026-04-26-ai-harness.md) — locked Q1–Q19, H-1 through H-25; §3.1 lists every generator name + corresponding output file.
- [Sprint H.0a per-task plan](./2026-04-26-harness-sprint-h0a-tasks.md) — substrate (loader, run_validate orchestrator, _common.py).
- [Sprint H.0b per-task plan](./2026-04-26-harness-sprint-h0b-tasks.md) — config files generators consume.
- [Sprint H.1a per-task plan](./2026-04-26-harness-sprint-h1a-tasks.md) — backend checks that consume generated truth files.
- [Sprint H.1b per-task plan](./2026-04-26-harness-sprint-h1b-tasks.md) — frontend checks.
- [Sprint H.1c per-task plan](./2026-04-26-harness-sprint-h1c-tasks.md) — cross-stack checks.
- [Sprint H.1d per-task plan](./2026-04-26-harness-sprint-h1d-tasks.md) — typecheck_policy + harness self-tests + baseline buffer.

**Prerequisites:** Sprints H.0a, H.0b, H.1a, H.1b, H.1c, H.1d complete and committed.

---

## Story map for Sprint H.2

| Story | Title | Tasks | Pts |
|---|---|---|---|
| H.2.0 | Generator helpers + `_common.py` deterministic-write contract | 0.1 – 0.5 | — (precondition) |
| H.2.1 | Generators 1–4 (frontend: api_endpoints, ui_primitives, routes, test_coverage_targets) | 1.1 – 1.10 | 5 |
| H.2.2 | Generators 5–8 (backend: backend_routes, db_models, gateway_methods, test_coverage_required_paths + test_inventory) | 2.1 – 2.10 | 5 |
| H.2.3 | Generators 9–12 (cross-stack: validation_inventory, dependency_inventory, performance_budgets, security_inventory) | 3.1 – 3.10 | 5 |
| H.2.4 | Generators 13–14 (a11y_inventory + documentation_inventory) | 4.1 – 4.7 | 3 |
| H.2.5 | Generators 15–17 (logging_inventory, error_taxonomy + outbound_http_inventory, conventions_inventory) | 5.1 – 5.10 | 4 |
| H.2.6 | Generator 18 (typecheck_inventory) + `tools/run_harness_regen.py` orchestrator | 6.1 – 6.7 | 3 |
| H.2.7 | Claude Code `.claude/settings.local.json` session-start hook invoking `tools/load_harness.py` | 7.1 – 7.5 | 3 |
| H.2.8 | `harness-init` bootstrap: `tools/init_harness.py` scaffolds the layout into a new repo | 8.1 – 8.10 | 5 |
| H.2.9 | `.harness/README.md` end-user documentation + `docs/api.md` first cut + onboarding polish | 9.1 – 9.7 | 3 |

**Total: 9 stories + 1 precondition, ~32 points, 2 weeks.**

---

## Story-template recap (applies to every generator story H.2.1 – H.2.6)

Each generator story follows this shape:

- **AC-1:** Generator exists at `.harness/generators/<name>.py`.
- **AC-2:** Output file path is `.harness/generated/<name>.json` (singular per generator).
- **AC-3:** Output is deterministic — `--regen` followed by `git diff --stat .harness/generated/` is empty.
- **AC-4:** Output schema validated by a paired JSON Schema under `.harness/schemas/generated/<name>.schema.json` (the schema check `harness_policy_schema.py` from H.1d.4 is extended to also validate generated/* files in Task 0.3 below).
- **AC-5:** Generator completes in < 5s on the live repo (smoke test in `tests/harness/generators/test_<name>.py`).
- **AC-6:** Wired into `tools/run_harness_regen.py` (added in Story H.2.6).
- **AC-7:** H-25 docstring present.
- **AC-8:** A consuming check OR documented-future-consumer references the generated file (`.harness/generated/<name>.json`) — i.e., the generator is not write-only.

Common task pattern per generator: write fixture-tree → write red test asserting expected JSON shape → red commit → implement generator → green test → run on live repo → schema → commit green.

---

# Story H.2.0 — Generator helpers + `_common.py` deterministic-write contract (precondition)

> Not separately story-pointed; it is a 30-minute prerequisite that **must complete before Story H.2.1**.

**Files:**
- Modify: `.harness/generators/_common.py` (add `write_generated`, `iter_python_files`, `iter_tsx_files`, `extract_jsx_props` helpers)
- Modify: `.harness/checks/harness_policy_schema.py` (extend to also validate `.harness/generated/*.json`)
- Create: `.harness/generated/_README.md` (warns "DO NOT EDIT — regenerated by tools/run_harness_regen.py")

### Task 0.1: Add `write_generated` helper

Append to `.harness/generators/_common.py`:

```python
def write_generated(name: str, payload: object) -> Path:
    """Write `payload` (JSON-serializable) to .harness/generated/<name>.json
    with sort_keys=True, indent=2, trailing newline. Idempotent + deterministic.

    H-4: generated files are auto-derived; they are NEVER hand-edited.
    Returns the path written.
    """
    import json
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[2]
    out_dir = repo_root / ".harness" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{name}.json"
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out_path


def iter_python_files(root: Path, exclude: tuple[str, ...] = ()) -> Iterable[Path]:
    """Yield .py files under root, sorted, deterministic, skipping any path
    whose virtual repr contains any string in `exclude`."""
    for path in sorted(root.rglob("*.py")):
        virtual = str(path)
        if any(token in virtual for token in exclude):
            continue
        yield path


def iter_tsx_files(root: Path, exclude: tuple[str, ...] = ()) -> Iterable[Path]:
    """Yield .ts/.tsx/.js/.jsx files under root, sorted, deterministic."""
    for ext in (".ts", ".tsx", ".js", ".jsx"):
        for path in sorted(root.rglob(f"*{ext}")):
            virtual = str(path)
            if any(token in virtual for token in exclude):
                continue
            yield path
```

If `Iterable` not yet imported, add `from typing import Iterable` at the top.

### Task 0.2: Create `.harness/generated/_README.md`

```markdown
# Generated truth files

Files in this directory are **auto-derived** from source code by
`.harness/generators/*.py`. They are **never hand-edited**.

To regenerate: `make harness` (alias for `python tools/run_harness_regen.py`).

The harness loader (`tools/load_harness.py`) reads these files when assembling
context for an AI session. Checks under `.harness/checks/*.py` may also read
them as their canonical source of truth (H-10).

If you find yourself wanting to edit a file here, instead:
1. Identify the generator that produces it (filename matches generator name).
2. Open `.harness/generators/<name>.py` and adjust the extraction logic there.
3. Run `make harness` to regenerate.
4. Commit both the generator change AND the regenerated JSON.
```

### Task 0.3: Extend `harness_policy_schema.py` to validate generated/

Edit `.harness/checks/harness_policy_schema.py` `scan` function — after the policy-yaml loop, add:

```python
# Also validate every .harness/generated/*.json against
# .harness/schemas/generated/<name>.schema.json (if present).
generated_dir = REPO_ROOT / ".harness" / "generated"
generated_schemas_dir = schemas_dir / "generated"
if generated_dir.exists():
    for json_path in sorted(generated_dir.glob("*.json")):
        if json_path.name == "_README.md":
            continue
        schema_path = generated_schemas_dir / f"{json_path.stem}.schema.json"
        if not schema_path.exists():
            emit(Finding(
                severity=Severity.WARN,
                file=json_path,
                line=0,
                rule="H21.policy-schema-missing",
                message=f"{json_path.name} has no matching generated schema",
                suggestion=f"add {schema_path.relative_to(REPO_ROOT)}",
            ))
            continue
        for finding in _validate_one(json_path, schema_path):
            emit(finding)
            if finding.severity == Severity.ERROR:
                total_errors += 1
```

> Adding generated-file schemas as the matching missing files is a graceful warn (H-25 upstream). Tighten to ERROR in a follow-up after Sprint H.2 fully populates the schemas.

### Task 0.4: Create the `make harness` target

Append to `Makefile` if not already present:

```makefile
.PHONY: harness
harness:  ## Regenerate every .harness/generated/*.json
	python tools/run_harness_regen.py
```

(The orchestrator script itself lands in Story H.2.6.)

### Task 0.5: Commit precondition

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
git add .harness/generators/_common.py .harness/generated/_README.md .harness/checks/harness_policy_schema.py Makefile
git commit -m "$(cat <<'EOF'
chore(green): H.2.0 — generator helpers + deterministic-write contract

Adds write_generated/iter_python_files/iter_tsx_files helpers to
.harness/generators/_common.py; .harness/generated/_README.md warns
DO NOT EDIT; harness_policy_schema.py extended to validate every
.harness/generated/*.json against .harness/schemas/generated/<name>
.schema.json (warn-only when schema file missing). Makefile gains the
`make harness` alias for tools/run_harness_regen.py (orchestrator
itself lands in H.2.6).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Story H.2.1 — Generators 1–4 (frontend)

Generators in this story:

| # | Name | Source | Output schema (top-level keys) |
|---|---|---|---|
| 1 | `extract_api_endpoints` | `frontend/src/services/api/*.ts` | `{ "endpoints": [{ "name", "url_template", "method", "request_type", "response_type", "file" }] }` |
| 2 | `extract_ui_primitives` | `frontend/src/components/ui/*.tsx` | `{ "primitives": [{ "name", "exports", "file", "uses_radix": bool }] }` |
| 3 | `extract_routes` | `frontend/src/router.tsx` | `{ "routes": [{ "path", "page_module", "lazy_imported": bool }] }` |
| 4 | `extract_test_coverage_targets` | `frontend/vitest.config.ts` | `{ "thresholds": [{ "glob", "branches", "functions", "lines", "statements" }] }` |

**Files:**
- Create: `.harness/generators/extract_api_endpoints.py`
- Create: `.harness/generators/extract_ui_primitives.py`
- Create: `.harness/generators/extract_routes.py`
- Create: `.harness/generators/extract_test_coverage_targets.py`
- Create: `tests/harness/generators/__init__.py`
- Create: `tests/harness/generators/test_extract_api_endpoints.py`
- Create: `tests/harness/generators/test_extract_ui_primitives.py`
- Create: `tests/harness/generators/test_extract_routes.py`
- Create: `tests/harness/generators/test_extract_test_coverage_targets.py`
- Create: `tests/harness/fixtures/generators/frontend/services/api/foo.ts`
- Create: `tests/harness/fixtures/generators/frontend/components/ui/button.tsx`
- Create: `tests/harness/fixtures/generators/frontend/router.tsx`
- Create: `tests/harness/fixtures/generators/frontend/vitest.config.ts`
- Create: `.harness/schemas/generated/api_endpoints.schema.json`
- Create: `.harness/schemas/generated/ui_primitives.schema.json`
- Create: `.harness/schemas/generated/routes.schema.json`
- Create: `.harness/schemas/generated/test_coverage_targets.schema.json`

### Task 1.1: Create the synthetic frontend fixture tree

```bash
mkdir -p tests/harness/fixtures/generators/frontend/services/api
mkdir -p tests/harness/fixtures/generators/frontend/components/ui
```

Create `tests/harness/fixtures/generators/frontend/services/api/foo.ts`:

```ts
import { apiClient } from "./client";

export interface FooRequest { id: string; }
export interface FooResponse { name: string; }

export const fetchFoo = (id: string) =>
  apiClient<FooResponse>(`/api/v4/foo/${id}`, { method: "GET" });

export const createFoo = (body: FooRequest) =>
  apiClient<FooResponse>(`/api/v4/foo`, { method: "POST", body });
```

Create `tests/harness/fixtures/generators/frontend/components/ui/button.tsx`:

```tsx
import * as React from "react";
import * as RadixSlot from "@radix-ui/react-slot";

export const Button = React.forwardRef<HTMLButtonElement, React.ButtonHTMLAttributes<HTMLButtonElement>>(
  ({ ...props }, ref) => <button ref={ref} {...props} />,
);
Button.displayName = "Button";
```

Create `tests/harness/fixtures/generators/frontend/router.tsx`:

```tsx
import { lazy } from "react";
import { createBrowserRouter } from "react-router-dom";

const IncidentsPage = lazy(() => import("@/pages/Incidents"));
const SettingsPage = lazy(() => import("@/pages/Settings"));

export const router = createBrowserRouter([
  { path: "/incidents", element: <IncidentsPage /> },
  { path: "/settings", element: <SettingsPage /> },
]);
```

Create `tests/harness/fixtures/generators/frontend/vitest.config.ts`:

```ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    coverage: {
      thresholds: {
        "frontend/src/services/api/**": { lines: 0.9, functions: 0.9, branches: 0.85, statements: 0.9 },
        "frontend/src/hooks/**": { lines: 0.85, functions: 0.85, branches: 0.8, statements: 0.85 },
      },
    },
  },
});
```

### Task 1.2: Implement `extract_api_endpoints`

Create `.harness/generators/extract_api_endpoints.py`:

```python
#!/usr/bin/env python3
"""Generator — frontend API endpoints.

Walks frontend/src/services/api/*.ts (skipping client.ts + index.ts +
*.test.ts) and emits, for each `apiClient<T>(...)` call, an entry with
url template, method, response type, and source file.

Output: .harness/generated/api_endpoints.json
Schema: .harness/schemas/generated/api_endpoints.schema.json

H-25:
  Missing input    — exit 0; emit empty list (frontend may not exist yet).
  Malformed input  — skip individual file; never block.
  Upstream failed  — none.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from .harness.generators._common import write_generated  # noqa: E402

EXPORT_RE = re.compile(
    r'export\s+const\s+(?P<name>\w+)\s*=\s*(?:\([^)]*\)\s*=>\s*)?'
    r'apiClient<(?P<resp>[^>]+?)>\s*\(\s*'
    r'`?["\']?(?P<url>[^"`\'),]+)["\'`]?'
    r'(?:\s*,\s*\{[^}]*method\s*:\s*["\'](?P<method>[A-Z]+)["\'])?',
    re.DOTALL,
)


def _scan(root: Path) -> list[dict]:
    api_dir = root / "frontend" / "src" / "services" / "api"
    out: list[dict] = []
    if not api_dir.exists():
        return out
    for path in sorted(api_dir.glob("*.ts")):
        if path.name in {"client.ts", "index.ts"} or path.name.endswith(".test.ts"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for m in EXPORT_RE.finditer(text):
            out.append({
                "name": m.group("name"),
                "url_template": m.group("url"),
                "method": (m.group("method") or "GET").upper(),
                "response_type": m.group("resp").strip(),
                "file": str(path.relative_to(root)),
            })
    out.sort(key=lambda e: (e["file"], e["name"]))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--print", action="store_true", help="Print JSON instead of writing.")
    args = parser.parse_args(argv)
    payload = {"endpoints": _scan(args.root)}
    if args.print:
        import json
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    out_path = write_generated("api_endpoints", payload)
    print(f"[INFO] wrote {len(payload['endpoints'])} endpoints → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### Task 1.3: Test `extract_api_endpoints`

Create `tests/harness/generators/__init__.py` (empty) and `tests/harness/generators/test_extract_api_endpoints.py`:

```python
"""H.2.1 — extract_api_endpoints generator test."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = REPO_ROOT / ".harness" / "generators" / "extract_api_endpoints.py"
FIXTURE_ROOT = REPO_ROOT / "tests" / "harness" / "fixtures" / "generators"


def test_extracts_two_endpoints() -> None:
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--root", str(FIXTURE_ROOT), "--print"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    names = {e["name"] for e in payload["endpoints"]}
    assert names == {"fetchFoo", "createFoo"}, payload
    by_name = {e["name"]: e for e in payload["endpoints"]}
    assert by_name["fetchFoo"]["method"] == "GET"
    assert by_name["createFoo"]["method"] == "POST"
    assert by_name["fetchFoo"]["response_type"] == "FooResponse"


def test_output_is_deterministic() -> None:
    runs = []
    for _ in range(2):
        result = subprocess.run(
            [sys.executable, str(GENERATOR), "--root", str(FIXTURE_ROOT), "--print"],
            capture_output=True, text=True, timeout=10,
        )
        runs.append(result.stdout)
    assert runs[0] == runs[1], "non-deterministic output"
```

### Task 1.4: Red commit

```bash
python -m pytest tests/harness/generators/test_extract_api_endpoints.py -v
git add tests/harness/fixtures/generators/frontend tests/harness/generators .harness/generators/extract_api_endpoints.py
git commit -m "$(cat <<'EOF'
test(red): H.2.1 — extract_api_endpoints fixture + test

Synthetic frontend services/api/foo.ts with two endpoints (fetchFoo GET
and createFoo POST). Tests assert the generator extracts names, methods,
and response types AND that output is byte-deterministic across two runs.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 1.5: Implement + test the remaining three generators

Repeat the same pattern for `extract_ui_primitives`, `extract_routes`, `extract_test_coverage_targets`:

**`extract_ui_primitives.py`:** Walk `frontend/src/components/ui/*.tsx`, parse top-level `export const|function` names, detect `@radix-ui/` imports → set `uses_radix: true`. Schema:

```python
EXPORT_NAME_RE = re.compile(r'^\s*export\s+(?:const|function)\s+(\w+)', re.MULTILINE)
RADIX_IMPORT_RE = re.compile(r'from\s+["\']@radix-ui/')
```

Emit `{ "primitives": [{ "name", "exports": [str], "file", "uses_radix": bool }] }`.

**`extract_routes.py`:** Walk `frontend/src/router.tsx`, parse `createBrowserRouter([...])` array members. For each `{ path: "...", element: <X /> }`, find the corresponding `const X = lazy(() => import("..."))` (set `lazy_imported=true`) or sync import (`lazy_imported=false`). Emit `{ "routes": [{ "path", "page_module", "lazy_imported": bool }] }`.

**`extract_test_coverage_targets.py`:** Read `frontend/vitest.config.ts`, regex-find the `thresholds` block, parse each glob → numeric mapping. Emit `{ "thresholds": [{ "glob", "branches", "functions", "lines", "statements" }] }`.

For each: write the generator, write a test asserting expected output (mirror the structure of test_extract_api_endpoints.py), TDD red → green, then commit each individually as `feat(green): H.2.1 — extract_<name> generator`.

### Task 1.6: Write generated-file schemas

Create `.harness/schemas/generated/api_endpoints.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "required": ["endpoints"],
  "properties": {
    "endpoints": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["name", "url_template", "method", "response_type", "file"],
        "properties": {
          "name": {"type": "string"},
          "url_template": {"type": "string"},
          "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
          "request_type": {"type": "string"},
          "response_type": {"type": "string"},
          "file": {"type": "string"}
        }
      }
    }
  }
}
```

Create the three sibling schemas (`ui_primitives`, `routes`, `test_coverage_targets`) following the same shape — top-level required key, item objects with `additionalProperties: false`.

### Task 1.7: Run all four generators against the live repo

```bash
mkdir -p .harness/generated
python .harness/generators/extract_api_endpoints.py
python .harness/generators/extract_ui_primitives.py
python .harness/generators/extract_routes.py
python .harness/generators/extract_test_coverage_targets.py
```

Expected: four JSON files appear under `.harness/generated/`. Inspect each — if a real endpoint is missing, the regex needs tweaking (extend test fixture FIRST, then refine generator).

### Task 1.8: Validate generated/ against schemas

```bash
python .harness/checks/harness_policy_schema.py
```

Expected: zero ERRORs. If any fire, tighten or loosen the schema until clean.

### Task 1.9: Determinism check

```bash
make harness-h21-only 2>/dev/null || (
  python .harness/generators/extract_api_endpoints.py
  python .harness/generators/extract_ui_primitives.py
  python .harness/generators/extract_routes.py
  python .harness/generators/extract_test_coverage_targets.py
)
git diff --stat .harness/generated/
```

Expected: empty diff after a re-run.

### Task 1.10: Commit green

```bash
git add .harness/generators/extract_*.py .harness/schemas/generated tests/harness/generators .harness/generated/
git commit -m "$(cat <<'EOF'
feat(green): H.2.1 — frontend generators (api_endpoints, ui_primitives, routes, test_coverage_targets)

Four generators emit deterministic JSON under .harness/generated/.
Sources: frontend/src/services/api/*.ts (apiClient<T> calls),
frontend/src/components/ui/*.tsx (export names + Radix detection),
frontend/src/router.tsx (createBrowserRouter route table with lazy
detection), frontend/vitest.config.ts (per-glob coverage thresholds).
Each ships a JSON-Schema validator under .harness/schemas/generated/.
H-25 docstrings cover missing/malformed/no-upstream.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Story H.2.2 — Generators 5–8 (backend)

Generators in this story:

| # | Name | Source | Output |
|---|---|---|---|
| 5 | `extract_backend_routes` | `backend/src/api/*.py` (FastAPI route decorators) | `{ "routes": [{ "method", "path", "handler", "module", "auth_dep", "rate_limit", "csrf_dep", "request_type", "response_type" }] }` |
| 6 | `extract_db_models` | `backend/src/models/db/*.py` (SQLModel + table=True) | `{ "models": [{ "class_name", "table_name", "fields": [...], "file" }] }` |
| 7 | `extract_storage_gateway_methods` | `backend/src/storage/gateway.py` (StorageGateway methods) | `{ "methods": [{ "name", "kind": "read|write", "args", "return_type", "audited": bool, "timed": bool }] }` |
| 8 | `extract_test_coverage_required_paths` + `extract_test_inventory` | `.harness/typecheck_policy.yaml` + `backend/tests/**/*.py` | one file per generator |

**Files (representative):**
- Create: `.harness/generators/extract_backend_routes.py`
- Create: `.harness/generators/extract_db_models.py`
- Create: `.harness/generators/extract_storage_gateway_methods.py`
- Create: `.harness/generators/extract_test_coverage_required_paths.py`
- Create: `.harness/generators/extract_test_inventory.py`
- Create: `tests/harness/generators/test_extract_backend_routes.py` (and four siblings)
- Create: `tests/harness/fixtures/generators/backend/api/routes_v4.py`
- Create: `tests/harness/fixtures/generators/backend/models/db/incident.py`
- Create: `tests/harness/fixtures/generators/backend/storage/gateway.py`
- Create: `tests/harness/fixtures/generators/backend/tests/test_dummy.py`
- Create: `.harness/schemas/generated/backend_routes.schema.json` (and four siblings)

### Task 2.1: Create the synthetic backend fixture tree

```bash
mkdir -p tests/harness/fixtures/generators/backend/{api,models/db,storage,tests}
```

`backend/api/routes_v4.py`:

```python
"""Synthetic backend API for generator tests."""
from fastapi import APIRouter, Depends, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


def require_user() -> None: ...


@router.get("/api/v4/incidents")
async def list_incidents() -> list[dict]:
    return []


@router.post("/api/v4/incidents")
@limiter.limit("10/minute")
async def create_incident(
    request: Request,
    payload: dict,
    user=Depends(require_user),
) -> dict:
    return {"ok": True}
```

`backend/models/db/incident.py`:

```python
"""Synthetic SQLModel db model."""
from sqlmodel import SQLModel, Field


class Incident(SQLModel, table=True):
    __tablename__ = "incidents"

    id: int | None = Field(default=None, primary_key=True)
    title: str = Field(max_length=200)
    severity: str = Field(max_length=16)
```

`backend/storage/gateway.py`:

```python
"""Synthetic StorageGateway for generator tests."""
from backend.src.storage._timing import timed_query


class StorageGateway:
    @timed_query("get_incident")
    async def get_incident(self, incident_id: str) -> dict | None:
        return None

    @timed_query("create_incident")
    async def create_incident(self, payload: dict) -> dict:
        await self._audit("create_incident", payload)
        return {"id": "x"}

    async def _audit(self, *args, **kwargs) -> None:
        return None
```

`backend/tests/test_dummy.py`:

```python
"""Synthetic test file for generator inventory."""
from hypothesis import given, strategies as st


def test_smoke() -> None:
    assert 1 == 1


@given(st.integers())
def test_property(x: int) -> None:
    assert x == x
```

### Task 2.2: Implement `extract_backend_routes`

Create `.harness/generators/extract_backend_routes.py`:

```python
#!/usr/bin/env python3
"""Generator — backend FastAPI routes inventory.

Walks backend/src/api/**/*.py (or fixture --root), parses each
@router.<verb>(<path>) decorator, extracts handler name, body type
annotation, return annotation, and the auth/rate-limit/csrf dependencies
already discovered by Q13.B's check (security_policy_b).

Output: .harness/generated/backend_routes.json
Schema: .harness/schemas/generated/backend_routes.schema.json

H-25:
  Missing input    — exit 0 with empty list.
  Malformed input  — skip unparseable file (no error).
  Upstream failed  — none.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from .harness.generators._common import iter_python_files, write_generated  # noqa: E402


def _route_info(dec: ast.AST) -> tuple[str, str] | None:
    if not isinstance(dec, ast.Call):
        return None
    if not (isinstance(dec.func, ast.Attribute) and isinstance(dec.func.value, ast.Name)):
        return None
    if dec.func.value.id not in {"router", "app"}:
        return None
    verb = dec.func.attr.upper()
    if verb not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        return None
    if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
        return verb, dec.args[0].value
    return None


def _depends_callee(default: ast.AST | None) -> str | None:
    if (
        isinstance(default, ast.Call)
        and isinstance(default.func, ast.Name)
        and default.func.id == "Depends"
        and default.args
    ):
        inner = default.args[0]
        if isinstance(inner, ast.Name):
            return inner.id
    return None


def _has_rate_limit(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(
        isinstance(d, ast.Call)
        and isinstance(d.func, ast.Attribute)
        and isinstance(d.func.value, ast.Name)
        and d.func.value.id == "limiter"
        and d.func.attr == "limit"
        for d in fn.decorator_list
    )


def _ann_str(ann: ast.AST | None) -> str | None:
    if ann is None:
        return None
    return ast.unparse(ann)


def _scan(root: Path) -> list[dict]:
    api_root = root / "backend" / "api"
    api_root_alt = root / "backend" / "src" / "api"
    candidates = api_root if api_root.exists() else api_root_alt
    out: list[dict] = []
    if not candidates.exists():
        return out
    for path in iter_python_files(candidates, exclude=("__pycache__",)):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                info = _route_info(dec)
                if info is None:
                    continue
                method, route_path = info
                # Discover auth dep + body/response types
                auth_dep = None
                request_type = None
                args_with_defaults = list(zip(node.args.args, [None] * (len(node.args.args) - len(node.args.defaults)) + list(node.args.defaults)))
                for arg, default in args_with_defaults:
                    callee = _depends_callee(default)
                    if callee:
                        auth_dep = callee
                    elif arg.annotation is not None and arg.arg in {"payload", "body"}:
                        request_type = _ann_str(arg.annotation)
                csrf_dep = False
                for arg in node.args.args + node.args.kwonlyargs:
                    if arg.annotation is not None and "CsrfProtect" in (_ann_str(arg.annotation) or ""):
                        csrf_dep = True
                out.append({
                    "method": method,
                    "path": route_path,
                    "handler": node.name,
                    "module": str(path.relative_to(root)),
                    "auth_dep": auth_dep,
                    "rate_limit": _has_rate_limit(node),
                    "csrf_dep": csrf_dep,
                    "request_type": request_type,
                    "response_type": _ann_str(node.returns),
                })
    out.sort(key=lambda e: (e["module"], e["path"], e["method"]))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args(argv)
    payload = {"routes": _scan(args.root)}
    if args.print:
        import json
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    out_path = write_generated("backend_routes", payload)
    print(f"[INFO] wrote {len(payload['routes'])} routes → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### Task 2.3: Test `extract_backend_routes`

Create `tests/harness/generators/test_extract_backend_routes.py`:

```python
"""H.2.2 — extract_backend_routes generator test."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = REPO_ROOT / ".harness" / "generators" / "extract_backend_routes.py"
FIXTURE_ROOT = REPO_ROOT / "tests" / "harness" / "fixtures" / "generators"


def test_extracts_two_routes() -> None:
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--root", str(FIXTURE_ROOT), "--print"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    paths = {(r["method"], r["path"]) for r in payload["routes"]}
    assert paths == {("GET", "/api/v4/incidents"), ("POST", "/api/v4/incidents")}
    by_method = {r["method"]: r for r in payload["routes"]}
    assert by_method["POST"]["auth_dep"] == "require_user"
    assert by_method["POST"]["rate_limit"] is True
    assert by_method["GET"]["auth_dep"] is None


def test_output_is_deterministic() -> None:
    runs = []
    for _ in range(2):
        result = subprocess.run(
            [sys.executable, str(GENERATOR), "--root", str(FIXTURE_ROOT), "--print"],
            capture_output=True, text=True, timeout=10,
        )
        runs.append(result.stdout)
    assert runs[0] == runs[1]
```

### Task 2.4: Red commit

```bash
python -m pytest tests/harness/generators/test_extract_backend_routes.py -v
git add tests/harness/fixtures/generators/backend tests/harness/generators/test_extract_backend_routes.py .harness/generators/extract_backend_routes.py
git commit -m "$(cat <<'EOF'
test(red): H.2.2 — extract_backend_routes fixture + test

Synthetic backend with one GET (no auth) and one POST (auth via
Depends(require_user) + @limiter.limit). Tests assert the generator
extracts method/path tuples + auth_dep + rate_limit flags AND output
is deterministic across two runs.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 2.5: Implement + test the four remaining generators

Repeat the same pattern for `extract_db_models`, `extract_storage_gateway_methods`, `extract_test_coverage_required_paths`, `extract_test_inventory`:

**`extract_db_models.py`:** AST-walk `backend/src/models/db/*.py`, find `class X(SQLModel, table=True)`, walk class body for `name: type = Field(...)` annotations. Emit `{ "models": [{ "class_name", "table_name", "fields": [{"name", "type", "primary_key": bool, "max_length": int|null}], "file" }] }`.

**`extract_storage_gateway_methods.py`:** AST-walk `backend/src/storage/gateway.py`, find `class StorageGateway:` body, for each method emit name, kind (`write` if name starts with `create_/update_/delete_/upsert_/merge_/set_`, else `read`), args (with annotations), return type, `audited` (true if body contains `self._audit(...)`), `timed` (true if has `@timed_query` decorator).

**`extract_test_coverage_required_paths.py`:** Read `.harness/typecheck_policy.yaml.mypy_strict_paths` (or a dedicated key in `documentation_policy.yaml`), emit `{ "required_paths": [str], "rationale": "Q19" }`.

**`extract_test_inventory.py`:** Walk `backend/tests/**/*.py`, count `def test_*` functions and `@given`-decorated functions (Hypothesis tests). Emit `{ "files": [{ "path", "test_count": int, "hypothesis_count": int }] }`.

For each: write generator → write test → red → green → commit individually.

### Task 2.6: Schema files

Create the five generated-file schemas under `.harness/schemas/generated/{backend_routes,db_models,storage_gateway_methods,test_coverage_required_paths,test_inventory}.schema.json` with the same shape as Story H.2.1 (top-level required key, item objects with `additionalProperties: false`).

### Task 2.7: Run all five generators against the live repo

```bash
python .harness/generators/extract_backend_routes.py
python .harness/generators/extract_db_models.py
python .harness/generators/extract_storage_gateway_methods.py
python .harness/generators/extract_test_coverage_required_paths.py
python .harness/generators/extract_test_inventory.py
```

Inspect each emitted file. If counts look wrong, adjust the AST walker (extend fixture FIRST).

### Task 2.8: Schema validation

```bash
python .harness/checks/harness_policy_schema.py
```

### Task 2.9: Determinism

```bash
for g in extract_backend_routes extract_db_models extract_storage_gateway_methods extract_test_coverage_required_paths extract_test_inventory; do
  python .harness/generators/${g}.py
done
git diff --stat .harness/generated/
```

Expected: empty.

### Task 2.10: Commit green

```bash
git add .harness/generators/extract_*.py .harness/schemas/generated tests/harness/generators .harness/generated/
git commit -m "$(cat <<'EOF'
feat(green): H.2.2 — backend generators (backend_routes, db_models, storage_gateway_methods, test_coverage_required_paths, test_inventory)

Five backend generators emit deterministic JSON under .harness/
generated/. Sources: backend/src/api/**/*.py (FastAPI decorators +
Depends + slowapi limiter + CsrfProtect dep), backend/src/models/db/
(SQLModel table=True classes + field annotations), backend/src/
storage/gateway.py (StorageGateway methods + audit/timed metadata),
.harness/typecheck_policy.yaml (required strict paths), and
backend/tests/**/*.py (test counts + Hypothesis counts). H-25
docstrings throughout.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Story H.2.3 — Generators 9–12 (cross-stack)

Generators in this story:

| # | Name | Source | Output |
|---|---|---|---|
| 9 | `extract_validation_inventory` | `backend/src/models/{api,agent}/**/*.py` | per-class summary of model_config + field bounds |
| 10 | `extract_dependency_inventory` | `backend/pyproject.toml` + `frontend/package.json` | merged dependency list with allow/deny status |
| 11 | `extract_performance_budgets` | `.harness/performance_budgets.yaml` | shaped projection of caps for AI |
| 12 | `extract_security_inventory` | `.harness/security_policy.yaml` + repo scan | summary of secrets/auth/rate-limit policy |

**Files (representative):**
- Create: `.harness/generators/extract_validation_inventory.py`
- Create: `.harness/generators/extract_dependency_inventory.py`
- Create: `.harness/generators/extract_performance_budgets.py`
- Create: `.harness/generators/extract_security_inventory.py`
- Create: 4 paired schema + test pairs

### Task 3.1: Create cross-stack fixtures

```bash
mkdir -p tests/harness/fixtures/generators/cross-stack/models/api
mkdir -p tests/harness/fixtures/generators/cross-stack/models/agent
```

Add a fixture `models/api/incident_request.py` (frozen+forbid request model with bounded fields) and `models/agent/finding.py` (forbid+frozen agent schema with confidence ge/le bounds). These mirror the H.1a.4 compliant fixtures.

Also drop in a fixture `pyproject.toml` (with 2 deps) and `package.json` (with 2 deps) under `cross-stack/`.

### Task 3.2: Implement `extract_validation_inventory`

Create `.harness/generators/extract_validation_inventory.py`:

```python
#!/usr/bin/env python3
"""Generator — Pydantic boundary model inventory.

Walks backend/src/models/{api,agent}/**/*.py, parses each pydantic class,
records: class name, model_config kwargs (extra, frozen), each field name
+ type annotation + Field() ge/le/min_length/max_length kwargs.

Output: .harness/generated/validation_inventory.json
Schema: .harness/schemas/generated/validation_inventory.schema.json

H-25 — same defaults as siblings.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from .harness.generators._common import iter_python_files, write_generated  # noqa: E402


def _config_kwargs(cls: ast.ClassDef) -> dict:
    out: dict = {}
    for stmt in cls.body:
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and stmt.targets[0].id == "model_config"
            and isinstance(stmt.value, ast.Call)
        ):
            for kw in stmt.value.keywords:
                if kw.arg and isinstance(kw.value, ast.Constant):
                    out[kw.arg] = kw.value.value
    return out


def _field_meta(stmt: ast.AnnAssign) -> dict:
    name = stmt.target.id if isinstance(stmt.target, ast.Name) else "?"
    type_str = ast.unparse(stmt.annotation) if stmt.annotation is not None else "?"
    field_meta: dict = {"name": name, "type": type_str}
    if (
        isinstance(stmt.value, ast.Call)
        and isinstance(stmt.value.func, ast.Name)
        and stmt.value.func.id == "Field"
    ):
        for kw in stmt.value.keywords:
            if kw.arg in {"ge", "le", "gt", "lt", "min_length", "max_length"} and isinstance(kw.value, ast.Constant):
                field_meta[kw.arg] = kw.value.value
    return field_meta


def _scan(root: Path) -> list[dict]:
    out: list[dict] = []
    for sub in ("api", "agent"):
        for base in (root / "backend" / "models" / sub, root / "backend" / "src" / "models" / sub):
            if not base.exists():
                continue
            for path in iter_python_files(base, exclude=("__pycache__",)):
                try:
                    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                except (OSError, UnicodeDecodeError, SyntaxError):
                    continue
                for node in ast.walk(tree):
                    if not isinstance(node, ast.ClassDef):
                        continue
                    fields = [_field_meta(s) for s in node.body if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name)]
                    out.append({
                        "kind": sub,
                        "class": node.name,
                        "config": _config_kwargs(node),
                        "fields": fields,
                        "file": str(path.relative_to(root)),
                    })
    out.sort(key=lambda e: (e["file"], e["class"]))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args(argv)
    payload = {"models": _scan(args.root)}
    if args.print:
        import json
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    out_path = write_generated("validation_inventory", payload)
    print(f"[INFO] wrote {len(payload['models'])} models → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### Task 3.3: Implement `extract_dependency_inventory`

Read `backend/pyproject.toml` (`[project.dependencies]`) + `frontend/package.json` (`dependencies` + `devDependencies`). Cross-reference each with `.harness/dependencies.yaml.python.allowed` / `npm.allowed` / `global_blacklist`. Emit:

```json
{
  "python": [{"name": "fastapi", "version": ">=0.110", "allowed": true, "on_spine": true}],
  "npm":    [{"name": "react",   "version": "18.0.0",  "allowed": true}]
}
```

### Task 3.4: Implement `extract_performance_budgets`

Read `.harness/performance_budgets.yaml`. Project into AI-readable shape:

```json
{
  "agent_caps": {"tool_calls_max": 8, "tokens_max": 4000, "wall_clock_max_ms": 30000},
  "db_query_max_ms": 100,
  "bundle_kb": {"initial": 220, "route": 100, "css": 50},
  "soft_track": ["api_p99", "lighthouse_fcp", "lighthouse_tti", "lighthouse_cls"]
}
```

### Task 3.5: Implement `extract_security_inventory`

Read `.harness/security_policy.yaml` + scan repo for routes that are auth-protected/rate-limited/CSRF-protected (consume the H.2.2 `extract_backend_routes` output). Emit consolidated security view:

```json
{
  "auth_dependency_names": ["get_current_user", "require_user", ...],
  "rate_limit_exempt": ["GET:/healthz", ...],
  "csrf_exempt": ["POST:/api/v4/webhooks/*"],
  "routes_summary": {"total": 42, "with_auth": 38, "with_rate_limit": 35, "with_csrf": 30}
}
```

> This generator depends on `backend_routes.json` already existing — Story H.2.6's orchestrator will run them in topological order. For now, fall back to scanning the source directly if the prior file is missing.

### Task 3.6: Tests

Per generator: write a paired `tests/harness/generators/test_extract_<name>.py` asserting expected JSON shape + determinism.

### Task 3.7: Schemas

Per generator: write `.harness/schemas/generated/<name>.schema.json`.

### Task 3.8: Live-repo regen

```bash
for g in extract_validation_inventory extract_dependency_inventory extract_performance_budgets extract_security_inventory; do
  python .harness/generators/${g}.py
done
```

### Task 3.9: Determinism + schema validation

```bash
python .harness/checks/harness_policy_schema.py
```

### Task 3.10: Commit green

```bash
git add .harness/generators/extract_*.py .harness/schemas/generated tests/harness/generators .harness/generated/
git commit -m "$(cat <<'EOF'
feat(green): H.2.3 — cross-stack generators (validation_inventory, dependency_inventory, performance_budgets, security_inventory)

Four cross-stack generators emit deterministic JSON under .harness/
generated/. Sources: backend/src/models/{api,agent}/** (Pydantic
class config + bounded field metadata), pyproject.toml + package.json
(dependency status against allow/deny lists), .harness/performance_
budgets.yaml (AI-readable shape), .harness/security_policy.yaml
+ generated/backend_routes.json (consolidated security view with
route protection summary). H-25 throughout.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Story H.2.4 — Generators 13–14 (a11y + documentation)

Generators in this story:

| # | Name | Source | Output |
|---|---|---|---|
| 13 | `extract_accessibility_inventory` | `frontend/src/components/ui/*.test.tsx` (axe presence) + `.harness/accessibility_policy.yaml` | summary of ui primitives' axe coverage + incident-critical pages list |
| 14 | `extract_documentation_inventory` | `backend/src/{api,storage,models,agents/**/runners}/**/*.py` + `frontend/src/{hooks,lib,services}/**/*.{ts,tsx}` + `docs/decisions/*.md` | per-symbol docstring/JSDoc presence + ADR list |

**Files:**
- Create: `.harness/generators/extract_accessibility_inventory.py`
- Create: `.harness/generators/extract_documentation_inventory.py`
- Create: 2 schema files + 2 test files

### Task 4.1: Implement `extract_accessibility_inventory`

Walk `frontend/src/components/ui/*.tsx`. For each primitive `name.tsx`, look for the paired `name.test.tsx` and check whether it contains `axe(` or `runAxe(` (matches the H.1b.6 rule). Read `.harness/accessibility_policy.yaml.incident_critical` and pair each entry with the existence of `frontend/e2e/a11y/<page-lower>.spec.ts`. Emit:

```json
{
  "ui_primitives": [{"name": "Button", "axe_test_present": true, "test_file": "..."}],
  "incident_critical_pages": [{"name": "InvestigationView", "e2e_spec_present": true, "spec_file": "..."}],
  "soft_warn_rules": ["color-contrast"]
}
```

### Task 4.2: Implement `extract_documentation_inventory`

Walk the spine paths from `.harness/documentation_policy.yaml.spine_python_paths` + `frontend_jsdoc_paths`. For each public symbol, record `{file, symbol, kind, has_docstring/has_jsdoc, line}`. Walk `docs/decisions/*.md` and emit each ADR with title + date.

### Task 4.3: Tests + schemas

Write paired tests asserting expected shape + determinism. Write paired schemas under `.harness/schemas/generated/`.

### Task 4.4: Live-repo regen

```bash
python .harness/generators/extract_accessibility_inventory.py
python .harness/generators/extract_documentation_inventory.py
```

### Task 4.5: Determinism + schema validation

```bash
python .harness/checks/harness_policy_schema.py
```

### Task 4.6: Commit green

```bash
git add .harness/generators/extract_accessibility_inventory.py .harness/generators/extract_documentation_inventory.py .harness/schemas/generated tests/harness/generators .harness/generated/
git commit -m "$(cat <<'EOF'
feat(green): H.2.4 — a11y + documentation generators

Two generators emit deterministic JSON under .harness/generated/.
Sources: frontend/src/components/ui/*.test.tsx (axe coverage
detection) + accessibility_policy.yaml (incident-critical pages with
e2e spec presence); spine python files + frontend hooks/lib/services
(per-symbol docstring/JSDoc presence) + docs/decisions/*.md (ADR
inventory).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 4.7: Verify discovery

```bash
ls .harness/generated/ | grep -E "^(accessibility|documentation)_inventory.json$"
```

Expected: both present.

---

# Story H.2.5 — Generators 15–17 (logging + errors + conventions)

Generators in this story:

| # | Name | Source | Output |
|---|---|---|---|
| 15 | `extract_logging_inventory` | `backend/src/observability/logging.py` + spine python | logger config summary + per-handler correlation kwargs |
| 16 | `extract_error_taxonomy` + `extract_outbound_http_inventory` | `backend/src/errors/**/*.py` + httpx callsites | (a) Result classes + raised exception classes; (b) outbound httpx callsites with retry status |
| 17 | `extract_conventions_inventory` | `backend/pyproject.toml` (ruff config) + `frontend/eslint.config.js` + `commitlint.config.*` | active rule sets per tool |

### Task 5.1: Implement `extract_logging_inventory`

Read `backend/src/observability/logging.py` (regex-find the structlog processors list). Walk spine python files, count `log.<level>(...)` calls, count those with each `request_id`/`tenant_id`/`session_id`/`correlation_id` kwarg. Emit:

```json
{
  "structlog_processors": ["redact_secrets", "add_log_level", "JSONRenderer"],
  "tracing_initialized": true,
  "log_calls": [{"file": "...", "level": "info", "event": "incident_created", "correlation_kwargs": ["request_id"]}]
}
```

### Task 5.2: Implement `extract_error_taxonomy`

AST-walk `backend/src/errors/**/*.py`. Emit list of public exception classes (with parent + docstring) + `Result` type aliases. Sources of expected vs unexpected outcomes.

### Task 5.3: Implement `extract_outbound_http_inventory`

Walk `backend/src/**/*.py`. For each `httpx.AsyncClient(...).get|post|put|patch|delete|request(...)` call, record `{file, line, url_arg_string, retry_decorated: bool, timeout_explicit: bool}`. Cross-reference with the `with_retry` decorator from `backend/src/utils/http.py`.

### Task 5.4: Implement `extract_conventions_inventory`

Read `backend/pyproject.toml [tool.ruff]`, list active rule sets. Read `frontend/eslint.config.js` (regex), list active plugins. Read `commitlint.config.{js,cjs}`, list extended preset. Emit consolidated:

```json
{
  "ruff": {"select": ["E", "F", "I", "N", "B", "D"], "ignore": [], "line_length": 100},
  "eslint": {"plugins": ["import", "jsx-a11y", "jsdoc"], "rule_count": 47},
  "commitlint": {"extends": ["@commitlint/config-conventional"]}
}
```

### Task 5.5–5.7: Tests + schemas + live-repo regen

Per generator: paired test + schema. Run on live repo. Determinism + schema validation. Each is its own red→green cycle, committed individually.

### Task 5.8: `extract_outbound_http_inventory` integration check

After running `extract_outbound_http_inventory`, every entry with `retry_decorated: false` AND not living under `backend/src/utils/http.py` is a Q17 violation — but the check `error_handling_policy.py` already enforces it. The generator's only job here is to provide the truth file for AI context.

### Task 5.9: Determinism + schema validation

```bash
python .harness/checks/harness_policy_schema.py
```

### Task 5.10: Commit green

```bash
git add .harness/generators/extract_logging_inventory.py .harness/generators/extract_error_taxonomy.py .harness/generators/extract_outbound_http_inventory.py .harness/generators/extract_conventions_inventory.py .harness/schemas/generated tests/harness/generators .harness/generated/
git commit -m "$(cat <<'EOF'
feat(green): H.2.5 — logging/errors/conventions generators

Four generators emit deterministic JSON under .harness/generated/.
extract_logging_inventory: structlog processors + per-call correlation
kwargs. extract_error_taxonomy: Result aliases + public exception
classes from backend/src/errors. extract_outbound_http_inventory:
httpx callsites with retry+timeout status. extract_conventions_
inventory: active ruff/eslint/commitlint rule sets.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Story H.2.6 — Generator 18 (typecheck_inventory) + run_harness_regen orchestrator

**Files:**
- Create: `.harness/generators/extract_typecheck_inventory.py`
- Create: `tools/run_harness_regen.py`
- Create: `tests/harness/generators/test_run_harness_regen.py`
- Create: `.harness/schemas/generated/typecheck_inventory.schema.json`

### Task 6.1: Implement `extract_typecheck_inventory`

Run `mypy --strict --json-output` on configured spine paths (or fall back to text-mode + parse). Read `.harness/baselines/{mypy,tsc}_baseline.json`. Emit consolidated view:

```json
{
  "strict_paths_python": ["backend/src/storage", ...],
  "tsc_strict": true,
  "tsc_no_unchecked_indexed_access": true,
  "mypy_baseline_size": 23,
  "tsc_baseline_size": 5,
  "current_findings_summary": {"mypy_new": 0, "tsc_new": 0}
}
```

### Task 6.2: Implement `tools/run_harness_regen.py`

Create:

```python
#!/usr/bin/env python3
"""Orchestrate `make harness` — run every .harness/generators/*.py script
in topological order, then validate every output against its schema.

Topological order is hand-coded here because generators depend on each
other (e.g., extract_security_inventory consumes backend_routes.json).
The DEPENDENCIES dict declares each generator's prerequisites; we run
the prerequisites first.

H-4: generated files are auto-derived; never hand-edited.
H-25:
  Missing input    — exit 2 if .harness/generators/ missing.
  Malformed input  — emit ERROR per generator that fails (does not block others).
  Upstream failed  — surfaces the failing generator's name + its stderr.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATORS_DIR = REPO_ROOT / ".harness" / "generators"

# Each key is a generator stem; value is the list of stems that must run first.
DEPENDENCIES: dict[str, list[str]] = {
    "extract_security_inventory": ["extract_backend_routes"],
    "extract_typecheck_inventory": [],
    # default: no deps
}


def _all_generators() -> list[str]:
    return sorted(
        p.stem for p in GENERATORS_DIR.glob("*.py")
        if p.name not in {"__init__.py", "_common.py"}
    )


def _topological_order(generators: list[str]) -> list[str]:
    visited: set[str] = set()
    order: list[str] = []

    def visit(name: str) -> None:
        if name in visited:
            return
        visited.add(name)
        for dep in DEPENDENCIES.get(name, []):
            visit(dep)
        order.append(name)

    for g in generators:
        visit(g)
    return order


def _run_one(name: str) -> tuple[str, int, str]:
    script = GENERATORS_DIR / f"{name}.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )
    return name, result.returncode, (result.stdout or "") + (result.stderr or "")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", action="append", help="Run only the named generator(s).")
    parser.add_argument("--parallel", type=int, default=4, help="Number of parallel workers.")
    args = parser.parse_args(argv)

    if not GENERATORS_DIR.exists():
        print(f"[ERROR] {GENERATORS_DIR} missing", file=sys.stderr)
        return 2

    targets = args.only if args.only else _all_generators()
    ordered = _topological_order(targets)

    overall = 0
    # Run dependency-roots sequentially, then independents in parallel
    independents: list[str] = []
    for name in ordered:
        if DEPENDENCIES.get(name):
            # has deps — run sequentially after deps already executed
            n, rc, output = _run_one(name)
            print(f"[GEN] {n} → exit {rc}")
            if rc != 0:
                print(output)
                overall = rc
        else:
            independents.append(name)

    with concurrent.futures.ProcessPoolExecutor(max_workers=args.parallel) as pool:
        for n, rc, output in pool.map(_run_one, independents):
            print(f"[GEN] {n} → exit {rc}")
            if rc != 0:
                print(output)
                overall = rc

    # Schema validate everything we just wrote
    rc = subprocess.run(
        [sys.executable, str(REPO_ROOT / ".harness" / "checks" / "harness_policy_schema.py")],
        cwd=REPO_ROOT,
    ).returncode
    if rc != 0:
        overall = rc
    print(f"\nHARNESS_REGEN_SUMMARY status={'PASS' if overall == 0 else 'FAIL'}")
    return overall


if __name__ == "__main__":
    sys.exit(main())
```

### Task 6.3: Test the orchestrator

Create `tests/harness/generators/test_run_harness_regen.py`:

```python
"""H.2.6 — run_harness_regen orchestrator test."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR = REPO_ROOT / "tools" / "run_harness_regen.py"


def test_orchestrator_runs_with_only_flag() -> None:
    result = subprocess.run(
        [sys.executable, str(ORCHESTRATOR), "--only", "extract_typecheck_inventory"],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode in {0, 1}, result.stderr
    assert "HARNESS_REGEN_SUMMARY" in result.stdout


def test_orchestrator_topological_order_respects_security_after_routes() -> None:
    """extract_security_inventory must run after extract_backend_routes."""
    result = subprocess.run(
        [sys.executable, str(ORCHESTRATOR), "--only", "extract_security_inventory"],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode in {0, 1}
    out = result.stdout
    assert out.find("[GEN] extract_backend_routes") < out.find("[GEN] extract_security_inventory")
```

### Task 6.4: Live-repo regen

```bash
python tools/run_harness_regen.py
```

Expected: every generator runs, every output passes schema, total wall time < 60s.

### Task 6.5: Determinism

```bash
python tools/run_harness_regen.py
git diff --stat .harness/generated/
```

Expected: empty.

### Task 6.6: Validate full

```bash
python tools/run_validate.py --full
```

Expected: PASS (combined fast + tests pass).

### Task 6.7: Commit green

```bash
git add .harness/generators/extract_typecheck_inventory.py tools/run_harness_regen.py tests/harness/generators/test_run_harness_regen.py .harness/schemas/generated/typecheck_inventory.schema.json .harness/generated/typecheck_inventory.json
git commit -m "$(cat <<'EOF'
feat(green): H.2.6 — extract_typecheck_inventory + run_harness_regen orchestrator

Final generator: typecheck_inventory consolidates strict-paths, tsc
flags, baseline sizes, and current new-findings summary into one AI-
readable file. tools/run_harness_regen.py runs every generator (parallel
where independent, sequential where dependent — extract_security_
inventory after extract_backend_routes), then invokes harness_policy_
schema for validation. Test asserts topological-order constraint
between dependent pairs. H-25 throughout.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Story H.2.7 — Claude Code session-start hook

**Acceptance criteria:**
- `.claude/settings.local.json` declares a `SessionStart` hook that invokes `python tools/load_harness.py --target <active-file>` and includes its stdout as system context.
- Hook only fires once per session; subsequent file opens use the loader's cache (or are no-ops).
- A test asserts the hook config is valid JSON and references the loader script.

**Files:**
- Modify: `.claude/settings.local.json`
- Create: `tools/_session_start_hook.sh` (the wrapper script the hook invokes)
- Create: `tests/harness/test_session_start_hook.py`

### Task 7.1: Read the existing settings file

```bash
cat .claude/settings.local.json 2>/dev/null || echo "{}"
```

### Task 7.2: Add the hook entry

Edit `.claude/settings.local.json` to include:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "bash tools/_session_start_hook.sh"
          }
        ]
      }
    ]
  }
}
```

(If the file already exists, merge the `hooks.SessionStart` block — do not overwrite other top-level keys.)

### Task 7.3: Create the wrapper script

Create `tools/_session_start_hook.sh`:

```bash
#!/usr/bin/env bash
# Session-start wrapper: invokes the harness loader against the repo root.
# Stdout is consumed by Claude Code as system context per its hook contract.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Use load_harness.py's "global" mode (no --target) — emits the root + cross-cutting
# context block. Per-file context is fetched on demand from the AI session loop.
python "${REPO_ROOT}/tools/load_harness.py" || true
```

Make it executable:

```bash
chmod +x tools/_session_start_hook.sh
```

### Task 7.4: Test

Create `tests/harness/test_session_start_hook.py`:

```python
"""H.2.7 — Claude Code session-start hook config test."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SETTINGS = REPO_ROOT / ".claude" / "settings.local.json"
WRAPPER = REPO_ROOT / "tools" / "_session_start_hook.sh"


def test_settings_file_is_valid_json() -> None:
    assert SETTINGS.exists()
    json.loads(SETTINGS.read_text(encoding="utf-8"))


def test_session_start_hook_is_declared() -> None:
    data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    hooks = (data.get("hooks") or {}).get("SessionStart") or []
    assert hooks, "no SessionStart hook declared"
    invocations = [h for entry in hooks for h in (entry.get("hooks") or [])]
    assert any("_session_start_hook.sh" in (h.get("command") or "") for h in invocations)


def test_wrapper_script_is_executable() -> None:
    import os
    assert WRAPPER.exists()
    assert os.access(WRAPPER, os.X_OK), "wrapper not executable"


def test_wrapper_invokes_load_harness() -> None:
    text = WRAPPER.read_text(encoding="utf-8")
    assert "load_harness.py" in text
```

### Task 7.5: Commit

```bash
python -m pytest tests/harness/test_session_start_hook.py -v
git add .claude/settings.local.json tools/_session_start_hook.sh tests/harness/test_session_start_hook.py
git commit -m "$(cat <<'EOF'
feat(green): H.2.7 — Claude Code session-start hook

.claude/settings.local.json declares SessionStart hook invoking
tools/_session_start_hook.sh, which calls tools/load_harness.py and
emits the root + cross-cutting harness context block as system context
on session start. Test asserts JSON validity, hook declaration,
wrapper executability, and that the wrapper references the loader.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Story H.2.8 — `harness-init` bootstrap

**Acceptance criteria:**
- `tools/init_harness.py` copies the entire `.harness/` skeleton + `tools/load_harness.py` + `tools/run_validate.py` + `tools/run_harness_regen.py` + minimal root `CLAUDE.md` template + `Makefile` targets into a target repo.
- The script prompts for `repo_root`, `owner` (top-level CLAUDE.md owner field), `tech_stack` (one of `python`, `typescript`, `polyglot`), and writes the destination's CLAUDE.md from a template with substitutions.
- Copies are idempotent: re-running on an already-bootstrapped repo only updates files that have changed (with `--force` to overwrite, default no-op).
- A pytest test runs the bootstrap into a tmp directory and asserts the expected files appear.

**Files:**
- Create: `tools/init_harness.py`
- Create: `tools/init_harness_templates/CLAUDE.md.tmpl`
- Create: `tools/init_harness_templates/Makefile.tmpl`
- Create: `tests/harness/test_init_harness.py`

### Task 8.1: Create the CLAUDE.md template

Create `tools/init_harness_templates/CLAUDE.md.tmpl`:

```markdown
---
name: root-claude-md
owner: {{OWNER}}
priority: 1
applies_to: ["**"]
type: behavior
---

# Project rules

This repo uses the AI harness. Always run `make validate-fast` before
declaring a task done.

## Rule loading contract
1. Root rules: this file (≤ 70 lines).
2. Directory rules: walk up from current file collecting CLAUDE.md.
3. Generated rules: `.harness/generated/*.json` (auto-derived).
4. Cross-cutting rules: `.harness/*.md` matched via `applies_to`.

Local-most wins. Conflicts surface as lint errors.

## Tech stack
{{TECH_STACK}}

## Validation
- `make validate-fast`: lint + custom checks (< 30s).
- `make validate-full`: + tests + heavy audits.

Discipline checklist: `CONTRIBUTING.md`.
```

### Task 8.2: Create the Makefile template

Create `tools/init_harness_templates/Makefile.tmpl`:

```makefile
.PHONY: validate-fast validate-full validate harness harness-install

validate-fast:  ## Inner-loop gate (< 30s)
	python tools/run_validate.py --fast

validate-full:  ## Pre-commit / CI gate
	python tools/run_validate.py --full

validate: validate-fast

harness:  ## Regenerate every .harness/generated/*.json
	python tools/run_harness_regen.py

harness-install:  ## Install pre-commit hook
	bash tools/install_pre_commit.sh
```

### Task 8.3: Implement `tools/init_harness.py`

```python
#!/usr/bin/env python3
"""Bootstrap the AI harness into a target repo.

Usage:
  python tools/init_harness.py --target /path/to/new/repo \
                               --owner @platform-team \
                               --tech-stack python

Idempotent: re-running on an already-bootstrapped repo updates only
files that have changed (use --force to overwrite without diff).

H-25:
  Missing input    — exit 2 if --target absent.
  Malformed input  — exit 2 if templates dir missing.
  Upstream failed  — none.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = REPO_ROOT / "tools" / "init_harness_templates"


def _render(template: str, owner: str, tech_stack: str) -> str:
    return (
        template
        .replace("{{OWNER}}", owner)
        .replace("{{TECH_STACK}}", tech_stack)
    )


def _copy_skeleton(src: Path, dest: Path, force: bool) -> int:
    """Copy .harness/ + tools/ stubs into dest. Returns number of files written."""
    written = 0
    for source in (src / ".harness").rglob("*"):
        if not source.is_file():
            continue
        rel = source.relative_to(src)
        out_path = dest / rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.exists() and not force:
            continue
        shutil.copy2(source, out_path)
        written += 1
    for tool in ("load_harness.py", "run_validate.py", "run_harness_regen.py", "_session_start_hook.sh", "install_pre_commit.sh"):
        source = src / "tools" / tool
        if not source.exists():
            continue
        out_path = dest / "tools" / tool
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.exists() and not force:
            continue
        shutil.copy2(source, out_path)
        written += 1
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True, help="Destination repo root.")
    parser.add_argument("--owner", type=str, required=True)
    parser.add_argument("--tech-stack", choices=["python", "typescript", "polyglot"], default="polyglot")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files.")
    args = parser.parse_args(argv)

    if not TEMPLATES_DIR.exists():
        print(f"[ERROR] templates dir missing: {TEMPLATES_DIR}", file=sys.stderr)
        return 2

    args.target.mkdir(parents=True, exist_ok=True)

    # CLAUDE.md
    claude_template = (TEMPLATES_DIR / "CLAUDE.md.tmpl").read_text(encoding="utf-8")
    claude_out = args.target / "CLAUDE.md"
    if not claude_out.exists() or args.force:
        claude_out.write_text(_render(claude_template, args.owner, args.tech_stack), encoding="utf-8")

    # Makefile
    makefile_template = (TEMPLATES_DIR / "Makefile.tmpl").read_text(encoding="utf-8")
    makefile_out = args.target / "Makefile"
    if not makefile_out.exists() or args.force:
        makefile_out.write_text(makefile_template, encoding="utf-8")

    # AGENTS.md alias
    agents_md = args.target / "AGENTS.md"
    if not agents_md.exists() or args.force:
        agents_md.write_text(claude_out.read_text(encoding="utf-8"), encoding="utf-8")

    # .cursorrules pointer
    cursor_rules = args.target / ".cursorrules"
    if not cursor_rules.exists() or args.force:
        cursor_rules.write_text("see CLAUDE.md and CLAUDE.md in subdirectories\n", encoding="utf-8")

    written = _copy_skeleton(REPO_ROOT, args.target, args.force)

    print(f"[INFO] bootstrap complete: {written} skeleton files + 4 root templates")
    print("Next steps:")
    print("  1. cd", args.target)
    print("  2. make harness-install   # install pre-commit hook")
    print("  3. make harness           # regenerate truth files")
    print("  4. make validate-fast     # smoke-test the harness")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### Task 8.4: Test

Create `tests/harness/test_init_harness.py`:

```python
"""H.2.8 — init_harness bootstrap test."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools" / "init_harness.py"


def test_bootstrap_creates_expected_files(tmp_path: Path) -> None:
    target = tmp_path / "new_repo"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--target", str(target), "--owner", "@bootstrap-test", "--tech-stack", "python"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert (target / "CLAUDE.md").exists()
    assert (target / "Makefile").exists()
    assert (target / "AGENTS.md").exists()
    assert (target / ".cursorrules").exists()
    assert (target / "tools" / "load_harness.py").exists()
    assert (target / "tools" / "run_validate.py").exists()
    assert (target / "tools" / "run_harness_regen.py").exists()
    # CLAUDE.md template substitutions occurred
    claude_text = (target / "CLAUDE.md").read_text(encoding="utf-8")
    assert "@bootstrap-test" in claude_text
    assert "{{OWNER}}" not in claude_text


def test_bootstrap_is_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "new_repo"
    for _ in range(2):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--target", str(target), "--owner", "@x", "--tech-stack", "python"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
    # second run did not error AND did not corrupt files
    assert "{{OWNER}}" not in (target / "CLAUDE.md").read_text(encoding="utf-8")
```

### Task 8.5: Run failing test + commit red

```bash
python -m pytest tests/harness/test_init_harness.py -v
git add tools/init_harness_templates tests/harness/test_init_harness.py
git commit -m "$(cat <<'EOF'
test(red): H.2.8 — init_harness bootstrap fixtures + assertions

CLAUDE.md.tmpl + Makefile.tmpl templates with {{OWNER}} and {{TECH_STACK}}
substitution markers. Tests assert bootstrap creates root files
(CLAUDE.md, AGENTS.md, .cursorrules, Makefile) + tools/load_harness.py
+ tools/run_validate.py + tools/run_harness_regen.py, that template
substitution succeeds, and that re-running is idempotent.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 8.6: Implement (already drafted in Task 8.3)

Add the script + run tests:

```bash
python -m pytest tests/harness/test_init_harness.py -v
```

Expected: pass.

### Task 8.7: Live smoke test

```bash
mkdir -p /tmp/harness-bootstrap-smoke
python tools/init_harness.py --target /tmp/harness-bootstrap-smoke --owner "@smoke-test" --tech-stack polyglot
ls /tmp/harness-bootstrap-smoke
```

Expected: CLAUDE.md, AGENTS.md, .cursorrules, Makefile, .harness/, tools/ all present.

### Task 8.8: Cleanup

```bash
rm -rf /tmp/harness-bootstrap-smoke
```

### Task 8.9: Run full validate

```bash
python tools/run_validate.py --full
```

### Task 8.10: Commit green

```bash
git add tools/init_harness.py
git commit -m "$(cat <<'EOF'
feat(green): H.2.8 — init_harness bootstrap

tools/init_harness.py copies .harness/ skeleton + tools/* + minimal
root templates (CLAUDE.md with {{OWNER}}+{{TECH_STACK}} substitution,
AGENTS.md alias, .cursorrules pointer, Makefile) into a target repo.
Idempotent: re-runs only update changed files; --force overwrites.
Smoke test verified into /tmp.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Story H.2.9 — Final docs + onboarding polish

**Acceptance criteria:**
- `.harness/README.md` documents how the harness works for human contributors: file layout, what each policy means, where to add a check, where to add an exemption, how to interpret findings.
- `docs/api.md` has at least three populated `## ` sections (Authentication, Endpoints, Error model) — first cut, not exhaustive.
- `CONTRIBUTING.md` (originally created in H.0a Story 10) is extended with a section pointing to `.harness/README.md` and `docs/api.md`.
- `docs/decisions/2026-04-26-harness-landed.md` ADR records the harness's GA — required by Q15.
- The harness's own self-checks all pass: `harness_rule_coverage`, `harness_fixture_pairing`, `harness_policy_schema`, `output_format_conformance` all silent.
- Sprint H.2 acceptance verification block (below) all pass.

**Files:**
- Create: `.harness/README.md`
- Create: `docs/api.md` (three sections)
- Modify: `CONTRIBUTING.md`
- Create: `docs/decisions/2026-04-26-harness-landed.md`

### Task 9.1: Write `.harness/README.md`

```markdown
# AI Harness — Contributor's Guide

This directory is the spine of how AI-assisted development works in this repo.

## What lives here

- `*.yaml` — policy files (one per domain: dependencies, performance_budgets,
  security_policy, accessibility_policy, documentation_policy, logging_policy,
  error_handling_policy, conventions_policy, typecheck_policy).
- `*.md` — cross-cutting rule files (loaded by the AI when their `applies_to:`
  glob matches the file the AI is editing).
- `checks/` — Python scripts that enforce rules. Each emits structured findings
  per H-16. Auto-discovered by `tools/run_validate.py`.
- `generators/` — Python scripts that produce machine-readable truth files
  under `generated/`. Auto-derived from source code; never hand-edited.
- `generated/` — JSON truth files. Read by the loader and by checks.
- `schemas/` — JSON schemas for every policy file and every generated file.
- `baselines/` — `mypy_baseline.json` + `tsc_baseline.json` + per-rule
  baselines that grandfather pre-existing violations.

## Daily flow

1. Make a code change.
2. `make validate-fast` (< 30s) — runs lint + every check in `checks/*.py`.
3. If anything fails, the output is structured; let the AI parse the
   `suggestion=` field and self-correct.
4. Commit. The pre-commit hook (installed via `make harness-install`) re-runs
   `validate-fast`.
5. Push. CI runs `make validate-full` (which includes tests).

## Adding a new rule

1. Add a check at `.harness/checks/<rule_id>.py`. Follow the template:
   - H-25 docstring (missing/malformed/upstream-failed answers).
   - Output conforms to H-16 (`[SEVERITY] file=… rule=… message="…" suggestion="…"`).
2. Add paired fixtures: `tests/harness/fixtures/<rule_id>/violation/` (≥ 1 file)
   and `tests/harness/fixtures/<rule_id>/compliant/` (≥ 1 file).
3. Add a test at `tests/harness/checks/test_<rule_id>.py` that uses
   `assert_check_fires` + `assert_check_silent`.
4. If the rule has tunable knobs, add them to `<topic>_policy.yaml` AND
   `schemas/<topic>_policy.schema.json`.
5. If the rule is documentation-only, add it to
   `rule_coverage_exemptions.yaml` with a `reason:`.

## Adding a new generator

1. Add `.harness/generators/<name>.py`. Use `write_generated()` from
   `_common.py` for deterministic output.
2. Add `.harness/schemas/generated/<name>.schema.json`.
3. Add a test at `tests/harness/generators/test_extract_<name>.py`.
4. Run `make harness` to invoke the orchestrator and ensure the generator
   participates.

## Interpreting findings

Every finding has four fields:
- `file=<path>:<line>` — where to look.
- `rule=<id>` — what was violated.
- `message="..."` — what's wrong, in human language.
- `suggestion="..."` — concrete fix for the AI to apply.

If the AI applies the suggestion and the same rule fires again, that's a
signal the rule has a false positive — file an issue rather than fight it.
```

### Task 9.2: Write `docs/api.md`

```markdown
# API guide

This document is curated. The OpenAPI spec at `/openapi.json` (FastAPI
auto-generated) is canonical for endpoint shapes; this file describes
intent, error model, and conventions.

## Authentication

All mutating endpoints require an authenticated user via
`Depends(require_user)` (or one of `require_admin` / `require_tenant_admin`
for elevated scopes). Read endpoints may be public — see
`security_policy.yaml.rate_limit_exempt` for the explicit allowlist.

## Endpoints

Endpoints are organized under `/api/v4/<domain>/...`. Each domain owns its
own tag in OpenAPI. The complete generated list lives at
`.harness/generated/backend_routes.json`.

## Error model

All errors are returned as `application/problem+json` per RFC 7807:

```json
{
  "type": "https://debugduck.example/errors/<code>",
  "title": "Human-readable title",
  "status": 400,
  "detail": "Specifics for this occurrence",
  "instance": "/api/v4/incidents/abc123"
}
```

Expected outcomes (validation failures, lookups, idempotent retries) return
typed `Result[T, E]` server-side and translate `Err(...)` into problem+json
with the appropriate status code. Unexpected failures raise a domain
exception that the global handler also renders as problem+json.
```

### Task 9.3: Extend `CONTRIBUTING.md`

Append a new section:

```markdown
## Working with the AI harness

If you're using Claude Code / Cursor / Copilot in this repo, the AI harness
provides structured rules + truth files that improve suggestion quality and
catch policy violations before they reach review.

- See `.harness/README.md` for the full contributor's guide.
- See `docs/api.md` for the curated API guide.
- Run `make validate-fast` before declaring any task done.
- Run `make harness` after adding a new endpoint, page, or model so the
  generated truth files stay current.
```

### Task 9.4: Write the GA ADR

Create `docs/decisions/2026-04-26-harness-landed.md`:

```markdown
# 2026-04-26 — AI harness GA

## Status
Accepted

## Context
Sprints H.0a → H.2 land the full harness substrate: 25 H-rules, 19 Q-decisions,
22+ checks, 18 generators, deterministic regen + load.

## Decision
The harness becomes the contract for AI-assisted development in this repo:

- Every PR runs `make validate-fast` via pre-commit.
- Every CI run executes `make validate-full`.
- Adding/changing any `.harness/*_policy.yaml`, dependencies.yaml, or
  `.harness/checks/*.py` requires an ADR (enforced by Q15.adr-required-on-change).
- Type-check baseline growth requires an ADR (enforced by Q19.baseline-grew-without-adr).

## Consequences
Positive: AI suggestions get richer context; policy violations caught locally;
contributors have a single source of truth for "how things work here".

Negative: Initial suite of checks may produce noise on legacy code (mitigated
via per-rule baselines under `.harness/baselines/`).

## Follow-up
- Promote tickets in `.harness/baselines/_TICKETS.md` to issues.
- Tighten generated-file schemas as fixture coverage grows.
```

### Task 9.5: Run full self-check

```bash
python .harness/checks/harness_rule_coverage.py
python .harness/checks/harness_fixture_pairing.py
python .harness/checks/harness_policy_schema.py
python .harness/checks/output_format_conformance.py
```

Expected: each exits 0 (or only emits documented exemptions).

### Task 9.6: Run validate-full

```bash
python tools/run_validate.py --full
```

Expected: PASS.

### Task 9.7: Commit

```bash
git add .harness/README.md docs/api.md CONTRIBUTING.md docs/decisions/2026-04-26-harness-landed.md
git commit -m "$(cat <<'EOF'
docs(green): H.2.9 — harness GA — README + api guide + GA ADR

.harness/README.md is the contributor's guide: file layout, daily flow,
how to add a rule, how to add a generator, how to interpret findings.
docs/api.md first cut: authentication, endpoints (pointer to generated
truth + OpenAPI), error model. CONTRIBUTING.md gains AI-harness section.
GA ADR records the contract: PRs run validate-fast pre-commit, CI runs
validate-full, policy/check changes require ADRs, baseline growth
requires ADRs.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## End-of-sprint acceptance verification

Run from the repo root:

```bash
# 1. All H.2 tests pass.
python -m pytest tests/harness/generators/ tests/harness/test_session_start_hook.py tests/harness/test_init_harness.py -v

# 2. Every generator has a paired test.
for g in .harness/generators/extract_*.py; do
  test_file="tests/harness/generators/test_$(basename $g .py).py"
  [ -f "$test_file" ] || echo "MISSING TEST: $test_file"
done
# Expected: no MISSING output.

# 3. Every generator output exists with a paired schema.
for g in .harness/generators/extract_*.py; do
  name=$(basename $g .py | sed 's/^extract_//')
  out=".harness/generated/${name}.json"
  schema=".harness/schemas/generated/${name}.schema.json"
  [ -f "$out" ] || echo "MISSING OUTPUT: $out"
  [ -f "$schema" ] || echo "MISSING SCHEMA: $schema"
done
# Expected: no MISSING output.

# 4. Orchestrator produces deterministic output.
python tools/run_harness_regen.py
git diff --stat .harness/generated/
# Expected: empty diff.

# 5. validate-full passes.
python tools/run_validate.py --full
# Expected: PASS exit 0.

# 6. Schema validation clean for every policy + generated file.
python .harness/checks/harness_policy_schema.py
# Expected: zero ERRORs.

# 7. Self-tests clean.
python .harness/checks/harness_rule_coverage.py
python .harness/checks/harness_fixture_pairing.py
python .harness/checks/output_format_conformance.py
# Expected: each exits 0.

# 8. Bootstrap smoke (into /tmp).
rm -rf /tmp/h2-smoke
python tools/init_harness.py --target /tmp/h2-smoke --owner "@smoke" --tech-stack polyglot
test -f /tmp/h2-smoke/CLAUDE.md
test -f /tmp/h2-smoke/Makefile
test -d /tmp/h2-smoke/.harness
test -d /tmp/h2-smoke/tools
rm -rf /tmp/h2-smoke

# 9. Session-start hook is wired.
python -c "import json; data=json.load(open('.claude/settings.local.json')); assert any('_session_start_hook.sh' in (h.get('command') or '') for entry in data['hooks']['SessionStart'] for h in entry['hooks'])"

# 10. GA ADR present.
test -f docs/decisions/2026-04-26-harness-landed.md
```

---

## Definition of Done — Sprint H.2

- [ ] All 9 stories' tests pass.
- [ ] All 18 generators produce deterministic JSON under `.harness/generated/` validated by paired schemas.
- [ ] `tools/run_harness_regen.py` orchestrates them with topological ordering and parallel execution.
- [ ] `make harness` runs the orchestrator end-to-end in < 60s.
- [ ] Generated files re-run produces byte-identical output (`git diff --stat .harness/generated/` empty).
- [ ] Claude Code session-start hook wired via `.claude/settings.local.json` + wrapper script.
- [ ] `tools/init_harness.py` bootstraps a target repo with CLAUDE.md / Makefile / AGENTS.md / .cursorrules / harness skeleton; idempotent.
- [ ] `.harness/README.md`, `docs/api.md`, GA ADR all committed.
- [ ] All four harness self-tests (rule_coverage, fixture_pairing, policy_schema, output_format_conformance) silent on the live repo.
- [ ] `validate-full` passes end-to-end.

---

## Sprint roadmap — done

With Sprint H.2 complete, all seven sprints from the consolidated harness plan have shipped:

| Sprint | Status |
|---|---|
| H.0a — Schema & substrate | per-task plan committed |
| H.0b — Stack-foundation scaffolding | per-task plan committed |
| H.1a — Backend basic checks | per-task plan committed |
| H.1b — Frontend checks | per-task plan committed |
| H.1c — Security/Docs/Logging/Errors | per-task plan committed |
| H.1d — Typecheck + harness self-tests | per-task plan committed |
| H.2 — Generators + AI integration | this plan |

The consolidated harness plan at `docs/plans/2026-04-26-ai-harness.md` is the
authoritative reference. Per the brainstorming-skill terminal flow, the next
step is execution — open a parallel session in a worktree and use
`superpowers:executing-plans` to walk these per-task plans batch-by-batch.

---

**Plan complete and saved to `docs/plans/2026-04-26-harness-sprint-h2-tasks.md`.**

Two execution options:

1. **Subagent-Driven (this session)** — I dispatch fresh subagent per task, review between tasks, fast iteration.
2. **Parallel Session (separate)** — Open new session with `executing-plans`, batch execution with checkpoints.

Or **hold** — all seven harness sprint plans are now committed. Total scope:
~36 stories, ~206 story points, ~13 weeks at 80% capacity.
