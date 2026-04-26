"""Sprint H.0a Story 5 — every directory CLAUDE.md exists, has front-matter,
stays under the 150-line cap (directory rules can be larger than root)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tools._common import parse_front_matter  # noqa: E402

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
