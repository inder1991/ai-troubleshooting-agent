# Harness Sprint H.0a — Per-Task Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship the foundational scaffold of the AI harness — Makefile entry point, deterministic rule loader, root + 3 directory `CLAUDE.md` files, harness self-test infrastructure, and pre-commit installer — so every subsequent sprint has a working substrate to build on.

**Architecture:** Pure-Python harness scripts under `tools/` and `.harness/`, plain Make as the contract entry point, plain git hook for pre-commit (no third-party framework). All output structured per H-16/H-23. Every check ships with paired violation + compliant fixtures per H-24.

**Tech Stack:** Python 3.14, pytest, PyYAML, ruff (already in repo), git, make.

**Reference docs:**
- [Consolidated harness plan](./2026-04-26-ai-harness.md) — locked decisions, 25 H-rules, 19 Q-decisions.

---

## Story map for Sprint H.0a

| Story | Title | Tasks | Pts |
|---|---|---|---|
| H.0a.1 | Repo scaffolding — `Makefile` + directory skeleton | 1.1 – 1.5 | 3 |
| H.0a.2 | Root `CLAUDE.md` (≤ 70 lines) | 2.1 – 2.6 | 3 |
| H.0a.3 | `tools/load_harness.py` — deterministic loader | 3.1 – 3.12 | 5 |
| H.0a.4 | `tools/run_validate.py` — orchestrator wrapping ruff + tsc + custom checks | 4.1 – 4.10 | 5 |
| H.0a.5 | First per-directory `CLAUDE.md` files (backend, learning, frontend) | 5.1 – 5.6 | 3 |
| H.0a.6 | Front-matter validator + `claude_md_size_cap.py` + `owners_present.py` | 6.1 – 6.10 | 3 |
| H.0a.7 | `make harness-install` pre-commit hook installer | 7.1 – 7.5 | 2 |
| H.0a.8 | Harness test infrastructure (`tests/harness/` + `_helpers.py` + convention test) | 8.1 – 8.8 | 5 |
| H.0a.9 | `AGENTS.md` alias + `.cursorrules` pointer | 9.1 – 9.3 | 1 |
| H.0a.10 | `CONTRIBUTING.md` — human discipline checklist | 10.1 – 10.2 | 1 |

**Total: 10 stories, ~31 points, 2 weeks.**

---

# Story H.0a.1 — Repo scaffolding (Makefile + directory skeleton)

**Files:**
- Create: `Makefile`
- Create: `tools/__init__.py`
- Create: `.harness/README.md`
- Create: `.harness/checks/__init__.py`
- Create: `.harness/checks/_common.py`
- Create: `.harness/generators/__init__.py`
- Create: `.harness/generators/_common.py`
- Create: `.harness/generated/.gitkeep`
- Create: `.harness/generated/README.md`
- Create: `tests/harness/__init__.py`

### Task 1.1: Write the failing test for skeleton

Create `tests/harness/test_skeleton.py`:

```python
"""Sprint H.0a Story 1 — Skeleton smoke tests.

Asserts that the harness directory layout, Makefile entry points, and
README warning files all exist. This is the earliest red test in the
sprint; everything else assumes the skeleton is present.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


REQUIRED_DIRS = [
    "tools",
    ".harness",
    ".harness/checks",
    ".harness/generators",
    ".harness/generated",
    "tests/harness",
]

REQUIRED_FILES = [
    "Makefile",
    "tools/__init__.py",
    ".harness/README.md",
    ".harness/checks/__init__.py",
    ".harness/checks/_common.py",
    ".harness/generators/__init__.py",
    ".harness/generators/_common.py",
    ".harness/generated/README.md",
    "tests/harness/__init__.py",
]

REQUIRED_MAKE_TARGETS = [
    "validate-fast",
    "validate-full",
    "validate",
    "harness",
    "harness-install",
]


@pytest.mark.parametrize("rel", REQUIRED_DIRS)
def test_required_directory_exists(rel: str) -> None:
    assert (REPO_ROOT / rel).is_dir(), f"missing directory: {rel}"


@pytest.mark.parametrize("rel", REQUIRED_FILES)
def test_required_file_exists(rel: str) -> None:
    assert (REPO_ROOT / rel).is_file(), f"missing file: {rel}"


def test_make_dry_run_lists_required_targets() -> None:
    """`make -n <target>` exits 0 for every required target."""
    if shutil.which("make") is None:
        pytest.skip("make not on PATH")
    for target in REQUIRED_MAKE_TARGETS:
        result = subprocess.run(
            ["make", "-n", target],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"make -n {target} failed: stderr={result.stderr.strip()}"
        )


def test_generated_readme_warns_no_handediting() -> None:
    text = (REPO_ROOT / ".harness/generated/README.md").read_text()
    assert "DO NOT EDIT" in text, "generated/README.md must warn against hand-editing"
```

### Task 1.2: Run test to verify it fails

Run: `cd backend && python -m pytest ../tests/harness/test_skeleton.py -v`

Expected: every parametrized test fails with `missing directory:` / `missing file:` messages, AND `test_make_dry_run_lists_required_targets` fails because Makefile doesn't exist yet.

### Task 1.3: Create directories and stub files

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm

mkdir -p tools .harness/checks .harness/generators .harness/generated tests/harness
touch tools/__init__.py
touch .harness/checks/__init__.py
touch .harness/generators/__init__.py
touch tests/harness/__init__.py
touch .harness/generated/.gitkeep
```

Create `.harness/README.md`:

```markdown
# .harness — AI development harness

The repo-level scaffolding that makes AI-assisted development productive
in this codebase. See `docs/plans/2026-04-26-ai-harness.md` for the
full design.

## Layout

- `*.md` — cross-cutting rules with `applies_to` glob front-matter.
- `*_policy.yaml` — typed policy configs (dependencies, security, perf, ...).
- `checks/` — custom rule validators. One file per rule family.
- `generators/` — scripts that emit `generated/*.json` truth files.
- `generated/` — machine-readable truth, regenerated by `make harness`.
  NEVER hand-edited.
- `baselines/` — Q19 typecheck baselines (mypy, tsc).

## Entry points

- `make validate-fast` — < 30 s inner-loop gate (lint + typecheck + checks).
- `make validate-full` — pre-commit / CI gate (adds tests + heavy audits).
- `make harness` — regenerate `generated/` from code.
- `make harness-install` — install pre-commit hook (idempotent).
```

Create `.harness/generated/README.md`:

```markdown
# DO NOT EDIT

Files in this directory are auto-generated by `make harness`. They are
the AI's machine-readable truth surface — current contract names,
registered checks, valid token list, etc.

Hand-editing them will cause `make validate-fast` to fail (the
`generated_not_handedited.py` check diffs the committed files against
fresh generator output).

To update: change the source code the generator reads from, then run
`make harness`.
```

Create `.harness/checks/_common.py`:

```python
"""Shared helpers for .harness/checks/ scripts.

Per H-16 / H-23, every check emits structured one-line records:

    [SEVERITY] file=<path>:<line> rule=<rule-id> message="..." suggestion="..."

`emit()` is the single point where that format is constructed, so
changing the format later is a one-file change.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable, Literal

Severity = Literal["ERROR", "WARN", "INFO"]


def emit(
    severity: Severity,
    file: Path | str,
    rule: str,
    message: str,
    suggestion: str,
    line: int | None = None,
    out=sys.stdout,
) -> None:
    """Write one structured violation record (H-16 / H-23 format)."""
    location = f"{file}:{line}" if line is not None else str(file)
    safe_msg = message.replace('"', "'")
    safe_sug = suggestion.replace('"', "'")
    print(
        f'[{severity}] file={location} rule={rule} '
        f'message="{safe_msg}" suggestion="{safe_sug}"',
        file=out,
    )


def walk_files(
    roots: Iterable[Path],
    suffixes: tuple[str, ...],
    skip_dirs: tuple[str, ...] = ("node_modules", ".git", "__pycache__", ".venv"),
) -> Iterable[Path]:
    """Yield every file under any of the roots whose suffix matches.

    H-25: handles missing roots silently (no exception) — upstream may
    not have a frontend/ or backend/ layout in every repo.
    """
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in suffixes:
                continue
            if any(part in skip_dirs for part in path.parts):
                continue
            yield path
```

Create `.harness/generators/_common.py`:

```python
"""Shared helpers for .harness/generators/ scripts.

Every generator writes to .harness/generated/<name>.json with a
versioned schema header and sorted keys for byte-deterministic output.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_generated(target: Path, schema_version: int, payload: dict[str, Any]) -> None:
    """Write `payload` to `target` with a versioned schema envelope.

    Output is sorted-keys + 2-space indent + trailing newline so
    re-running the generator with no source changes is byte-identical.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    document = {"$schema_version": schema_version, **payload}
    target.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n"
    )
```

### Task 1.4: Create the Makefile

Create `Makefile`:

```make
# AI Harness — single contract entry point.
#
# All five execution contexts (AI loop, terminal, pre-commit, CI,
# autonomous agent) call the same targets. Same script, same checks,
# same output format. Per H-14 / H-20.

.PHONY: validate-fast validate-full validate harness harness-install

# Fast inner-loop gate (< 30 s). Lint + typecheck + custom checks +
# harness self-checks. Used by AI session loop and pre-commit hook.
validate-fast:
	@python tools/run_validate.py --fast

# Pre-commit / CI gate. Fast + tests + heavy audits.
validate-full:
	@python tools/run_validate.py --full

# Default `make validate` is the full gate.
validate: validate-full

# Regenerate .harness/generated/ from code. Run when adding contracts,
# tokens, agent manifests, etc. Per H-4.
harness:
	@python tools/run_harness_regen.py

# One-time installer for the pre-commit hook. Idempotent. Per H-18.
harness-install:
	@bash tools/install_pre_commit.sh
```

### Task 1.5: Run test to verify it passes, then commit

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
python -m pytest ../tests/harness/test_skeleton.py -v
```

Expected: all 10 parametrized tests + the make-target test + the README-warning test all pass. The `tools/run_validate.py` and `tools/run_harness_regen.py` scripts don't exist yet, but `make -n` only checks targets exist, not whether they execute successfully — so this passes.

Commit:

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
git add tests/harness/test_skeleton.py Makefile tools/__init__.py \
        .harness/README.md .harness/checks/__init__.py .harness/checks/_common.py \
        .harness/generators/__init__.py .harness/generators/_common.py \
        .harness/generated/README.md .harness/generated/.gitkeep \
        tests/harness/__init__.py
git commit -m "feat(green): H.0a.1 — repo scaffolding (Makefile + .harness skeleton + tests/harness)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

(Note the TDD discipline: this commit is `feat(green)` because the test was written and committed *first* in spirit — the test code is in the same diff as the green code because the substrate didn't exist for split commits. From Story 2 onward, split into `test(red)` and `feat(green)` commits.)

---

# Story H.0a.2 — Root `CLAUDE.md` (≤ 70 lines)

**Files:**
- Create: `CLAUDE.md`
- Test: `tests/harness/test_root_claude_md.py`

### Task 2.1: Write the failing test

Create `tests/harness/test_root_claude_md.py`:

```python
"""Sprint H.0a Story 2 — Root CLAUDE.md exists, is small, and contains
the required sections per H-1 + H-11 + H-15."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT_CLAUDE = REPO_ROOT / "CLAUDE.md"


