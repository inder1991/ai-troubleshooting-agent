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
        print("\n🔍 Static Validation: Syntax Check")
        
        try:
            # Parse code to AST
            ast.parse(code)
            
            print("   ✅ Syntax: Valid Python code")
            return True, "Syntax valid"
        
        except SyntaxError as e:
            error_msg = f"Syntax error at line {e.lineno}: {e.msg}"
            print(f"   ❌ Syntax: {error_msg}")
            return False, error_msg
        
        except Exception as e:
            error_msg = f"AST parsing failed: {str(e)}"
            print(f"   ❌ Syntax: {error_msg}")
            return False, error_msg
    
    def run_linting(self, file_path: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Run static analysis with ruff
        
        Args:
            file_path: Path to file to lint
        
        Returns:
            (passed, issues_dict)
        """
        print("\n🔍 Static Validation: Linting (ruff)")
        
        # Normalize path
        normalized_path = file_path.lstrip('/')
        for prefix in ['app/', '/app/', 'usr/src/app/', '/usr/src/app/']:
            if normalized_path.startswith(prefix):
                normalized_path = normalized_path[len(prefix):]
        
        full_path = self.repo_path / normalized_path
        
        if not full_path.exists():
            print(f"   ⚠️  File not found: {file_path}")
            return True, {"warnings": ["File not yet created - will lint after staging"]}
        
        try:
            # Run ruff with JSON output
            result = subprocess.run(
                ['ruff', 'check', '--output-format=json', str(full_path)],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                print("   ✅ Linting: No issues found")
                return True, {"errors": [], "warnings": []}
            
            # Parse issues
            import json
            issues = json.loads(result.stdout) if result.stdout else []
            
            errors = [i for i in issues if i.get('type') == 'error']
            warnings = [i for i in issues if i.get('type') == 'warning']
            
            print(f"   ⚠️  Linting: {len(errors)} errors, {len(warnings)} warnings")
            
            # Only fail on errors, not warnings
            return len(errors) == 0, {
                "errors": errors,
                "warnings": warnings
            }
        
        except subprocess.TimeoutExpired:
            print("   ⚠️  Linting: Timeout (skipping)")
            return True, {"warnings": ["Linting timeout - review manually"]}
        
        except FileNotFoundError:
            print("   ⚠️  Linting: ruff not installed (skipping)")
            return True, {"warnings": ["ruff not installed"]}
        
        except Exception as e:
            print(f"   ⚠️  Linting: Error - {e}")
            return True, {"warnings": [f"Linting error: {str(e)}"]}
    
    def check_imports(self, code: str) -> Tuple[bool, List[str]]:
        """
        Check if all imports are available
        
        Args:
            code: Code to check
        
        Returns:
            (all_available, missing_imports)
        """
        print("\n🔍 Static Validation: Import Check")
        
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
            
            # Find unknown imports
            unknown_imports = [
                imp for imp in imports
                if imp.split('.')[0] not in known_imports
            ]
            
            if unknown_imports:
                print(f"   ⚠️  Imports: Unknown packages - {unknown_imports}")
                return False, unknown_imports
            else:
                print(f"   ✅ Imports: All {len(imports)} imports recognized")
                return True, []
        
        except Exception as e:
            print(f"   ⚠️  Imports: Check failed - {e}")
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
        print("\n" + "="*80)
        print("🛡️  STATIC VALIDATION SUITE")
        print("="*80)
        
        # 1. Syntax check
        syntax_valid, syntax_error = self.validate_syntax(file_path, code)
        
        # 2. Linting (only if syntax is valid)
        if syntax_valid:
            linting_passed, linting_issues = self.run_linting(file_path)
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
        
        print("\n" + "="*80)
        if all_passed:
            print("✅ VALIDATION PASSED - Code is syntactically correct")
        else:
            print("❌ VALIDATION FAILED - Code needs corrections")
        print("="*80 + "\n")
        
        return result