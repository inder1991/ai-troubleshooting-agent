"""K.10 — code_agent._stamp_stale_frames marks out-of-range lines."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.agents.code_agent import CodeNavigatorAgent


@pytest.fixture
def agent():
    # Bypass ReActAgent init — only exercise _stamp_stale_frames.
    a = CodeNavigatorAgent.__new__(CodeNavigatorAgent)
    return a


class TestStaleFrames:
    def test_marks_out_of_range_line_as_stale(self, agent):
        result = {
            "root_cause_location": {
                "file_path": "src/foo.py",
                "relevant_lines": [{"start": 45, "end": 999}],
            },
        }
        file_contents = {"src/foo.py": "a\nb\nc\n"}
        agent._stamp_stale_frames(result, file_contents)
        assert result["root_cause_location"]["is_stale"] is True
        assert "999" in result["root_cause_location"]["stale_reason"]

    def test_valid_line_is_not_stale(self, agent):
        result = {
            "root_cause_location": {
                "file_path": "src/foo.py",
                "relevant_lines": [{"start": 1, "end": 3}],
            },
        }
        file_contents = {"src/foo.py": "a\nb\nc\nd\n"}
        agent._stamp_stale_frames(result, file_contents)
        assert result["root_cause_location"]["is_stale"] is False

    def test_missing_file_content_leaves_flag_unset(self, agent):
        result = {
            "root_cause_location": {
                "file_path": "src/missing.py",
                "relevant_lines": [{"start": 10, "end": 50}],
            },
        }
        # Don't include src/missing.py in file_contents
        agent._stamp_stale_frames(result, {"src/other.py": "x"})
        # is_stale stays unset rather than defaulting to True —
        # unknown != stale.
        assert "is_stale" not in result["root_cause_location"]

    def test_walks_impacted_files_and_suggested_fixes(self, agent):
        result = {
            "root_cause_location": {
                "file_path": "src/foo.py",
                "relevant_lines": [{"start": 1, "end": 1}],
            },
            "impacted_files": [
                {"file_path": "src/foo.py", "relevant_lines": [99]},
                {"file_path": "src/foo.py", "relevant_lines": [{"start": 1, "end": 2}]},
            ],
            "suggested_fix_areas": [
                {"file_path": "src/foo.py", "relevant_lines": [{"end": 500}]},
            ],
        }
        file_contents = {"src/foo.py": "\n".join(["x"] * 5)}
        agent._stamp_stale_frames(result, file_contents)
        assert result["impacted_files"][0]["is_stale"] is True  # 99 > 5
        assert result["impacted_files"][1]["is_stale"] is False  # 2 <= 5
        assert result["suggested_fix_areas"][0]["is_stale"] is True  # 500 > 5

    def test_no_op_on_empty_file_contents(self, agent):
        result = {
            "root_cause_location": {
                "file_path": "src/foo.py",
                "relevant_lines": [{"start": 1, "end": 999}],
            },
        }
        agent._stamp_stale_frames(result, {})
        # Without content we can't prove staleness; flag stays absent.
        assert "is_stale" not in result["root_cause_location"]

    def test_tolerates_missing_relevant_lines(self, agent):
        result = {
            "root_cause_location": {"file_path": "src/foo.py"},
        }
        agent._stamp_stale_frames(result, {"src/foo.py": "one\ntwo\n"})
        # No lines to check -> no stale markers.
        assert result["root_cause_location"]["is_stale"] is False
