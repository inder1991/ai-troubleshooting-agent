"""Stack-trace line validator — catches stale / hallucinated line numbers.

An LLM looking at an error stack trace will happily quote "auth.py:147"
even when the deployed auth.py at that SHA has 90 lines. The user then
opens the wrong line in their editor and trust evaporates.

``validate_stack_trace`` fetches each file's line count at the deployed
SHA (via an injectable ``RepoClient``) and flags any (file, line) pair
whose line exceeds the file's current length. Deterministic; no LLM.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol


@dataclass(frozen=True)
class StackFrame:
    file: str
    line: int


@dataclass(frozen=True)
class FrameValidation:
    file: str
    line: int
    is_stale: bool
    file_line_count: int | None
    reason: str = ""


class RepoClient(Protocol):
    """What we need from a repo access layer.

    In production this is a thin shim over ``github_client``; in tests
    it's an in-memory fake. Keeping the contract narrow means the
    validator doesn't know whether we're hitting GitHub, GitLab, or a
    local checkout.
    """

    async def get_file_line_count(self, *, path: str, sha: str) -> int | None: ...


async def validate_stack_trace(
    frames: list[StackFrame | dict],
    *,
    deployed_sha: str,
    repo: RepoClient,
) -> list[FrameValidation]:
    """Validate each (file, line) against the file's length at ``deployed_sha``.

    Frames can be passed as ``StackFrame`` dataclasses or as dicts
    (``{"file": "...", "line": 42}``) — this matches the shape the
    existing code agent emits.
    """
    normalised = [_to_frame(f) for f in frames]
    out: list[FrameValidation] = []
    for frame in normalised:
        try:
            length = await repo.get_file_line_count(path=frame.file, sha=deployed_sha)
        except Exception as exc:
            out.append(
                FrameValidation(
                    file=frame.file,
                    line=frame.line,
                    is_stale=False,  # unknown != stale — don't cry wolf
                    file_line_count=None,
                    reason=f"validation_error: {type(exc).__name__}",
                )
            )
            continue
        if length is None:
            out.append(
                FrameValidation(
                    file=frame.file,
                    line=frame.line,
                    is_stale=True,
                    file_line_count=None,
                    reason="file_not_found_at_deployed_sha",
                )
            )
            continue
        if frame.line <= 0:
            out.append(
                FrameValidation(
                    file=frame.file,
                    line=frame.line,
                    is_stale=True,
                    file_line_count=length,
                    reason="line_number_invalid",
                )
            )
            continue
        if frame.line > length:
            out.append(
                FrameValidation(
                    file=frame.file,
                    line=frame.line,
                    is_stale=True,
                    file_line_count=length,
                    reason=f"line {frame.line} > file length {length}",
                )
            )
            continue
        out.append(
            FrameValidation(
                file=frame.file,
                line=frame.line,
                is_stale=False,
                file_line_count=length,
            )
        )
    return out


def _to_frame(f: StackFrame | dict) -> StackFrame:
    if isinstance(f, StackFrame):
        return f
    if isinstance(f, dict):
        return StackFrame(file=str(f["file"]), line=int(f["line"]))
    raise TypeError(f"frame must be StackFrame or dict, got {type(f).__name__}")
