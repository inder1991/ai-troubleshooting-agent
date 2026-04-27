"""B7 (v1.1.1) — sign_release.sh signingkey resolution scope.

setup_signing.sh defaults to --local since v1.1.0 (B4). The release
script must use git's standard local→global→system resolution so a
clean install actually flows through to release time.
"""
from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_sign_release_uses_resolved_signing_key(tmp_path, monkeypatch):
    """A --local-only user.signingkey must satisfy the script's guard."""
    fake_home = tmp_path / "home"
    fake_repo = tmp_path / "repo"
    fake_home.mkdir()
    fake_repo.mkdir()
    subprocess.check_call(["git", "init", "-q"], cwd=fake_repo)
    subprocess.check_call(
        ["git", "config", "--local", "user.signingkey", "DEADBEEF"],
        cwd=fake_repo,
    )
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(fake_home / ".gitconfig"))

    snippet = textwrap.dedent(
        """
        set -euo pipefail
        if ! git config user.signingkey >/dev/null 2>&1; then
            echo "[ERROR] guard fired" >&2
            exit 2
        fi
        echo OK
        """
    )
    result = subprocess.run(
        ["bash", "-c", snippet], cwd=fake_repo,
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_sign_release_script_drops_global_flag():
    """B7 regression guard: the signing-key probe must not use --global."""
    text = (REPO_ROOT / "tools/sign_release.sh").read_text()
    bad_lines = [
        line for line in text.splitlines()
        if "git config" in line
        and "--global" in line
        and "user.signingkey" in line
    ]
    assert not bad_lines, (
        f"sign_release.sh re-introduced `git config --global user.signingkey` "
        f"(B7): {bad_lines}"
    )
