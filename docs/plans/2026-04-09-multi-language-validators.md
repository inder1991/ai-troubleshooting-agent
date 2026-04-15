# Multi-Language Validators Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend `StaticValidator` to validate generated code for Go, JavaScript, TypeScript, Kotlin, and Java — not just Python.

**Architecture:** Config-driven approach where each language maps to external tool commands for syntax checking and linting. Language is detected from file extension. Tools are best-effort — if not installed, validation passes with a warning. Self-correction prompt is updated to include the detected language.

**Tech Stack:** Python subprocess (calling `go vet`, `node --check`, `npx tsc`, `eslint`, `golangci-lint`, `kotlinc`, `ktlint`, `javac`, `checkstyle`), pytest with unittest.mock for testing.

---

### Task 1: Language Detection + Config Registry

**Files:**
- Modify: `backend/src/agents/agent3/validators.py:1-18`
- Test: `backend/tests/test_static_validators.py`

**Step 1: Write failing tests for language detection**

Create `backend/tests/test_static_validators.py`:

```python
"""Tests for multi-language StaticValidator."""

import pytest
from unittest.mock import patch, MagicMock
from src.agents.agent3.validators import StaticValidator, detect_language, LANGUAGE_CONFIG


class TestDetectLanguage:
    def test_python(self):
        assert detect_language("src/main.py") == "python"

    def test_go(self):
        assert detect_language("cmd/server/main.go") == "go"

    def test_javascript(self):
        assert detect_language("src/index.js") == "javascript"

    def test_javascript_jsx(self):
        assert detect_language("src/App.jsx") == "javascript"

    def test_typescript(self):
        assert detect_language("src/index.ts") == "typescript"

    def test_typescript_tsx(self):
        assert detect_language("src/App.tsx") == "typescript"

    def test_kotlin(self):
        assert detect_language("src/Main.kt") == "kotlin"

    def test_java(self):
        assert detect_language("src/Main.java") == "java"

    def test_unknown_extension(self):
        assert detect_language("README.md") is None

    def test_no_extension(self):
        assert detect_language("Makefile") is None

    def test_config_has_all_languages(self):
        expected = {"python", "go", "javascript", "typescript", "kotlin", "java"}
        assert set(LANGUAGE_CONFIG.keys()) == expected
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend && python -m pytest tests/test_static_validators.py -v`
Expected: FAIL with `ImportError` — `detect_language` and `LANGUAGE_CONFIG` don't exist yet.

**Step 3: Implement language config and detection**

At the top of `backend/src/agents/agent3/validators.py`, after the imports and before the `StaticValidator` class, add:

```python
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
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend && python -m pytest tests/test_static_validators.py -v`
Expected: All 12 tests PASS.

