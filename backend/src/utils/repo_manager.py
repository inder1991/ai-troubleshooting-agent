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
    def clone_local(source_path: str, target_path: str) -> Dict[str, Any]:
        """Clone from a local path. Shallow, no network.

        Args:
            source_path: path to an existing local git repository
            target_path: local path to clone into
        """
        try:
            if os.path.exists(target_path):
                shutil.rmtree(target_path)

            Path(target_path).parent.mkdir(parents=True, exist_ok=True)

            logger.info(
                "Cloning local repository",
                extra={"extra": {"source": source_path}},
            )

            subprocess.run(
                ["git", "clone", "--depth", "1", source_path, target_path],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )

            file_count = sum(1 for f in Path(target_path).rglob("*") if f.is_file())

            return {
                "success": True,
                "path": target_path,
                "file_count": file_count,
            }

        except subprocess.CalledProcessError as e:
            return {"success": False, "error": f"Git clone failed: {e.stderr}"}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Git clone timed out"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def apply_sparse_checkout(repo_path: str, target_files: list[str]) -> bool:
        """Enable sparse checkout, keep only dirs containing target files.

        Returns True if succeeded. On failure, disables sparse checkout to
        keep the full clone intact.
        """
        if not target_files:
            return False

        try:
            run_kw = dict(
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )

            subprocess.run(
                ["git", "sparse-checkout", "init", "--no-cone"],
                **run_kw,
            )

            # Collect unique parent directories from target files
            dirs = sorted(
                {str(Path(f).parent) for f in target_files if str(Path(f).parent) != "."}
            )
            if not dirs:
                dirs = ["."]

            # In no-cone mode, use directory glob patterns
            patterns = [f"/{d}/" for d in dirs]

            subprocess.run(
                ["git", "sparse-checkout", "set"] + patterns,
                **run_kw,
            )

            return True

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            logger.warning("Sparse checkout failed, disabling: %s", exc)
            try:
                subprocess.run(
                    ["git", "sparse-checkout", "disable"],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            except Exception:
                pass
            return False

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