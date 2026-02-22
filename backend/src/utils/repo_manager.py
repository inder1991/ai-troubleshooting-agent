"""
Repository management utilities
"""

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Pattern to strip tokens/credentials from URLs in error messages
_TOKEN_URL_RE = re.compile(r"https://[^@]+@")


def _sanitize_stderr(stderr: str) -> str:
    """Remove embedded tokens/credentials from git stderr output."""
    return _TOKEN_URL_RE.sub("https://***@", stderr)


class RepoManager:
    """Manages repository cloning and cleanup"""

    @staticmethod
    def clone_repo(
        github_repo: str,
        target_path: str,
        shallow: bool = True,
        token: str = "",
    ) -> Dict[str, Any]:
        """Clone a GitHub repository.

        Args:
            github_repo: owner/repo string
            target_path: local path to clone into
            shallow: if True, use --depth 1 (default); False for full history
            token: GitHub token for authenticated clones
        """
        try:
            # Clean up if exists
            if os.path.exists(target_path):
                shutil.rmtree(target_path)

            # Create parent directory
            Path(target_path).parent.mkdir(parents=True, exist_ok=True)

            # Build clone URL
            if token:
                repo_url = f"https://x-access-token:{token}@github.com/{github_repo}.git"
            else:
                repo_url = f"https://github.com/{github_repo}.git"
            logger.info("Cloning repository", extra={"extra": {"repo": github_repo, "shallow": shallow}})

            cmd = ["git", "clone"]
            if shallow:
                cmd.extend(["--depth", "1"])
            cmd.extend([repo_url, target_path])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0:
                return {
                    "success": False,
                    "error": f"Git clone failed: {_sanitize_stderr(result.stderr)}"
                }

            # Count files
            file_count = sum(1 for _ in Path(target_path).rglob('*') if _.is_file())

            return {
                "success": True,
                "path": target_path,
                "file_count": file_count
            }

        except Exception as e:
            return {
                "success": False,
                "error": _sanitize_stderr(str(e))
            }

    @staticmethod
    def cleanup_repo(repo_path: str) -> bool:
        """Remove cloned repository"""
        try:
            if os.path.exists(repo_path):
                shutil.rmtree(repo_path)
                return True
            return False
        except Exception as e:
            logger.warning("Cleanup failed: %s", e)
            return False