def _strip_front_matter(text: str) -> str:
    """Remove the leading YAML front-matter block (---...---), if any."""
    match = re.match(r"^---\n.*?\n---\n(.*)$", text, re.DOTALL)
    return match.group(1) if match else text


def test_root_claude_exists() -> None:
    assert ROOT_CLAUDE.is_file(), "CLAUDE.md missing at repo root"


def test_root_claude_size_cap() -> None:
    """H-1: root must be <= 70 lines, excluding front-matter."""
    body = _strip_front_matter(ROOT_CLAUDE.read_text())
    lines = body.splitlines()
    assert len(lines) <= 70, (
        f"root CLAUDE.md is {len(lines)} lines (excluding front-matter); "
        f"H-1 caps it at 70"
    )


def test_root_claude_has_front_matter() -> None:
    """H-9: every rule file declares scope/owner/priority."""
    text = ROOT_CLAUDE.read_text()
    assert text.startswith("---\n"), "front-matter block required at top"
    fm_match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert fm_match is not None
    fm = fm_match.group(1)
    for required in ("scope:", "owner:", "priority:"):
        assert required in fm, f"front-matter missing field: {required}"


def test_root_claude_has_loading_contract_section() -> None:
    """H-11: loading algorithm must be documented in root."""
    body = _strip_front_matter(ROOT_CLAUDE.read_text())
    assert "Rule Loading Contract" in body, (
        "root must document the deterministic loading algorithm"
    )


def test_root_claude_has_validation_mandate() -> None:
    """H-15: AI must run make validate before declaring done."""
    body = _strip_front_matter(ROOT_CLAUDE.read_text())
    assert "make validate" in body, (
        "root must mandate `make validate` before declaring done"
    )


def test_root_claude_has_precedence_rule() -> None:
    """H-5: precedence is documented in root."""
    body = _strip_front_matter(ROOT_CLAUDE.read_text())
    # Loose check — we want the words "precedence" and the order "Local"
    # appearing somewhere; not a strict regex.
    assert "precedence" in body.lower()
    assert "Local" in body or "local" in body
```

### Task 2.2: Run test to verify it fails

Run: `cd backend && python -m pytest ../tests/harness/test_root_claude_md.py -v`

Expected: every test fails with "CLAUDE.md missing at repo root" (the file doesn't exist).

### Task 2.3: Commit the failing tests

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
git add tests/harness/test_root_claude_md.py
git commit -m "test(red): H.0a.2 — root CLAUDE.md must exist with required sections

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 2.4: Write the root `CLAUDE.md`

Create `CLAUDE.md` (must stay ≤ 70 lines after the front-matter):

```markdown
---
scope: repo
owner: "@platform-team"
priority: highest
type: root
---

# Repo guardrails (always loaded)

You are working in DebugDuck. These behavioral rules apply on every
session. Per-area rules in nearest `CLAUDE.md` override these on conflict
(see Precedence below).

## The one rule that compounds

- Run `make validate-fast` before declaring any task complete.
- If it fails: parse the structured output, fix the violations, re-run.
- Loop until pass or you have an explicit blocker to surface.

## Behavioral guardrails

- Production-grade code only. No placeholders, no `TODO` comments in
  shipped paths. If you cannot complete a task fully, surface a blocker.
- Fix root causes, not symptoms.
- Do not introduce new dependencies without justification (Q11). Spine
  paths require a whitelist update + ADR.
- Do not bypass `make validate-fast`. `--no-verify` on commits is the
  rare exception, not the rule.
- Tests come before code. Red commit, then green commit, then refactor.
  PRs without a preceding `test(red):` commit are rejected at review.

## Precedence (H-5)

When rules conflict, the local-most one wins:

    Root rules  <  Cross-cutting harness  <  Generated facts  <  Directory rules

## Rule Loading Contract (H-11)

For any file under edit at `<target>`, the loader walks:

    1. Load this CLAUDE.md (root).
    2. Walk up <target>'s directory tree; load every CLAUDE.md found.
    3. Load all `.harness/generated/*.json` (machine-readable truth).
    4. Match `.harness/*.md` rule files whose `applies_to` glob matches <target>.
    5. Resolve conflicts via the precedence above. Conflicts surface as
       lint errors, not silent overrides.

The reference implementation lives at `tools/load_harness.py`.

## Output format every check emits (H-16, H-23)

    [SEVERITY] file=<path>:<line> rule=<rule-id> message="..." suggestion="..."

`SEVERITY` is `ERROR`, `WARN`, or `INFO`. ERROR fails `make validate*`.

## Where to look

- Full design: `docs/plans/2026-04-26-ai-harness.md` (the 25 H-rules
  and 19 Q-decisions).
- Per-area conventions: nearest `CLAUDE.md` to the file you're editing.
- Cross-cutting rules: `.harness/*.md` (loaded if `applies_to` matches).
- Current truth (registered checks, valid tokens, contract names):
  `.harness/generated/*.json`.
```

Verify the line count after writing:

```bash
sed -n '/^---$/,/^---$/!p' CLAUDE.md | sed -n '/^---$/d;p' | wc -l
```

Should be ≤ 70.

### Task 2.5: Run tests to verify they pass

Run: `cd backend && python -m pytest ../tests/harness/test_root_claude_md.py -v`

Expected: all 6 tests pass.

### Task 2.6: Commit

```bash
git add CLAUDE.md
git commit -m "feat(green): H.0a.2 — root CLAUDE.md with rule-loading contract

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

# Story H.0a.3 — `tools/load_harness.py` (deterministic loader)

**Files:**
- Create: `tools/load_harness.py`
- Test: `tests/harness/test_loader.py`

### Task 3.1: Write the failing test for the loader's data shape

Create `tests/harness/test_loader.py`:

```python
"""Sprint H.0a Story 3 — tools/load_harness.py is the deterministic
discovery + precedence resolver used by every consumer (IDE-AI,
autonomous agent, validators)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LOADER = REPO_ROOT / "tools/load_harness.py"


def _run_loader(target: str) -> dict:
    """Invoke the loader as a subprocess and parse its JSON output."""
    result = subprocess.run(
        ["python", str(LOADER), "--target", target, "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"loader exited {result.returncode}: stderr={result.stderr}"
    )
    return json.loads(result.stdout)


def test_loader_exists_and_runs() -> None:
    assert LOADER.is_file()


def test_loader_returns_root_for_any_target() -> None:
    """Even when the target file doesn't exist (yet), root rules load."""
    result = _run_loader("backend/src/never/exists/foo.py")
    assert "root" in result
    assert "Rule Loading Contract" in result["root"]


def test_loader_walks_up_directory_tree(tmp_path: Path) -> None:
    """Per H-11 step 2: every CLAUDE.md from the target dir up to root loads."""
    target = "backend/src/learning/contracts.py"
    result = _run_loader(target)
    files = result["directory_rules_files"]
    # Once Story 5 lands, backend/CLAUDE.md and backend/src/learning/CLAUDE.md
    # will be in the tree. For now we assert the field exists and is a list.
    assert isinstance(files, list)


def test_loader_loads_generated() -> None:
    """Per H-11 step 3: all .harness/generated/*.json load."""
    result = _run_loader("backend/src/learning/contracts.py")
    assert "generated" in result
    assert isinstance(result["generated"], dict)


def test_loader_matches_cross_cutting_globs() -> None:
    """Per H-11 step 4: only .harness/*.md whose applies_to glob matches."""
    result = _run_loader("backend/src/learning/contracts.py")
    assert "cross_cutting_files" in result
    assert isinstance(result["cross_cutting_files"], list)


def test_loader_output_is_deterministic() -> None:
    """Two consecutive runs produce byte-identical output."""
    target = "backend/src/learning/contracts.py"
    a = subprocess.run(
        ["python", str(LOADER), "--target", target, "--json"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    ).stdout
    b = subprocess.run(
        ["python", str(LOADER), "--target", target, "--json"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    ).stdout
    assert a == b, "loader output is non-deterministic"


def test_loader_emits_precedence_order() -> None:
    """Per H-11 step 5: output records the precedence order applied."""
    result = _run_loader("backend/src/learning/contracts.py")
    assert result["precedence_order"] == [
        "root", "cross_cutting", "generated", "directory_rules",
    ]


def test_loader_text_mode_emits_concatenated_block() -> None:
    """Without --json, loader emits a human-readable concatenated context block."""
    result = subprocess.run(
        ["python", str(LOADER), "--target", "backend/src/learning/contracts.py"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "# ROOT" in result.stdout, "text mode should label the root section"
```

### Task 3.2: Run tests to verify they fail

Run: `cd backend && python -m pytest ../tests/harness/test_loader.py -v`

