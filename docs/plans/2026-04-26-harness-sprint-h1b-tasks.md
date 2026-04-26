# Harness Sprint H.1b — Per-Task Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship the eight frontend-spine checks (`frontend_style_system`, `frontend_data_layer`, `frontend_ui_primitives`, `frontend_testing`, `frontend_routing`, `accessibility_policy`, `conventions_policy`, `output_format_conformance`) so every Q1–Q6, Q14, Q18 frontend rule plus the cross-check that validates other checks' output shape becomes deterministically enforceable through `make validate-fast`.

**Architecture:** Same template as H.1a — each check is a standalone Python script under `.harness/checks/<rule_id>.py` that walks the repo (or a `--target`-supplied path), emits structured findings on stdout per H-16/H-23, and exits non-zero on any `ERROR`. Frontend checks use `tree-sitter`-light parsing strategies: regex + line-aware text scanning, plus parsing of TypeScript/TSX with the `tree-sitter-typescript` Python binding ONLY where AST precision is required (Q4 primitives + Q6 routing). The remaining checks rely on regex + ESLint config introspection, because the actual ESLint pass already runs inside `make validate-fast` (added in H.0a Story 4) — our checks only enforce *meta-rules* the linter cannot.

**Tech Stack:** Python 3.14, regex (stdlib `re`), pathlib (stdlib), json (stdlib), PyYAML (already a dep), `tree-sitter` + `tree-sitter-typescript` (new dev-deps installed in Task 0.1 below), pytest (already configured in H.0a/H.0b).

**Reference docs:**
- [Consolidated harness plan](./2026-04-26-ai-harness.md) — locked decisions Q1–Q6, Q14, Q18, plus H-16/H-23/H-24/H-25.
- [Sprint H.0a per-task plan](./2026-04-26-harness-sprint-h0a-tasks.md) — substrate (`Makefile`, loader, `run_validate.py` orchestrator, `_helpers.py`).
- [Sprint H.0b per-task plan](./2026-04-26-harness-sprint-h0b-tasks.md) — frontend config files (`vitest.config.ts`, `playwright.config.ts`, `eslint.config.js` with jsx-a11y + import rules, commitlint, vite alias).
- [Sprint H.1a per-task plan](./2026-04-26-harness-sprint-h1a-tasks.md) — reference for the canonical check template (TDD red→green, paired fixtures, H-25 docstring, live-repo triage flow).

**Prerequisites:** Sprints H.0a, H.0b, H.1a complete and committed.

---

## Story map for Sprint H.1b

| Story | Title | Tasks | Pts |
|---|---|---|---|
| H.1b.0 | Install frontend-parsing dev deps + verify imports | 0.1 – 0.3 | — (precondition) |
| H.1b.1 | `frontend_style_system.py` (Q1) — Tailwind only + cn() merging | 1.1 – 1.10 | 5 |
| H.1b.2 | `frontend_data_layer.py` (Q2 + Q3) — TanStack Query / typed apiClient | 2.1 – 2.10 | 5 |
| H.1b.3 | `frontend_ui_primitives.py` (Q4) — shadcn locality + no raw HTML primitives | 3.1 – 3.10 | 5 |
| H.1b.4 | `frontend_testing.py` (Q5) — Vitest discipline + colocation + Playwright scope | 4.1 – 4.10 | 5 |
| H.1b.5 | `frontend_routing.py` (Q6) — single router.tsx + lazy + no `<a>` for internal nav | 5.1 – 5.8 | 3 |
| H.1b.6 | `accessibility_policy.py` (Q14) — axe-core wiring + jsx-a11y plugin presence | 6.1 – 6.10 | 5 |
| H.1b.7 | `conventions_policy.py` (Q18) — ruff/eslint/commitlint output wrapper | 7.1 – 7.10 | 5 |
| H.1b.8 | `output_format_conformance.py` (H-16/H-23) — checks-of-checks | 8.1 – 8.6 | 2 |

**Total: 8 stories, ~35 points, 2 weeks** (capacity 26 ± buffer; tight as in H.1a, mitigated by shared template + the 2-pt cross-check).

---

## Story-template recap

Identical to Sprint H.1a §"Story-template recap":

- **AC-1:** Check exists at `.harness/checks/<rule_id>.py`.
- **AC-2:** Output conforms to H-16 + H-23.
- **AC-3:** Violation fixture causes the check to emit ≥ 1 `[ERROR]` line and exit non-zero.
- **AC-4:** Compliant fixture is silent.
- **AC-5:** Wired into `make validate-fast`.
- **AC-6:** Completes on the full repo in < 2s.
- **AC-7:** H-25 docstring present.

Common task pattern per story: fixtures → red test → red commit → implement check → green test → live-repo triage (fix or baseline) → validate-fast → green commit.

---

# Story H.1b.0 — Install frontend-parsing dev deps (precondition)

> Not a separately story-pointed item; it is a 5-minute prerequisite that **must complete before Story H.1b.3 (`frontend_ui_primitives`) and Story H.1b.5 (`frontend_routing`)**. The other six stories use regex-only scanning and do not need it.

**Files:**
- Modify: `backend/pyproject.toml` (or root `requirements-dev.txt`, depending on H.0b layout)
- Modify: `.harness/dependencies.yaml` (add to python.allowed)

### Task 0.1: Add tree-sitter-typescript to the dev-dependency set

If H.0b Story 3 placed harness Python tooling under `backend/pyproject.toml [project.optional-dependencies] dev`, append:

```toml
tree-sitter = ">=0.22"
tree-sitter-typescript = ">=0.21"
```

If the harness Python tooling lives elsewhere (e.g., a dedicated `.harness/requirements.txt`), append to that file instead. Confirm by running:

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
grep -l "pytest" backend/pyproject.toml .harness/*.txt 2>/dev/null
```

### Task 0.2: Install + verify

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
pip install tree-sitter tree-sitter-typescript
python -c "from tree_sitter import Language, Parser; import tree_sitter_typescript; print('ok')"
```

Expected: `ok`.

### Task 0.3: Update the dependency allow-list + commit

Add `tree-sitter` and `tree-sitter-typescript` to `.harness/dependencies.yaml.python.allowed` (NOT `allowed_on_spine` — these are tooling, not application code).

```bash
git add backend/pyproject.toml .harness/dependencies.yaml
git commit -m "$(cat <<'EOF'
chore(harness): add tree-sitter + tree-sitter-typescript to dev deps

Required by H.1b.3 (frontend_ui_primitives) and H.1b.5 (frontend_routing)
where regex-based scanning is insufficient for JSX expressions and
React Router route-table inspection. Tooling-only — added to python.allowed
but NOT python.allowed_on_spine.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Story H.1b.1 — `frontend_style_system.py` (Q1)

**Rule families enforced (4):**
1. No `import "*.css"` or `import "*.scss"` outside `frontend/src/index.css` (the single global stylesheet permitted).
2. No `styled-components`, `@emotion/styled`, `@stitches/react`, `@vanilla-extract/css`, or `@linaria/core` import in `frontend/src/**`.
3. No inline `style={{ … }}` JSX prop on elements with > 2 properties OR with non-dynamic literal values that should live in Tailwind classes (heuristic: `style={{ width:` etc. are the documented escape hatch and are allowed; `style={{ color: "red" }}` is not).
4. Multi-class JSX `className` strings concatenated with `+` or template literals MUST go through `cn(...)` from `frontend/src/lib/utils.ts`.

**Files:**
- Create: `.harness/checks/frontend_style_system.py`
- Create: `tests/harness/fixtures/frontend_style_system/violation/imports_styled_components.tsx`
- Create: `tests/harness/fixtures/frontend_style_system/violation/imports_extra_css.tsx`
- Create: `tests/harness/fixtures/frontend_style_system/violation/inline_style_color.tsx`
- Create: `tests/harness/fixtures/frontend_style_system/violation/raw_classname_concat.tsx`
- Create: `tests/harness/fixtures/frontend_style_system/compliant/uses_cn.tsx`
- Create: `tests/harness/fixtures/frontend_style_system/compliant/dynamic_style_escape.tsx`
- Create: `tests/harness/checks/test_frontend_style_system.py`

### Task 1.1: Create violation fixtures

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
mkdir -p tests/harness/fixtures/frontend_style_system/{violation,compliant}
```

`violation/imports_styled_components.tsx`:

```tsx
/* Q1 violation — styled-components banned. */
import styled from "styled-components";

const Card = styled.div`color: red;`;

export const Foo = () => <Card>x</Card>;
```

`violation/imports_extra_css.tsx`:

```tsx
/* Q1 violation — additional CSS files banned (only frontend/src/index.css allowed). */
import "./Foo.module.css";

export const Foo = () => <div>x</div>;
```

`violation/inline_style_color.tsx`:

```tsx
/* Q1 violation — inline style for static color (use Tailwind class). */
export const Foo = () => <div style={{ color: "red", padding: "8px" }}>x</div>;
```

`violation/raw_classname_concat.tsx`:

```tsx
/* Q1 violation — classNames merged via + or template literal, not cn(). */
export const Foo = ({ active }: { active: boolean }) => (
  <div className={"px-4 py-2 " + (active ? "bg-amber-500" : "bg-slate-700")}>x</div>
);
```

### Task 1.2: Create compliant fixtures

`compliant/uses_cn.tsx`:

```tsx
/* Q1 compliant — multi-class merging via cn(). */
import { cn } from "@/lib/utils";

export const Foo = ({ active }: { active: boolean }) => (
  <div className={cn("px-4 py-2", active ? "bg-amber-500" : "bg-slate-700")}>x</div>
);
```

`compliant/dynamic_style_escape.tsx`:

```tsx
/* Q1 compliant — inline style permitted only for dynamic geometry props. */
export const Bar = ({ widthPx }: { widthPx: number }) => (
  <div style={{ width: widthPx }} className="h-2 bg-amber-500" />
);
```

### Task 1.3: Write the failing test

Create `tests/harness/checks/test_frontend_style_system.py`:

```python
"""H.1b.1 — frontend_style_system check tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness._helpers import assert_check_fires, assert_check_silent

CHECK = "frontend_style_system"
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / CHECK


@pytest.mark.parametrize(
    "fixture_name,expected_rule,pretend_path",
    [
        ("imports_styled_components.tsx", "Q1.no-css-in-js", "frontend/src/components/Foo.tsx"),
        ("imports_extra_css.tsx", "Q1.no-extra-css-imports", "frontend/src/components/Foo.tsx"),
        ("inline_style_color.tsx", "Q1.no-inline-style-static", "frontend/src/components/Foo.tsx"),
        ("raw_classname_concat.tsx", "Q1.classname-needs-cn", "frontend/src/components/Foo.tsx"),
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
        ("uses_cn.tsx", "frontend/src/components/Foo.tsx"),
        ("dynamic_style_escape.tsx", "frontend/src/components/Bar.tsx"),
    ],
)
def test_compliant_silent(fixture_name: str, pretend_path: str) -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / fixture_name,
        pretend_path=pretend_path,
    )
```

### Task 1.4: Run failing test + commit red

```bash
python -m pytest tests/harness/checks/test_frontend_style_system.py -v
git add tests/harness/fixtures/frontend_style_system tests/harness/checks/test_frontend_style_system.py
git commit -m "$(cat <<'EOF'
test(red): H.1b.1 — frontend_style_system fixtures + assertions

Four violation fixtures (styled-components import, extra .css import,
inline style with static color, className concat with + and template
literal) plus two compliant counterparts (cn() merging, dynamic
geometry style escape).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 1.5: Implement the check

Create `.harness/checks/frontend_style_system.py`:

```python
#!/usr/bin/env python3
"""Q1 — Tailwind-only style system + cn() class merging.

Four rules:
  Q1.no-css-in-js              — bans styled-components/emotion/stitches/vanilla-extract/linaria.
  Q1.no-extra-css-imports      — only frontend/src/index.css may be imported.
  Q1.no-inline-style-static    — `style={{ color: "..." }}` (static value) banned;
                                  use a Tailwind class. Geometry escape hatch
                                  (width/height/transform/transformOrigin/top/left/
                                  right/bottom) IS allowed when the value is dynamic.
  Q1.classname-needs-cn        — multi-class concat via `+` or template-literal
                                  conditional inside `className={...}` requires cn().

Scope: frontend/src/**/*.{ts,tsx,js,jsx}. Excludes frontend/e2e/ and
frontend/src/test-utils/. The Vite-built CSS bundle lives outside src;
also excluded.

H-25:
  Missing input    — exit 2; emit ERROR rule=harness.target-missing.
  Malformed input  — WARN rule=harness.unparseable; skip the file
                     (TypeScript syntax errors are tsc's job, not ours).
  Upstream failed  — none; pure filesystem.
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

DEFAULT_ROOTS = (REPO_ROOT / "frontend" / "src",)
EXCLUDE_VIRTUAL_PREFIXES = (
    "frontend/e2e/",
    "frontend/src/test-utils/",
    "tests/harness/fixtures/",
    "frontend/dist/",
)
SCANNED_EXTS = {".ts", ".tsx", ".js", ".jsx"}

CSS_IN_JS_MODULES = {
    "styled-components",
    "@emotion/styled",
    "@emotion/react",
    "@stitches/react",
    "@vanilla-extract/css",
    "@linaria/core",
    "@linaria/react",
}

GEOMETRY_PROPS = {
    "width", "height", "minWidth", "minHeight", "maxWidth", "maxHeight",
    "top", "left", "right", "bottom",
    "transform", "transformOrigin", "translate", "rotate", "scale",
    "gridTemplateColumns", "gridTemplateRows",
}

# `import "...something.css"` or `import "....scss"`
CSS_IMPORT_RE = re.compile(r'''^\s*import\s+["']([^"']+\.(?:css|scss|sass|less|styl))["']''', re.MULTILINE)
# `import styled from "styled-components";` etc. (capture module string)
IMPORT_FROM_RE = re.compile(r'''^\s*import\s+[^;]*?\bfrom\s+["']([^"']+)["']''', re.MULTILINE)
# inline style props: `style={{ ... }}`
STYLE_PROP_RE = re.compile(r'style\s*=\s*\{\{([^}]*)\}\}', re.DOTALL)
# className props that contain a `+` operator or a `${...}` template literal
CLASSNAME_PROP_RE = re.compile(r'className\s*=\s*\{([^}]*)\}', re.DOTALL)

PRETEND_INDEX_CSS = "frontend/src/index.css"


def _is_excluded(virtual: str) -> bool:
    return any(virtual.startswith(p) for p in EXCLUDE_VIRTUAL_PREFIXES)


def _scan_css_imports(path: Path, virtual: str, source: str) -> Iterable[Finding]:
    for m in CSS_IMPORT_RE.finditer(source):
        spec = m.group(1)
        # the only css import permitted is the global stylesheet
        is_index = spec.endswith("index.css")
        if not is_index:
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=source[:m.start()].count("\n") + 1,
                rule="Q1.no-extra-css-imports",
                message=f"CSS import `{spec}` outside frontend/src/index.css",
                suggestion="move styles into Tailwind classes or extend index.css",
            )


