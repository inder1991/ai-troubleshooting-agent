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
