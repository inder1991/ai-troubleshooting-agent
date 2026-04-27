"""B9 (v1.1.1) — _resolve_latest_tag must semver-sort, not lexically.

Lexical sort ranks v1.10.0 below v1.2.0; once the harness crosses
v1.10 the bug would have pinned a stale ref.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tools.init_harness import _resolve_latest_tag  # noqa: E402


def test_semver_not_lexical():
    fake = (
        "abc\trefs/tags/v1.0.4\n"
        "def\trefs/tags/v1.10.0\n"
        "ghi\trefs/tags/v1.2.0\n"
        "jkl\trefs/tags/v1.10.0^{}\n"
    )
    with patch("subprocess.check_output", return_value=fake):
        assert _resolve_latest_tag("https://x/y.git") == "v1.10.0"


def test_no_tags_fallback_to_main():
    with patch("subprocess.check_output", return_value=""):
        assert _resolve_latest_tag("https://x/y.git") == "main"


def test_rejects_non_semver_tags():
    fake = (
        "abc\trefs/tags/v1.0.4\n"
        "def\trefs/tags/some-feature-branch\n"
        "ghi\trefs/tags/v1.4\n"
        "jkl\trefs/tags/v1.0.4-rc1\n"
    )
    with patch("subprocess.check_output", return_value=fake):
        assert _resolve_latest_tag("https://x/y.git") == "v1.0.4"
