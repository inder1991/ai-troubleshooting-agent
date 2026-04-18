"""Deterministic trace-pattern detectors (TA-PR2).

Each detector is a pure function over ``list[SpanInfo]`` → ``list[PatternFinding]``.
Zero LLM involvement. Every detector is unit-testable in isolation.

Ship list (v1):
  n_plus_one        sequential children with identical (service, op) under one parent
  fan_out           concurrent children where slowest dominates total latency
  retry_cluster     app-level repeat of (service, op) from same parent
  critical_path     single span dominates > threshold of total trace time
  baseline_reg      span duration exceeds historical P99 for that (service, op)

Shipped as individual modules so new detectors slot in without touching the
runner or the agent orchestrator.
"""

from .base import PatternDetector
from .n_plus_one import NPlusOneDetector
from .fan_out import FanOutDetector
from .retry_cluster import RetryClusterDetector
from .critical_path import CriticalPathDetector
from .baseline_regression import BaselineRegressionDetector

__all__ = [
    "PatternDetector",
    "NPlusOneDetector",
    "FanOutDetector",
    "RetryClusterDetector",
    "CriticalPathDetector",
    "BaselineRegressionDetector",
]
