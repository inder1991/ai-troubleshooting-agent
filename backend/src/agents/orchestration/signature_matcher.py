"""Signature matcher — deterministic fast-path before the ReAct loop.

If the observed signals cleanly match a pattern in the library with
confidence at or above the floor, the supervisor can emit a hypothesis
directly and run a single critic pass to verify — instead of burning a
whole ReAct loop on something we already recognise.

Pure function, no LLM. Returns ``None`` if no pattern qualifies, so the
supervisor falls back to the normal loop.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from src.patterns import LIBRARY, Signal, SignaturePattern


_DEFAULT_MATCH_FLOOR: float = 0.70


@dataclass(frozen=True)
class SignatureHypothesis:
    """Hypothesis produced by a high-confidence signature match."""

    pattern_name: str
    confidence: float
    summary: str
    suggested_remediation: Optional[str]
    matched_kinds: tuple[str, ...]


def try_signature_match(
    signals: Iterable[Signal],
    *,
    library: Iterable[SignaturePattern] = LIBRARY,
    match_floor: float = _DEFAULT_MATCH_FLOOR,
) -> Optional[SignatureHypothesis]:
    """Return a hypothesis if a pattern matches at or above the floor.

    When multiple patterns match, pick the highest-confidence one. Ties
    break on name (alphabetical) so the result is deterministic across
    runs — we don't want "sometimes oom_cascade, sometimes
    deploy_regression" on the same evidence set.
    """
    signals_list = list(signals)
    if not signals_list:
        return None

    scored: list[tuple[float, SignaturePattern]] = []
    for p in library:
        result = p.matches(signals_list)
        if result.matched and result.confidence >= match_floor:
            scored.append((result.confidence, p))

    if not scored:
        return None

    scored.sort(key=lambda pr: (-pr[0], pr[1].name))
    best_conf, best_pattern = scored[0]
    # Re-run matches() so the summary can interpolate the service name
    # from the actual signals.
    summary = best_pattern.render_summary(signals_list)
    return SignatureHypothesis(
        pattern_name=best_pattern.name,
        confidence=best_conf,
        summary=summary,
        suggested_remediation=best_pattern.suggested_remediation,
        matched_kinds=tuple(
            k for k in best_pattern.required_signals
        ),
    )