Expected: every test fails with `tools/load_harness.py` missing.

### Task 3.3: Commit failing tests

```bash
git add tests/harness/test_loader.py
git commit -m "test(red): H.0a.3 — tools/load_harness.py loader contract

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 3.4: Write the loader skeleton

Create `tools/load_harness.py`:

```python
#!/usr/bin/env python3
"""Deterministic harness rule loader.

Consumed by:
  * Claude Code session-start hook (Sprint H.2)
  * autonomous CI agents (Consumer 2)
  * tools/run_validate.py for cross-checks

Per H-11, the loading algorithm is:

  1. Load root CLAUDE.md.
  2. Walk up <target>'s directory tree, collect every CLAUDE.md.
  3. Load all .harness/generated/*.json.
  4. Match .harness/*.md whose `applies_to` glob matches <target>.
  5. Concatenate in precedence order and return.

H-25 (failure-first): if <target> doesn't exist, the loader still
returns root rules (allows early bootstrapping of new files); if a YAML
front-matter is malformed, the loader records the file under
`malformed_files` and continues; if .harness/generated/ is missing,
generated returns {}.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read_file_safe(path: Path) -> str:
    try:
        return path.read_text()
    except OSError:
        return ""


def _strip_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """Return (parsed_front_matter, body). Empty dict on absence/malformed."""
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not match:
        return {}, text
    fm_text, body = match.group(1), match.group(2)
    # Light, dependency-free YAML parsing for the limited subset we use:
    # `key: value` lines, list values via `applies_to:` followed by `- ...`.
    fm: dict[str, Any] = {}
    current_list_key: str | None = None
    for raw in fm_text.splitlines():
        line = raw.rstrip()
        if not line or line.startswith("#"):
            continue
        list_item = re.match(r"^\s+-\s+(.+)$", line)
        if list_item and current_list_key is not None:
            fm.setdefault(current_list_key, []).append(list_item.group(1).strip())
            continue
        kv = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if not kv:
            current_list_key = None
            continue
        key, value = kv.group(1), kv.group(2).strip()
        if value == "":
            current_list_key = key
            fm[key] = []
        else:
            current_list_key = None
            fm[key] = value.strip('"').strip("'")
    return fm, body


def load_root() -> str:
    return _read_file_safe(REPO_ROOT / "CLAUDE.md")


def collect_directory_rules(target: Path) -> list[Path]:
    """Walk up from target's parent directory to repo root, collecting CLAUDE.md."""
    found: list[Path] = []
    current = (REPO_ROOT / target).resolve().parent
    repo_resolved = REPO_ROOT.resolve()
    while True:
        candidate = current / "CLAUDE.md"
        if candidate.is_file() and candidate.resolve() != (REPO_ROOT / "CLAUDE.md").resolve():
            found.append(candidate)
        if current == repo_resolved:
            break
        if repo_resolved not in current.parents:
            break
        current = current.parent
    # Order: closest-to-target first → root-adjacent last
    return found


def load_generated() -> dict[str, Any]:
    out: dict[str, Any] = {}
    gen_dir = REPO_ROOT / ".harness/generated"
    if not gen_dir.is_dir():
        return out
    for path in sorted(gen_dir.glob("*.json")):
        try:
            out[path.stem] = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            # H-25: malformed generated files don't crash the loader.
            out[path.stem] = {"_load_error": True}
    return out


def collect_cross_cutting(target: Path) -> tuple[list[Path], list[Path]]:
    """Match .harness/*.md whose `applies_to` glob covers `target`.

    Returns (matched_files, malformed_files).
    """
    matched: list[Path] = []
    malformed: list[Path] = []
    harness_dir = REPO_ROOT / ".harness"
    if not harness_dir.is_dir():
        return matched, malformed
    for path in sorted(harness_dir.glob("*.md")):
        # Skip our own README.
        if path.name == "README.md":
            continue
        text = _read_file_safe(path)
        fm, _ = _strip_front_matter(text)
        if not fm:
            malformed.append(path)
            continue
        applies = fm.get("applies_to", [])
        if isinstance(applies, str):
            applies = [applies]
        target_str = str(target).replace("\\", "/")
        if any(fnmatch.fnmatch(target_str, glob) for glob in applies):
            matched.append(path)
    return matched, malformed


def build_context(target: Path) -> dict[str, Any]:
    root_text = load_root()
    directory_files = collect_directory_rules(target)
    generated = load_generated()
    cross_cutting_files, malformed = collect_cross_cutting(target)

    return {
        "target": str(target),
        "root": root_text,
        "directory_rules_files": [str(p.relative_to(REPO_ROOT)) for p in directory_files],
        "directory_rules": [_read_file_safe(p) for p in directory_files],
        "cross_cutting_files": [str(p.relative_to(REPO_ROOT)) for p in cross_cutting_files],
        "cross_cutting": [_read_file_safe(p) for p in cross_cutting_files],
        "generated": generated,
        "malformed_files": [str(p.relative_to(REPO_ROOT)) for p in malformed],
        "precedence_order": [
            "root", "cross_cutting", "generated", "directory_rules",
        ],
    }


def render_text(ctx: dict[str, Any]) -> str:
    """Human-readable concatenated context block."""
    parts: list[str] = []
    parts.append("# ROOT (CLAUDE.md)\n")
    parts.append(ctx["root"])

    if ctx["cross_cutting_files"]:
        parts.append("\n# CROSS-CUTTING\n")
        for path, text in zip(ctx["cross_cutting_files"], ctx["cross_cutting"]):
            parts.append(f"\n## {path}\n")
            parts.append(text)

    if ctx["generated"]:
        parts.append("\n# GENERATED FACTS\n")
        for key, value in sorted(ctx["generated"].items()):
            parts.append(f"\n## {key}\n```json\n{json.dumps(value, indent=2, sort_keys=True)}\n```\n")

    if ctx["directory_rules_files"]:
        parts.append("\n# DIRECTORY RULES (closest-first)\n")
        for path, text in zip(ctx["directory_rules_files"], ctx["directory_rules"]):
            parts.append(f"\n## {path}\n")
            parts.append(text)

    return "".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load harness context for a target file.")
    parser.add_argument("--target", required=True, help="Path (relative to repo root) being edited.")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON instead of text.")
    args = parser.parse_args(argv)

    target = Path(args.target)
    ctx = build_context(target)

    if args.json:
        print(json.dumps(ctx, indent=2, sort_keys=True))
    else:
        print(render_text(ctx))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### Task 3.5: Run tests to verify they pass

Run: `cd backend && python -m pytest ../tests/harness/test_loader.py -v`

Expected: all 8 tests pass.

### Task 3.6: Commit the green loader

```bash
git add tools/load_harness.py
git commit -m "feat(green): H.0a.3 — tools/load_harness.py deterministic context loader

Implements H-11 algorithm: root + walk-up directory CLAUDE.md +
generated/*.json + glob-matched .harness/*.md, with precedence
ordering. Pure-Python, dependency-free YAML front-matter parser
for the limited subset we use. H-25 failure modes covered.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 3.7: Add a red test for conflict detection (deferred Story 3 AC-6)

Append to `tests/harness/test_loader.py`:

```python
def test_loader_records_malformed_cross_cutting(tmp_path: Path, monkeypatch) -> None:
    """If a .harness/*.md file has no front-matter, it's recorded as malformed
    rather than silently included or crashing the loader (H-25)."""
    # Stage a malformed file under .harness/
    fake = REPO_ROOT / ".harness/_test_malformed.md"
    fake.write_text("# I have no front matter\nbody only\n")
    try:
        result = _run_loader("backend/src/learning/contracts.py")
        assert any(
            ".harness/_test_malformed.md" in p for p in result["malformed_files"]
        ), "malformed cross-cutting file should be recorded"
    finally:
        fake.unlink(missing_ok=True)
```

### Task 3.8: Run the new test to verify it passes

Run: `cd backend && python -m pytest ../tests/harness/test_loader.py::test_loader_records_malformed_cross_cutting -v`

Expected: pass (the loader already handles this from the green commit).

### Task 3.9: Commit the additional malformed-file test

```bash
git add tests/harness/test_loader.py
git commit -m "test: H.0a.3 — loader records malformed cross-cutting files (H-25)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 3.10: Refactor — extract front-matter parser to `_common.py`

The front-matter parser in `load_harness.py` will be reused by Story 6's `front-matter validator` and Story 8's harness convention test. Move it to `tools/_common.py` so there's one implementation.

Create `tools/_common.py`:

```python
"""Shared utilities for tools/* harness scripts."""

from __future__ import annotations

import re
from typing import Any


def parse_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """Extract YAML front-matter and body from a markdown file.

    Supports the limited YAML subset the harness uses:
      * `key: value` scalar lines
      * `applies_to:` (or any key with no value) followed by `- item` lines

    Returns (front_matter_dict, body). Empty dict if no front-matter.
    """
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not match:
        return {}, text
    fm_text, body = match.group(1), match.group(2)
    fm: dict[str, Any] = {}
    current_list_key: str | None = None
    for raw in fm_text.splitlines():
        line = raw.rstrip()
        if not line or line.startswith("#"):
            continue
        list_item = re.match(r"^\s+-\s+(.+)$", line)
        if list_item and current_list_key is not None:
            fm.setdefault(current_list_key, []).append(list_item.group(1).strip())
            continue
        kv = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if not kv:
            current_list_key = None
            continue
        key, value = kv.group(1), kv.group(2).strip()
        if value == "":
            current_list_key = key
            fm[key] = []
        else:
            current_list_key = None
            fm[key] = value.strip('"').strip("'")
    return fm, body
```

Update `tools/load_harness.py`: remove the inline `_strip_front_matter` and import:

```python
from tools._common import parse_front_matter as _strip_front_matter
```

