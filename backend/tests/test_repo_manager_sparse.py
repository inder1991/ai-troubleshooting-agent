"""Tests for RepoManager sparse checkout and local clone support."""

import os
import subprocess

import pytest

from src.utils.repo_manager import RepoManager


@pytest.fixture
def fake_repo(tmp_path):
    """Create a local git repo with a handful of files."""
    repo = tmp_path / "fake_repo"
    repo.mkdir()

    files = {
        "src/app.py": "print('app')\n",
        "src/utils.py": "print('utils')\n",
        "tests/test_app.py": "print('test')\n",
        "README.md": "# Readme\n",
        "docs/guide.md": "# Guide\n",
    }

    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)

    subprocess.run(["git", "init"], cwd=str(repo), capture_output=True, check=True)
    subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=str(repo),
        capture_output=True,
        check=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t"},
    )

    return repo


class TestCloneLocal:
    def test_clone_shallow(self, fake_repo, tmp_path):
        target = str(tmp_path / "cloned")
        result = RepoManager.clone_local(str(fake_repo), target)

        assert result["success"] is True
        assert result["path"] == target
        assert result["file_count"] >= 5

        # Verify key files exist
        assert os.path.isfile(os.path.join(target, "src", "app.py"))
        assert os.path.isfile(os.path.join(target, "README.md"))


class TestSparseCheckout:
    def test_sparse_checkout(self, fake_repo, tmp_path):
        target = str(tmp_path / "cloned")
        RepoManager.clone_local(str(fake_repo), target)

        ok = RepoManager.apply_sparse_checkout(target, ["src/app.py", "src/utils.py"])
        assert ok is True

        # src/ files should exist
        assert os.path.isfile(os.path.join(target, "src", "app.py"))
        assert os.path.isfile(os.path.join(target, "src", "utils.py"))

        # README.md should NOT exist after sparse checkout
        assert not os.path.isfile(os.path.join(target, "README.md"))

    def test_sparse_checkout_fallback_on_failure(self, fake_repo, tmp_path):
        target = str(tmp_path / "cloned")
        RepoManager.clone_local(str(fake_repo), target)

        # Empty list should return False without breaking the clone
        ok = RepoManager.apply_sparse_checkout(target, [])
        assert ok is False

        # Full clone files should still be present
        assert os.path.isfile(os.path.join(target, "src", "app.py"))
        assert os.path.isfile(os.path.join(target, "README.md"))
        assert os.path.isfile(os.path.join(target, "docs", "guide.md"))
