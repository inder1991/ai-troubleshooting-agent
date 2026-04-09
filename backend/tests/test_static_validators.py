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
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "go"

    @patch("subprocess.run")
    def test_go_invalid_syntax(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="syntax error: unexpected }")
        valid, msg = self.validator.validate_syntax("main.go", "package main\n}\n")
        assert valid is False

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
        assert "not available" in msg.lower()

    def test_unknown_language_passes(self):
        valid, msg = self.validator.validate_syntax("README.md", "# Hello\n")
        assert valid is True