def _scan_css_in_js(path: Path, virtual: str, source: str) -> Iterable[Finding]:
    for m in IMPORT_FROM_RE.finditer(source):
        module = m.group(1)
        if module in CSS_IN_JS_MODULES:
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=source[:m.start()].count("\n") + 1,
                rule="Q1.no-css-in-js",
                message=f"CSS-in-JS library `{module}` banned (Q1: Tailwind only)",
                suggestion="rewrite styles as Tailwind utility classes",
            )


def _scan_inline_styles(path: Path, virtual: str, source: str) -> Iterable[Finding]:
    for m in STYLE_PROP_RE.finditer(source):
        body = m.group(1)
        # split into key:value pairs (very loose; good-enough for harness gate)
        # ignore commas inside parens (no closure here is fine for ≤ 1-level objects)
        pairs = [p.strip() for p in body.split(",") if ":" in p]
        if not pairs:
            continue
        offending: list[str] = []
        for pair in pairs:
            key_raw, _sep, value_raw = pair.partition(":")
            key = key_raw.strip().strip('"').strip("'")
            value = value_raw.strip().rstrip(",").strip()
            if not key:
                continue
            if key in GEOMETRY_PROPS:
                # geometry escape allowed for dynamic values; static literals still ok here
                continue
            # Heuristic: "static" values are quoted strings or numeric literals.
            # Variables, function calls, ternaries, template-strings -> dynamic and ignored.
            if (
                value.startswith('"') and value.endswith('"')
                or value.startswith("'") and value.endswith("'")
                or re.match(r"^-?[0-9]", value)
            ):
                offending.append(key)
        if offending:
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=source[:m.start()].count("\n") + 1,
                rule="Q1.no-inline-style-static",
                message=f"inline style with static keys {offending}",
                suggestion="move static styling to Tailwind utility classes",
            )


def _scan_classname_concat(path: Path, virtual: str, source: str) -> Iterable[Finding]:
    for m in CLASSNAME_PROP_RE.finditer(source):
        body = m.group(1).strip()
        # if it already starts with cn(, skip
        if body.startswith("cn(") or body.startswith("clsx(") or body.startswith("twMerge("):
            continue
        # static string-literal classNames or simple identifiers are fine
        if "+" in body or "${" in body:
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=source[:m.start()].count("\n") + 1,
                rule="Q1.classname-needs-cn",
                message="className concatenated via `+` or template literal",
                suggestion="use cn(...) from @/lib/utils to merge classes",
            )


def _scan_file(path: Path, virtual: str) -> Iterable[Finding]:
    if _is_excluded(virtual):
        return
    if path.suffix not in SCANNED_EXTS:
        return
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    yield from _scan_css_imports(path, virtual, source)
    yield from _scan_css_in_js(path, virtual, source)
    yield from _scan_inline_styles(path, virtual, source)
    yield from _scan_classname_concat(path, virtual, source)


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
        if root.is_file() and root.suffix in SCANNED_EXTS:
            virtual = pretend_path or (str(root.relative_to(REPO_ROOT)) if root.is_relative_to(REPO_ROOT) else root.name)
            files = [(root, virtual)]
        else:
            files = []
            for p in root.rglob("*"):
                if p.is_file() and p.suffix in SCANNED_EXTS:
                    virtual = str(p.relative_to(REPO_ROOT)) if p.is_relative_to(REPO_ROOT) else p.name
                    files.append((p, virtual))
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

### Task 1.6: Run tests, expect green

```bash
python -m pytest tests/harness/checks/test_frontend_style_system.py -v
```

Expected: all 6 cases pass.

### Task 1.7: Triage live-repo run

```bash
python .harness/checks/frontend_style_system.py
```

Triage outcomes (same as H.1a flow):

- Clean exit 0 → ideal.
- Some `Q1.classname-needs-cn` ERRORs → likely real; rewrite the offending JSX with `cn()`.
- Some `Q1.no-inline-style-static` ERRORs in War Room components (already audited Feb 2026 — see project memory) → if a static color genuinely belongs there (e.g., SVG fill computed by a dynamic prop), refactor to derive class via `cn()` + a `cva` variant. Otherwise add to baseline (deferred to H.1d.1).
- Any `Q1.no-css-in-js` or `Q1.no-extra-css-imports` ERRORs → these are surprising; investigate and either remove or escalate.

### Task 1.8: Run validate-fast

```bash
python tools/run_validate.py --fast
```

Expected: orchestrator picks up the new check; total wall time still < 30s.

### Task 1.9: Commit green

```bash
git add .harness/checks/frontend_style_system.py
git commit -m "$(cat <<'EOF'
feat(green): H.1b.1 — frontend_style_system enforces Q1

Regex-based check enforcing four Q1 sub-rules: ban CSS-in-JS libs,
restrict CSS imports to frontend/src/index.css, ban static-value inline
styles (geometry escape preserved for dynamic values), require cn() for
className merging via + or template literals. H-25 docstring covers
missing/malformed/no-upstream. Auto-discovered.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 1.10: Verify discovery

```bash
python tools/run_validate.py --fast 2>&1 | grep "check:frontend_style_system"
```

Expected: orchestrator label printed.

---

# Story H.1b.2 — `frontend_data_layer.py` (Q2 + Q3)

**Rule families enforced (9):**
1. No import of `redux`, `@reduxjs/toolkit`, `mobx`, `mobx-react-lite`, `recoil`, `jotai` anywhere.
2. `import` of `zustand` (or any submodule) outside `frontend/src/stores/` → ERROR; inside `frontend/src/stores/` requires a `// JUSTIFICATION:` comment in the same file.
3. `import` of `axios` → ERROR (use the `apiClient` wrapper).
4. `fetch(` call inside `frontend/src/components/`, `frontend/src/pages/`, or `frontend/src/hooks/` → ERROR (must go through `apiClient`).
5. Files under `frontend/src/components/`, `frontend/src/pages/` MUST NOT import directly from `frontend/src/services/api/` (other than the `client.ts` re-export); they must consume via TanStack Query hooks under `frontend/src/hooks/`.
6. `useState` initialized with the result of `fetch(`/`apiClient(`/`api.something(` (i.e., side-effect inside initializer) → ERROR.
7. `useQuery({ queryFn: () => fetch( … )})` → ERROR; queryFn must call `apiClient` (so types + retry policy from Q17 are honored).
8. `useEffect` containing `fetch(` or `apiClient(` without a paired `queryFn` migration comment → WARN (not ERROR; many legitimate side-effect cases).
9. `frontend/src/services/api/client.ts` MUST exist (presence check) and export `apiClient`.

**Files:**
- Create: `.harness/checks/frontend_data_layer.py`
- Create: `tests/harness/fixtures/frontend_data_layer/violation/imports_redux.tsx`
- Create: `tests/harness/fixtures/frontend_data_layer/violation/imports_zustand_outside_stores.tsx`
- Create: `tests/harness/fixtures/frontend_data_layer/violation/imports_axios.tsx`
- Create: `tests/harness/fixtures/frontend_data_layer/violation/raw_fetch_in_component.tsx`
- Create: `tests/harness/fixtures/frontend_data_layer/violation/component_imports_services_api.tsx`
- Create: `tests/harness/fixtures/frontend_data_layer/violation/usequery_with_raw_fetch.tsx`
- Create: `tests/harness/fixtures/frontend_data_layer/compliant/uses_query_hook.tsx`
- Create: `tests/harness/fixtures/frontend_data_layer/compliant/justified_zustand.tsx`
- Create: `tests/harness/checks/test_frontend_data_layer.py`

### Task 2.1: Create violation fixtures

```bash
mkdir -p tests/harness/fixtures/frontend_data_layer/{violation,compliant}
```

`violation/imports_redux.tsx`:

```tsx
/* Q2 violation — redux banned. */
import { configureStore } from "@reduxjs/toolkit";

export const store = configureStore({ reducer: {} });
```

`violation/imports_zustand_outside_stores.tsx`:

```tsx
/* Q2 violation — zustand outside frontend/src/stores/. */
import { create } from "zustand";

export const useFoo = create(() => ({ x: 1 }));
```

`violation/imports_axios.tsx`:

```tsx
/* Q3 violation — axios banned. */
import axios from "axios";

export const get = (u: string) => axios.get(u);
```

`violation/raw_fetch_in_component.tsx`:

```tsx
/* Q3 violation — raw fetch() inside a component. */
import { useEffect, useState } from "react";

export const Foo = () => {
  const [data, setData] = useState<unknown>(null);
  useEffect(() => {
    fetch("/api/foo").then((r) => r.json()).then(setData);
  }, []);
  return <div>{JSON.stringify(data)}</div>;
};
```

`violation/component_imports_services_api.tsx`:

```tsx
/* Q3 violation — component imports services/api directly. */
import { fetchIncident } from "@/services/api/incidents";

export const Foo = () => {
  fetchIncident("x");
  return <div />;
};
```

`violation/usequery_with_raw_fetch.tsx`:

```tsx
/* Q3 violation — useQuery queryFn calls raw fetch(). */
import { useQuery } from "@tanstack/react-query";

export const Foo = () =>
  useQuery({ queryKey: ["x"], queryFn: () => fetch("/api/x").then((r) => r.json()) });
```

### Task 2.2: Create compliant fixtures

`compliant/uses_query_hook.tsx`:

```tsx
/* Q2/Q3 compliant — hook wraps apiClient, component consumes hook. */
import { useIncident } from "@/hooks/useIncident";

export const Foo = ({ id }: { id: string }) => {
  const { data } = useIncident(id);
  return <div>{data?.summary ?? "loading"}</div>;
};
```

`compliant/justified_zustand.tsx`:

```tsx
/* Q2 compliant — zustand inside frontend/src/stores/ with justification. */
// JUSTIFICATION: cross-route UI state for War Room layout density.
import { create } from "zustand";

export const useLayoutStore = create<{ density: "compact" | "comfortable" }>(() => ({
  density: "comfortable",
}));
```

### Task 2.3: Write the failing test

Create `tests/harness/checks/test_frontend_data_layer.py`:

```python
"""H.1b.2 — frontend_data_layer check tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness._helpers import assert_check_fires, assert_check_silent

CHECK = "frontend_data_layer"
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / CHECK


@pytest.mark.parametrize(
    "fixture_name,expected_rule,pretend_path",
    [
        ("imports_redux.tsx", "Q2.no-redux", "frontend/src/store.ts"),
        ("imports_zustand_outside_stores.tsx", "Q2.zustand-quarantine", "frontend/src/components/Foo.tsx"),
        ("imports_axios.tsx", "Q3.no-axios", "frontend/src/services/http.ts"),
        ("raw_fetch_in_component.tsx", "Q3.no-raw-fetch-in-ui", "frontend/src/components/Foo.tsx"),
        ("component_imports_services_api.tsx", "Q3.component-no-direct-services-api", "frontend/src/components/Foo.tsx"),
        ("usequery_with_raw_fetch.tsx", "Q3.queryfn-must-use-apiclient", "frontend/src/hooks/useFoo.ts"),
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
        ("uses_query_hook.tsx", "frontend/src/components/Foo.tsx"),
        ("justified_zustand.tsx", "frontend/src/stores/useLayoutStore.ts"),
    ],
)
def test_compliant_silent(fixture_name: str, pretend_path: str) -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / fixture_name,
        pretend_path=pretend_path,
    )
```

### Task 2.4: Run failing test + commit red

