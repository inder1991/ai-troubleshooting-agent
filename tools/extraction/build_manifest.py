#!/usr/bin/env python3
"""Walks the repo and writes the canonical file list for harness extraction.

Output: tools/extraction/manifest.txt — one path per line, sorted, deterministic.

Used by H.3.2 to drive `git filter-repo` (or a plain `cp -r` fallback) when
carving the harness substrate out of DebugDuck into a standalone repo.

H-25:
  Missing input    — silently skip include roots that don't exist.
  Malformed input  — none (filesystem walk only).
  Upstream failed  — none (no subprocess).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Each entry is either a directory (everything inside is included) or a file.
INCLUDE_ROOTS = (
    ".harness",
    "tools",
    "docs/plans/2026-04-26-ai-harness.md",
    "docs/plans/2026-04-26-harness-sprint-h0a-tasks.md",
    "docs/plans/2026-04-26-harness-sprint-h0b-tasks.md",
    "docs/plans/2026-04-26-harness-sprint-h1a-tasks.md",
    "docs/plans/2026-04-26-harness-sprint-h1b-tasks.md",
    "docs/plans/2026-04-26-harness-sprint-h1c-tasks.md",
    "docs/plans/2026-04-26-harness-sprint-h1d-tasks.md",
    "docs/plans/2026-04-26-harness-sprint-h2-tasks.md",
    "docs/plans/2026-04-26-harness-sprint-h3-extract-tasks.md",
    "docs/decisions",
    "tests/harness",
    ".claude/settings.json",
    "CLAUDE.md",
    "AGENTS.md",
    ".cursorrules",
    "Makefile",
    "CONTRIBUTING.md",
)

EXCLUDE_TOKENS = (
    "__pycache__",
    ".venv",
    "node_modules",
    ".pytest_cache",
    "/.harness/baselines/",
    "/.harness/generated/",
)


def collect() -> list[str]:
    """Return sorted list of project-relative paths to include in the carve."""
    out: set[str] = set()
    for entry in INCLUDE_ROOTS:
        path = REPO_ROOT / entry
        if not path.exists():
            continue
        if path.is_file():
            out.add(entry)
            continue
        for f in path.rglob("*"):
            if not f.is_file():
                continue
            f_str = str(f)
            if any(tok in f_str for tok in EXCLUDE_TOKENS):
                continue
            out.add(str(f.relative_to(REPO_ROOT)))
    return sorted(out)


def main() -> int:
    """Write tools/extraction/manifest.txt with one path per line."""
    manifest = REPO_ROOT / "tools" / "extraction" / "manifest.txt"
    paths = collect()
    manifest.write_text("\n".join(paths) + "\n", encoding="utf-8")
    print(f"[INFO] {manifest.relative_to(REPO_ROOT)}: {len(paths)} entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
