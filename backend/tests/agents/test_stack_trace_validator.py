"""Task 3.13 — stack-trace line validator."""
from __future__ import annotations

import pytest

from src.agents.stack_trace_validator import (
    FrameValidation,
    StackFrame,
    validate_stack_trace,
)


class FakeRepo:
    """In-memory repo that responds to get_file_line_count."""

    def __init__(self):
        self._files: dict[tuple[str, str], int] = {}
        self._raise_on: tuple[str, str] | None = None

    def set_file(self, path: str, sha: str, *, lines: int) -> None:
        self._files[(path, sha)] = lines

    def set_raise_on(self, path: str, sha: str) -> None:
        self._raise_on = (path, sha)

    async def get_file_line_count(self, *, path: str, sha: str) -> int | None:
        if self._raise_on == (path, sha):
            raise RuntimeError("simulated 500")
        return self._files.get((path, sha))


class TestStaleDetection:
    @pytest.mark.asyncio
    async def test_stale_line_numbers_flagged(self):
        repo = FakeRepo()
        repo.set_file("src/foo.py", "deployed_sha", lines=20)
        out = await validate_stack_trace(
            [{"file": "src/foo.py", "line": 50}],
            deployed_sha="deployed_sha",
            repo=repo,
        )
        assert out[0].is_stale is True
        assert out[0].file_line_count == 20
        assert "line 50" in out[0].reason

    @pytest.mark.asyncio
    async def test_valid_lines_pass(self):
        repo = FakeRepo()
        repo.set_file("src/foo.py", "deployed_sha", lines=200)
        out = await validate_stack_trace(
            [{"file": "src/foo.py", "line": 50}],
            deployed_sha="deployed_sha",
            repo=repo,
        )
        assert out[0].is_stale is False


class TestFileMissing:
    @pytest.mark.asyncio
    async def test_file_not_at_deployed_sha_is_stale(self):
        repo = FakeRepo()  # no files seeded
        out = await validate_stack_trace(
            [StackFrame(file="src/gone.py", line=5)],
            deployed_sha="deployed_sha",
            repo=repo,
        )
        assert out[0].is_stale is True
        assert "file_not_found" in out[0].reason


class TestInvalidInput:
    @pytest.mark.asyncio
    async def test_zero_or_negative_line_is_stale(self):
        repo = FakeRepo()
        repo.set_file("src/foo.py", "deployed_sha", lines=50)
        out = await validate_stack_trace(
            [
                {"file": "src/foo.py", "line": 0},
                {"file": "src/foo.py", "line": -5},
            ],
            deployed_sha="deployed_sha",
            repo=repo,
        )
        assert all(v.is_stale for v in out)
        assert all("invalid" in v.reason for v in out)


class TestErrorPath:
    @pytest.mark.asyncio
    async def test_repo_error_does_not_flag_as_stale(self):
        """An upstream 500 is an unknown, not a stale line — don't cry wolf."""
        repo = FakeRepo()
        repo.set_raise_on("src/foo.py", "deployed_sha")
        out = await validate_stack_trace(
            [StackFrame(file="src/foo.py", line=50)],
            deployed_sha="deployed_sha",
            repo=repo,
        )
        assert out[0].is_stale is False
        assert out[0].file_line_count is None
        assert "validation_error" in out[0].reason


class TestMixedFrames:
    @pytest.mark.asyncio
    async def test_mixed_valid_and_stale(self):
        repo = FakeRepo()
        repo.set_file("src/a.py", "deployed_sha", lines=100)
        repo.set_file("src/b.py", "deployed_sha", lines=30)
        out = await validate_stack_trace(
            [
                {"file": "src/a.py", "line": 42},   # ok
                {"file": "src/b.py", "line": 99},   # stale
                {"file": "src/a.py", "line": 101},  # stale
            ],
            deployed_sha="deployed_sha",
            repo=repo,
        )
        assert out[0].is_stale is False
        assert out[1].is_stale is True
        assert out[2].is_stale is True
