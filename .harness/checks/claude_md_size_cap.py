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
            f"Trim to <= {LIMIT} lines. Move detail to per-directory CLAUDE.md or .harness/*.md.",
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