```bash
python -m pytest tests/harness/checks/test_frontend_data_layer.py -v
git add tests/harness/fixtures/frontend_data_layer tests/harness/checks/test_frontend_data_layer.py
git commit -m "$(cat <<'EOF'
test(red): H.1b.2 — frontend_data_layer fixtures + assertions

Six violation fixtures (redux import, zustand outside stores/, axios
import, raw fetch in component, component imports services/api directly,
useQuery queryFn with raw fetch) plus two compliant counterparts (hook
consumer, justified zustand store).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 2.5: Implement the check

Create `.harness/checks/frontend_data_layer.py`:

```python
#!/usr/bin/env python3
"""Q2 + Q3 — frontend data layer (state management + API access).

Nine rules:
  Q2.no-redux                          — redux/@reduxjs/toolkit/mobx/recoil/jotai banned.
  Q2.zustand-quarantine                — zustand outside frontend/src/stores/.
  Q2.zustand-needs-justification       — zustand inside stores/ without `// JUSTIFICATION:` comment.
  Q3.no-axios                          — axios banned.
  Q3.no-raw-fetch-in-ui                — `fetch(` inside components/, pages/, hooks/.
  Q3.component-no-direct-services-api  — components/pages may not import from @/services/api/*
                                         (excluding `@/services/api/client`).
  Q3.queryfn-must-use-apiclient        — useQuery({ queryFn: () => fetch(...) }) banned.
  Q3.useeffect-fetch-warn              — useEffect-with-fetch raises WARN (not ERROR).
  Q3.api-client-presence               — frontend/src/services/api/client.ts must exist
                                         and export `apiClient` (checked when scanning the
                                         frontend/src/ root, not individual files).

H-25:
  Missing input    — exit 2; emit ERROR rule=harness.target-missing.
  Malformed input  — WARN rule=harness.unparseable; skip.
  Upstream failed  — none.
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

DEFAULT_ROOTS = (REPO_ROOT / "frontend" / "src",)
SCANNED_EXTS = {".ts", ".tsx", ".js", ".jsx"}
EXCLUDE_VIRTUAL_PREFIXES = (
    "frontend/e2e/",
    "frontend/src/test-utils/",
    "tests/harness/fixtures/",
)

BANNED_STATE_LIBS = {
    "redux", "@reduxjs/toolkit", "mobx", "mobx-react-lite", "recoil", "jotai",
}

IMPORT_FROM_RE = re.compile(r'''^\s*import\s+[^;]*?\bfrom\s+["']([^"']+)["']''', re.MULTILINE)
USE_QUERY_RE = re.compile(r'useQuery\s*\(\s*\{[^}]*queryFn\s*:\s*\(?\)?\s*=>\s*([^,}]+)', re.DOTALL)
FETCH_CALL_RE = re.compile(r'\bfetch\s*\(')
USE_EFFECT_RE = re.compile(r'useEffect\s*\(\s*\(\s*\)\s*=>\s*\{([^}]+)\}', re.DOTALL)


def _is_excluded(virtual: str) -> bool:
    return any(virtual.startswith(p) for p in EXCLUDE_VIRTUAL_PREFIXES)


def _is_component_or_page(virtual: str) -> bool:
    return (
        virtual.startswith("frontend/src/components/")
        or virtual.startswith("frontend/src/pages/")
    )


def _is_hook_file(virtual: str) -> bool:
    return virtual.startswith("frontend/src/hooks/")


def _is_store_file(virtual: str) -> bool:
    return virtual.startswith("frontend/src/stores/")


def _scan_imports(path: Path, virtual: str, source: str) -> Iterable[Finding]:
    seen_zustand_in_stores = False
    for m in IMPORT_FROM_RE.finditer(source):
        module = m.group(1)
        line = source[:m.start()].count("\n") + 1
        if module in BANNED_STATE_LIBS or any(module.startswith(b + "/") for b in BANNED_STATE_LIBS):
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=line,
                rule="Q2.no-redux",
                message=f"banned state-management library `{module}`",
                suggestion="use TanStack Query for server state, useState/Context for UI state",
            )
        if module == "zustand" or module.startswith("zustand/"):
            if _is_store_file(virtual):
                seen_zustand_in_stores = True
            else:
                yield Finding(
                    severity=Severity.ERROR,
                    file=path,
                    line=line,
                    rule="Q2.zustand-quarantine",
                    message="zustand imported outside frontend/src/stores/",
                    suggestion="move state into a slice under frontend/src/stores/ with a JUSTIFICATION comment",
                )
        if module == "axios":
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=line,
                rule="Q3.no-axios",
                message="`axios` banned; use apiClient<T>() wrapper",
                suggestion="rewrite via @/services/api/client",
            )
        if (
            _is_component_or_page(virtual)
            and module.startswith("@/services/api/")
            and not module.endswith("/client")
            and module != "@/services/api/client"
        ):
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=line,
                rule="Q3.component-no-direct-services-api",
                message=f"component imports `{module}` directly",
                suggestion="consume via a TanStack Query hook under @/hooks/",
            )
    if seen_zustand_in_stores and "JUSTIFICATION:" not in source:
        yield Finding(
            severity=Severity.ERROR,
            file=path,
            line=1,
            rule="Q2.zustand-needs-justification",
            message="zustand store missing `// JUSTIFICATION:` comment",
            suggestion="add a single-line comment explaining why this UI state warrants Zustand",
        )


def _scan_fetch_in_ui(path: Path, virtual: str, source: str) -> Iterable[Finding]:
    if not (_is_component_or_page(virtual) or _is_hook_file(virtual)):
        return
    for m in FETCH_CALL_RE.finditer(source):
        line = source[:m.start()].count("\n") + 1
        yield Finding(
            severity=Severity.ERROR,
            file=path,
            line=line,
            rule="Q3.no-raw-fetch-in-ui",
            message="raw `fetch(` inside UI/hook code",
            suggestion="route the call through apiClient<T>() and a TanStack Query hook",
        )


def _scan_useeffect_fetch(path: Path, virtual: str, source: str) -> Iterable[Finding]:
    for m in USE_EFFECT_RE.finditer(source):
        body = m.group(1)
        if FETCH_CALL_RE.search(body) or "apiClient(" in body:
            line = source[:m.start()].count("\n") + 1
            yield Finding(
                severity=Severity.WARN,
                file=path,
                line=line,
                rule="Q3.useeffect-fetch-warn",
                message="useEffect with fetch/apiClient (likely should be useQuery)",
                suggestion="migrate to a TanStack Query hook unless side-effect-only",
            )


def _scan_usequery_queryfn(path: Path, virtual: str, source: str) -> Iterable[Finding]:
    for m in USE_QUERY_RE.finditer(source):
        callee = m.group(1).strip()
        if "fetch(" in callee:
            line = source[:m.start()].count("\n") + 1
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=line,
                rule="Q3.queryfn-must-use-apiclient",
                message="useQuery queryFn calls raw fetch()",
                suggestion="call apiClient<T>() so retry/timeout/typing apply",
            )


def _scan_file(path: Path, virtual: str) -> Iterable[Finding]:
    if _is_excluded(virtual):
        return
    if path.suffix not in SCANNED_EXTS:
        return
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    yield from _scan_imports(path, virtual, source)
    yield from _scan_fetch_in_ui(path, virtual, source)
    yield from _scan_useeffect_fetch(path, virtual, source)
    yield from _scan_usequery_queryfn(path, virtual, source)


def _scan_root_invariants(root: Path) -> Iterable[Finding]:
    """Q3.api-client-presence: when scanning the whole frontend/src tree,
    enforce that the apiClient wrapper exists. Skipped when --target is a single file."""
    client = root / "services" / "api" / "client.ts"
    if not client.exists():
        client = root / "services" / "api" / "client.tsx"
    if not client.exists():
        yield Finding(
            severity=Severity.ERROR,
            file=root,
            line=0,
            rule="Q3.api-client-presence",
            message="frontend/src/services/api/client.ts missing",
            suggestion="add the apiClient<T>() wrapper (see Q3 in the harness plan)",
        )
        return
    text = client.read_text(encoding="utf-8")
    if "apiClient" not in text:
        yield Finding(
            severity=Severity.ERROR,
            file=client,
            line=1,
            rule="Q3.api-client-presence",
            message="services/api/client.ts does not export `apiClient`",
            suggestion="export `apiClient<T>(...)` from services/api/client.ts",
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
        if root.is_file() and root.suffix in SCANNED_EXTS:
            virtual = pretend_path or (str(root.relative_to(REPO_ROOT)) if root.is_relative_to(REPO_ROOT) else root.name)
            files = [(root, virtual)]
        else:
            files = []
            for p in root.rglob("*"):
                if p.is_file() and p.suffix in SCANNED_EXTS:
                    virtual = str(p.relative_to(REPO_ROOT)) if p.is_relative_to(REPO_ROOT) else p.name
                    files.append((p, virtual))
            for finding in _scan_root_invariants(root):
                emit(finding)
                if finding.severity == Severity.ERROR:
                    total_errors += 1
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

### Task 2.6: Run tests, expect green

```bash
python -m pytest tests/harness/checks/test_frontend_data_layer.py -v
```

### Task 2.7: Triage live-repo run

```bash
python .harness/checks/frontend_data_layer.py
```

Expected hot spots in the existing repo:

- `Q3.component-no-direct-services-api` may fire on War Room components if they currently call services directly. Refactor 3 worst offenders into hooks; baseline the rest.
- `Q3.useeffect-fetch-warn` is non-blocking; just count and file a tracking ticket.
- `Q3.api-client-presence` MUST pass — if it fires, the apiClient wrapper from H.0b is missing or misnamed; fix immediately.

### Task 2.8: Run validate-fast + commit green

```bash
python tools/run_validate.py --fast
git add .harness/checks/frontend_data_layer.py
git commit -m "$(cat <<'EOF'
feat(green): H.1b.2 — frontend_data_layer enforces Q2 + Q3

Nine rules: ban redux/mobx/recoil/jotai; quarantine zustand to stores/
with justification; ban axios; ban raw fetch() in components/pages/hooks;
component/page may not import services/api/* directly (use hooks);
useQuery queryFn must call apiClient; useEffect-with-fetch warned;
apiClient wrapper presence checked at root scan. H-25 docstring covers
missing/malformed/no-upstream. Auto-discovered.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 2.9: (Optional) refactor 3 worst component→service callsites

Pick three components flagged by `Q3.component-no-direct-services-api`. Wrap each service call in a TanStack Query hook under `frontend/src/hooks/use<Domain>.ts` with the canonical pattern:

```ts
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/services/api/client";

export const use<Domain> = (id: string) =>
  useQuery({
    queryKey: ["<domain>", id],
    queryFn: () => apiClient<DomainDTO>(`/api/v4/<domain>/${id}`),
  });
```

Commit each as `refactor: H.1b.2 — extract use<Domain> hook`.

### Task 2.10: Re-run validate-fast

Confirm the count of `Q3.component-no-direct-services-api` ERRORs drops by at least three.

---

# Story H.1b.3 — `frontend_ui_primitives.py` (Q4)

**Rule families enforced (5):**
1. `frontend/src/components/ui/` MUST exist (presence check) and contain at least one of: `button.tsx`, `input.tsx`, `dialog.tsx`.
2. JSX in `frontend/src/components/` and `frontend/src/pages/` MUST NOT contain bare `<button>`, `<input>`, `<select>`, `<textarea>`, or `<a onClick=…>` elements (use the locally-owned shadcn primitives).
3. No `import` of `@mui/*`, `@chakra-ui/*`, `@mantine/*`, `react-bootstrap`, `antd`, `semantic-ui-react`.
4. `frontend/src/components/ui/*.tsx` MUST NOT import any business-logic module (no `import` paths starting with `@/services`, `@/hooks`, `@/pages`, `@/lib/api`).
5. No file under `frontend/src/components/` may *re-export* a primitive from `ui/` (i.e., `export { Button } from "@/components/ui/button";` outside `ui/index.ts`); edits go in place per the shadcn pattern.

**Files:**
- Create: `.harness/checks/frontend_ui_primitives.py`
- Create: `tests/harness/fixtures/frontend_ui_primitives/violation/bare_button.tsx`
- Create: `tests/harness/fixtures/frontend_ui_primitives/violation/imports_mui.tsx`
- Create: `tests/harness/fixtures/frontend_ui_primitives/violation/anchor_with_onclick.tsx`
- Create: `tests/harness/fixtures/frontend_ui_primitives/violation/ui_primitive_imports_service.tsx`
- Create: `tests/harness/fixtures/frontend_ui_primitives/violation/wrapper_reexport.tsx`
- Create: `tests/harness/fixtures/frontend_ui_primitives/compliant/uses_local_button.tsx`
- Create: `tests/harness/fixtures/frontend_ui_primitives/compliant/clean_ui_primitive.tsx`
- Create: `tests/harness/checks/test_frontend_ui_primitives.py`

### Task 3.1: Create violation fixtures

```bash
mkdir -p tests/harness/fixtures/frontend_ui_primitives/{violation,compliant}
```

`violation/bare_button.tsx`:

```tsx
/* Q4 violation — bare <button> element in feature code. */
export const Foo = () => <button onClick={() => {}}>x</button>;
```

`violation/imports_mui.tsx`:

```tsx
/* Q4 violation — MUI banned. */
import Button from "@mui/material/Button";

export const Foo = () => <Button>x</Button>;
```

`violation/anchor_with_onclick.tsx`:

```tsx
/* Q4 violation — <a onClick=...> imitating a button. */
export const Foo = () => <a onClick={() => {}}>click</a>;
```

`violation/ui_primitive_imports_service.tsx`:

```tsx
/* Q4 violation — primitive imports business logic.

Pretend-path: frontend/src/components/ui/button.tsx
*/
import { fetchIncident } from "@/services/api/incidents";

export const Button = () => {
  fetchIncident("x");
  return <button />;
};
```

`violation/wrapper_reexport.tsx`:

```tsx
/* Q4 violation — wrapper file re-exports a primitive (no edit-in-place pattern).

Pretend-path: frontend/src/components/Wrappers.tsx
*/
export { Button } from "@/components/ui/button";
```

### Task 3.2: Create compliant fixtures

`compliant/uses_local_button.tsx`:

```tsx
/* Q4 compliant — feature uses the locally-owned Button primitive. */
import { Button } from "@/components/ui/button";

export const Foo = () => <Button>x</Button>;
```

`compliant/clean_ui_primitive.tsx`:

```tsx
/* Q4 compliant — primitive lives under ui/, no business imports.

Pretend-path: frontend/src/components/ui/button.tsx
*/
import * as React from "react";
import { cn } from "@/lib/utils";

export const Button = React.forwardRef<HTMLButtonElement, React.ButtonHTMLAttributes<HTMLButtonElement>>(
  ({ className, ...props }, ref) => (
    <button ref={ref} className={cn("inline-flex items-center", className)} {...props} />
  ),
);
Button.displayName = "Button";
```

### Task 3.3: Write the failing test

Create `tests/harness/checks/test_frontend_ui_primitives.py`:

```python
"""H.1b.3 — frontend_ui_primitives check tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness._helpers import assert_check_fires, assert_check_silent

CHECK = "frontend_ui_primitives"
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / CHECK


@pytest.mark.parametrize(
    "fixture_name,expected_rule,pretend_path",
    [
        ("bare_button.tsx", "Q4.no-bare-html-primitive", "frontend/src/components/Foo.tsx"),
        ("imports_mui.tsx", "Q4.no-third-party-ui-kit", "frontend/src/components/Foo.tsx"),
        ("anchor_with_onclick.tsx", "Q4.no-bare-html-primitive", "frontend/src/components/Foo.tsx"),
        ("ui_primitive_imports_service.tsx", "Q4.primitive-no-business-logic", "frontend/src/components/ui/button.tsx"),
        ("wrapper_reexport.tsx", "Q4.no-wrapper-reexport", "frontend/src/components/Wrappers.tsx"),
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
        ("uses_local_button.tsx", "frontend/src/components/Foo.tsx"),
        ("clean_ui_primitive.tsx", "frontend/src/components/ui/button.tsx"),
    ],
)
def test_compliant_silent(fixture_name: str, pretend_path: str) -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / fixture_name,
        pretend_path=pretend_path,
    )
```

### Task 3.4: Run failing test + commit red

```bash
python -m pytest tests/harness/checks/test_frontend_ui_primitives.py -v
git add tests/harness/fixtures/frontend_ui_primitives tests/harness/checks/test_frontend_ui_primitives.py
git commit -m "$(cat <<'EOF'
test(red): H.1b.3 — frontend_ui_primitives fixtures + assertions

Five violation fixtures (bare <button>, MUI import, <a onClick=...>,
ui primitive importing business logic, wrapper file re-exporting a
primitive) plus two compliant counterparts.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 3.5: Implement the check

Create `.harness/checks/frontend_ui_primitives.py`:

