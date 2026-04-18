"""Runs every PatternDetector over a trace and consolidates findings.

Responsibilities:
  - invoke all configured detectors
  - swallow-and-log exceptions from individual detectors (one broken detector
    must never crash the agent)
  - light deduplication: if two detectors flag overlapping spans with the
    same semantic root cause, keep the more-specific one
  - return findings sorted by severity then confidence
"""
from __future__ import annotations

from typing import Optional

from src.agents.tracing.patterns import (
    BaselineRegressionDetector,
    CriticalPathDetector,
    FanOutDetector,
    NPlusOneDetector,
    PatternDetector,
    RetryClusterDetector,
)
from src.agents.tracing.patterns.baseline_regression import BaselineFetcher
from src.models.schemas import LatencyRegressionHint, PatternFinding, SpanInfo
from src.utils.logger import get_logger

logger = get_logger(__name__)


_SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1}


class PatternsRunner:
    """Stateless runner. Safe to construct once per agent instance."""

    def __init__(
        self,
        detectors: Optional[list[PatternDetector]] = None,
        baseline_fetcher: Optional[BaselineFetcher] = None,
    ) -> None:
        if detectors is None:
            detectors = [
                NPlusOneDetector(),
                FanOutDetector(),
                RetryClusterDetector(),
                CriticalPathDetector(),
                BaselineRegressionDetector(fetcher=baseline_fetcher),
            ]
        self._detectors: list[PatternDetector] = detectors
        self._baseline_detector: Optional[BaselineRegressionDetector] = next(
            (d for d in detectors if isinstance(d, BaselineRegressionDetector)),
            None,
        )

    def run(self, spans: list[SpanInfo]) -> list[PatternFinding]:
        if not spans:
            return []

        all_findings: list[PatternFinding] = []
        for detector in self._detectors:
            try:
                all_findings.extend(detector.detect(spans))
            except Exception:
                logger.exception("pattern detector %s crashed — continuing", detector.kind)

        # Sort most-severe-most-confident first — the LLM prompt surfaces
        # the top findings only, so ordering matters.
        all_findings.sort(
            key=lambda f: (_SEVERITY_ORDER.get(f.severity, 0), f.confidence),
            reverse=True,
        )
        return all_findings

    def hints_for_metrics(
        self, findings: list[PatternFinding]
    ) -> list[LatencyRegressionHint]:
        """Convert baseline-regression findings → metrics-agent handoff hints."""
        if self._baseline_detector is None:
            return []
        return self._baseline_detector.as_hints(findings)