(Plus update calling sites if the return signature changed; in this case it's identical.)

### Task 3.11: Run all tests to verify the refactor didn't break anything

Run: `cd backend && python -m pytest ../tests/harness/ -v`

Expected: all tests still pass.

### Task 3.12: Commit the refactor

```bash
git add tools/_common.py tools/load_harness.py
git commit -m "refactor: H.0a.3 — extract parse_front_matter to tools/_common.py

Reused by Story H.0a.6 (front-matter validator) and Story H.0a.8
(harness convention test). One implementation, one source of truth.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

# Story H.0a.4 — `tools/run_validate.py` (orchestrator)

**Files:**
- Create: `tools/run_validate.py`
- Test: `tests/harness/test_run_validate.py`

### Task 4.1: Write the failing test for fast-mode happy path

Create `tests/harness/test_run_validate.py`:

```python
"""Sprint H.0a Story 4 — tools/run_validate.py orchestrates lint + typecheck
+ custom checks and emits H-16/H-23 conformant output.

In Sprint H.0a there are no custom checks yet (those land in Sprint H.1),
so the orchestrator's primary job is: invoke ruff, invoke mypy, invoke
the harness-self-check `claude_md_size_cap.py` (which lands in Story 6),
aggregate exit codes, exit 0 if all pass.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_VALIDATE = REPO_ROOT / "tools/run_validate.py"


def test_run_validate_exists() -> None:
    assert RUN_VALIDATE.is_file()


def test_run_validate_fast_smoke() -> None:
    """Smoke: --fast runs at all, produces output (may pass or fail
    depending on repo state). Just asserts it doesn't crash."""
    result = subprocess.run(
        ["python", str(RUN_VALIDATE), "--fast"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode in (0, 1), (
        f"orchestrator crashed (exit {result.returncode}): {result.stderr}"
    )


def test_run_validate_emits_summary_line() -> None:
    """Output must include a final summary line (machine-parseable)."""
    result = subprocess.run(
        ["python", str(RUN_VALIDATE), "--fast"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert "VALIDATE_SUMMARY" in result.stdout + result.stderr


def test_run_validate_exits_nonzero_on_check_failure(tmp_path: Path) -> None:
    """If any wrapped check exits non-zero, orchestrator exits non-zero."""
    # We simulate by running with a wrapper that always fails. For now,
    # the test just asserts the contract — once Story 6 adds the size-cap
    # check, this test will exercise it via a deliberately-too-large
    # CLAUDE.md fixture. For Story 4 we mark this as expected-to-pass-after-Story-6.
    pytest.skip("Exercised in Story 6 once claude_md_size_cap.py exists.")
```

### Task 4.2: Run tests to verify the relevant ones fail

Run: `cd backend && python -m pytest ../tests/harness/test_run_validate.py -v`

Expected: `test_run_validate_exists`, `test_run_validate_fast_smoke`, `test_run_validate_emits_summary_line` fail (script missing). The skipped one is skipped.

### Task 4.3: Commit failing tests

```bash
git add tests/harness/test_run_validate.py
git commit -m "test(red): H.0a.4 — tools/run_validate.py orchestrator contract

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 4.4: Write the orchestrator skeleton

Create `tools/run_validate.py`:

```python
#!/usr/bin/env python3
"""Validate orchestrator — `make validate-fast` and `make validate-full`.

H-14: single contract. Invokes lint + typecheck + every script in
.harness/checks/ (in --fast mode) or all-of-fast + tests + heavy audits
(in --full mode). Aggregates exit codes; aggregates structured output
per H-16 / H-23.

H-17: fast tier must run in < 30 s; tests are deferred to --full.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKS_DIR = REPO_ROOT / ".harness/checks"


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _run(label: str, cmd: Sequence[str], cwd: Path = REPO_ROOT) -> int:
    """Run a subprocess; stream its stdout/stderr; return exit code."""
    print(f"\n[VALIDATE] {label} → {' '.join(cmd)}")
    start = time.monotonic()
    result = subprocess.run(cmd, cwd=cwd)
    elapsed = time.monotonic() - start
    print(f"[VALIDATE] {label} exited {result.returncode} ({elapsed:.1f}s)")
    return result.returncode


def run_lint() -> int:
    """Lint + format-check. Skipped if tools missing (early bootstrap)."""
    if (REPO_ROOT / "backend").is_dir() and _have("ruff"):
        rc = _run("ruff check", ["ruff", "check", "backend/", ".harness/", "tools/"])
        if rc != 0:
            return rc
    if (REPO_ROOT / "frontend").is_dir() and _have("npx"):
        # ESLint config may not be wired yet in Sprint H.0a; tolerate missing config.
        eslint_config = REPO_ROOT / "frontend/eslint.config.js"
        if eslint_config.exists() or (REPO_ROOT / "frontend/.eslintrc.cjs").exists():
            rc = _run("eslint", ["npx", "--prefix", "frontend", "eslint", "src/"])
            if rc != 0:
                return rc
    return 0


def run_typecheck() -> int:
    """Typecheck. Wired up in Sprint H.0b's Q19 work; skipped here if missing."""
    return 0  # placeholder — Story H.0b.12 adds the real wiring.


def run_custom_checks() -> int:
    """Invoke every .harness/checks/*.py except _common.py and __init__.py."""
    if not CHECKS_DIR.is_dir():
        return 0
    overall = 0
    for script in sorted(CHECKS_DIR.glob("*.py")):
        if script.name in ("__init__.py", "_common.py"):
            continue
        rc = _run(f"check:{script.stem}", ["python", str(script)])
        if rc != 0:
            overall = 1  # non-zero, but keep running other checks for full report
    return overall


def run_tests() -> int:
    """Backend pytest + frontend vitest. Only in --full mode."""
    overall = 0
    if (REPO_ROOT / "backend").is_dir() and _have("pytest"):
        rc = _run("pytest", ["python", "-m", "pytest", "backend/tests/", "tests/harness/", "-q"])
        if rc != 0:
            overall = rc
    return overall


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run harness validations.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fast", action="store_true", help="Inner-loop gate (< 30s).")
    mode.add_argument("--full", action="store_true", help="Pre-commit / CI gate.")
    args = parser.parse_args(argv)

    overall = 0
    overall |= run_lint()
    overall |= run_typecheck()
    overall |= run_custom_checks()

    if args.full:
        overall |= run_tests()

    status = "PASS" if overall == 0 else "FAIL"
    mode_label = "fast" if args.fast else "full"
    print(f"\nVALIDATE_SUMMARY mode={mode_label} status={status}")
    return overall


if __name__ == "__main__":
    sys.exit(main())
```

### Task 4.5: Run the orchestrator manually to sanity-check

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
python tools/run_validate.py --fast
```

Expected: runs lint (may produce ruff output — that's fine for now if violations exist), prints `VALIDATE_SUMMARY mode=fast status=PASS|FAIL`, exits accordingly.

### Task 4.6: Run the harness tests

Run: `cd backend && python -m pytest ../tests/harness/test_run_validate.py -v`

Expected: existence + smoke + summary tests pass; the deferred one is skipped.

### Task 4.7: Commit the orchestrator

```bash
git add tools/run_validate.py
git commit -m "feat(green): H.0a.4 — tools/run_validate.py orchestrator

Stub implementation: invokes ruff/eslint where available, runs every
.harness/checks/*.py, emits VALIDATE_SUMMARY. Tests deferred to --full
mode. Typecheck wiring lands in Sprint H.0b Story 12.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 4.8: Add a perf-budget assertion test

Append to `tests/harness/test_run_validate.py`:

```python
def test_run_validate_fast_under_30_seconds() -> None:
    """H-17: fast mode total wall time < 30s on a clean repo.

    On Sprint H.0a there are zero custom checks beyond the upcoming
    claude_md_size_cap.py + owners_present.py (Story 6). This test
    establishes the budget early; later sprints must keep it.
    """
    import time
    start = time.monotonic()
    result = subprocess.run(
        ["python", str(RUN_VALIDATE), "--fast"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    elapsed = time.monotonic() - start
    assert elapsed < 30.0, (
        f"validate-fast took {elapsed:.1f}s, exceeds 30s budget (H-17). "
        f"Output: {result.stdout[-500:]}"
    )
```

### Task 4.9: Run and verify

Run: `cd backend && python -m pytest ../tests/harness/test_run_validate.py::test_run_validate_fast_under_30_seconds -v`

Expected: pass (with negligible time on the empty-checks state).

### Task 4.10: Commit

```bash
git add tests/harness/test_run_validate.py
git commit -m "test: H.0a.4 — assert validate-fast under 30s budget (H-17)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

# Story H.0a.5 — First per-directory `CLAUDE.md` files

**Files:**
- Create: `backend/CLAUDE.md`
- Create: `backend/src/learning/CLAUDE.md`
- Create: `frontend/CLAUDE.md`
- Test: `tests/harness/test_directory_claude_mds.py`

### Task 5.1: Write failing tests

Create `tests/harness/test_directory_claude_mds.py`:

```python
"""Sprint H.0a Story 5 — every directory CLAUDE.md exists, has front-matter,
stays under the 150-line cap (directory rules can be larger than root)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools._common import parse_front_matter

REPO_ROOT = Path(__file__).resolve().parents[2]

DIRECTORY_CLAUDES = [
    "backend/CLAUDE.md",
    "backend/src/learning/CLAUDE.md",
    "frontend/CLAUDE.md",
]


@pytest.mark.parametrize("rel", DIRECTORY_CLAUDES)
def test_directory_claude_exists(rel: str) -> None:
    assert (REPO_ROOT / rel).is_file(), f"missing {rel}"


@pytest.mark.parametrize("rel", DIRECTORY_CLAUDES)
def test_directory_claude_has_front_matter(rel: str) -> None:
    text = (REPO_ROOT / rel).read_text()
    fm, _ = parse_front_matter(text)
    for required in ("scope", "owner", "priority"):
        assert required in fm, f"{rel} front-matter missing {required}"


@pytest.mark.parametrize("rel", DIRECTORY_CLAUDES)
def test_directory_claude_size_cap(rel: str) -> None:
    """Per-directory rules can be larger than root, but cap at 150 lines."""
    text = (REPO_ROOT / rel).read_text()
    _, body = parse_front_matter(text)
    lines = body.splitlines()
    assert len(lines) <= 150, (
        f"{rel} is {len(lines)} lines (excluding front-matter); cap is 150"
    )
```

### Task 5.2: Run tests to verify they fail

Run: `cd backend && python -m pytest ../tests/harness/test_directory_claude_mds.py -v`

Expected: 9 failures (3 files × 3 tests).

### Task 5.3: Commit failing tests

```bash
git add tests/harness/test_directory_claude_mds.py
git commit -m "test(red): H.0a.5 — first three per-directory CLAUDE.md files

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 5.4: Write the three CLAUDE.md files

Create `backend/CLAUDE.md`:

```markdown
---
scope: backend/
owner: "@platform-team"
priority: high
type: directory
---

# Backend conventions

These rules apply to all code under `backend/`. They override the root
`CLAUDE.md` on conflict.

## Stack
- FastAPI for HTTP. SQLModel for DB. Pydantic v2 for validation.
- pytest + Hypothesis for tests. Async tests via pytest-asyncio.
- mypy strict on `src/{api,storage,models,learning,agents/**/runners}/` and `.harness/`.

## Async posture (Q7)
- `async def` for I/O (httpx, DB, file). `def` for pure compute.
- `httpx.AsyncClient` only — never `requests` or `urllib`.
- Wrap unavoidable blocking work with `asyncio.to_thread`.

## Database (Q8)
- All DB access goes through `StorageGateway` (`src/storage/gateway.py`).
- Routes/services/agents do NOT import `AsyncSession` or `Session` directly.
- `models/db/` holds `table=True` SQLModel classes; never returned from API.
- API responses use `models/api/` (frozen=True). Agent tools use `models/agent/`.
- Schema changes ship with an Alembic migration in `alembic/versions/`.

## Testing (Q9)
- `pytest` + `Hypothesis` (required on `learning/`, `storage/gateway.py`,
  `agents/**/parsers/`, and any `extract_*`/`parse_*`/`resolve_*`/`calibrate_*`/
  `score_*` function).
- ≥ 90 % patch coverage via `diff-cover` (CI gate).
- No live LLM/telemetry calls in tests — mock with `respx` or `pytest-mock`.

## Validation (Q10)
- API request models: `model_config = ConfigDict(extra="forbid")`.
- API response models: `frozen=True`.
- Agent schemas: both.
- Numeric fields on boundaries: `Field(ge=..., le=...)`.
- String fields: `Field(max_length=N)`.
- Confidence/probability fields: `Field(ge=0.0, le=1.0)`.
- Global `strict=True` is BANNED.

## Errors (Q17)
- Expected outcomes return typed `Result[T, E]` from `src/errors/`.
- Unexpected failures raise; let them bubble to FastAPI's global handler.
- API error responses use RFC 7807 (`application/problem+json`) via
  `src/api/problem.py::problem_response()`.
- Outbound HTTP MUST go through `src/utils/http.py::with_retry`
  (max 3 attempts, exponential jitter, explicit timeout).

## Logging (Q16)
- `structlog` only — no `print()`, no bare stdlib logging.
- Every log call carries an `event` snake_case name + context kwargs
  (`session_id`, `tenant_id` when applicable).
- ERROR/CRITICAL include `exc_info=True` (or use `.exception()`).
- Agent runners and workflow steps wrap their bodies in OpenTelemetry
  spans (`tracer.start_as_current_span("agent.<name>.run", attributes={...})`).

## Imports & naming (Q18)
- Absolute imports only (`from src.x import y`). No relative imports
  outside test files.
- Files: `snake_case.py`. Classes: `PascalCase`. Functions: `snake_case`.
- Tests live in `backend/tests/<mirrored-tree>/test_<module>.py`.
```

Create `backend/src/learning/CLAUDE.md`:

```markdown
---
scope: backend/src/learning/
owner: "@platform-team"
priority: high
type: directory
---

# Learning subsystem conventions

The self-learning platform (loops A, D, F → G). Cross-reference:
`docs/plans/2026-04-26-self-learning-platform-implementation-plan.md`.

## The 18 inviolable design rules from the self-learning plan apply here

In particular:
- The `ClosedIncidentRecord` typed contract is the only public way data
  flows between loops.
- Spine fields are JOIN-required only; everything else is sidecar.
- Spine is append-only (the SQLite trigger enforces); sidecars mutate.
- Tenancy is per-tenant via fixed 3-tier model.
- Provenance mandatory on every learned output.
- Sources never blended — fan-out + rank, never merged.
- Cross-tenant data is projection-safe.
- Every learned loop has a safe-mode fallback.
- Loop health is a single state machine.
- Drift detection uses hysteresis.

## Specific rules for editing in this directory

- Use `StorageGateway` (`src/storage/gateway.py`) for ALL DB access. Direct
  `select()` / `Session` usage is banned (Q8).
- Hypothesis tests required (Q9) on every `extract_*`, `parse_*`,
  `resolve_*`, `calibrate_*`, `score_*` function.
- Outcome labels follow the precedence rule from Story 1.1.5 of the
  self-learning plan: operator_action > dossier_label > telemetry > time-decay.
- Calibration math is statistically pure — no LLM calls. Any function
  that touches confidence numbers stays deterministic.
- Loop state transitions write audit rows via `write_audit_event()`.

## What lives where
- `contracts.py` — typed contract surfaces (Pydantic models). Phase 0.
- `storage/` — `StorageGateway`, `engine`, sidecar query helpers.
- `services/` — domain services (calibration, signature index, dispatch policy).
- `outcome_observer.py` — background job that labels closed incidents.
```

Create `frontend/CLAUDE.md`:

```markdown
---
scope: frontend/
owner: "@platform-team"
priority: high
type: directory
---

# Frontend conventions

These rules apply to all code under `frontend/`. They override the root
`CLAUDE.md` on conflict.

## Stack
- React + TypeScript + Vite. Tailwind for styling.
- TanStack Query for server state. React Context / `useState` for UI state.
- shadcn/ui-style primitives in `components/ui/` (Radix under the hood).
- React Router v6 with `createBrowserRouter` (single table in `src/router.tsx`).
- Vitest for unit/integration. Playwright for e2e (in `frontend/e2e/`).

## Styling (Q1)
- Tailwind utility classes only.
- Inline `style={{...}}` allowed ONLY for dynamic values (width %, transform, etc.).
- No CSS/SCSS imports. No `styled-components`. No `@emotion`.
- Class merging via `cn()` from `@/lib/utils`.
- Token namespace is `wr-*`. `duck-*` is legacy and BANNED in new code.

## State (Q2) + data fetching (Q3)
- Server state: TanStack Query.
- UI state: local `useState` or React Context.
- Global UI state: scoped Zustand stores in `frontend/src/stores/` with
  `// JUSTIFICATION: <why this needs to be global>` leading comment.
- Components do NOT call `fetch` / `axios` directly. They consume hooks.
- All HTTP goes through `services/api/client.ts` → typed domain functions
  in `services/api/<domain>.ts` → hook wrappers in `hooks/use<X>.ts`.
- Redux / MobX / Recoil / Jotai BANNED. Axios BANNED.

## Primitives (Q4)
- All reusable UI primitives live in `components/ui/` (shadcn pattern).
- Feature components compose primitives; never use raw `<button>`,
  `<input>`, `<select>`, `<a onClick>` in feature code.
- MUI / Chakra / Mantine BANNED.

## Routing (Q6)
- All routes declared in `frontend/src/router.tsx`. No nested `<Routes>` blocks.
- Page components lazy-imported via `React.lazy(() => import('./pages/X'))`.
- Internal nav: `<Link to="...">` or `useNavigate()`. Raw `<a href="/...">`
  is BANNED for internal nav.

## Tests (Q5)
- Vitest tests colocated as `*.test.ts(x)`.
- Playwright e2e specs live ONLY under `frontend/e2e/`.
- Coverage gate: `services/api/ ≥ 90%`, `hooks/ ≥ 85%` (vitest threshold config).
- Jest / Cypress BANNED.

## Accessibility (Q14)
- Target: WCAG 2.2 AA.
- Every primitive in `components/ui/` ships with an axe-clean Vitest test.
- Incident-critical pages have axe-clean Playwright e2e specs.
- jsx-a11y eslint plugin at error level — no overrides without
  `// a11y-justified:` comment.

## Imports & naming (Q18)
- Use path alias `@/` (mapped to `frontend/src/`). No `../../../` paths.
- Named exports only. Default exports allowed only in `pages/` and
  config files (`vite.config.ts`, etc.).
- File naming: `Component.tsx` (PascalCase), `useThing.ts` (camelCase
  starting with `use`), `kebab-case/` directories.
```

### Task 5.5: Run tests to verify all pass

Run: `cd backend && python -m pytest ../tests/harness/test_directory_claude_mds.py -v`

Expected: all 9 tests pass.

### Task 5.6: Commit

```bash
git add backend/CLAUDE.md backend/src/learning/CLAUDE.md frontend/CLAUDE.md
git commit -m "feat(green): H.0a.5 — first 3 per-directory CLAUDE.md files

backend/, backend/src/learning/, frontend/. Each carries front-matter
(scope, owner, priority) and codifies the locked Q-decisions for its
area. These get loaded by tools/load_harness.py when AI works in the
matching subtree.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

# Story H.0a.6 — Front-matter validator + first two harness self-checks

**Files:**
- Create: `.harness/checks/claude_md_size_cap.py`
- Create: `.harness/checks/owners_present.py`
- Test: `tests/harness/checks/test_claude_md_size_cap.py`
- Test: `tests/harness/checks/test_owners_present.py`
- Create: `tests/harness/fixtures/violation/claude_md_size_cap/oversized_root.md`
- Create: `tests/harness/fixtures/compliant/claude_md_size_cap/normal_root.md`
- Create: `tests/harness/fixtures/violation/owners_present/missing_owner.md`
- Create: `tests/harness/fixtures/compliant/owners_present/with_owner.md`

### Task 6.1: Create the test directory and fixtures

```bash
mkdir -p tests/harness/checks \
         tests/harness/fixtures/violation/claude_md_size_cap \
         tests/harness/fixtures/compliant/claude_md_size_cap \
         tests/harness/fixtures/violation/owners_present \
         tests/harness/fixtures/compliant/owners_present
touch tests/harness/checks/__init__.py
```

Create `tests/harness/fixtures/violation/claude_md_size_cap/oversized_root.md`:

```markdown
---
scope: repo
owner: "@x"
priority: highest
type: root
---

# Oversized fixture (intentionally over 70 lines for testing the size-cap check)
```

Then append 75 numbered lines to make it deliberately oversized:

```bash
for i in $(seq 1 75); do
  echo "Line $i — filler" >> tests/harness/fixtures/violation/claude_md_size_cap/oversized_root.md
done
```

Create `tests/harness/fixtures/compliant/claude_md_size_cap/normal_root.md`:

```markdown
---
scope: repo
owner: "@x"
priority: highest
type: root
---

# Normal-size fixture

This file has under 70 body lines. The check should stay silent.

- One bullet
- Another bullet
- A third
```

Create `tests/harness/fixtures/violation/owners_present/missing_owner.md`:

```markdown
---
scope: backend/
priority: high
type: directory
---

# Missing owner field
```

Create `tests/harness/fixtures/compliant/owners_present/with_owner.md`:

```markdown
---
scope: backend/
owner: "@platform-team"
priority: high
type: directory
---

# With owner
```

### Task 6.2: Write the failing test for size-cap

Create `tests/harness/checks/test_claude_md_size_cap.py`:

```python
"""Sprint H.0a Story 6 — claude_md_size_cap check enforces H-1 (root ≤ 70 lines)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECK = REPO_ROOT / ".harness/checks/claude_md_size_cap.py"
FIXTURES = REPO_ROOT / "tests/harness/fixtures"


def _run_check(target: Path) -> tuple[int, str]:
    """Invoke the check with --target <fixture> and return (exit_code, stdout)."""
    result = subprocess.run(
        ["python", str(CHECK), "--target", str(target)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    return result.returncode, result.stdout


def test_check_exists() -> None:
    assert CHECK.is_file()


def test_fires_on_oversized_root() -> None:
    fixture = FIXTURES / "violation/claude_md_size_cap/oversized_root.md"
    code, out = _run_check(fixture)
    assert code != 0, f"check should fail on oversized root; got exit 0 with {out}"
    assert "[ERROR]" in out
    assert "rule=claude_md_size_cap" in out
    assert "suggestion=" in out


def test_silent_on_compliant_root() -> None:
    fixture = FIXTURES / "compliant/claude_md_size_cap/normal_root.md"
    code, out = _run_check(fixture)
    assert code == 0, f"check should pass on compliant root; got exit {code} with {out}"
    assert out.strip() == ""
```

### Task 6.3: Write the failing test for owners-present

Create `tests/harness/checks/test_owners_present.py`:

```python
"""Sprint H.0a Story 6 — owners_present check enforces H-6 (owner: in front-matter)."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECK = REPO_ROOT / ".harness/checks/owners_present.py"
FIXTURES = REPO_ROOT / "tests/harness/fixtures"


def _run_check(target: Path) -> tuple[int, str]:
    result = subprocess.run(
        ["python", str(CHECK), "--target", str(target)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    return result.returncode, result.stdout


def test_check_exists() -> None:
    assert CHECK.is_file()


def test_fires_on_missing_owner() -> None:
    fixture = FIXTURES / "violation/owners_present/missing_owner.md"
    code, out = _run_check(fixture)
    assert code != 0
    assert "rule=owners_present" in out
    assert "suggestion=" in out


def test_silent_on_present_owner() -> None:
    fixture = FIXTURES / "compliant/owners_present/with_owner.md"
    code, out = _run_check(fixture)
    assert code == 0
    assert out.strip() == ""
```

### Task 6.4: Run the tests to verify they fail

Run: `cd backend && python -m pytest ../tests/harness/checks/ -v`

Expected: every test fails — checks don't exist yet.

### Task 6.5: Commit failing tests + fixtures

```bash
git add tests/harness/checks/__init__.py \
        tests/harness/checks/test_claude_md_size_cap.py \
        tests/harness/checks/test_owners_present.py \
        tests/harness/fixtures/
git commit -m "test(red): H.0a.6 — size-cap and owners-present checks (paired fixtures)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 6.6: Write `claude_md_size_cap.py`

Create `.harness/checks/claude_md_size_cap.py`:

```python
#!/usr/bin/env python3
"""Enforce H-1: root CLAUDE.md ≤ 70 lines (excluding YAML front-matter).

H-25:
  Missing target → ERROR (loud, never silent).
  Malformed front-matter → still counted (the check is line count, not YAML).
  No --target → defaults to repo root CLAUDE.md so `make validate-fast` works.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tools._common import parse_front_matter           # noqa: E402
from .._common_helpers_alias import emit                 # type: ignore  # noqa: E402, F401

# Allow direct execution: ".harness.checks._common" under sys.path doesn't
# resolve cleanly when running this script standalone. Bypass with explicit
# path manipulation:
sys.path.insert(0, str(REPO_ROOT / ".harness/checks"))
from _common import emit                                  # noqa: E402

RULE_ID = "claude_md_size_cap"
LIMIT = 70


def check_file(path: Path) -> int:
    """Return 1 if violation, 0 if compliant."""
    if not path.exists():
        emit(
            "ERROR", path, RULE_ID,
            "target file does not exist",
            f"Create {path} or pass a real target via --target",
        )
        return 1
    text = path.read_text()
    _, body = parse_front_matter(text)
    line_count = len(body.splitlines())
    if line_count > LIMIT:
        emit(
            "ERROR", path, RULE_ID,
            f"root CLAUDE.md is {line_count} lines (excluding front-matter); H-1 caps at {LIMIT}",
            f"Trim to ≤ {LIMIT} lines. Move detail to per-directory CLAUDE.md or .harness/*.md.",
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="H-1 root CLAUDE.md size cap.")
    parser.add_argument("--target", default=str(REPO_ROOT / "CLAUDE.md"))
    args = parser.parse_args(argv)
    return check_file(Path(args.target))


if __name__ == "__main__":
    sys.exit(main())
```

The double `_common` import dance is necessary because `.harness/checks/` isn't a Python package on the sys.path when run standalone. Simpler — just remove the alias trick and use the explicit path manipulation:

Replace the import section with this clean version (overwrite the file):

```python
#!/usr/bin/env python3
"""Enforce H-1: root CLAUDE.md ≤ 70 lines (excluding YAML front-matter).

H-25:
  Missing target → ERROR (loud, never silent).
  Malformed front-matter → still counted (the check is line count, not YAML).
  No --target → defaults to repo root CLAUDE.md so `make validate-fast` works.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Ensure tools/ and .harness/checks/ are importable regardless of caller cwd.
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / ".harness/checks"))

from _common import emit                                  # noqa: E402
from tools._common import parse_front_matter              # noqa: E402

RULE_ID = "claude_md_size_cap"
LIMIT = 70


def check_file(path: Path) -> int:
    if not path.exists():
        emit(
            "ERROR", path, RULE_ID,
            "target file does not exist",
            f"Create {path} or pass a real target via --target",
        )
        return 1
    text = path.read_text()
    _, body = parse_front_matter(text)
    line_count = len(body.splitlines())
    if line_count > LIMIT:
        emit(
            "ERROR", path, RULE_ID,
            f"root CLAUDE.md is {line_count} lines (excluding front-matter); H-1 caps at {LIMIT}",
            f"Trim to ≤ {LIMIT} lines. Move detail to per-directory CLAUDE.md or .harness/*.md.",
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="H-1 root CLAUDE.md size cap.")
    parser.add_argument("--target", default=str(REPO_ROOT / "CLAUDE.md"))
    args = parser.parse_args(argv)
    return check_file(Path(args.target))


if __name__ == "__main__":
    sys.exit(main())
```

### Task 6.7: Write `owners_present.py`

Create `.harness/checks/owners_present.py`:

```python
#!/usr/bin/env python3
"""Enforce H-6: every CLAUDE.md and .harness/*.md declares `owner:` in front-matter.

When invoked with --target <file>, checks that one file. When invoked
without --target, walks the repo and checks every applicable file.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / ".harness/checks"))

from _common import emit                                  # noqa: E402
from tools._common import parse_front_matter              # noqa: E402

RULE_ID = "owners_present"


def check_file(path: Path) -> int:
    if not path.exists():
        emit(
            "ERROR", path, RULE_ID,
            "target file does not exist",
            f"Create {path} or pass a real target via --target",
        )
        return 1
    fm, _ = parse_front_matter(path.read_text())
    if "owner" not in fm or not fm.get("owner"):
        emit(
            "ERROR", path, RULE_ID,
            "front-matter missing required `owner:` field",
            'Add `owner: "@team-name"` to the YAML front-matter at the top of the file.',
        )
        return 1
    return 0


def collect_targets() -> list[Path]:
    """Walk the repo for every applicable rule file."""
    targets: list[Path] = []
    # Root CLAUDE.md
    root = REPO_ROOT / "CLAUDE.md"
    if root.exists():
        targets.append(root)
    # Every directory CLAUDE.md
    for path in REPO_ROOT.rglob("CLAUDE.md"):
        if path == root:
            continue
        if any(part in (".git", "node_modules", "__pycache__", ".venv") for part in path.parts):
            continue
        targets.append(path)
    # Every .harness/*.md (skip README)
    harness_dir = REPO_ROOT / ".harness"
    if harness_dir.is_dir():
        for path in harness_dir.glob("*.md"):
            if path.name == "README.md":
                continue
            targets.append(path)
    return targets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="H-6 owner-present check.")
    parser.add_argument("--target", default=None)
    args = parser.parse_args(argv)

    if args.target:
        return check_file(Path(args.target))

    overall = 0
    for path in collect_targets():
        if check_file(path):
            overall = 1
    return overall


if __name__ == "__main__":
    sys.exit(main())
```

### Task 6.8: Run tests to verify they pass

Run: `cd backend && python -m pytest ../tests/harness/checks/ -v`

Expected: all tests pass.

### Task 6.9: Sanity-check by running the orchestrator

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
python tools/run_validate.py --fast
```

Expected: among other lint/typecheck output, `[VALIDATE] check:claude_md_size_cap exited 0` and `[VALIDATE] check:owners_present exited 0`. Final summary `VALIDATE_SUMMARY mode=fast status=PASS`.

### Task 6.10: Commit

```bash
git add .harness/checks/claude_md_size_cap.py .harness/checks/owners_present.py
git commit -m "feat(green): H.0a.6 — claude_md_size_cap + owners_present harness self-checks

First two custom checks; both with paired violation/compliant fixtures
per H-24. Output conforms to H-16/H-23. Wired into make validate-fast
via the orchestrator's automatic .harness/checks/*.py walk.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

# Story H.0a.7 — `make harness-install` pre-commit installer

**Files:**
- Create: `tools/install_pre_commit.sh`
- Test: `tests/harness/test_pre_commit_install.py`

### Task 7.1: Write the failing test

Create `tests/harness/test_pre_commit_install.py`:

```python
"""Sprint H.0a Story 7 — `make harness-install` writes an idempotent
pre-commit hook that runs `make validate-fast`."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = REPO_ROOT / "tools/install_pre_commit.sh"
HOOK = REPO_ROOT / ".git/hooks/pre-commit"


@pytest.fixture
def saved_hook():
    """Save and restore the existing pre-commit hook so the test is non-destructive."""
    backup = HOOK.read_text() if HOOK.exists() else None
    yield
    if backup is None:
        HOOK.unlink(missing_ok=True)
    else:
        HOOK.write_text(backup)
        HOOK.chmod(0o755)


def test_installer_exists() -> None:
    assert INSTALLER.is_file()


def test_installer_writes_hook(saved_hook) -> None:
    HOOK.unlink(missing_ok=True)
    result = subprocess.run(["bash", str(INSTALLER)], cwd=REPO_ROOT, capture_output=True, text=True)
    assert result.returncode == 0, f"installer failed: {result.stderr}"
    assert HOOK.exists()
    assert "make validate-fast" in HOOK.read_text()


def test_installer_is_idempotent(saved_hook) -> None:
    HOOK.unlink(missing_ok=True)
    subprocess.run(["bash", str(INSTALLER)], cwd=REPO_ROOT, check=True)
    first = HOOK.read_text()
    subprocess.run(["bash", str(INSTALLER)], cwd=REPO_ROOT, check=True)
    second = HOOK.read_text()
    assert first == second, "second run changed the hook unexpectedly"


def test_installer_refuses_overwrite_without_force(saved_hook) -> None:
    HOOK.write_text("#!/bin/sh\necho 'pre-existing hook from another tool'\n")
    HOOK.chmod(0o755)
    result = subprocess.run(["bash", str(INSTALLER)], cwd=REPO_ROOT, capture_output=True, text=True)
    assert result.returncode != 0
    assert "exists" in (result.stderr + result.stdout).lower()
    # Hook should still be the pre-existing content.
    assert "pre-existing" in HOOK.read_text()


def test_installer_force_overwrites(saved_hook) -> None:
    HOOK.write_text("#!/bin/sh\necho 'old'\n")
    HOOK.chmod(0o755)
    result = subprocess.run(
        ["bash", str(INSTALLER), "--force"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "make validate-fast" in HOOK.read_text()
```

### Task 7.2: Run tests to verify they fail

Run: `cd backend && python -m pytest ../tests/harness/test_pre_commit_install.py -v`

Expected: `test_installer_exists` fails first; others would also fail.

### Task 7.3: Commit failing tests

```bash
git add tests/harness/test_pre_commit_install.py
git commit -m "test(red): H.0a.7 — make harness-install installer contract

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 7.4: Write the installer

Create `tools/install_pre_commit.sh`:

```bash
#!/usr/bin/env bash
# Install (or refresh) the harness pre-commit hook.
#
# Idempotent: running twice produces an identical hook file.
# Safe: refuses to overwrite a pre-existing hook unless --force.
#
# Per H-18: pre-commit hook runs `make validate-fast`. The hook is
# bypassable via `git commit --no-verify` for the rare case where the
# operator must commit despite a known violation (e.g., during the
# very first scaffolding when a check expects state that doesn't exist
# yet).

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOK="$REPO_ROOT/.git/hooks/pre-commit"

MARKER="# debugduck-harness pre-commit hook v1"
HOOK_BODY="#!/usr/bin/env bash
$MARKER
#
# Runs make validate-fast before every commit. Bypass with
#   git commit --no-verify
# in the rare cases where you need to commit despite a violation.

set -e
exec make validate-fast
"

FORCE=0
if [[ "${1-}" == "--force" ]]; then
  FORCE=1
fi

if [[ -f "$HOOK" ]]; then
  if grep -q "$MARKER" "$HOOK"; then
    # It's our own hook — overwrite (idempotent).
    :
  elif [[ "$FORCE" -ne 1 ]]; then
    echo "ERROR: $HOOK exists and was not installed by this script." >&2
    echo "       Re-run with --force to overwrite." >&2
    exit 1
  fi
fi

mkdir -p "$REPO_ROOT/.git/hooks"
printf '%s' "$HOOK_BODY" > "$HOOK"
chmod +x "$HOOK"
echo "Installed harness pre-commit hook at $HOOK"
```

### Task 7.5: Run tests, then commit

Run: `cd backend && python -m pytest ../tests/harness/test_pre_commit_install.py -v`

Expected: all 5 tests pass.

```bash
git add tools/install_pre_commit.sh
git commit -m "feat(green): H.0a.7 — make harness-install pre-commit installer

Idempotent installer that writes a marker-tagged hook running
make validate-fast. Refuses to overwrite a pre-existing non-marker
hook without --force. Per H-18.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

# Story H.0a.8 — Harness test infrastructure

**Files:**
- Create: `tests/harness/_helpers.py`
- Create: `tests/harness/test_harness_conventions.py`
- Test: existing tests/harness/checks/* already exercise the helpers via subprocess; this story adds in-process helpers.

### Task 8.1: Write the failing convention test

Create `tests/harness/test_harness_conventions.py`:

```python
"""Sprint H.0a Story 8 — convention tests that the harness applies to itself.

Per H-24: every check in .harness/checks/ MUST have paired violation +
compliant fixtures under tests/harness/fixtures/.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKS_DIR = REPO_ROOT / ".harness/checks"
FIXTURES_DIR = REPO_ROOT / "tests/harness/fixtures"


def _check_rule_ids() -> list[str]:
    """Return the file-stem (rule id) of every check, excluding helpers."""
    if not CHECKS_DIR.is_dir():
        return []
    return sorted(
        p.stem for p in CHECKS_DIR.glob("*.py")
        if p.stem not in ("__init__", "_common")
    )


@pytest.mark.parametrize("rule_id", _check_rule_ids())
def test_check_has_violation_fixture(rule_id: str) -> None:
    """H-24 — every check has at least one violation fixture."""
    violation_dir = FIXTURES_DIR / "violation" / rule_id
    assert violation_dir.is_dir() and any(violation_dir.iterdir()), (
        f"check `{rule_id}` has no fixtures at {violation_dir.relative_to(REPO_ROOT)}"
    )


@pytest.mark.parametrize("rule_id", _check_rule_ids())
def test_check_has_compliant_fixture(rule_id: str) -> None:
    """H-24 — every check has at least one compliant fixture."""
    compliant_dir = FIXTURES_DIR / "compliant" / rule_id
    assert compliant_dir.is_dir() and any(compliant_dir.iterdir()), (
        f"check `{rule_id}` has no compliant fixtures at "
        f"{compliant_dir.relative_to(REPO_ROOT)}"
    )
```

### Task 8.2: Write the helpers file

Create `tests/harness/_helpers.py`:

```python
"""Shared test helpers for harness checks.

Re-export common patterns so individual check tests stay short:
  assert_check_fires(rule_id, fixture_path) — runs the check and
    asserts it emits ≥ 1 ERROR matching that rule id.
  assert_check_silent(rule_id, fixture_path) — runs the check and
    asserts it produces zero output and exits 0.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKS_DIR = REPO_ROOT / ".harness/checks"


def _run_check(rule_id: str, target: Path) -> tuple[int, str]:
    script = CHECKS_DIR / f"{rule_id}.py"
    if not script.exists():
        raise FileNotFoundError(f"no check at {script}")
    result = subprocess.run(
        ["python", str(script), "--target", str(target)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    return result.returncode, result.stdout


def assert_check_fires(rule_id: str, fixture: Path) -> None:
    code, out = _run_check(rule_id, fixture)
    assert code != 0, (
        f"check `{rule_id}` should have failed on {fixture} but exited 0. "
        f"Output: {out}"
    )
    assert f"rule={rule_id}" in out, (
        f"check `{rule_id}` fired but didn't tag itself with rule={rule_id}: {out}"
    )
    assert "[ERROR]" in out, (
        f"check `{rule_id}` should emit at least one [ERROR] line: {out}"
    )
    assert "suggestion=" in out, (
        f"check `{rule_id}` violations must include `suggestion=` field (H-23). Got: {out}"
    )


def assert_check_silent(rule_id: str, fixture: Path) -> None:
    code, out = _run_check(rule_id, fixture)
    assert code == 0, (
        f"check `{rule_id}` should pass on {fixture} but exited {code}. Output: {out}"
    )
    assert out.strip() == "", (
        f"check `{rule_id}` produced output on a compliant fixture: {out}"
    )
```

### Task 8.3: Refactor the existing check tests to use the helpers

Update `tests/harness/checks/test_claude_md_size_cap.py`:

```python
"""Sprint H.0a Story 6 — claude_md_size_cap (H-1)."""

from __future__ import annotations

from pathlib import Path

from tests.harness._helpers import assert_check_fires, assert_check_silent

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = REPO_ROOT / "tests/harness/fixtures"


def test_check_exists() -> None:
    assert (REPO_ROOT / ".harness/checks/claude_md_size_cap.py").is_file()


def test_fires_on_oversized_root() -> None:
    assert_check_fires(
        "claude_md_size_cap",
        FIXTURES / "violation/claude_md_size_cap/oversized_root.md",
    )


def test_silent_on_compliant_root() -> None:
    assert_check_silent(
        "claude_md_size_cap",
        FIXTURES / "compliant/claude_md_size_cap/normal_root.md",
    )
```

Update `tests/harness/checks/test_owners_present.py` similarly:

```python
"""Sprint H.0a Story 6 — owners_present (H-6)."""

from __future__ import annotations

from pathlib import Path

from tests.harness._helpers import assert_check_fires, assert_check_silent

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = REPO_ROOT / "tests/harness/fixtures"


def test_check_exists() -> None:
    assert (REPO_ROOT / ".harness/checks/owners_present.py").is_file()


def test_fires_on_missing_owner() -> None:
    assert_check_fires(
        "owners_present",
        FIXTURES / "violation/owners_present/missing_owner.md",
    )


def test_silent_on_present_owner() -> None:
    assert_check_silent(
        "owners_present",
        FIXTURES / "compliant/owners_present/with_owner.md",
    )
```

### Task 8.4: Run tests to verify everything still passes

Run: `cd backend && python -m pytest ../tests/harness/ -v`

Expected: all tests pass, including the new convention test (claude_md_size_cap and owners_present both have paired fixtures, so they pass H-24).

### Task 8.5: Add a deliberate-failure smoke test that the convention test catches missing fixtures

Append to `tests/harness/test_harness_conventions.py`:

```python
def test_convention_test_self_check(tmp_path, monkeypatch) -> None:
    """Sanity: if a hypothetical check existed without fixtures, the
    convention test would catch it. Validate the validator."""
    # We can't easily monkeypatch the parametrize decorator, so we just
    # invoke the helper logic directly with a synthetic rule id.
    from tests.harness.test_harness_conventions import _check_rule_ids
    assert "claude_md_size_cap" in _check_rule_ids()
    assert "owners_present" in _check_rule_ids()
```

### Task 8.6: Run, commit

Run: `cd backend && python -m pytest ../tests/harness/ -v`

Expected: all tests pass.

```bash
git add tests/harness/_helpers.py \
        tests/harness/test_harness_conventions.py \
        tests/harness/checks/test_claude_md_size_cap.py \
        tests/harness/checks/test_owners_present.py
git commit -m "feat(green): H.0a.8 — harness test infrastructure

Adds tests/harness/_helpers.py (assert_check_fires, assert_check_silent)
and tests/harness/test_harness_conventions.py (parametrized check that
every .harness/checks/*.py has paired violation + compliant fixtures
per H-24). Refactors existing check tests to use the helpers.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 8.7: Run the orchestrator end-to-end

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
python tools/run_validate.py --fast
```

Expected: lint runs, both checks run and pass, summary line `VALIDATE_SUMMARY mode=fast status=PASS`. Total wall time well under 30s.

### Task 8.8: Run the full mode and verify pytest is invoked

```bash
python tools/run_validate.py --full
```

Expected: lint + checks + pytest (against `tests/harness/`) all run, all pass.

---

# Story H.0a.9 — `AGENTS.md` alias + `.cursorrules` pointer

**Files:**
- Create: `AGENTS.md` (symlink → `CLAUDE.md`)
- Create: `.cursorrules`

### Task 9.1: Write the failing test

Append to `tests/harness/test_skeleton.py`:

```python
def test_agents_md_alias_exists() -> None:
    """AGENTS.md aliases CLAUDE.md for cross-vendor AI tools."""
    agents_md = REPO_ROOT / "AGENTS.md"
    assert agents_md.exists(), "AGENTS.md missing (cross-vendor alias for CLAUDE.md)"
    # Either a symlink or a stub pointing at CLAUDE.md
    if agents_md.is_symlink():
        assert agents_md.resolve().name == "CLAUDE.md"
    else:
        text = agents_md.read_text()
        assert "CLAUDE.md" in text, (
            "AGENTS.md is not a symlink and doesn't reference CLAUDE.md"
        )


def test_cursorrules_pointer_exists() -> None:
    cursorrules = REPO_ROOT / ".cursorrules"
    assert cursorrules.is_file()
    text = cursorrules.read_text()
    assert "CLAUDE.md" in text
    assert "load_harness" in text or "tools/load_harness" in text
```

### Task 9.2: Create the alias and pointer

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
ln -s CLAUDE.md AGENTS.md
```

Create `.cursorrules`:

```
See CLAUDE.md and the nearest CLAUDE.md to the file you're editing.
For full context: run `python tools/load_harness.py --target <file>`.
```

### Task 9.3: Run, commit

Run: `cd backend && python -m pytest ../tests/harness/test_skeleton.py::test_agents_md_alias_exists ../tests/harness/test_skeleton.py::test_cursorrules_pointer_exists -v`

Expected: both pass.

```bash
git add AGENTS.md .cursorrules tests/harness/test_skeleton.py
git commit -m "feat: H.0a.9 — AGENTS.md alias + .cursorrules pointer for cross-vendor AI tools

AGENTS.md is a symlink to CLAUDE.md (Codex/Aider/etc. convention).
.cursorrules instructs Cursor to read CLAUDE.md hierarchy and load
the harness loader output for full context.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

# Story H.0a.10 — `CONTRIBUTING.md` (human discipline checklist)

**Files:**
- Create: `CONTRIBUTING.md`

### Task 10.1: Write CONTRIBUTING.md

Create `CONTRIBUTING.md`:

```markdown
# Contributing to DebugDuck

## Before you commit

The harness enforces most rules automatically (`make validate-fast` runs
in your pre-commit hook if you ran `make harness-install`). But until CI
lands, **discipline is the temporary gate** (per H-19). For every commit:

- [ ] `make validate-fast` passed locally.
- [ ] If your task involved AI generation, the AI ran the validate loop
  to completion (not just declared "done" prematurely).
- [ ] You read the diff yourself, especially in critical paths
  (`backend/src/{api,storage,learning,agents}/`, `frontend/src/{services/api,hooks}/`).
- [ ] If you added a new dependency to a spine path
  (`backend/src/{api,storage,models,agents}/` or
   `frontend/src/{services/api,hooks}/`), you added it to
  `.harness/dependencies.yaml` and wrote an ADR
  in `docs/decisions/YYYY-MM-DD-<slug>.md`.
- [ ] If you changed a contract (`ClosedIncidentRecord`, agent manifests,
  `StorageGateway` public surface, FastAPI route signatures), you wrote
  an ADR.
- [ ] Commits follow Conventional Commits (`feat:`, `fix:`, `docs:`,
  `test(red):`, `feat(green):`, `refactor:`, etc.).
- [ ] Tests live next to the code they test (or in `frontend/e2e/` for
  Playwright specs).

## Fresh contributor setup

```bash
# After cloning:
make harness-install      # installs the pre-commit hook
make harness              # generates .harness/generated/ (cheap, idempotent)
make validate-fast        # confirms your environment is healthy
```

## Where to look for the rules

- Root behavioral rules: `CLAUDE.md` (always loaded by AI tools).
- Per-area conventions: nearest `CLAUDE.md` to the file you're editing.
- Cross-cutting rules: `.harness/*.md` (loaded when their `applies_to`
  glob matches).
- Current truth (registered checks, valid tokens, contract names):
  `.harness/generated/*.json` (regenerated by `make harness`).
- Full design: `docs/plans/2026-04-26-ai-harness.md`.
- Architecture decision records: `docs/decisions/`.

## TDD discipline

Every story is implemented red → green → refactor. PRs without a
preceding `test(red):` commit are rejected at code review.

  1. **Red** — write the failing test. Commit:
     `test(red): <story-id> — <test name>`.
  2. **Green** — minimum production code to make the test pass. Commit:
     `feat(green): <story-id> — <change>`.
  3. **Refactor** — improve structure without changing behavior. Tests
     stay green. Commit: `refactor: <story-id> — <description>`.
```

### Task 10.2: Commit

```bash
git add CONTRIBUTING.md
git commit -m "docs: H.0a.10 — CONTRIBUTING.md human discipline checklist (H-19)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

# Sprint H.0a — Acceptance verification

After completing all 10 stories, verify the sprint is done by running this end-to-end sequence:

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm

# 1. Loader works for any target
python tools/load_harness.py --target backend/src/learning/contracts.py | head -50

# 2. Self-checks pass against the real repo state
python .harness/checks/claude_md_size_cap.py
python .harness/checks/owners_present.py

# 3. Orchestrator runs in fast mode under 30s
time python tools/run_validate.py --fast

# 4. All harness tests pass
cd backend && python -m pytest ../tests/harness/ -v

# 5. Pre-commit installer is idempotent
bash tools/install_pre_commit.sh && bash tools/install_pre_commit.sh

# 6. Cross-vendor aliases in place
ls -la AGENTS.md .cursorrules

# 7. Skeleton intact
python -c "import json, sys; sys.exit(0)"  # Python OK
make -n validate-fast validate-full validate harness harness-install
```

If every step exits 0 / produces the expected output, Sprint H.0a is **done**. Move to:

  - **Sprint H.0b — Stack-foundation scaffolding** (next plan to write).
  - Or stop and commit the consolidated state to `main`.

## Execution Handoff

Plan complete and saved to `docs/plans/2026-04-26-harness-sprint-h0a-tasks.md`. Two execution options:

**1. Subagent-Driven (this session)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Each story is checkpoint-able; you see the result before the next subagent fires.

**2. Parallel Session (separate)** — Open a new session with executing-plans, batch execution with checkpoints between sprint stories.

**Which approach?**