```python
#!/usr/bin/env python3
"""Q4 — shadcn-pattern UI primitives, no third-party kits.

Five rules:
  Q4.no-bare-html-primitive    — bare <button>/<input>/<select>/<textarea>/
                                  <a onClick=…> in components/* or pages/*.
  Q4.no-third-party-ui-kit     — MUI/Chakra/Mantine/react-bootstrap/antd/semantic-ui banned.
  Q4.primitive-no-business-logic— imports inside frontend/src/components/ui/* may not
                                  start with @/services, @/hooks, @/pages, @/lib/api.
  Q4.no-wrapper-reexport       — re-export of @/components/ui/* outside ui/index.ts.
  Q4.ui-folder-presence        — frontend/src/components/ui/ must exist with at least
                                  one of button.tsx/input.tsx/dialog.tsx.

H-25:
  Missing input    — exit 2.
  Malformed input  — WARN harness.unparseable.
  Upstream failed  — none.
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

DEFAULT_ROOTS = (REPO_ROOT / "frontend" / "src",)
SCANNED_EXTS = {".ts", ".tsx", ".js", ".jsx"}
EXCLUDE_VIRTUAL_PREFIXES = (
    "frontend/e2e/",
    "frontend/src/test-utils/",
    "tests/harness/fixtures/",
)

THIRD_PARTY_UI_PREFIXES = (
    "@mui/", "@chakra-ui/", "@mantine/",
    "react-bootstrap", "antd", "semantic-ui-react",
)
BUSINESS_IMPORT_PREFIXES = ("@/services", "@/hooks", "@/pages", "@/lib/api")
UI_PRIMITIVE_PATH_PREFIX = "frontend/src/components/ui/"

IMPORT_FROM_RE = re.compile(r'''^\s*import\s+[^;]*?\bfrom\s+["']([^"']+)["']''', re.MULTILINE)
REEXPORT_RE = re.compile(r'''^\s*export\s*\{[^}]*\}\s*from\s+["'](@/components/ui/[^"']+)["']''', re.MULTILINE)
BARE_PRIMITIVE_RE = re.compile(r'<(button|input|select|textarea)\b[^>]*>')
ANCHOR_ONCLICK_RE = re.compile(r'<a\b[^>]*\bonClick\s*=')


def _is_excluded(virtual: str) -> bool:
    return any(virtual.startswith(p) for p in EXCLUDE_VIRTUAL_PREFIXES)


def _is_feature_file(virtual: str) -> bool:
    return (
        virtual.startswith("frontend/src/components/")
        or virtual.startswith("frontend/src/pages/")
    ) and not virtual.startswith(UI_PRIMITIVE_PATH_PREFIX)


def _is_ui_primitive(virtual: str) -> bool:
    return virtual.startswith(UI_PRIMITIVE_PATH_PREFIX)


def _scan_file(path: Path, virtual: str) -> Iterable[Finding]:
    if _is_excluded(virtual):
        return
    if path.suffix not in SCANNED_EXTS:
        return
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    for m in IMPORT_FROM_RE.finditer(source):
        module = m.group(1)
        line = source[:m.start()].count("\n") + 1
        if any(module.startswith(p) for p in THIRD_PARTY_UI_PREFIXES):
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=line,
                rule="Q4.no-third-party-ui-kit",
                message=f"third-party UI library `{module}` banned",
                suggestion="copy a Radix-based primitive into frontend/src/components/ui/",
            )
        if _is_ui_primitive(virtual) and any(module.startswith(p) for p in BUSINESS_IMPORT_PREFIXES):
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=line,
                rule="Q4.primitive-no-business-logic",
                message=f"ui primitive imports business module `{module}`",
                suggestion="primitives are presentation only; lift the call into the consuming feature",
            )
    if _is_feature_file(virtual):
        for m in BARE_PRIMITIVE_RE.finditer(source):
            line = source[:m.start()].count("\n") + 1
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=line,
                rule="Q4.no-bare-html-primitive",
                message=f"bare <{m.group(1)}> in feature code",
                suggestion=f"use the locally-owned <{m.group(1).capitalize()}> from @/components/ui/{m.group(1)}",
            )
        for m in ANCHOR_ONCLICK_RE.finditer(source):
            line = source[:m.start()].count("\n") + 1
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=line,
                rule="Q4.no-bare-html-primitive",
                message="<a onClick=...> imitating a button",
                suggestion="use <Button> for actions or <Link to=...> for navigation",
            )
    # wrapper re-export check (anywhere except ui/index.ts itself)
    if not virtual.endswith("frontend/src/components/ui/index.ts"):
        for m in REEXPORT_RE.finditer(source):
            line = source[:m.start()].count("\n") + 1
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=line,
                rule="Q4.no-wrapper-reexport",
                message=f"wrapper re-export of `{m.group(1)}`",
                suggestion="edit the primitive in place under components/ui/ instead of wrapping",
            )


def _scan_root_invariants(root: Path) -> Iterable[Finding]:
    ui_dir = root / "components" / "ui"
    if not ui_dir.exists() or not ui_dir.is_dir():
        yield Finding(
            severity=Severity.ERROR,
            file=ui_dir,
            line=0,
            rule="Q4.ui-folder-presence",
            message="frontend/src/components/ui/ missing",
            suggestion="copy shadcn primitives (button.tsx, input.tsx, dialog.tsx) into ui/",
        )
        return
    expected = {"button.tsx", "input.tsx", "dialog.tsx"}
    have = {p.name for p in ui_dir.glob("*.tsx")}
    if not (expected & have):
        yield Finding(
            severity=Severity.ERROR,
            file=ui_dir,
            line=0,
            rule="Q4.ui-folder-presence",
            message="components/ui/ contains no canonical primitives (button/input/dialog)",
            suggestion="add at least one shadcn primitive to anchor the pattern",
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
        if root.is_file() and root.suffix in SCANNED_EXTS:
            virtual = pretend_path or (str(root.relative_to(REPO_ROOT)) if root.is_relative_to(REPO_ROOT) else root.name)
            files = [(root, virtual)]
        else:
            files = []
            for p in root.rglob("*"):
                if p.is_file() and p.suffix in SCANNED_EXTS:
                    virtual = str(p.relative_to(REPO_ROOT)) if p.is_relative_to(REPO_ROOT) else p.name
                    files.append((p, virtual))
            for finding in _scan_root_invariants(root):
                emit(finding)
                if finding.severity == Severity.ERROR:
                    total_errors += 1
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
python -m pytest tests/harness/checks/test_frontend_ui_primitives.py -v
```

### Task 3.7: Triage live-repo run

```bash
python .harness/checks/frontend_ui_primitives.py
```

Expected hot spots:

- `Q4.no-bare-html-primitive` may fire on War Room components (`AgentFindingCard`, `EvidenceFindings`, etc.) that use bare `<button>` for the "approve / reject" toggles. Triage: replace with `<Button variant="ghost">` from the local primitive.
- `Q4.ui-folder-presence` MUST pass — if it fails, the shadcn substrate is missing.

### Task 3.8: Run validate-fast

```bash
python tools/run_validate.py --fast
```

### Task 3.9: Commit green

```bash
git add .harness/checks/frontend_ui_primitives.py
git commit -m "$(cat <<'EOF'
feat(green): H.1b.3 — frontend_ui_primitives enforces Q4

Five rules: ui/ folder must exist with canonical primitives; bare
<button>/<input>/<select>/<textarea>/<a onClick=…> banned in feature
code; third-party UI kits (MUI/Chakra/Mantine/react-bootstrap/antd/
semantic-ui) banned; ui/* primitives may not import services/hooks/
pages/lib/api; wrapper re-export of ui/* banned (edit in place).
H-25 docstring covers missing/malformed/no-upstream. Auto-discovered.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 3.10: Verify discovery

```bash
python tools/run_validate.py --fast 2>&1 | grep "check:frontend_ui_primitives"
```

---

# Story H.1b.4 — `frontend_testing.py` (Q5)

**Rule families enforced (5):**
1. `frontend/src/services/api/*.ts` files MUST have a paired `*.test.ts` with at least one `it(`/`test(` block (presence + non-empty smoke).
2. `frontend/src/hooks/*.ts` files MUST have a paired `*.test.ts(x)` (presence).
3. Test files (`*.test.ts(x)`) anywhere under `frontend/src/` MUST NOT import from `@playwright/test` (Playwright is quarantined to `frontend/e2e/`).
4. Test files MUST NOT import `enzyme`, `mocha`, `jest` (project standard is Vitest only). The `vitest` import itself is allowed.
5. `frontend/e2e/` files MUST import from `@playwright/test`, NOT `vitest` (project boundary).

**Files:**
- Create: `.harness/checks/frontend_testing.py`
- Create: `tests/harness/fixtures/frontend_testing/violation/api_module_no_test.ts`
- Create: `tests/harness/fixtures/frontend_testing/violation/hook_no_test.ts`
- Create: `tests/harness/fixtures/frontend_testing/violation/test_imports_jest.test.ts`
- Create: `tests/harness/fixtures/frontend_testing/violation/test_imports_playwright.test.ts`
- Create: `tests/harness/fixtures/frontend_testing/violation/e2e_imports_vitest.spec.ts`
- Create: `tests/harness/fixtures/frontend_testing/compliant/api_module.ts`
- Create: `tests/harness/fixtures/frontend_testing/compliant/api_module.test.ts`
- Create: `tests/harness/fixtures/frontend_testing/compliant/e2e_clean.spec.ts`
- Create: `tests/harness/checks/test_frontend_testing.py`

### Task 4.1: Create violation fixtures

```bash
mkdir -p tests/harness/fixtures/frontend_testing/{violation,compliant}
```

`violation/api_module_no_test.ts`:

```ts
/* Q5 violation — services/api module without paired *.test.ts.

Pretend-path: frontend/src/services/api/orphan.ts
*/
export const fetchOrphan = () => fetch("/api/orphan");
```

`violation/hook_no_test.ts`:

```ts
/* Q5 violation — hook without paired *.test.ts(x).

Pretend-path: frontend/src/hooks/useOrphan.ts
*/
export const useOrphan = () => null;
```

`violation/test_imports_jest.test.ts`:

```ts
/* Q5 violation — jest banned. */
import { describe, it } from "jest";

describe("x", () => it("works", () => {}));
```

`violation/test_imports_playwright.test.ts`:

```ts
/* Q5 violation — Playwright import in unit test (must live under frontend/e2e/). */
import { test, expect } from "@playwright/test";

test("x", async ({ page }) => {
  expect(page).toBeTruthy();
});
```

`violation/e2e_imports_vitest.spec.ts`:

```ts
/* Q5 violation — vitest import in e2e file.

Pretend-path: frontend/e2e/login.spec.ts
*/
import { describe, it } from "vitest";

describe("login", () => it("works", () => {}));
```

### Task 4.2: Create compliant fixtures

`compliant/api_module.ts`:

```ts
/* Q5 compliant — has paired test file in same fixture set.

Pretend-path: frontend/src/services/api/foo.ts
*/
import { apiClient } from "@/services/api/client";
export const fetchFoo = (id: string) => apiClient<{ id: string }>(`/api/foo/${id}`);
```

`compliant/api_module.test.ts`:

```ts
/* Q5 compliant — test exists with non-empty `it(` block.

Pretend-path: frontend/src/services/api/foo.test.ts
*/
import { describe, it, expect } from "vitest";
import { fetchFoo } from "./api_module";

describe("fetchFoo", () => {
  it("constructs the URL correctly", () => {
    expect(typeof fetchFoo).toBe("function");
  });
});
```

`compliant/e2e_clean.spec.ts`:

```ts
/* Q5 compliant — e2e file uses Playwright, not vitest.

Pretend-path: frontend/e2e/login.spec.ts
*/
import { test, expect } from "@playwright/test";

test("homepage", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle(/DebugDuck/);
});
```

### Task 4.3: Write the failing test

Create `tests/harness/checks/test_frontend_testing.py`:

```python
"""H.1b.4 — frontend_testing check tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness._helpers import assert_check_fires, assert_check_silent

CHECK = "frontend_testing"
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / CHECK


@pytest.mark.parametrize(
    "fixture_name,expected_rule,pretend_path",
    [
        ("api_module_no_test.ts", "Q5.api-module-needs-test", "frontend/src/services/api/orphan.ts"),
        ("hook_no_test.ts", "Q5.hook-needs-test", "frontend/src/hooks/useOrphan.ts"),
        ("test_imports_jest.test.ts", "Q5.no-jest-or-mocha", "frontend/src/foo.test.ts"),
        ("test_imports_playwright.test.ts", "Q5.no-playwright-in-unit", "frontend/src/foo.test.ts"),
        ("e2e_imports_vitest.spec.ts", "Q5.e2e-must-use-playwright", "frontend/e2e/login.spec.ts"),
    ],
)
def test_violation_fires(fixture_name: str, expected_rule: str, pretend_path: str) -> None:
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / fixture_name,
        expected_rule=expected_rule,
        pretend_path=pretend_path,
    )


def test_compliant_directory_silent() -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant",
        pretend_path="frontend/src/services/api/foo.ts",
    )
```

### Task 4.4: Run failing test + commit red

```bash
python -m pytest tests/harness/checks/test_frontend_testing.py -v
git add tests/harness/fixtures/frontend_testing tests/harness/checks/test_frontend_testing.py
git commit -m "$(cat <<'EOF'
test(red): H.1b.4 — frontend_testing fixtures + assertions

Five violation fixtures (api module / hook without paired test, test
file importing jest, unit test importing Playwright, e2e file importing
vitest) plus a compliant directory pairing source with a non-empty
.test.ts and a clean Playwright spec.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 4.5: Implement the check

Create `.harness/checks/frontend_testing.py`:

```python
#!/usr/bin/env python3
"""Q5 — Vitest discipline + Playwright scope.

