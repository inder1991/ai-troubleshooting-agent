#!/usr/bin/env python3
"""Enforce H-6: every CLAUDE.md and .harness/*.md declares `owner:` in front-matter.

When invoked with --target <file>, checks that one file. When invoked
without --target, walks the repo and checks every applicable file.

H-25:
  Missing target → ERROR with suggestion (loud, never silent).
  Malformed front-matter → reported as missing owner (front-matter parser
                            returns empty dict on parse failure).
  Walking with no files → exit 0 (nothing to enforce).
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
    root = REPO_ROOT / "CLAUDE.md"
    if root.exists():
        targets.append(root)
    for path in REPO_ROOT.rglob("CLAUDE.md"):
        if path == root:
            continue
        if any(part in (".git", "node_modules", "__pycache__", ".venv", "venv", "site-packages", "dist", ".pytest_cache") for part in path.parts):
            continue
        targets.append(path)
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
