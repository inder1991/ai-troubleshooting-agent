"""H.3.5 hardening — sync_harness tag verification tests.

Validates that the verification gate refuses unsigned tags / branch refs
and only allows the overlay to proceed when the ref is an annotated,
signed tag with a trusted key.

Network-free: every test creates a local "upstream" git repo in tmp_path
and points sync_harness at file:// for that repo.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools" / "sync_harness.py"


def _git(cwd: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True, env=env,
    )


def _seed_upstream(tmp: Path) -> Path:
    """Create a minimal upstream git repo containing a .harness/ skeleton + an annotated (unsigned) tag v1.0.0."""
    upstream = tmp / "upstream"
    upstream.mkdir()
    _git(upstream, "init", "-b", "main")
    _git(upstream, "config", "user.email", "test@local")
    _git(upstream, "config", "user.name", "test")
    (upstream / ".harness").mkdir()
    (upstream / ".harness" / "marker.txt").write_text("upstream content\n")
    (upstream / "tools").mkdir()
    (upstream / "tools" / "_common.py").write_text("# upstream tools _common\n")
    _git(upstream, "add", "-A")
    _git(upstream, "-c", "commit.gpgsign=false", "commit", "-m", "init")
    _git(upstream, "tag", "-a", "v1.0.0", "-m", "v1.0.0 unsigned annotated tag")
    _git(upstream, "tag", "lightweight-tag")  # for the lightweight-tag negative test
    return upstream


def _seed_consumer(tmp: Path, ref: str) -> Path:
    """Create a consumer repo with .harness-version pinning ref."""
    consumer = tmp / "consumer"
    consumer.mkdir()
    (consumer / ".harness-version").write_text(f"{ref}\n")
    return consumer


def _run_sync(consumer: Path, upstream: Path, *extra: str) -> subprocess.CompletedProcess:
    """Invoke sync_harness with --git-url file://upstream from consumer cwd."""
    repo_root_env_aware_script = REPO_ROOT / "tools" / "sync_harness.py"
    # We can't override sync_harness's REPO_ROOT (it's resolved from __file__),
    # so simulate by copying the script into the consumer and running it.
    consumer_tools = consumer / "tools"
    consumer_tools.mkdir(exist_ok=True)
    consumer_script = consumer_tools / "sync_harness.py"
    shutil.copy2(repo_root_env_aware_script, consumer_script)
    return subprocess.run(
        [sys.executable, str(consumer_script),
         "--git-url", f"file://{upstream}",
         *extra],
        capture_output=True, text=True, timeout=30,
    )


def test_unsigned_tag_is_rejected_by_default(tmp_path: Path) -> None:
    """Default mode (verification ON): an unsigned annotated tag must exit 3."""
    upstream = _seed_upstream(tmp_path)
    consumer = _seed_consumer(tmp_path, "v1.0.0")
    result = _run_sync(consumer, upstream)
    assert result.returncode == 3, (
        f"expected exit 3 (signature bad); got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "tag verification failed" in result.stderr


def test_lightweight_tag_is_rejected(tmp_path: Path) -> None:
    """Even if signed, a non-annotated tag must be rejected (no metadata to sign)."""
    upstream = _seed_upstream(tmp_path)
    consumer = _seed_consumer(tmp_path, "lightweight-tag")
    result = _run_sync(consumer, upstream)
    assert result.returncode == 3, (
        f"expected exit 3 (signature bad); got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "not an annotated tag" in result.stderr or "tag verification failed" in result.stderr


def test_no_verify_tag_overlay_proceeds_with_warning(tmp_path: Path) -> None:
    """--no-verify-tag bypasses the gate but emits a loud WARN."""
    upstream = _seed_upstream(tmp_path)
    consumer = _seed_consumer(tmp_path, "v1.0.0")
    result = _run_sync(consumer, upstream, "--no-verify-tag")
    assert result.returncode == 0, (
        f"expected exit 0 with --no-verify-tag; got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "tag verification SKIPPED" in result.stderr
    # Overlay actually happened.
    assert (consumer / ".harness" / "marker.txt").exists()
    assert (consumer / ".harness" / "marker.txt").read_text() == "upstream content\n"