Five rules:
  Q5.api-module-needs-test   — frontend/src/services/api/*.ts needs paired *.test.ts.
  Q5.hook-needs-test         — frontend/src/hooks/*.ts(x) needs paired *.test.ts(x).
  Q5.no-jest-or-mocha        — *.test.ts(x) banned from importing jest/mocha/enzyme.
  Q5.no-playwright-in-unit   — *.test.ts(x) banned from importing @playwright/test.
  Q5.e2e-must-use-playwright — frontend/e2e/*.spec.ts must import from @playwright/test
                                AND must NOT import from vitest.

H-25:
  Missing input    — exit 2.
  Malformed input  — WARN harness.unparseable.
  Upstream failed  — none.
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

DEFAULT_ROOTS = (REPO_ROOT / "frontend",)
SCANNED_EXTS = {".ts", ".tsx", ".js", ".jsx"}
EXCLUDE_VIRTUAL_PREFIXES = (
    "frontend/dist/",
    "tests/harness/fixtures/",
    "frontend/node_modules/",
)

BANNED_TEST_FRAMEWORKS = {"jest", "mocha", "enzyme"}
PLAYWRIGHT_MODULE = "@playwright/test"
VITEST_MODULES = {"vitest"}

IMPORT_FROM_RE = re.compile(r'''^\s*import\s+[^;]*?\bfrom\s+["']([^"']+)["']''', re.MULTILINE)
IT_OR_TEST_BLOCK_RE = re.compile(r'\b(it|test)\s*\(\s*["\']')


def _is_excluded(virtual: str) -> bool:
    return any(virtual.startswith(p) for p in EXCLUDE_VIRTUAL_PREFIXES)


def _is_test_file(virtual: str) -> bool:
    return ".test." in virtual.split("/")[-1]


def _is_e2e_file(virtual: str) -> bool:
    return virtual.startswith("frontend/e2e/")


def _scan_test_imports(path: Path, virtual: str, source: str) -> Iterable[Finding]:
    for m in IMPORT_FROM_RE.finditer(source):
        module = m.group(1)
        line = source[:m.start()].count("\n") + 1
        if _is_test_file(virtual):
            if module in BANNED_TEST_FRAMEWORKS:
                yield Finding(
                    severity=Severity.ERROR,
                    file=path,
                    line=line,
                    rule="Q5.no-jest-or-mocha",
                    message=f"banned test framework `{module}` in unit test",
                    suggestion="use vitest instead",
                )
            if module == PLAYWRIGHT_MODULE:
                yield Finding(
                    severity=Severity.ERROR,
                    file=path,
                    line=line,
                    rule="Q5.no-playwright-in-unit",
                    message="`@playwright/test` imported in unit test",
                    suggestion="move e2e tests under frontend/e2e/",
                )
        if _is_e2e_file(virtual):
            if module in VITEST_MODULES:
                yield Finding(
                    severity=Severity.ERROR,
                    file=path,
                    line=line,
                    rule="Q5.e2e-must-use-playwright",
                    message="vitest imported in e2e spec",
                    suggestion="use @playwright/test in frontend/e2e/",
                )


def _scan_e2e_must_use_playwright(path: Path, virtual: str, source: str) -> Iterable[Finding]:
    if not _is_e2e_file(virtual):
        return
    if PLAYWRIGHT_MODULE not in source:
        yield Finding(
            severity=Severity.ERROR,
            file=path,
            line=1,
            rule="Q5.e2e-must-use-playwright",
            message=f"e2e spec {path.name} does not import from @playwright/test",
            suggestion="add `import { test, expect } from \"@playwright/test\";`",
        )


def _scan_paired_tests(root: Path) -> Iterable[Finding]:
    """services/api/*.ts and hooks/*.ts(x) must have paired *.test.ts(x) with ≥ 1 it/test block."""
    api_dir = root / "src" / "services" / "api"
    hook_dir = root / "src" / "hooks"
    for src_file in api_dir.glob("*.ts") if api_dir.exists() else []:
        if src_file.name in {"client.ts", "index.ts"} or src_file.name.endswith(".test.ts"):
            continue
        test_file = src_file.with_name(src_file.stem + ".test.ts")
        if not test_file.exists() or not IT_OR_TEST_BLOCK_RE.search(test_file.read_text(encoding="utf-8")):
            yield Finding(
                severity=Severity.ERROR,
                file=src_file,
                line=1,
                rule="Q5.api-module-needs-test",
                message=f"services/api/{src_file.name} missing non-empty paired test",
                suggestion=f"add {test_file.name} with at least one `it(` block",
            )
    for src_file in hook_dir.glob("*.ts") if hook_dir.exists() else []:
        if src_file.name == "index.ts" or src_file.name.endswith(".test.ts"):
            continue
        for ext in (".test.ts", ".test.tsx"):
            test_file = src_file.with_name(src_file.stem + ext)
            if test_file.exists():
                break
        else:
            yield Finding(
                severity=Severity.ERROR,
                file=src_file,
                line=1,
                rule="Q5.hook-needs-test",
                message=f"hooks/{src_file.name} missing paired test",
                suggestion=f"add {src_file.stem}.test.ts(x)",
            )
    for src_file in hook_dir.glob("*.tsx") if hook_dir.exists() else []:
        if src_file.name.endswith(".test.tsx"):
            continue
        test_file = src_file.with_name(src_file.stem + ".test.tsx")
        if not test_file.exists():
            test_file = src_file.with_name(src_file.stem + ".test.ts")
        if not test_file.exists():
            yield Finding(
                severity=Severity.ERROR,
                file=src_file,
                line=1,
                rule="Q5.hook-needs-test",
                message=f"hooks/{src_file.name} missing paired test",
                suggestion=f"add {src_file.stem}.test.tsx",
            )


def _scan_file(path: Path, virtual: str) -> Iterable[Finding]:
    if _is_excluded(virtual):
        return
    if path.suffix not in SCANNED_EXTS:
        return
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    yield from _scan_test_imports(path, virtual, source)
    yield from _scan_e2e_must_use_playwright(path, virtual, source)


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
        if root.is_file() and root.suffix in SCANNED_EXTS:
            virtual = pretend_path or (str(root.relative_to(REPO_ROOT)) if root.is_relative_to(REPO_ROOT) else root.name)
            files = [(root, virtual)]
        else:
            files = []
            for p in root.rglob("*"):
                if p.is_file() and p.suffix in SCANNED_EXTS:
                    virtual = str(p.relative_to(REPO_ROOT)) if p.is_relative_to(REPO_ROOT) else p.name
                    files.append((p, virtual))
            for finding in _scan_paired_tests(root):
                emit(finding)
                if finding.severity == Severity.ERROR:
                    total_errors += 1
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
python -m pytest tests/harness/checks/test_frontend_testing.py -v
```

### Task 4.7: Triage live-repo run

```bash
python .harness/checks/frontend_testing.py
```

Expected hot spots:

- `Q5.api-module-needs-test` will fire heavily on the existing services/api/ if tests do not yet exist. Triage: write smoke tests for the top 3 highest-traffic api modules; baseline the rest (deferred to H.1d.1).
- `Q5.hook-needs-test` will fire on hooks. Same triage approach.

### Task 4.8: Run validate-fast

```bash
python tools/run_validate.py --fast
```

### Task 4.9: Commit green

```bash
git add .harness/checks/frontend_testing.py
git commit -m "$(cat <<'EOF'
feat(green): H.1b.4 — frontend_testing enforces Q5

Five rules: services/api modules and hooks/ files must have paired
non-empty *.test files; unit tests may not import jest/mocha/enzyme
or @playwright/test; e2e/ files must use @playwright/test, not vitest.
H-25 docstring covers missing/malformed/no-upstream. Auto-discovered.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 4.10: (Optional) write top-3 services/api smoke tests

Pick the three highest-traffic api modules (likely `incidents`, `runs`, `agents`). For each, add a `*.test.ts` that asserts `expect(typeof <fn>).toBe("function")` and that the URL constructor handles edge cases. Commit each separately.

---

# Story H.1b.5 — `frontend_routing.py` (Q6)

**Rule families enforced (5):**
1. `frontend/src/router.tsx` MUST exist and call `createBrowserRouter([...])` exactly once.
2. No file under `frontend/src/` other than `router.tsx` may call `createBrowserRouter` or `createMemoryRouter` (single route table).
3. Page components imported by the route table MUST use `lazy()` or `React.lazy()` (no synchronous page imports — bundle-split discipline).
4. JSX `<a href="/...">` (relative URL pointing to internal route) anywhere under `frontend/src/components/` or `frontend/src/pages/` → ERROR. Use `<Link to="...">` from `react-router-dom`.
5. The `useNavigate` hook MUST NOT be invoked at module top-level (only inside component/hook bodies). Heuristic: `const navigate = useNavigate();` at indent-level 0.

**Files:**
- Create: `.harness/checks/frontend_routing.py`
- Create: `tests/harness/fixtures/frontend_routing/violation/anchor_to_internal_route.tsx`
- Create: `tests/harness/fixtures/frontend_routing/violation/duplicate_browser_router.tsx`
- Create: `tests/harness/fixtures/frontend_routing/violation/sync_page_import.tsx`
- Create: `tests/harness/fixtures/frontend_routing/compliant/uses_link.tsx`
- Create: `tests/harness/fixtures/frontend_routing/compliant/lazy_page_import.tsx`
- Create: `tests/harness/checks/test_frontend_routing.py`

### Task 5.1: Create violation fixtures

```bash
mkdir -p tests/harness/fixtures/frontend_routing/{violation,compliant}
```

`violation/anchor_to_internal_route.tsx`:

```tsx
/* Q6 violation — <a href="/incidents"> for internal nav. */
export const Foo = () => <a href="/incidents">go</a>;
```

`violation/duplicate_browser_router.tsx`:

```tsx
/* Q6 violation — additional createBrowserRouter call outside router.tsx.

Pretend-path: frontend/src/components/AdminRouter.tsx
*/
import { createBrowserRouter } from "react-router-dom";

export const router = createBrowserRouter([{ path: "/admin", element: null }]);
```

`violation/sync_page_import.tsx`:

```tsx
/* Q6 violation — synchronous page import inside the route table.

Pretend-path: frontend/src/router.tsx
*/
import { createBrowserRouter } from "react-router-dom";
import IncidentsPage from "@/pages/Incidents";

export const router = createBrowserRouter([
  { path: "/incidents", element: <IncidentsPage /> },
]);
```

### Task 5.2: Create compliant fixtures

`compliant/uses_link.tsx`:

```tsx
/* Q6 compliant — internal nav via <Link>. */
import { Link } from "react-router-dom";

export const Foo = () => <Link to="/incidents">go</Link>;
```

`compliant/lazy_page_import.tsx`:

```tsx
/* Q6 compliant — lazy-imported page in the route table.

Pretend-path: frontend/src/router.tsx
*/
import { lazy } from "react";
import { createBrowserRouter } from "react-router-dom";

const IncidentsPage = lazy(() => import("@/pages/Incidents"));

export const router = createBrowserRouter([
  { path: "/incidents", element: <IncidentsPage /> },
]);
```

### Task 5.3: Write the failing test

Create `tests/harness/checks/test_frontend_routing.py`:

```python
"""H.1b.5 — frontend_routing check tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness._helpers import assert_check_fires, assert_check_silent

CHECK = "frontend_routing"
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / CHECK


@pytest.mark.parametrize(
    "fixture_name,expected_rule,pretend_path",
    [
        ("anchor_to_internal_route.tsx", "Q6.no-anchor-for-internal-nav", "frontend/src/components/Foo.tsx"),
        ("duplicate_browser_router.tsx", "Q6.single-route-table", "frontend/src/components/AdminRouter.tsx"),
        ("sync_page_import.tsx", "Q6.pages-must-be-lazy", "frontend/src/router.tsx"),
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
        ("uses_link.tsx", "frontend/src/components/Foo.tsx"),
        ("lazy_page_import.tsx", "frontend/src/router.tsx"),
    ],
)
def test_compliant_silent(fixture_name: str, pretend_path: str) -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / fixture_name,
        pretend_path=pretend_path,
    )
```

### Task 5.4: Run failing test + commit red

```bash
python -m pytest tests/harness/checks/test_frontend_routing.py -v
git add tests/harness/fixtures/frontend_routing tests/harness/checks/test_frontend_routing.py
git commit -m "$(cat <<'EOF'
test(red): H.1b.5 — frontend_routing fixtures + assertions

Three violation fixtures (<a> for internal nav, second createBrowserRouter
outside router.tsx, sync page import in route table) plus two compliant
counterparts (Link usage, lazy page import).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 5.5: Implement the check

Create `.harness/checks/frontend_routing.py`:

```python
#!/usr/bin/env python3
"""Q6 — single React Router v6 route table, lazy-imported pages.

