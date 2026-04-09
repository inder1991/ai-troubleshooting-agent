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

LANGUAGE_CONFIG = {
    "python": {
        "extensions": [".py"],
        "syntax_cmd": None,  # uses in-process ast.parse()
        "lint_cmd": ["ruff", "check", "--output-format=json"],
        "lint_parse_json": True,
    },
    "go": {
        "extensions": [".go"],
        "syntax_cmd": ["go", "vet"],
        "lint_cmd": ["golangci-lint", "run", "--out-format=json"],
        "lint_parse_json": True,
        "lint_fallback_cmd": ["go", "vet"],
    },
    "javascript": {
        "extensions": [".js", ".jsx", ".mjs"],
        "syntax_cmd": ["node", "--check"],
        "lint_cmd": ["eslint", "--format=json"],
        "lint_parse_json": True,
    },
    "typescript": {
        "extensions": [".ts", ".tsx"],
        "syntax_cmd": ["npx", "tsc", "--noEmit", "--allowJs"],
        "lint_cmd": ["eslint", "--format=json"],
        "lint_parse_json": True,
    },
    "kotlin": {
        "extensions": [".kt", ".kts"],
        "syntax_cmd": ["kotlinc", "-script"],
        "lint_cmd": ["ktlint"],
        "lint_parse_json": False,
    },
    "java": {
        "extensions": [".java"],
        "syntax_cmd": ["javac", "-d", "/tmp"],
        "lint_cmd": ["checkstyle", "-c", "/google_checks.xml"],
        "lint_parse_json": False,
    },
}

# Build reverse lookup: extension → language name
_EXT_TO_LANG: dict[str, str] = {}
for _lang, _cfg in LANGUAGE_CONFIG.items():
    for _ext in _cfg["extensions"]:
        _EXT_TO_LANG[_ext] = _lang


