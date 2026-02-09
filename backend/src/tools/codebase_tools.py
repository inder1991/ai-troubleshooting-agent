"""
Codebase Tools for Navigating and Analyzing Code
Provides grep search, file reading, and directory structure
Location: backend/src/tools/codebase_tools.py
"""

import subprocess
from pathlib import Path
from typing import List, Dict, Any


class CodebaseTools:
    """Tools for navigating and analyzing cloned codebases"""
    
    def __init__(self, repo_path: str):
        """
        Initialize codebase tools
        
        Args:
            repo_path: Path to cloned repository
        """
        self.repo_path = Path(repo_path)
        
        if not self.repo_path.exists():
            print(f"⚠️  Warning: Repository path doesn't exist: {repo_path}")
    
    def grep_search(self, pattern: str, file_extension: str = "*", max_results: int = 50) -> List[Dict[str, Any]]:
        """
        Search for pattern in codebase using grep
        
        Args:
            pattern: Search pattern (can be regex)
            file_extension: File extension to search (e.g., "py", "js") or "*" for all
            max_results: Maximum number of results to return
            
        Returns:
            List of matches: [{"file": str, "line": str, "content": str}, ...]
        """
        try:
            if not self.repo_path.exists():
                return [{"error": f"Repository path doesn't exist: {self.repo_path}"}]
            
            # Build grep command
            if file_extension == "*":
                cmd = f"grep -rn '{pattern}' {self.repo_path}"
            else:
                cmd = f"grep -rn --include='*.{file_extension}' '{pattern}' {self.repo_path}"
            
            # Add common exclusions
            cmd += " --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=venv --exclude-dir=__pycache__"
            
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            matches = []
            for line in result.stdout.split('\n')[:max_results]:
                if line:
                    parts = line.split(':', 2)
                    if len(parts) >= 3:
                        file_path = parts[0].replace(str(self.repo_path) + '/', '')
                        matches.append({
                            'file': file_path,
                            'line': parts[1],
                            'content': parts[2].strip()
                        })
            
            return matches
            
        except subprocess.TimeoutExpired:
            return [{"error": "Grep search timeout after 30 seconds"}]
        except Exception as e:
            return [{"error": f"Grep search failed: {str(e)}"}]
    
    def read_file(self, file_path: str, start_line: int = 0, end_line: int = -1) -> str:
        """
        Read file content with optional line range
        
        Args:
            file_path: Relative path to file from repo root
            start_line: Starting line number (0-indexed)
            end_line: Ending line number (-1 for end of file)
            
        Returns:
            File content as string, or error message
        """
        try:
            # Handle both absolute and relative paths
            if file_path.startswith('/'):
                # If file_path is absolute, check if it's under repo_path
                full_path = Path(file_path)
                if not str(full_path).startswith(str(self.repo_path)):
                    # Try as relative path
                    full_path = self.repo_path / file_path.lstrip('/')
            else:
                full_path = self.repo_path / file_path
            
            if not full_path.exists():
                # Try common variations
                variations = [
                    self.repo_path / file_path,
                    self.repo_path / file_path.lstrip('./'),
                    self.repo_path / 'src' / file_path,
                    self.repo_path / 'app' / file_path,
                ]
                
                for variant in variations:
                    if variant.exists():
                        full_path = variant
                        break
                else:
                    return f"Error: File not found: {file_path}"
            
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                
                # Apply line range
                if end_line == -1:
                    end_line = len(lines)
                
                # Add line numbers
                numbered_lines = []
                for i in range(start_line, min(end_line, len(lines))):
                    numbered_lines.append(f"{i+1:4d} | {lines[i]}")
                
                return ''.join(numbered_lines)
                
        except Exception as e:
            return f"Error reading file: {str(e)}"
    
    def get_file_structure(self, directory: str = "", max_depth: int = 3) -> List[str]:
        """
        Get directory structure
        
        Args:
            directory: Subdirectory to list (empty for root)
            max_depth: Maximum depth to traverse
            
        Returns:
            List of file paths
        """
        try:
            target_path = self.repo_path / directory if directory else self.repo_path
            
            if not target_path.exists():
                return [f"Error: Directory not found: {directory}"]
            
            files = []
            
            def walk_directory(path: Path, current_depth: int = 0):
                if current_depth > max_depth:
                    return
                
                try:
                    for item in path.iterdir():
                        # Skip hidden files and common ignores
                        if item.name.startswith('.') or item.name in ['node_modules', '__pycache__', 'venv']:
                            continue
                        
                        if item.is_file():
                            rel_path = item.relative_to(self.repo_path)
                            files.append(str(rel_path))
                        elif item.is_dir():
                            walk_directory(item, current_depth + 1)
                except PermissionError:
                    pass
            
            walk_directory(target_path)
            return files[:200]  # Limit to 200 files
            
        except Exception as e:
            return [f"Error: {str(e)}"]
    
    def find_function(self, function_name: str) -> List[Dict[str, Any]]:
        """
        Find function/method definitions in codebase
        
        Args:
            function_name: Name of function to find
            
        Returns:
            List of matches with file and line number
        """
        # Search for function definitions (supports Python, JS, Java, etc.)
        patterns = [
            f"def {function_name}",  # Python
            f"function {function_name}",  # JavaScript
            f"const {function_name} =",  # JavaScript arrow function
            f"public .* {function_name}\\(",  # Java
        ]
        
        all_matches = []
        for pattern in patterns:
            matches = self.grep_search(pattern, max_results=10)
            all_matches.extend([m for m in matches if 'error' not in m])
        
        return all_matches
    
    def get_imports(self, file_path: str) -> List[str]:
        """
        Extract import statements from a file
        
        Args:
            file_path: Path to file
            
        Returns:
            List of import statements
        """
        content = self.read_file(file_path)
        
        if content.startswith("Error"):
            return []
        
        imports = []
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('import ') or line.startswith('from ') or line.startswith('require('):
                imports.append(line)
        
        return imports[:50]  # Limit to 50 imports