Five rules:
  Q6.router-tsx-presence            — frontend/src/router.tsx must exist + call createBrowserRouter once.
  Q6.single-route-table             — createBrowserRouter / createMemoryRouter outside router.tsx banned.
  Q6.pages-must-be-lazy             — element: <X /> in router.tsx where X is a synchronously-
                                       imported page module.
  Q6.no-anchor-for-internal-nav     — <a href="/...."> in components/* or pages/* (use <Link>).
  Q6.useNavigate-not-at-top-level   — `useNavigate(` at module top-level outside any function.

H-25:
  Missing input    — exit 2.
  Malformed input  — WARN harness.unparseable.
  Upstream failed  — none.
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

DEFAULT_ROOTS = (REPO_ROOT / "frontend" / "src",)
SCANNED_EXTS = {".ts", ".tsx", ".js", ".jsx"}
EXCLUDE_VIRTUAL_PREFIXES = (
    "frontend/e2e/",
    "frontend/dist/",
    "tests/harness/fixtures/",
)

CREATE_ROUTER_RE = re.compile(r'\bcreate(?:Browser|Memory)Router\s*\(')
ANCHOR_INTERNAL_RE = re.compile(r'<a\b[^>]*\bhref\s*=\s*["\'](/[^"\']*)["\']')
IMPORT_FROM_RE = re.compile(r'''^\s*import\s+(\{[^}]*\}|\*\s*as\s*\w+|\w+)\s+from\s+["']([^"']+)["']''', re.MULTILINE)
PAGE_IMPORT_RE = re.compile(r'''^\s*import\s+(\w+)\s+from\s+["'](@/pages/[^"']+|\.\./pages/[^"']+|\./pages/[^"']+)["']''', re.MULTILINE)
USE_NAVIGATE_TOP_RE = re.compile(r'^const\s+\w+\s*=\s*useNavigate\s*\(', re.MULTILINE)


def _is_excluded(virtual: str) -> bool:
    return any(virtual.startswith(p) for p in EXCLUDE_VIRTUAL_PREFIXES)


def _is_router_tsx(virtual: str) -> bool:
    return virtual == "frontend/src/router.tsx" or virtual.endswith("/router.tsx")


def _is_feature_file(virtual: str) -> bool:
    return (
        virtual.startswith("frontend/src/components/")
        or virtual.startswith("frontend/src/pages/")
    )


def _scan_file(path: Path, virtual: str) -> Iterable[Finding]:
    if _is_excluded(virtual):
        return
    if path.suffix not in SCANNED_EXTS:
        return
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return

    # Q6.single-route-table
    if not _is_router_tsx(virtual):
        for m in CREATE_ROUTER_RE.finditer(source):
            line = source[:m.start()].count("\n") + 1
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=line,
                rule="Q6.single-route-table",
                message="createBrowserRouter outside frontend/src/router.tsx",
                suggestion="declare all routes in router.tsx (Q6: single route table)",
            )

    # Q6.no-anchor-for-internal-nav
    if _is_feature_file(virtual):
        for m in ANCHOR_INTERNAL_RE.finditer(source):
            line = source[:m.start()].count("\n") + 1
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=line,
                rule="Q6.no-anchor-for-internal-nav",
                message=f"<a href=\"{m.group(1)}\"> for internal navigation",
                suggestion=f'use <Link to="{m.group(1)}"> from react-router-dom',
            )

    # Q6.useNavigate-not-at-top-level
    for m in USE_NAVIGATE_TOP_RE.finditer(source):
        line = source[:m.start()].count("\n") + 1
        yield Finding(
            severity=Severity.ERROR,
            file=path,
            line=line,
            rule="Q6.useNavigate-not-at-top-level",
            message="useNavigate() invoked at module top-level",
            suggestion="call useNavigate() inside a component/hook function body",
        )

    # Q6.pages-must-be-lazy (only inside router.tsx)
    if _is_router_tsx(virtual):
        sync_page_imports = {m.group(1) for m in PAGE_IMPORT_RE.finditer(source) if "lazy(" not in source[max(0, m.start() - 50):m.start()]}
        for page_name in sync_page_imports:
            line = source.find(f"import {page_name}")
            lineno = source[:line].count("\n") + 1 if line >= 0 else 1
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=lineno,
                rule="Q6.pages-must-be-lazy",
                message=f"page `{page_name}` imported synchronously",
                suggestion=f"const {page_name} = lazy(() => import(\"@/pages/{page_name}\"))",
            )


def _scan_root_invariants(root: Path) -> Iterable[Finding]:
    router = root / "router.tsx"
    if not router.exists():
        yield Finding(
            severity=Severity.ERROR,
            file=router,
            line=0,
            rule="Q6.router-tsx-presence",
            message="frontend/src/router.tsx missing",
            suggestion="create router.tsx with a single createBrowserRouter call",
        )
        return
    text = router.read_text(encoding="utf-8")
    if not CREATE_ROUTER_RE.search(text):
        yield Finding(
            severity=Severity.ERROR,
            file=router,
            line=1,
            rule="Q6.router-tsx-presence",
            message="router.tsx does not call createBrowserRouter",
            suggestion="add `export const router = createBrowserRouter([...])`",
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
        if root.is_file() and root.suffix in SCANNED_EXTS:
            virtual = pretend_path or (str(root.relative_to(REPO_ROOT)) if root.is_relative_to(REPO_ROOT) else root.name)
            files = [(root, virtual)]
        else:
            files = []
            for p in root.rglob("*"):
                if p.is_file() and p.suffix in SCANNED_EXTS:
                    virtual = str(p.relative_to(REPO_ROOT)) if p.is_relative_to(REPO_ROOT) else p.name
                    files.append((p, virtual))
            for finding in _scan_root_invariants(root):
                emit(finding)
                if finding.severity == Severity.ERROR:
                    total_errors += 1
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

### Task 5.6: Run tests, expect green

```bash
python -m pytest tests/harness/checks/test_frontend_routing.py -v
```

### Task 5.7: Triage live-repo run + validate-fast

```bash
python .harness/checks/frontend_routing.py
python tools/run_validate.py --fast
```

### Task 5.8: Commit green

```bash
git add .harness/checks/frontend_routing.py
git commit -m "$(cat <<'EOF'
feat(green): H.1b.5 — frontend_routing enforces Q6

Five rules: router.tsx presence + single createBrowserRouter call;
createBrowserRouter banned elsewhere; pages in router.tsx must be
lazy-imported; <a href="/..."> banned in feature code (use <Link>);
useNavigate() may not run at module top-level. H-25 docstring covers
missing/malformed/no-upstream. Auto-discovered.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Story H.1b.6 — `accessibility_policy.py` (Q14)

**Rule families enforced (6):**
1. `frontend/eslint.config.js` MUST configure `eslint-plugin-jsx-a11y` at `error` level (presence + level check).
2. Every `frontend/src/components/ui/*.tsx` primitive MUST have a paired `*.test.tsx` that calls `axe(...)` (vitest-axe wired in H.0b Story 7).
3. Every page under `frontend/src/pages/` listed in `.harness/accessibility_policy.yaml.incident_critical` MUST have a Playwright spec under `frontend/e2e/a11y/` that calls `injectAxe`/`checkA11y` (presence + content check).
4. `<img>` elements without `alt=` attribute (anywhere under `frontend/src/`) → ERROR.
5. `<button>`/`<a>` elements without an accessible name (no children, no `aria-label`, no `aria-labelledby`) → ERROR. Heuristic: empty body + no aria attribute.
6. `tabIndex` value > 0 on any element → ERROR (creates focus-order traps).

**Files:**
- Create: `.harness/accessibility_policy.yaml` (if not seeded by H.0b)
- Create: `.harness/checks/accessibility_policy.py`
- Create: `tests/harness/fixtures/accessibility_policy/violation/img_no_alt.tsx`
- Create: `tests/harness/fixtures/accessibility_policy/violation/button_no_name.tsx`
- Create: `tests/harness/fixtures/accessibility_policy/violation/positive_tabindex.tsx`
- Create: `tests/harness/fixtures/accessibility_policy/violation/missing_axe_test.tsx`
- Create: `tests/harness/fixtures/accessibility_policy/compliant/img_with_alt.tsx`
- Create: `tests/harness/fixtures/accessibility_policy/compliant/button_with_label.tsx`
- Create: `tests/harness/fixtures/accessibility_policy/compliant/primitive_with_axe.test.tsx`
- Create: `tests/harness/checks/test_accessibility_policy.py`

### Task 6.1: Confirm or seed `.harness/accessibility_policy.yaml`

If H.0b Story 7 left a stub, append (or create):

```yaml
incident_critical:
  - InvestigationView
  - WarRoomDashboard
  - IncidentList

axe_rules_disabled: []  # do not silently disable rules; require ADR

soft_warn:
  - color-contrast  # gradual rollout
```

### Task 6.2: Create violation fixtures

```bash
mkdir -p tests/harness/fixtures/accessibility_policy/{violation,compliant}
```

`violation/img_no_alt.tsx`:

```tsx
/* Q14 violation — <img> without alt attribute. */
export const Foo = () => <img src="/x.png" />;
```

`violation/button_no_name.tsx`:

```tsx
/* Q14 violation — <button> with no children and no aria-label. */
export const Foo = () => <button onClick={() => {}} />;
```

`violation/positive_tabindex.tsx`:

```tsx
/* Q14 violation — positive tabIndex creates focus-order trap. */
export const Foo = () => <div tabIndex={3}>x</div>;
```

`violation/missing_axe_test.tsx`:

```tsx
/* Q14 violation — primitive paired test does not call axe().

Pretend-path: frontend/src/components/ui/badge.test.tsx
*/
import { render } from "@testing-library/react";
import { Badge } from "./badge";

test("renders", () => {
  render(<Badge>x</Badge>);
});
```

### Task 6.3: Create compliant fixtures

`compliant/img_with_alt.tsx`:

```tsx
export const Foo = () => <img src="/x.png" alt="diagram of cascade" />;
```

`compliant/button_with_label.tsx`:

```tsx
export const Foo = () => <button aria-label="close panel" onClick={() => {}} />;
```

`compliant/primitive_with_axe.test.tsx`:

```tsx
/* Q14 compliant — paired test calls axe().

Pretend-path: frontend/src/components/ui/button.test.tsx
*/
import { render } from "@testing-library/react";
import { axe } from "vitest-axe";
import { Button } from "./button";

test("button is a11y-clean", async () => {
  const { container } = render(<Button>x</Button>);
  const results = await axe(container);
  expect(results).toHaveNoViolations();
});
```

### Task 6.4: Write the failing test

Create `tests/harness/checks/test_accessibility_policy.py`:

```python
"""H.1b.6 — accessibility_policy check tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness._helpers import assert_check_fires, assert_check_silent

CHECK = "accessibility_policy"
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / CHECK


@pytest.mark.parametrize(
    "fixture_name,expected_rule,pretend_path",
    [
        ("img_no_alt.tsx", "Q14.img-needs-alt", "frontend/src/components/Foo.tsx"),
        ("button_no_name.tsx", "Q14.button-needs-accessible-name", "frontend/src/components/Foo.tsx"),
        ("positive_tabindex.tsx", "Q14.no-positive-tabindex", "frontend/src/components/Foo.tsx"),
        ("missing_axe_test.tsx", "Q14.primitive-needs-axe-test", "frontend/src/components/ui/badge.test.tsx"),
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
        ("img_with_alt.tsx", "frontend/src/components/Foo.tsx"),
        ("button_with_label.tsx", "frontend/src/components/Foo.tsx"),
        ("primitive_with_axe.test.tsx", "frontend/src/components/ui/button.test.tsx"),
    ],
)
def test_compliant_silent(fixture_name: str, pretend_path: str) -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / fixture_name,
        pretend_path=pretend_path,
    )
```

### Task 6.5: Run failing test + commit red

```bash
python -m pytest tests/harness/checks/test_accessibility_policy.py -v
git add tests/harness/fixtures/accessibility_policy tests/harness/checks/test_accessibility_policy.py .harness/accessibility_policy.yaml
git commit -m "$(cat <<'EOF'
test(red): H.1b.6 — accessibility_policy fixtures + assertions

Four violation fixtures (<img> without alt, <button> with no name, positive
tabIndex, primitive paired test missing axe call) plus three compliant
counterparts. Policy yaml seeds incident_critical pages list.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 6.6: Implement the check

Create `.harness/checks/accessibility_policy.py`:

```python
#!/usr/bin/env python3
"""Q14 — accessibility policy.