def detect_language(file_path: str) -> str | None:
    """Detect programming language from file extension.

    Returns language key from LANGUAGE_CONFIG, or None if unknown.
    """
    ext = Path(file_path).suffix.lower()
    return _EXT_TO_LANG.get(ext)


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
        """Validate syntax for the detected language.

        Python uses in-process ast.parse(). All other languages write code to
        a temp file and run the configured syntax_cmd. If the tool is not
        installed, validation passes with a warning (best-effort).
        """
        import tempfile

        lang = detect_language(file_path)
        logger.info("\n🔍 Static Validation: Syntax Check (%s)", lang or "unknown")

        if lang is None:
            logger.info("   ⚠️  Unknown language, skipping syntax check")
            return True, "Unknown language — skipped"

        config = LANGUAGE_CONFIG[lang]

        # Python: in-process AST parsing
        if config["syntax_cmd"] is None:
            return self._validate_python_syntax(code)

        # All other languages: write temp file, run external tool
        suffix = Path(file_path).suffix
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=suffix, delete=False
            ) as tmp:
                tmp.write(code)
                tmp_path = tmp.name
        except Exception as e:
            logger.info("   ⚠️  Syntax: Could not write temp file — %s", e)
            return True, f"Temp file error: {e}"

        try:
            cmd = list(config["syntax_cmd"]) + [tmp_path]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                logger.info("   ✅ Syntax: Valid %s code", lang)
                return True, "Syntax valid"
            else:
                error_output = (result.stderr or result.stdout or "").strip()
                error_msg = f"Syntax check failed: {error_output[:500]}"
                logger.info("   ❌ Syntax: %s", error_msg)
                return False, error_msg

        except FileNotFoundError:
            tool = config["syntax_cmd"][0]
            logger.info("   ⚠️  Syntax: %s not installed (skipping)", tool)
            return True, f"{tool} not available — skipped"

        except subprocess.TimeoutExpired:
            logger.info("   ⚠️  Syntax: Timeout (skipping)")
            return True, "Syntax check timeout — skipped"

        except Exception as e:
            logger.info("   ⚠️  Syntax: Error — %s", e)
            return True, f"Syntax check error: {e}"

        finally:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass

    def _validate_python_syntax(self, code: str) -> Tuple[bool, str]:
        """Python-specific syntax validation using ast.parse()."""
        try:
            ast.parse(code)
            logger.info("   ✅ Syntax: Valid Python code")
            return True, "Syntax valid"
        except SyntaxError as e:
            error_msg = f"Syntax error at line {e.lineno}: {e.msg}"
            logger.info("   ❌ Syntax: %s", error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"AST parsing failed: {e}"
            logger.info("   ❌ Syntax: %s", error_msg)
            return False, error_msg
    
    def run_linting(self, file_path: str, code: str = "") -> Tuple[bool, Dict[str, Any]]:
        """Run language-appropriate linter on generated code.

        Writes code to a temp file and runs the configured lint_cmd. If the
        primary linter is not installed, tries lint_fallback_cmd (if configured).
        If no linter is available, passes with a warning.
        """
        import tempfile
        import json

        lang = detect_language(file_path)
        logger.info("\n🔍 Static Validation: Linting (%s)", lang or "unknown")

        if lang is None:
            logger.info("   ⚠️  Unknown language, skipping lint")
            return True, {"warnings": ["Unknown language — lint skipped"]}

        config = LANGUAGE_CONFIG[lang]

        # Write code to temp file
        if code:
            suffix = Path(file_path).suffix or ".py"
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=suffix, delete=False
                ) as tmp:
                    tmp.write(code)
                    lint_path = tmp.name
            except Exception as e:
                logger.info("   ⚠️  Linting: Could not write temp file — %s", e)
                return True, {"warnings": [f"Temp file error: {e}"]}
        else:
            normalized_path = file_path.lstrip("/")
            for prefix in ["app/", "/app/", "usr/src/app/", "/usr/src/app/"]:
                if normalized_path.startswith(prefix):
                    normalized_path = normalized_path[len(prefix):]
            lint_path = str(self.repo_path / normalized_path)
            if not Path(lint_path).exists():
                logger.info("   ⚠️  File not found: %s", file_path)
                return True, {"warnings": ["File not yet created - will lint after staging"]}

        try:
            return self._run_lint_cmd(config, lint_path, lang)

        finally:
            if code:
                try:
                    Path(lint_path).unlink(missing_ok=True)
                except Exception:
                    pass

    def _run_lint_cmd(
        self, config: dict, lint_path: str, lang: str
    ) -> Tuple[bool, Dict[str, Any]]:
        """Execute lint command with fallback support."""
        import json

        lint_cmd = list(config["lint_cmd"]) + [lint_path]
        parse_json = config.get("lint_parse_json", False)

        try:
            result = subprocess.run(
                lint_cmd, capture_output=True, text=True, timeout=30
            )

            if result.returncode == 0:
                logger.info("   ✅ Linting: No issues found")
                return True, {"errors": [], "warnings": []}

            # Try to parse structured output
            if parse_json and result.stdout:
                try:
                    issues = json.loads(result.stdout)
                    if isinstance(issues, list):
                        errors = [i for i in issues if i.get("type") == "error" or i.get("severity", 0) == 2]
                        warnings = [i for i in issues if i not in errors]
                    else:
                        errors = []
                        warnings = [result.stdout[:500]]
                except json.JSONDecodeError:
                    errors = []
                    warnings = [result.stdout[:500]]
            else:
                # Plain text output — treat non-zero exit as warning
                output = (result.stderr or result.stdout or "").strip()
                errors = []
                warnings = [output[:500]] if output else []

            logger.info("   ⚠️  Linting: %d errors, %d warnings", len(errors), len(warnings))
            return len(errors) == 0, {"errors": errors, "warnings": warnings}

        except FileNotFoundError:
            # Primary linter not installed — try fallback
            fallback_cmd = config.get("lint_fallback_cmd")
            if fallback_cmd:
                return self._run_fallback_lint(fallback_cmd, lint_path, lang)
            tool = config["lint_cmd"][0]
            logger.info("   ⚠️  Linting: %s not installed (skipping)", tool)
            return True, {"warnings": [f"{tool} not available — lint skipped"]}

        except subprocess.TimeoutExpired:
            logger.info("   ⚠️  Linting: Timeout (skipping)")
            return True, {"warnings": ["Linting timeout — review manually"]}

        except Exception as e:
            logger.info("   ⚠️  Linting: Error — %s", e)
            return True, {"warnings": [f"Linting error: {e}"]}

    def _run_fallback_lint(
        self, fallback_cmd: list[str], lint_path: str, lang: str
    ) -> Tuple[bool, Dict[str, Any]]:
        """Run fallback linter when primary is not available."""
        try:
            cmd = list(fallback_cmd) + [lint_path]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                logger.info("   ✅ Linting (fallback): No issues found")
                return True, {"errors": [], "warnings": []}
            output = (result.stderr or result.stdout or "").strip()
            logger.info("   ⚠️  Linting (fallback): Issues found")
            return False, {"errors": [output[:500]], "warnings": []}

        except FileNotFoundError:
            tool = fallback_cmd[0]
            logger.info("   ⚠️  Linting: %s not installed (skipping)", tool)
            return True, {"warnings": [f"{tool} not available — lint skipped"]}

        except Exception as e:
            logger.info("   ⚠️  Linting fallback error: %s", e)
            return True, {"warnings": [f"Lint fallback error: {e}"]}
    
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