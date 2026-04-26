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