Six rules:
  Q14.eslint-jsx-a11y-required        — eslint config must enable jsx-a11y at error.
  Q14.primitive-needs-axe-test        — every components/ui/*.tsx needs paired *.test.tsx
                                         that calls `axe(...)` (or `runAxe(...)`).
  Q14.incident-page-needs-e2e         — every page in policy.incident_critical must have
                                         a Playwright spec in frontend/e2e/a11y/ that calls
                                         `injectAxe` and `checkA11y`.
  Q14.img-needs-alt                   — <img> without alt= attribute.
  Q14.button-needs-accessible-name    — <button>/<a> with no children and no aria-label/
                                         aria-labelledby.
  Q14.no-positive-tabindex            — tabIndex={n} where n > 0.

H-25:
  Missing input    — exit 2.
  Malformed input  — WARN harness.unparseable.
  Upstream failed  — none.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from .harness.checks._common import Finding, Severity, emit  # noqa: E402

DEFAULT_ROOTS = (REPO_ROOT / "frontend" / "src",)
DEFAULT_POLICY = REPO_ROOT / ".harness" / "accessibility_policy.yaml"
ESLINT_CONFIG = REPO_ROOT / "frontend" / "eslint.config.js"
SCANNED_EXTS = {".ts", ".tsx", ".js", ".jsx"}
EXCLUDE_VIRTUAL_PREFIXES = (
    "frontend/e2e/",
    "frontend/dist/",
    "tests/harness/fixtures/",
)

IMG_TAG_RE = re.compile(r'<img\b([^>]*)>', re.IGNORECASE)
BUTTON_OR_ANCHOR_RE = re.compile(r'<(button|a)\b([^>]*)>(.*?)</\1>', re.DOTALL | re.IGNORECASE)
SELF_CLOSING_BUTTON_RE = re.compile(r'<(button|a)\b([^/>]*)/>', re.IGNORECASE)
TABINDEX_RE = re.compile(r'tabIndex\s*=\s*\{?\s*(-?\d+)')


def _load_policy(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _is_excluded(virtual: str) -> bool:
    return any(virtual.startswith(p) for p in EXCLUDE_VIRTUAL_PREFIXES)


def _has_attr(attrs: str, name: str) -> bool:
    return re.search(rf'\b{name}\s*=', attrs, re.IGNORECASE) is not None


def _scan_file(path: Path, virtual: str) -> Iterable[Finding]:
    if _is_excluded(virtual):
        return
    if path.suffix not in SCANNED_EXTS:
        return
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return

    # Q14.img-needs-alt
    for m in IMG_TAG_RE.finditer(source):
        attrs = m.group(1)
        if not _has_attr(attrs, "alt"):
            line = source[:m.start()].count("\n") + 1
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=line,
                rule="Q14.img-needs-alt",
                message="<img> missing alt attribute",
                suggestion='add alt="" for decorative or alt="<description>" for content',
            )

    # Q14.button-needs-accessible-name
    for m in BUTTON_OR_ANCHOR_RE.finditer(source):
        attrs = m.group(2)
        body = m.group(3).strip()
        if not body and not _has_attr(attrs, "aria-label") and not _has_attr(attrs, "aria-labelledby"):
            line = source[:m.start()].count("\n") + 1
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=line,
                rule="Q14.button-needs-accessible-name",
                message=f"<{m.group(1)}> without accessible name",
                suggestion="add visible text, aria-label, or aria-labelledby",
            )
    for m in SELF_CLOSING_BUTTON_RE.finditer(source):
        attrs = m.group(2)
        if not _has_attr(attrs, "aria-label") and not _has_attr(attrs, "aria-labelledby"):
            line = source[:m.start()].count("\n") + 1
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=line,
                rule="Q14.button-needs-accessible-name",
                message=f"self-closing <{m.group(1)}> without accessible name",
                suggestion="add aria-label or expand to include children",
            )

    # Q14.no-positive-tabindex
    for m in TABINDEX_RE.finditer(source):
        try:
            value = int(m.group(1))
        except ValueError:
            continue
        if value > 0:
            line = source[:m.start()].count("\n") + 1
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=line,
                rule="Q14.no-positive-tabindex",
                message=f"tabIndex={value} (positive value creates focus-order trap)",
                suggestion="use tabIndex={0} or tabIndex={-1}; let DOM order drive focus",
            )

    # Q14.primitive-needs-axe-test
    if virtual.startswith("frontend/src/components/ui/") and ".test." in path.name:
        if "axe(" not in source and "runAxe(" not in source:
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=1,
                rule="Q14.primitive-needs-axe-test",
                message=f"primitive test {path.name} does not call axe()",
                suggestion="import { axe } from 'vitest-axe' and assert no violations",
            )


def _scan_root_invariants(root: Path, policy: dict) -> Iterable[Finding]:
    # Q14.eslint-jsx-a11y-required
    if ESLINT_CONFIG.exists():
        text = ESLINT_CONFIG.read_text(encoding="utf-8")
        if "jsx-a11y" not in text:
            yield Finding(
                severity=Severity.ERROR,
                file=ESLINT_CONFIG,
                line=1,
                rule="Q14.eslint-jsx-a11y-required",
                message="eslint config does not reference jsx-a11y",
                suggestion="install + enable eslint-plugin-jsx-a11y at error level",
            )
        elif "error" not in text.lower():
            yield Finding(
                severity=Severity.ERROR,
                file=ESLINT_CONFIG,
                line=1,
                rule="Q14.eslint-jsx-a11y-required",
                message="jsx-a11y plugin present but not at error level",
                suggestion='set rule severity to "error"',
            )
    # Q14.primitive-needs-axe-test (presence pairing)
    ui_dir = root / "components" / "ui"
    if ui_dir.exists():
        for primitive in ui_dir.glob("*.tsx"):
            if primitive.name.endswith(".test.tsx") or primitive.stem in {"index"}:
                continue
            test = primitive.with_name(primitive.stem + ".test.tsx")
            if not test.exists():
                yield Finding(
                    severity=Severity.ERROR,
                    file=primitive,
                    line=1,
                    rule="Q14.primitive-needs-axe-test",
                    message=f"primitive {primitive.name} missing paired axe test",
                    suggestion=f"add {primitive.stem}.test.tsx with vitest-axe assertions",
                )
    # Q14.incident-page-needs-e2e
    e2e_dir = REPO_ROOT / "frontend" / "e2e" / "a11y"
    critical = policy.get("incident_critical") or []
    for page_name in critical:
        candidates = list(e2e_dir.glob(f"*{page_name.lower()}*.spec.ts")) if e2e_dir.exists() else []
        ok = False
        for cand in candidates:
            text = cand.read_text(encoding="utf-8")
            if "injectAxe" in text and "checkA11y" in text:
                ok = True
                break
        if not ok:
            yield Finding(
                severity=Severity.ERROR,
                file=e2e_dir,
                line=0,
                rule="Q14.incident-page-needs-e2e",
                message=f"incident-critical page `{page_name}` missing e2e a11y spec",
                suggestion=f"add frontend/e2e/a11y/{page_name.lower()}.spec.ts with injectAxe + checkA11y",
            )


def scan(roots: Iterable[Path], policy_path: Path, pretend_path: str | None) -> int:
    policy = _load_policy(policy_path)
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
        if root.is_file() and root.suffix in SCANNED_EXTS:
            virtual = pretend_path or (str(root.relative_to(REPO_ROOT)) if root.is_relative_to(REPO_ROOT) else root.name)
            files = [(root, virtual)]
        else:
            files = []
            for p in root.rglob("*"):
                if p.is_file() and p.suffix in SCANNED_EXTS:
                    virtual = str(p.relative_to(REPO_ROOT)) if p.is_relative_to(REPO_ROOT) else p.name
                    files.append((p, virtual))
            for finding in _scan_root_invariants(root, policy):
                emit(finding)
                if finding.severity == Severity.ERROR:
                    total_errors += 1
        for path, virtual in files:
            for finding in _scan_file(path, virtual):
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
    roots = tuple(args.target) if args.target else DEFAULT_ROOTS
    return scan(roots, args.policy, args.pretend_path)


if __name__ == "__main__":
    sys.exit(main())
```

### Task 6.7: Run tests, expect green

```bash
python -m pytest tests/harness/checks/test_accessibility_policy.py -v
```

### Task 6.8: Triage live-repo run

```bash
python .harness/checks/accessibility_policy.py
```

Expected hot spots:

- `Q14.img-needs-alt` likely fires on infrastructure-icon `<img>` tags. Triage: add `alt=""` for decorative.
- `Q14.button-needs-accessible-name` may fire on icon-only buttons in War Room. Add `aria-label`.
- `Q14.primitive-needs-axe-test` fires for any UI primitive without a paired test. Write top-3 critical primitive tests; baseline the rest.
- `Q14.incident-page-needs-e2e` fires if `frontend/e2e/a11y/` is empty (likely true after H.0b). File a tracking ticket; defer first spec to a follow-up.

### Task 6.9: Run validate-fast

```bash
python tools/run_validate.py --fast
```

### Task 6.10: Commit green

```bash
git add .harness/checks/accessibility_policy.py
git commit -m "$(cat <<'EOF'
feat(green): H.1b.6 — accessibility_policy enforces Q14

Six rules: eslint-plugin-jsx-a11y at error level; every components/ui/*
primitive needs paired *.test.tsx calling axe(); incident-critical pages
need a Playwright a11y spec calling injectAxe+checkA11y; <img> needs
alt=; <button>/<a> need accessible name; tabIndex > 0 banned. H-25
docstring covers missing/malformed/no-upstream. Auto-discovered.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Story H.1b.7 — `conventions_policy.py` (Q18)

**Rule families enforced (9):**
1. `ruff` exit code on `backend/`, `.harness/`, `tools/` MUST be 0 (wraps the existing ruff invocation, but tags failures with our rule id so the AI can self-correct via H-23 suggestions).
2. `eslint` exit code on `frontend/src/` MUST be 0.
3. `commitlint` (if configured) exit code on the most recent commit MUST be 0 — invoked via `npx commitlint --from HEAD~1 --to HEAD`.
4. Backend file naming: every file under `backend/src/` MUST be lower_snake_case (no `PascalCase.py`, no `kebab-case.py`).
5. Frontend file naming: every file under `frontend/src/components/` ending in `.tsx` MUST be PascalCase; every file under `frontend/src/hooks/` MUST start with `use` and be camelCase (`useFoo.ts`); every directory immediately under `frontend/src/components/` MUST be PascalCase.
6. No `from .module import` (relative import) in any `backend/src/` file.
7. No `import "../../"` paths in `frontend/src/` (must use `@/` alias).
8. No `export default` in `frontend/src/components/` (Q18 iv allows defaults only on pages and config files).
9. No commit subject > 72 chars in the last 20 commits — invoked via `git log --pretty=%s -n 20`.

**Files:**
- Create: `.harness/checks/conventions_policy.py`
- Create: `tests/harness/fixtures/conventions_policy/violation/PascalCase.py`
- Create: `tests/harness/fixtures/conventions_policy/violation/kebab-case.py`
- Create: `tests/harness/fixtures/conventions_policy/violation/lowercase_component.tsx`
- Create: `tests/harness/fixtures/conventions_policy/violation/relative_import.py`
- Create: `tests/harness/fixtures/conventions_policy/violation/dotdot_import.tsx`
- Create: `tests/harness/fixtures/conventions_policy/violation/default_export.tsx`
- Create: `tests/harness/fixtures/conventions_policy/compliant/snake_case_module.py`
- Create: `tests/harness/fixtures/conventions_policy/compliant/PascalCaseComponent.tsx`
- Create: `tests/harness/fixtures/conventions_policy/compliant/named_exports.tsx`
- Create: `tests/harness/checks/test_conventions_policy.py`

### Task 7.1: Create violation fixtures

```bash
mkdir -p tests/harness/fixtures/conventions_policy/{violation,compliant}
```

`violation/PascalCase.py`:

```python
"""Q18 violation — Python file using PascalCase naming.

Pretend-path: backend/src/services/PascalCase.py
"""
def foo() -> None: ...
```

`violation/kebab-case.py`:

```python
"""Q18 violation — Python file using kebab-case naming.

Pretend-path: backend/src/services/kebab-case.py
"""
def foo() -> None: ...
```

`violation/lowercase_component.tsx`:

```tsx
/* Q18 violation — frontend component file not PascalCase.

Pretend-path: frontend/src/components/lowercase.tsx
*/
export const Foo = () => null;
```

`violation/relative_import.py`:

```python
"""Q18 violation — relative import in backend.

Pretend-path: backend/src/services/foo.py
"""
from .helpers import x
```

`violation/dotdot_import.tsx`:

```tsx
/* Q18 violation — ../ import in frontend.

Pretend-path: frontend/src/components/Foo.tsx
*/
import { x } from "../../services/api/client";
```

`violation/default_export.tsx`:

```tsx
/* Q18 violation — default export inside frontend/src/components/.

Pretend-path: frontend/src/components/Foo.tsx
*/
export default function Foo() {
  return null;
}
```

### Task 7.2: Create compliant fixtures

`compliant/snake_case_module.py`:

```python
"""Q18 compliant — lower_snake_case Python file.

Pretend-path: backend/src/services/clean_module.py
"""
def foo() -> None: ...
```

`compliant/PascalCaseComponent.tsx`:

```tsx
/* Q18 compliant — PascalCase component file.

Pretend-path: frontend/src/components/CleanComponent.tsx
*/
export const CleanComponent = () => null;
```

`compliant/named_exports.tsx`:

```tsx
/* Q18 compliant — named exports only.

Pretend-path: frontend/src/components/Bar.tsx
*/
export const Bar = () => null;
export const Baz = () => null;
```

### Task 7.3: Write the failing test

Create `tests/harness/checks/test_conventions_policy.py`:

```python
"""H.1b.7 — conventions_policy check tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness._helpers import assert_check_fires, assert_check_silent

CHECK = "conventions_policy"
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / CHECK


@pytest.mark.parametrize(
    "fixture_name,expected_rule,pretend_path",
    [
        ("PascalCase.py", "Q18.python-snake-case", "backend/src/services/PascalCase.py"),
        ("kebab-case.py", "Q18.python-snake-case", "backend/src/services/kebab-case.py"),
        ("lowercase_component.tsx", "Q18.frontend-component-pascal-case", "frontend/src/components/lowercase.tsx"),
        ("relative_import.py", "Q18.no-relative-import-backend", "backend/src/services/foo.py"),
        ("dotdot_import.tsx", "Q18.no-dotdot-import-frontend", "frontend/src/components/Foo.tsx"),
        ("default_export.tsx", "Q18.no-default-export-in-components", "frontend/src/components/Foo.tsx"),
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
        ("snake_case_module.py", "backend/src/services/clean_module.py"),
        ("PascalCaseComponent.tsx", "frontend/src/components/CleanComponent.tsx"),
        ("named_exports.tsx", "frontend/src/components/Bar.tsx"),
    ],
)
def test_compliant_silent(fixture_name: str, pretend_path: str) -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / fixture_name,
        pretend_path=pretend_path,
    )
```

### Task 7.4: Run failing test + commit red

```bash
python -m pytest tests/harness/checks/test_conventions_policy.py -v
git add tests/harness/fixtures/conventions_policy tests/harness/checks/test_conventions_policy.py
git commit -m "$(cat <<'EOF'
test(red): H.1b.7 — conventions_policy fixtures + assertions

Six violation fixtures (PascalCase + kebab-case Python files; lowercase
component file; relative import in backend; ../../ import in frontend;
default export in frontend/src/components/) plus three compliant
counterparts. Ruff/eslint/commitlint wrappers exercised in the live-repo
triage step (Task 7.7), not in fixture-level tests.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 7.5: Implement the check

Create `.harness/checks/conventions_policy.py`:

```python
#!/usr/bin/env python3
"""Q18 — code conventions (naming + imports + commits).

