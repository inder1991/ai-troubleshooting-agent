"""B15 (v1.2.0) — sync_harness must accept a --trust-key fingerprint
pin and reject signatures that don't match.

git verify-tag accepts ANY key in the consumer's local keyring, which
downgrades the trust model. --trust-key (or HARNESS_TRUST_KEY env)
requires the tag's signature to come from a specific fingerprint.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tools import sync_harness  # noqa: E402


def test_trust_key_flag_registered():
    """--trust-key must appear in the parser's recognized flags."""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools/sync_harness.py"), "--help"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
    assert "--trust-key" in result.stdout, (
        "sync_harness --help must advertise --trust-key for fingerprint pinning"
    )
    assert "HARNESS_TRUST_KEY" in result.stdout, (
        "--trust-key help must mention the HARNESS_TRUST_KEY env var fallback"
    )


def test_verify_tag_accepts_matching_fingerprint(tmp_path):
    """When trust_fingerprint matches the signature's VALIDSIG line,
    _verify_tag returns ok=True."""
    fake_clone = tmp_path / "clone"
    fake_clone.mkdir()

    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["git", "cat-file", "-t"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="tag\n", stderr="")
        if cmd[:2] == ["git", "verify-tag"]:
            stderr = (
                "gpg: Signature made ...\n"
                "[GNUPG:] VALIDSIG 73A7AF8F04F40EC9 2026-04-27 1745... 0 4 0 22 8 73A7AF8F04F40EC9\n"
                "gpg: Good signature\n"
            )
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr=stderr)
        raise AssertionError(f"unexpected command: {cmd}")

    with patch("subprocess.run", side_effect=fake_run):
        ok, msg = sync_harness._verify_tag(
            fake_clone, "v1.0.0", trust_fingerprint="73A7AF8F04F40EC9",
        )
    assert ok, f"expected ok; got {msg}"


def test_verify_tag_rejects_mismatched_fingerprint(tmp_path):
    """When trust_fingerprint differs from VALIDSIG, _verify_tag fails."""
    fake_clone = tmp_path / "clone"
    fake_clone.mkdir()

    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["git", "cat-file", "-t"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="tag\n", stderr="")
        if cmd[:2] == ["git", "verify-tag"]:
            stderr = (
                "[GNUPG:] VALIDSIG ATTACKER_FPR_DEADBEEF 2026-04-27 1745... 0 4 0 22 8 ATTACKER_FPR_DEADBEEF\n"
            )
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr=stderr)
        raise AssertionError(f"unexpected command: {cmd}")

    with patch("subprocess.run", side_effect=fake_run):
        ok, msg = sync_harness._verify_tag(
            fake_clone, "v1.0.0", trust_fingerprint="73A7AF8F04F40EC9",
        )
    assert not ok, "fingerprint mismatch must reject"
    assert "fingerprint" in msg.lower()
    assert "73A7AF8F04F40EC9" in msg
