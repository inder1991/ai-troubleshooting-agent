"""PatternDetector protocol — every detector must conform.

Detectors MUST:
  * be pure functions (no I/O other than the optional baseline lookup)
  * be safe to call on any well-formed ``list[SpanInfo]``, including empty
  * return an EMPTY list when no pattern matches (never raise)
  * never depend on LLM output

The runner treats detector failures as non-fatal — one broken detector
does not prevent the others from producing findings.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.models.schemas import PatternFinding, SpanInfo


@runtime_checkable
class PatternDetector(Protocol):
    """Stateless detector. Construct once; call ``detect()`` many times."""

    #: Short identifier logged alongside the runner's output; matches the
    #: ``PatternFinding.kind`` the detector emits.
    kind: str

    def detect(self, spans: list[SpanInfo]) -> list[PatternFinding]:
        """Return zero or more findings. Must never raise."""
        ...
