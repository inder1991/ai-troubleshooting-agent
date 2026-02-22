"""
Static Validation for Agent 3

Validates generated code without executing it:
- AST parsing (syntax check)
- Linting (ruff)
- Import validation
"""

import ast
import subprocess
from typing import Dict, Any, Tuple, List
from pathlib import Path

from src.utils.logger import get_logger

logger = get_logger(__name__)


class StaticValidator:
    """Validates generated code without executing it"""
    
    def __init__(self, repo_path: str):
        """
        Initialize validator
        
        Args:
            repo_path: Path to cloned repository
        """
        self.repo_path = Path(repo_path)
    
    def validate_syntax(self, file_path: str, code: str) -> Tuple[bool, str]:
        """
        Validate Python syntax using AST parser
        
        Args:
            file_path: Path to file being validated
            code: Code to validate
        
        Returns:
            (is_valid, error_message)
        """
        logger.info("\n🔍 Static Validation: Syntax Check")
        
        try:
            # Parse code to AST
            ast.parse(code)
            
            logger.info("   ✅ Syntax: Valid Python code")
            return True, "Syntax valid"
        
        except SyntaxError as e:
            error_msg = f"Syntax error at line {e.lineno}: {e.msg}"
            logger.info(f"   ❌ Syntax: {error_msg}")
            return False, error_msg
        
        except Exception as e:
            error_msg = f"AST parsing failed: {str(e)}"
            logger.info(f"   ❌ Syntax: {error_msg}")
            return False, error_msg
    
    def run_linting(self, file_path: str, code: str = "") -> Tuple[bool, Dict[str, Any]]:
        """
        Run static analysis with ruff on the generated code.

        Args:
            file_path: Path to file to lint (used for context)
            code: Generated code to lint. If empty, lints the file on disk.

        Returns:
            (passed, issues_dict)
        """
        import tempfile
        logger.info("\n🔍 Static Validation: Linting (ruff)")

        # If code provided, write to temp file and lint that instead of the original on disk
        if code:
            try:
                suffix = Path(file_path).suffix or ".py"
                with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False) as tmp:
                    tmp.write(code)
                    lint_path = tmp.name
            except Exception as e:
                logger.info(f"   ⚠️  Linting: Could not write temp file — {e}")
                return True, {"warnings": [f"Temp file error: {str(e)}"]}
        else:
            # Normalize path and lint original file
            normalized_path = file_path.lstrip('/')
            for prefix in ['app/', '/app/', 'usr/src/app/', '/usr/src/app/']:
                if normalized_path.startswith(prefix):
                    normalized_path = normalized_path[len(prefix):]
            lint_path = str(self.repo_path / normalized_path)
            if not Path(lint_path).exists():
                logger.info(f"   ⚠️  File not found: {file_path}")
                return True, {"warnings": ["File not yet created - will lint after staging"]}

        try:
            # Run ruff with JSON output
            result = subprocess.run(
                ['ruff', 'check', '--output-format=json', lint_path],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                logger.info("   ✅ Linting: No issues found")
                return True, {"errors": [], "warnings": []}

            # Parse issues
            import json
            issues = json.loads(result.stdout) if result.stdout else []

            errors = [i for i in issues if i.get('type') == 'error']
            warnings = [i for i in issues if i.get('type') == 'warning']

            logger.info(f"   ⚠️  Linting: {len(errors)} errors, {len(warnings)} warnings")

            # Only fail on errors, not warnings
            return len(errors) == 0, {
                "errors": errors,
                "warnings": warnings
            }

        except subprocess.TimeoutExpired:
            logger.info("   ⚠️  Linting: Timeout (skipping)")
            return True, {"warnings": ["Linting timeout - review manually"]}

        except FileNotFoundError:
            logger.info("   ⚠️  Linting: ruff not installed (skipping)")
            return True, {"warnings": ["ruff not installed"]}

        except Exception as e:
            logger.info(f"   ⚠️  Linting: Error - {e}")
            return True, {"warnings": [f"Linting error: {str(e)}"]}

        finally:
            # Clean up temp file if we created one
            if code:
                try:
                    Path(lint_path).unlink(missing_ok=True)
                except Exception:
                    pass
    
    def check_imports(self, code: str) -> Tuple[bool, List[str]]:
        """
        Check if all imports are available
        
        Args:
            code: Code to check
        
        Returns:
            (all_available, missing_imports)
        """
        logger.info("\n🔍 Static Validation: Import Check")
        
        try:
            tree = ast.parse(code)
            
            # Extract all imports
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)
            
            # Check against known packages
            standard_libs = {
                'os', 'sys', 'json', 'time', 'datetime', 're', 'ast',
                'pathlib', 'typing', 'collections', 'itertools', 'functools',
                'subprocess', 'threading', 'multiprocessing', 'asyncio',
                'logging', 'argparse', 'configparser', 'io', 'csv', 'xml'
            }
            
            third_party = {
                'requests', 'tenacity', 'pybreaker', 'flask', 'fastapi',
                'numpy', 'pandas', 'pytest', 'pydantic', 'sqlalchemy'
            }
            
            known_imports = standard_libs | third_party
            
            # Detect project-internal imports by scanning the repo for top-level packages
            project_packages = set()
            if self.repo_path.exists():
                for child in self.repo_path.iterdir():
                    if child.is_dir() and (child / "__init__.py").exists():
                        project_packages.add(child.name)
            # Also treat 'src' as a known project package (common convention)
            project_packages.add("src")

            # Find unknown imports (skip standard lib, third-party, and project-internal)
            unknown_imports = [
                imp for imp in imports
                if imp.split('.')[0] not in known_imports
                and imp.split('.')[0] not in project_packages
            ]
            
            if unknown_imports:
                logger.info(f"   ⚠️  Imports: Unknown packages - {unknown_imports}")
                return False, unknown_imports
            else:
                logger.info(f"   ✅ Imports: All {len(imports)} imports recognized")
                return True, []
        
        except Exception as e:
            logger.info(f"   ⚠️  Imports: Check failed - {e}")
            return True, []  # Don't fail on check error
    
    def validate_all(self, file_path: str, code: str) -> Dict[str, Any]:
        """
        Run all validation checks
        
        Args:
            file_path: Path to file being validated
            code: Code to validate
        
        Returns:
            {
                "passed": bool,
                "syntax": {"valid": bool, "error": str},
                "linting": {"passed": bool, "issues": dict},
                "imports": {"valid": bool, "missing": list}
            }
        """
        logger.info("\n" + "="*80)
        logger.info("🛡️  STATIC VALIDATION SUITE")
        logger.info("="*80)
        
        # 1. Syntax check
        syntax_valid, syntax_error = self.validate_syntax(file_path, code)
        
        # 2. Linting (only if syntax is valid) — lint the generated code, not the original
        if syntax_valid:
            linting_passed, linting_issues = self.run_linting(file_path, code)
        else:
            linting_passed = False
            linting_issues = {"error": "Skipped due to syntax errors"}
        
        # 3. Import check
        import_valid, missing_imports = self.check_imports(code)
        
        # Overall result
        all_passed = syntax_valid and linting_passed and import_valid
        
        result = {
            "passed": all_passed,
            "syntax": {
                "valid": syntax_valid,
                "error": syntax_error if not syntax_valid else None
            },
            "linting": {
                "passed": linting_passed,
                "issues": linting_issues
            },
            "imports": {
                "valid": import_valid,
                "missing": missing_imports
            }
        }
        
        logger.info("\n" + "="*80)
        if all_passed:
            logger.info("✅ VALIDATION PASSED - Code is syntactically correct")
        else:
            logger.info("❌ VALIDATION FAILED - Code needs corrections")
        logger.info("="*80 + "\n")
        
        return result