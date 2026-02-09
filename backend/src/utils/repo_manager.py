"""
Repository management utilities
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any


class RepoManager:
    """Manages repository cloning and cleanup"""
    
    @staticmethod
    def clone_repo(github_repo: str, target_path: str) -> Dict[str, Any]:
        """Clone a GitHub repository"""
        try:
            # Clean up if exists
            if os.path.exists(target_path):
                shutil.rmtree(target_path)
            
            # Create parent directory
            Path(target_path).parent.mkdir(parents=True, exist_ok=True)
            
            # Clone repository
            repo_url = f"https://github.com/{github_repo}.git"
            print(f"Cloning {repo_url}...")
            
            result = subprocess.run(
                ["git", "clone", "--depth", "1", repo_url, target_path],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                return {
                    "success": False,
                    "error": f"Git clone failed: {result.stderr}"
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
                "error": str(e)
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
            print(f"⚠️  Cleanup failed: {e}")
            return False