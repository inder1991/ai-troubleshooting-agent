"""B13 (v1.2.0) — every git subprocess in the harness tooling must
include a `timeout=` argument. A hung remote (DNS, partition, dead
host) hangs the bootstrap or sync indefinitely otherwise.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGETS = [
    REPO_ROOT / "tools/init_harness.py",
    REPO_ROOT / "tools/sync_harness.py",
]

GIT_CALL_RE = re.compile(
    r'subprocess\.(?:run|check_call|check_output)\s*\(\s*\[\s*["\']git["\']',
    re.MULTILINE,
)


def _call_text_starting_at(text: str, start: int) -> str:
    """Return the call's text from `start` to the matching close paren."""
    depth = 0
    for i in range(start, min(len(text), start + 1200)):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[start: i + 1]
    return text[start: start + 1200]


def test_every_git_subprocess_has_timeout():
    offenders: list[str] = []
    for path in TARGETS:
        text = path.read_text()
        for match in GIT_CALL_RE.finditer(text):
            call_text = _call_text_starting_at(text, match.start())
            if "timeout=" not in call_text:
                line_no = text[: match.start()].count("\n") + 1
                offenders.append(f"{path.name}:{line_no}")
    assert not offenders, (
        f"{len(offenders)} git subprocess call(s) missing `timeout=`: "
        f"{offenders}"
    )