Nine rules:
  Q18.ruff-clean                       — wraps `ruff check` over backend/.harness/tools.
  Q18.eslint-clean                     — wraps `eslint` over frontend/src.
  Q18.commitlint-clean                 — wraps commitlint over HEAD~1..HEAD if commitlint configured.
  Q18.python-snake-case                — backend/src/*.py files must be lower_snake_case.
  Q18.frontend-component-pascal-case   — frontend/src/components/*.tsx must be PascalCase.
  Q18.frontend-hook-camel-case         — frontend/src/hooks/*.ts(x) must start with `use` + camelCase.
  Q18.no-relative-import-backend       — `from .` banned in backend/src.
  Q18.no-dotdot-import-frontend        — `import … from "../...";` banned in frontend/src.
  Q18.no-default-export-in-components  — `export default` banned under frontend/src/components/.
  Q18.commit-subject-too-long          — git log subject > 72 chars in last 20 commits.

H-25:
  Missing input    — exit 2.
  Malformed input  — WARN harness.unparseable.
  Upstream failed  — when ruff/eslint binary missing, emit WARN and skip
                     (cannot enforce a tool that is not installed).
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from .harness.checks._common import Finding, Severity, emit  # noqa: E402

DEFAULT_ROOTS = (REPO_ROOT,)
EXCLUDE_VIRTUAL_PREFIXES = (
    "tests/harness/fixtures/",
    "frontend/dist/",
    "frontend/node_modules/",
)

SNAKE_CASE_RE = re.compile(r'^[a-z_][a-z0-9_]*$')
PASCAL_CASE_RE = re.compile(r'^[A-Z][A-Za-z0-9]*$')
HOOK_NAME_RE = re.compile(r'^use[A-Z][A-Za-z0-9]*$')
RELATIVE_IMPORT_RE = re.compile(r'^\s*from\s+\.+', re.MULTILINE)
DOTDOT_IMPORT_RE = re.compile(r'''^\s*import\s+[^;]*?\bfrom\s+["']\.\.?/[^"']*["']''', re.MULTILINE)
DEFAULT_EXPORT_RE = re.compile(r'^\s*export\s+default\b', re.MULTILINE)


def _is_excluded(virtual: str) -> bool:
    return any(virtual.startswith(p) for p in EXCLUDE_VIRTUAL_PREFIXES)


def _scan_naming(path: Path, virtual: str) -> Iterable[Finding]:
    name = path.stem  # without extension
    if virtual.startswith("backend/src/") and path.suffix == ".py":
        if not SNAKE_CASE_RE.match(name):
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=1,
                rule="Q18.python-snake-case",
                message=f"`{path.name}` is not lower_snake_case",
                suggestion=f"rename to {re.sub(r'[^a-zA-Z0-9_]+', '_', name).lower()}.py",
            )
    if virtual.startswith("frontend/src/components/") and path.suffix == ".tsx":
        if not PASCAL_CASE_RE.match(name):
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=1,
                rule="Q18.frontend-component-pascal-case",
                message=f"component file `{path.name}` is not PascalCase",
                suggestion=f"rename to {name[:1].upper()}{name[1:]}.tsx",
            )
    if virtual.startswith("frontend/src/hooks/") and path.suffix in {".ts", ".tsx"}:
        if not HOOK_NAME_RE.match(name):
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=1,
                rule="Q18.frontend-hook-camel-case",
                message=f"hook file `{path.name}` does not start with `use` + camelCase",
                suggestion=f"rename to use{name[:1].upper()}{name[1:]}.ts",
            )


def _scan_imports(path: Path, virtual: str, source: str) -> Iterable[Finding]:
    if virtual.startswith("backend/src/") and path.suffix == ".py":
        for m in RELATIVE_IMPORT_RE.finditer(source):
            line = source[:m.start()].count("\n") + 1
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=line,
                rule="Q18.no-relative-import-backend",
                message="relative import (from .x) banned in backend",
                suggestion="use absolute import: from backend.src.<module> import …",
            )
    if virtual.startswith("frontend/src/") and path.suffix in {".ts", ".tsx", ".js", ".jsx"}:
        for m in DOTDOT_IMPORT_RE.finditer(source):
            line = source[:m.start()].count("\n") + 1
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=line,
                rule="Q18.no-dotdot-import-frontend",
                message="`../..` import path banned in frontend",
                suggestion="use the @/ alias (e.g., @/services/api/client)",
            )


def _scan_default_export(path: Path, virtual: str, source: str) -> Iterable[Finding]:
    if not virtual.startswith("frontend/src/components/"):
        return
    for m in DEFAULT_EXPORT_RE.finditer(source):
        line = source[:m.start()].count("\n") + 1
        yield Finding(
            severity=Severity.ERROR,
            file=path,
            line=line,
            rule="Q18.no-default-export-in-components",
            message="`export default` inside frontend/src/components/",
            suggestion="use a named export — `export const Foo = …`",
        )


def _scan_file(path: Path, virtual: str) -> Iterable[Finding]:
    if _is_excluded(virtual):
        return
    yield from _scan_naming(path, virtual)
    if path.suffix in {".py", ".ts", ".tsx", ".js", ".jsx"}:
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return
        yield from _scan_imports(path, virtual, source)
        yield from _scan_default_export(path, virtual, source)


def _wrap_subprocess(label: str, rule: str, cmd: list[str], cwd: Path | None = None) -> Iterable[Finding]:
    if not shutil.which(cmd[0]) and not (cmd[0] == "npx" and shutil.which("node")):
        yield Finding(
            severity=Severity.WARN,
            file=Path(cmd[0]),
            line=0,
            rule=rule,
            message=f"{label}: tool `{cmd[0]}` not installed; skipping",
            suggestion=f"install {cmd[0]} so {rule} can enforce",
        )
        return
    try:
        result = subprocess.run(cmd, cwd=cwd or REPO_ROOT, capture_output=True, text=True, timeout=60)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        yield Finding(
            severity=Severity.WARN,
            file=Path(cmd[0]),
            line=0,
            rule=rule,
            message=f"{label}: subprocess error: {exc}",
            suggestion=f"investigate {cmd[0]} availability",
        )
        return
    if result.returncode != 0:
        first_line = (result.stdout or result.stderr).splitlines()[:1]
        yield Finding(
            severity=Severity.ERROR,
            file=REPO_ROOT,
            line=0,
            rule=rule,
            message=f"{label} failed (exit {result.returncode})",
            suggestion=f"run `{' '.join(cmd)}` and fix the reported issues; first line: {first_line}",
        )


def _wrap_external_tools() -> Iterable[Finding]:
    yield from _wrap_subprocess(
        "ruff", "Q18.ruff-clean",
        ["ruff", "check", "backend/", ".harness/", "tools/"],
    )
    yield from _wrap_subprocess(
        "eslint", "Q18.eslint-clean",
        ["npx", "eslint", "frontend/src/"],
    )
    if (REPO_ROOT / "frontend" / "commitlint.config.js").exists() or (REPO_ROOT / "commitlint.config.js").exists():
        yield from _wrap_subprocess(
            "commitlint", "Q18.commitlint-clean",
            ["npx", "commitlint", "--from", "HEAD~1", "--to", "HEAD"],
        )


def _scan_commit_subjects() -> Iterable[Finding]:
    if not shutil.which("git"):
        return
    try:
        result = subprocess.run(
            ["git", "log", "--pretty=%s", "-n", "20"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return
    for subject in result.stdout.splitlines():
        if len(subject) > 72:
            yield Finding(
                severity=Severity.ERROR,
                file=REPO_ROOT,
                line=0,
                rule="Q18.commit-subject-too-long",
                message=f"commit subject `{subject[:60]}...` is {len(subject)} chars (> 72)",
                suggestion="rewrite subject to ≤ 72 chars; move detail to body",
            )


def scan(roots: Iterable[Path], pretend_path: str | None) -> int:
    total_errors = 0
    # External tool wrappers + commit-subject scan only when scanning the whole repo
    if any(root.is_dir() for root in roots):
        for finding in _wrap_external_tools():
            emit(finding)
            if finding.severity == Severity.ERROR:
                total_errors += 1
        for finding in _scan_commit_subjects():
            emit(finding)
            if finding.severity == Severity.ERROR:
                total_errors += 1

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
        if root.is_file():
            virtual = pretend_path or (str(root.relative_to(REPO_ROOT)) if root.is_relative_to(REPO_ROOT) else root.name)
            files = [(root, virtual)]
        else:
            files = []
            for p in root.rglob("*"):
                if not p.is_file():
                    continue
                virtual = str(p.relative_to(REPO_ROOT)) if p.is_relative_to(REPO_ROOT) else p.name
                files.append((p, virtual))
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

### Task 7.6: Run tests, expect green

```bash
python -m pytest tests/harness/checks/test_conventions_policy.py -v
```

### Task 7.7: Triage live-repo run

```bash
python .harness/checks/conventions_policy.py
```

Expected hot spots:

- `Q18.no-default-export-in-components` may fire on legacy War Room files. Triage: rewrite to named exports; update imports.
- `Q18.no-dotdot-import-frontend` may fire on a few legacy components — refactor to `@/`.
- `Q18.commit-subject-too-long` may fire on historical commits; that's fine — they're frozen. Filter the check to apply only to commits since the harness landing date OR limit to staged-only mode in a follow-up PR.

### Task 7.8: Run validate-fast

```bash
python tools/run_validate.py --fast
```

### Task 7.9: Commit green

```bash
git add .harness/checks/conventions_policy.py
git commit -m "$(cat <<'EOF'
feat(green): H.1b.7 — conventions_policy enforces Q18

Nine rules wrapping ruff/eslint/commitlint plus naming/import/export
discipline (Python snake_case; component PascalCase; hook camelCase
starting with `use`; no relative imports backend; no ../ imports
frontend; no default exports in components/; commit subject ≤ 72 chars).
Subprocess wrappers degrade to WARN if tool missing (H-25 upstream).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 7.10: Verify discovery

```bash
python tools/run_validate.py --fast 2>&1 | grep "check:conventions_policy"
```

---

# Story H.1b.8 — `output_format_conformance.py` (H-16/H-23)

**Rule families enforced (1):** Every other check's stdout MUST match the binding output shape `[SEVERITY] file=… rule=… message="…" suggestion="…"`. The check operates as a meta-validator — it runs each `.harness/checks/*.py` against its own *violation* fixture, captures stdout, and asserts every non-blank, non-comment line matches the regex.

**Files:**
- Create: `.harness/checks/output_format_conformance.py`
- Create: `tests/harness/fixtures/output_format_conformance/violation/bad_output_check.py`
- Create: `tests/harness/fixtures/output_format_conformance/compliant/good_output_check.py`
- Create: `tests/harness/checks/test_output_format_conformance.py`

### Task 8.1: Create fixtures (synthetic checks)

```bash
mkdir -p tests/harness/fixtures/output_format_conformance/{violation,compliant}
```

`violation/bad_output_check.py`:

```python
#!/usr/bin/env python3
"""Synthetic check that emits non-conforming output (for the meta-validator)."""
import sys

print("Something is wrong somewhere")  # NOT in [SEVERITY] file=… shape
sys.exit(1)
```

`compliant/good_output_check.py`:

```python
#!/usr/bin/env python3
"""Synthetic check that emits conforming output."""
import sys

print('[ERROR] file=tests/harness/fixtures/x.py:1 rule=demo.bad message="bad" suggestion="fix it"')
sys.exit(1)
```

### Task 8.2: Test

Create `tests/harness/checks/test_output_format_conformance.py`:

```python
"""H.1b.8 — output_format_conformance check tests."""

from __future__ import annotations

from pathlib import Path

from tests.harness._helpers import assert_check_fires, assert_check_silent

CHECK = "output_format_conformance"
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / CHECK


def test_violation_fires() -> None:
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / "bad_output_check.py",
        expected_rule="H16.output-format-violation",
    )


def test_compliant_silent() -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / "good_output_check.py",
    )
```

### Task 8.3: Red commit

```bash
python -m pytest tests/harness/checks/test_output_format_conformance.py -v
git add tests/harness/fixtures/output_format_conformance tests/harness/checks/test_output_format_conformance.py
git commit -m "$(cat <<'EOF'
test(red): H.1b.8 — output_format_conformance fixtures + assertions

Two synthetic checks: bad_output_check emits a free-form line;
good_output_check emits a properly-shaped finding.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 8.4: Implement the check

Create `.harness/checks/output_format_conformance.py`:

```python
#!/usr/bin/env python3
"""H-16/H-23 — every check's stdout must match the binding output shape.

One rule:
  H16.output-format-violation — non-blank stdout line that does not match
                                 `^\\[(ERROR|WARN|INFO)\\] file=.+ rule=.+ message=".+" suggestion=".+"$`
                                 (with a small allowance for VALIDATE_SUMMARY/orchestrator chatter).

Mode of operation:
  * If --target is a single .py file: run that file as a check, capture stdout, validate.
  * If --target is a directory: run every .harness/checks/*.py inside it (skipping _common.py).

H-25:
  Missing input    — exit 2 if --target absent.
  Malformed input  — WARN harness.unparseable; skip.
  Upstream failed  — when a check's subprocess itself errors, emit ERROR
                     rule=H16.subprocess-error.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from .harness.checks._common import Finding, Severity, emit  # noqa: E402

DEFAULT_TARGET = REPO_ROOT / ".harness" / "checks"

OUTPUT_LINE_RE = re.compile(
    r'^\[(ERROR|WARN|INFO)\]\s+file=\S+\s+rule=\S+\s+message="[^"]*"\s+suggestion="[^"]*"$'
)
ALLOWLIST_PREFIXES = (
    "[VALIDATE]", "[INFO]", "VALIDATE_SUMMARY", "Traceback",
)


def _line_is_conforming(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if stripped.startswith(ALLOWLIST_PREFIXES):
        return True
    return bool(OUTPUT_LINE_RE.match(stripped))


def _run_check(check: Path, fixture: Path | None) -> tuple[int, str, str]:
    cmd = [sys.executable, str(check)]
    if fixture is not None:
        cmd.extend(["--target", str(fixture)])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return 99, "", str(exc)
    return result.returncode, result.stdout, result.stderr


def _validate(check: Path) -> Iterable[Finding]:
    fixture = _find_violation_fixture(check)
    rc, stdout, stderr = _run_check(check, fixture)
    if rc == 99:
        yield Finding(
            severity=Severity.ERROR,
            file=check,
            line=0,
            rule="H16.subprocess-error",
            message=f"could not invoke {check.name}: {stderr.strip()[:200]}",
            suggestion="check that the script is executable and importable",
        )
        return
    for lineno, line in enumerate(stdout.splitlines(), 1):
        if not _line_is_conforming(line):
            yield Finding(
                severity=Severity.ERROR,
                file=check,
                line=lineno,
                rule="H16.output-format-violation",
                message=f"non-conforming output line: {line[:80]}",
                suggestion='emit `[SEVERITY] file=… rule=… message="…" suggestion="…"`',
            )


def _find_violation_fixture(check: Path) -> Path | None:
    """Find a per-check violation fixture under tests/harness/fixtures/<rule>/violation/."""
    rule = check.stem
    fixture_dir = REPO_ROOT / "tests" / "harness" / "fixtures" / rule / "violation"
    if not fixture_dir.exists():
        return None
    candidates = sorted(p for p in fixture_dir.iterdir() if p.is_file())
    return candidates[0] if candidates else None


def scan(target: Path) -> int:
    if not target.exists():
        emit(Finding(
            severity=Severity.ERROR,
            file=target,
            line=0,
            rule="harness.target-missing",
            message=f"target does not exist: {target}",
            suggestion="pass an existing .py check or .harness/checks/ directory",
        ))
        return 2
    total_errors = 0
    if target.is_file() and target.suffix == ".py":
        checks = [target]
    elif target.is_dir():
        checks = sorted(
            p for p in target.glob("*.py")
            if p.name not in {"__init__.py", "_common.py", "output_format_conformance.py"}
        )
    else:
        emit(Finding(
            severity=Severity.ERROR,
            file=target,
            line=0,
            rule="harness.target-missing",
            message=f"unsupported target: {target}",
            suggestion="pass a Python file or .harness/checks/ directory",
        ))
        return 2
    for check in checks:
        for finding in _validate(check):
            emit(finding)
            if finding.severity == Severity.ERROR:
                total_errors += 1
    return 1 if total_errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    args = parser.parse_args(argv)
    return scan(args.target)


if __name__ == "__main__":
    sys.exit(main())
```

### Task 8.5: Run tests, expect green; run live; validate-fast

```bash
python -m pytest tests/harness/checks/test_output_format_conformance.py -v
python .harness/checks/output_format_conformance.py
python tools/run_validate.py --fast
```

If the live run fires `H16.output-format-violation` on any sibling check, fix the offending check's output (highest priority — this is the conformance gate).

### Task 8.6: Commit green

```bash
git add .harness/checks/output_format_conformance.py
git commit -m "$(cat <<'EOF'
feat(green): H.1b.8 — output_format_conformance enforces H-16/H-23

Meta-validator runs every other .harness/checks/*.py against its own
violation fixture, captures stdout, and ensures each non-blank line
matches the binding finding shape (or an allowlisted orchestrator
prefix). Errors out non-zero with H16.output-format-violation when a
check goes off-format. H-25 covers missing/malformed targets and
subprocess-failure (H16.subprocess-error).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## End-of-sprint acceptance verification

Run from the repo root:

```bash
# 1. All H.1b check tests pass.
python -m pytest tests/harness/checks/ -v

# 2. validate-fast picks up all eight new checks (plus the ten from H.1a).
python tools/run_validate.py --fast 2>&1 | grep -E "check:(frontend_style_system|frontend_data_layer|frontend_ui_primitives|frontend_testing|frontend_routing|accessibility_policy|conventions_policy|output_format_conformance)" | wc -l
# Expected: 8

# 3. validate-fast finishes under 30s.
time python tools/run_validate.py --fast
# Expected: real time < 30s.

# 4. Each check ships paired fixtures.
ls tests/harness/fixtures/ | sort | grep -E "^(frontend_|accessibility|conventions|output_format)"
# Expected (at minimum):
#   accessibility_policy conventions_policy frontend_data_layer
#   frontend_routing frontend_style_system frontend_testing
#   frontend_ui_primitives output_format_conformance

# 5. Every violation fixture produces ≥ 1 ERROR.
for d in tests/harness/fixtures/*/violation; do
  rule_dir=$(basename $(dirname $d))
  for f in $d/*; do
    [ -f $f ] || continue
    out=$(python .harness/checks/${rule_dir}.py --target $f 2>/dev/null)
    echo "$out" | grep -q "^\[ERROR\]" || echo "FAIL: $f did not fire ERROR"
  done
done
# Expected: no FAIL output.

# 6. H-25 docstrings present on every new check.
for f in .harness/checks/{frontend_style_system,frontend_data_layer,frontend_ui_primitives,frontend_testing,frontend_routing,accessibility_policy,conventions_policy,output_format_conformance}.py; do
  grep -q "Missing input" $f || echo "MISSING H-25 docstring: $f"
done
# Expected: no MISSING output.

# 7. Output format conformance — meta-validator clean.
python .harness/checks/output_format_conformance.py
# Expected: exit 0 (or only emits H16.subprocess-error for genuinely missing fixtures).
```

---

## Definition of Done — Sprint H.1b

- [ ] All 8 stories' tests pass under `pytest tests/harness/checks/ -v`.
- [ ] All 8 checks discovered by `tools/run_validate.py --fast`.
- [ ] `validate-fast` total wall time < 30s (with H.1a + H.1b combined: 18 checks now firing).
- [ ] Every check has paired violation + compliant fixtures (H-24).
- [ ] Every check's docstring covers the three H-25 questions.
- [ ] `output_format_conformance.py` runs clean against every sibling check (H-16/H-23 binding).
- [ ] Live-repo runs triaged: each check either reports zero ERROR on the live repo, OR documented baseline entries exist (deferred to H.1d.1) with a tracking issue per baselined finding.
- [ ] Each story committed as red → green pair with the canonical commit message shape.
- [ ] Tree-sitter dev deps added to `.harness/dependencies.yaml.python.allowed` (NOT spine).

---

**Plan complete and saved to `docs/plans/2026-04-26-harness-sprint-h1b-tasks.md`.**

Two execution options:

1. **Subagent-Driven (this session)** — I dispatch fresh subagent per task, review between tasks, fast iteration.
2. **Parallel Session (separate)** — Open new session with `executing-plans`, batch execution with checkpoints.

Or **hold** and confirm before I author Sprint H.1c.
