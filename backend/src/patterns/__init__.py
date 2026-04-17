"""Signature pattern library.

Import ``LIBRARY`` to iterate every registered pattern. Adding a pattern
is a 2-line diff: write the module, import it here.
"""
from src.patterns.library.deploy_regression import DEPLOY_REGRESSION
from src.patterns.library.oom_cascade import OOM_CASCADE
from src.patterns.library.retry_storm import RETRY_STORM
from src.patterns.schema import (
    MatchResult,
    Signal,
    SignaturePattern,
    TemporalRule,
)

LIBRARY: tuple[SignaturePattern, ...] = (
    OOM_CASCADE,
    DEPLOY_REGRESSION,
    RETRY_STORM,
)


__all__ = [
    "DEPLOY_REGRESSION",
    "LIBRARY",
    "MatchResult",
    "OOM_CASCADE",
    "RETRY_STORM",
    "Signal",
    "SignaturePattern",
    "TemporalRule",
]
