"""Tests for command injection prevention in codebase tools."""
import subprocess
from unittest.mock import patch, MagicMock
from pathlib import Path

from src.tools.codebase_tools import CodebaseTools


def test_search_uses_list_args_not_shell():
    """grep_search must pass a list to subprocess.run and never use shell=True."""
    tool = CodebaseTools(repo_path="/tmp")
    with patch("src.tools.codebase_tools.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=1)
        tool.grep_search("harmless_pattern", file_extension="py")
        call_args = mock_run.call_args
        # shell must be False or absent
        assert call_args.kwargs.get("shell", False) is False
        # first positional arg must be a list, not a string
        assert isinstance(call_args.args[0], list)


def test_search_with_malicious_pattern():
    """A malicious pattern must be passed as a single list element, not interpolated into a shell string."""
    tool = CodebaseTools(repo_path="/tmp")
    malicious = "'; rm -rf /; '"
    with patch("src.tools.codebase_tools.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=1)
        tool.grep_search(malicious, file_extension="*")
        call_args = mock_run.call_args
        cmd_list = call_args.args[0]
        # Must still be a list
        assert isinstance(cmd_list, list)
        # The malicious string must appear as a single, intact element — not split by the shell
        assert malicious in cmd_list


def test_search_with_malicious_file_extension():
    """A crafted file_extension must not break out of the command."""
    tool = CodebaseTools(repo_path="/tmp")
    with patch("src.tools.codebase_tools.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=1)
        tool.grep_search("pattern", file_extension="py' /etc/passwd '")
        call_args = mock_run.call_args
        cmd_list = call_args.args[0]
        assert isinstance(cmd_list, list)
        # The extension must be embedded inside a single --include flag, not as a separate arg
        include_args = [arg for arg in cmd_list if arg.startswith("--include=")]
        assert len(include_args) == 1
        # /etc/passwd must NOT appear as its own element
        assert "/etc/passwd" not in cmd_list


def test_search_exclude_dirs_present():
    """Standard exclusion directories must appear in the command."""
    tool = CodebaseTools(repo_path="/tmp")
    with patch("src.tools.codebase_tools.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=1)
        tool.grep_search("pattern")
        cmd_list = mock_run.call_args.args[0]
        assert "--exclude-dir=node_modules" in cmd_list
        assert "--exclude-dir=.git" in cmd_list
        assert "--exclude-dir=venv" in cmd_list
        assert "--exclude-dir=__pycache__" in cmd_list


def test_search_wildcard_extension_omits_include():
    """When file_extension is '*', no --include flag should be present."""
    tool = CodebaseTools(repo_path="/tmp")
    with patch("src.tools.codebase_tools.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=1)
        tool.grep_search("pattern", file_extension="*")
        cmd_list = mock_run.call_args.args[0]
        include_args = [arg for arg in cmd_list if arg.startswith("--include=")]
        assert len(include_args) == 0


def test_search_specific_extension_includes_flag():
    """When a specific extension is given, --include=*.ext must be present."""
    tool = CodebaseTools(repo_path="/tmp")
    with patch("src.tools.codebase_tools.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=1)
        tool.grep_search("pattern", file_extension="js")
        cmd_list = mock_run.call_args.args[0]
        assert "--include=*.js" in cmd_list