**Step 5: Commit**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
git add backend/src/agents/agent3/validators.py backend/tests/test_static_validators.py
git commit -m "feat(validators): add language config registry and detect_language()"
```

---

### Task 2: Multi-Language Syntax Validation

**Files:**
- Modify: `backend/src/agents/agent3/validators.py:32-60` (the `validate_syntax` method)
- Test: `backend/tests/test_static_validators.py`

**Step 1: Write failing tests for multi-language syntax validation**

Append to `backend/tests/test_static_validators.py`:

```python
class TestValidateSyntax:
    """Test syntax validation across languages."""

    def setup_method(self):
        self.validator = StaticValidator("/tmp/fake-repo")

    def test_python_valid_syntax(self):
        valid, msg = self.validator.validate_syntax("main.py", "x = 1\nprint(x)\n")
        assert valid is True

    def test_python_invalid_syntax(self):
        valid, msg = self.validator.validate_syntax("main.py", "def foo(\n")
        assert valid is False
        assert "Syntax error" in msg

    @patch("subprocess.run")
    def test_go_valid_syntax(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        valid, msg = self.validator.validate_syntax("main.go", "package main\n")
        assert valid is True
        # Should have called go vet on a temp file
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "go"

    @patch("subprocess.run")
    def test_go_invalid_syntax(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="syntax error: unexpected }")
        valid, msg = self.validator.validate_syntax("main.go", "package main\n}\n")
        assert valid is False
        assert "syntax error" in msg.lower() or "Syntax check failed" in msg

    @patch("subprocess.run")
    def test_js_valid_syntax(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        valid, msg = self.validator.validate_syntax("index.js", "const x = 1;\n")
        assert valid is True
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "node"

    @patch("subprocess.run")
    def test_tool_not_installed_passes(self, mock_run):
        mock_run.side_effect = FileNotFoundError("go not found")
        valid, msg = self.validator.validate_syntax("main.go", "package main\n")
        assert valid is True
        assert "not installed" in msg.lower() or "not available" in msg.lower()

    def test_unknown_language_passes(self):
        valid, msg = self.validator.validate_syntax("README.md", "# Hello\n")
        assert valid is True
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend && python -m pytest tests/test_static_validators.py::TestValidateSyntax -v`
Expected: FAIL — current `validate_syntax` always uses `ast.parse()`, so Go/JS tests will fail.

**Step 3: Refactor validate_syntax to be language-aware**

Replace the `validate_syntax` method in `backend/src/agents/agent3/validators.py`:

```python
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
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend && python -m pytest tests/test_static_validators.py -v`
Expected: All tests PASS.

**Step 5: Commit**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
git add backend/src/agents/agent3/validators.py backend/tests/test_static_validators.py
git commit -m "feat(validators): multi-language syntax validation with best-effort fallback"
```

---

### Task 3: Multi-Language Linting

**Files:**
- Modify: `backend/src/agents/agent3/validators.py:62-143` (the `run_linting` method)
- Test: `backend/tests/test_static_validators.py`

**Step 1: Write failing tests for multi-language linting**

Append to `backend/tests/test_static_validators.py`:

```python
class TestRunLinting:
    """Test linting dispatch across languages."""

    def setup_method(self):
        self.validator = StaticValidator("/tmp/fake-repo")

    @patch("subprocess.run")
    def test_go_lint_with_golangci(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        passed, issues = self.validator.run_linting("main.go", "package main\n")
        assert passed is True
        cmd = mock_run.call_args[0][0]
        assert "golangci-lint" in cmd[0] or "go" in cmd[0]

    @patch("subprocess.run")
    def test_go_lint_fallback_to_go_vet(self, mock_run):
        """When golangci-lint is not installed, fall back to go vet."""
        def side_effect(cmd, **kwargs):
            if cmd[0] == "golangci-lint":
                raise FileNotFoundError("golangci-lint not found")
            return MagicMock(returncode=0, stdout="", stderr="")
        mock_run.side_effect = side_effect
        passed, issues = self.validator.run_linting("main.go", "package main\n")
        assert passed is True

    @patch("subprocess.run")
    def test_js_lint_with_eslint(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="[]", stderr="")
        passed, issues = self.validator.run_linting("index.js", "const x = 1;\n")
        assert passed is True

    @patch("subprocess.run")
    def test_lint_tool_not_installed_passes(self, mock_run):
        mock_run.side_effect = FileNotFoundError("eslint not found")
        passed, issues = self.validator.run_linting("index.ts", "const x: number = 1;\n")
        assert passed is True
        assert any("not installed" in str(w).lower() or "not available" in str(w).lower()
                    for w in issues.get("warnings", []))

    def test_unknown_language_passes(self):
        passed, issues = self.validator.run_linting("README.md", "# Hello\n")
        assert passed is True
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend && python -m pytest tests/test_static_validators.py::TestRunLinting -v`
Expected: FAIL — current `run_linting` always runs `ruff`.

**Step 3: Refactor run_linting to be language-aware**

Replace the `run_linting` method in `backend/src/agents/agent3/validators.py`:

```python
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
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend && python -m pytest tests/test_static_validators.py -v`
Expected: All tests PASS.

**Step 5: Commit**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
git add backend/src/agents/agent3/validators.py backend/tests/test_static_validators.py
git commit -m "feat(validators): multi-language linting with fallback support"
```

---

### Task 4: Language-Aware validate_all and Import Check

**Files:**
- Modify: `backend/src/agents/agent3/validators.py:145-271` (`check_imports` and `validate_all`)
- Test: `backend/tests/test_static_validators.py`

**Step 1: Write failing tests**

Append to `backend/tests/test_static_validators.py`:

```python
class TestCheckImports:
    def setup_method(self):
        self.validator = StaticValidator("/tmp/fake-repo")

    def test_python_imports_checked(self):
        code = "import os\nimport json\n"
        valid, missing = self.validator.check_imports("main.py", code)
        assert valid is True

    def test_non_python_skips_import_check(self):
        valid, missing = self.validator.check_imports("main.go", "package main\n")
        assert valid is True
        assert missing == []


class TestValidateAll:
    def setup_method(self):
        self.validator = StaticValidator("/tmp/fake-repo")

    def test_python_runs_all_three_checks(self):
        code = "import os\nx = 1\n"
        result = self.validator.validate_all("main.py", code)
        assert "syntax" in result
        assert "linting" in result
        assert "imports" in result
        assert "language" in result
        assert result["language"] == "python"

    @patch("subprocess.run")
    def test_go_runs_syntax_and_lint(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
        result = self.validator.validate_all("main.go", "package main\n")
        assert result["language"] == "go"
        assert result["imports"]["valid"] is True  # skipped for Go

    def test_unknown_language_passes(self):
        result = self.validator.validate_all("README.md", "# Hello\n")
        assert result["passed"] is True
        assert result["language"] is None
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend && python -m pytest tests/test_static_validators.py::TestCheckImports tests/test_static_validators.py::TestValidateAll -v`
Expected: FAIL — `check_imports` doesn't accept `file_path`, `validate_all` doesn't return `language`.

**Step 3: Update check_imports and validate_all**

Update `check_imports` signature and body in `backend/src/agents/agent3/validators.py`:

```python
    def check_imports(self, file_path: str, code: str) -> Tuple[bool, List[str]]:
        """Check if all imports are available. Python only — other languages skip."""
        lang = detect_language(file_path)
        if lang != "python":
            logger.info("\n🔍 Static Validation: Import Check (skipped for %s)", lang or "unknown")
            return True, []

        logger.info("\n🔍 Static Validation: Import Check")

        try:
            tree = ast.parse(code)

            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)

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

            project_packages = set()
            if self.repo_path.exists():
                for child in self.repo_path.iterdir():
                    if child.is_dir() and (child / "__init__.py").exists():
                        project_packages.add(child.name)
            project_packages.add("src")

            unknown_imports = [
                imp for imp in imports
                if imp.split('.')[0] not in known_imports
                and imp.split('.')[0] not in project_packages
            ]

            if unknown_imports:
                logger.info("   ⚠️  Imports: Unknown packages — %s", unknown_imports)
                return False, unknown_imports
            else:
                logger.info("   ✅ Imports: All %d imports recognized", len(imports))
                return True, []

        except Exception as e:
            logger.info("   ⚠️  Imports: Check failed — %s", e)
            return True, []
```

Update `validate_all`:

```python
    def validate_all(self, file_path: str, code: str) -> Dict[str, Any]:
        """Run all validation checks appropriate for the detected language."""
        lang = detect_language(file_path)

        logger.info("\n" + "=" * 80)
        logger.info("🛡️  STATIC VALIDATION SUITE (%s)", lang or "unknown")
        logger.info("=" * 80)

        # 1. Syntax check
        syntax_valid, syntax_error = self.validate_syntax(file_path, code)

        # 2. Linting (only if syntax is valid)
        if syntax_valid:
            linting_passed, linting_issues = self.run_linting(file_path, code)
        else:
            linting_passed = False
            linting_issues = {"error": "Skipped due to syntax errors"}

        # 3. Import check (Python only, others skip)
        import_valid, missing_imports = self.check_imports(file_path, code)

        all_passed = syntax_valid and linting_passed and import_valid

        result = {
            "passed": all_passed,
            "language": lang,
            "syntax": {
                "valid": syntax_valid,
                "error": syntax_error if not syntax_valid else None,
            },
            "linting": {
                "passed": linting_passed,
                "issues": linting_issues,
            },
            "imports": {
                "valid": import_valid,
                "missing": missing_imports,
            },
        }

        logger.info("\n" + "=" * 80)
        if all_passed:
            logger.info("✅ VALIDATION PASSED — %s code is valid", lang or "unknown")
        else:
            logger.info("❌ VALIDATION FAILED — code needs corrections")
        logger.info("=" * 80 + "\n")

        return result
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend && python -m pytest tests/test_static_validators.py -v`
Expected: All tests PASS.

**Step 5: Commit**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
git add backend/src/agents/agent3/validators.py backend/tests/test_static_validators.py
git commit -m "feat(validators): language-aware import check and validate_all"
```

---

### Task 5: Language-Aware Self-Correction in fix_generator.py

**Files:**
- Modify: `backend/src/agents/agent3/fix_generator.py:154-170,962-1010`
- Test: `backend/tests/test_static_validators.py`

**Step 1: Write failing test**

Append to `backend/tests/test_static_validators.py`:

```python
class TestSelfCorrectionLanguage:
    """Verify self-correction prompt includes the detected language."""

    @pytest.mark.asyncio
    @patch("src.agents.agent3.fix_generator.Agent3FixGenerator._self_correct")
    async def test_self_correct_called_with_file_path(self, mock_correct):
        """Verify _self_correct receives file_path so it can detect language."""
        # This test just verifies the signature change — _self_correct now takes file_path
        mock_correct.return_value = "fixed code"
        from src.agents.agent3.fix_generator import Agent3FixGenerator
        import inspect
        sig = inspect.signature(Agent3FixGenerator._self_correct)
        params = list(sig.parameters.keys())
        assert "file_path" in params, "_self_correct must accept file_path parameter"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend && python -m pytest tests/test_static_validators.py::TestSelfCorrectionLanguage -v`
Expected: FAIL — `_self_correct` doesn't have `file_path` param yet.

**Step 3: Update _self_correct and its caller**

In `backend/src/agents/agent3/fix_generator.py`, update `_self_correct` method (around line 962):

```python
    async def _self_correct(
        self, code: str, validation: Dict[str, Any], file_path: str = ""
    ) -> str:
        """Attempt to auto-correct validation issues using AnthropicClient."""
        from .validators import detect_language

        logger.info("\nSelf-correcting validation issues...")

        lang = detect_language(file_path) or "python"

        errors = []
        if not validation["syntax"]["valid"]:
            errors.append(f"Syntax error: {validation['syntax']['error']}")
        linting_errors = validation.get("linting", {}).get("issues", {}).get("errors")
        if linting_errors:
            for error in linting_errors[:3]:
                errors.append(f"Linting error: {error}")

        system_prompt = (
            f"You are a code fixer. Fix ONLY the syntax/linting errors in this {lang} code. "
            "Output ONLY the corrected code, no explanation."
        )

        user_prompt = (
            f"Code with errors:\n```{lang}\n{code}\n```\n\n"
            f"Errors to fix:\n{chr(10).join(errors)}\n\n"
            f"Output corrected code:"
        )

        response = await self.llm_client.chat(
            prompt=user_prompt,
            system=system_prompt,
            max_tokens=4096,
        )

        corrected = response.text
        import re as _re
        _fence_match = _re.search(r'```\w*\n(.*?)```', corrected, _re.DOTALL)
        if _fence_match:
            corrected = _fence_match.group(1)
        elif "```" in corrected:
            parts = corrected.split("```")
            if len(parts) >= 3:
                content = parts[1]
                first_nl = content.find('\n')
                if first_nl != -1 and content[:first_nl].strip().isalpha():
                    content = content[first_nl + 1:]
                corrected = content

        logger.info("   Self-correction attempted (%s)", lang)
        return corrected.strip()
```

Update the call site in `run_verification_phase` (around line 162-163) to pass `file_path`:

```python
                code = await self._self_correct(code, validation, fp)
```

**Step 4: Run all tests to verify they pass**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend && python -m pytest tests/test_static_validators.py -v`
Expected: All tests PASS.

**Step 5: Also run existing fix_generator tests to check for regressions**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend && python -m pytest tests/test_fix_generator.py -v`
Expected: All existing tests still PASS.

**Step 6: Commit**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
git add backend/src/agents/agent3/fix_generator.py backend/tests/test_static_validators.py
git commit -m "feat(validators): language-aware self-correction prompt"
```

---

### Task 6: Update check_imports Call Site + Run Full Test Suite

**Files:**
- Modify: `backend/src/agents/agent3/fix_generator.py` (no changes if Task 4 handled validate_all correctly)
- Verify: all existing tests still pass

The `check_imports` signature changed from `(code)` to `(file_path, code)`. The only call site is inside `validate_all` which was already updated in Task 4. However, we need to verify no other code calls `check_imports` directly.

**Step 1: Search for other call sites**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend && grep -rn "check_imports" --include="*.py" .`
Expected: Only `validators.py` (definition + call in `validate_all`) and tests.

**Step 2: Run the full test suite**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend && python -m pytest tests/test_static_validators.py tests/test_fix_generator.py tests/test_fix_job_queue.py tests/test_fix_pipeline_integration.py tests/test_repo_manager_sparse.py -v`
Expected: All tests PASS.

**Step 3: Commit (only if any fixes were needed)**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
git add -A backend/
git commit -m "fix(validators): ensure check_imports call sites use updated signature"
```
