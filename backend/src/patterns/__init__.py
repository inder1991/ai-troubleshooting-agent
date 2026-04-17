"""Signature pattern library.

Import ``LIBRARY`` to iterate every registered pattern. Adding a pattern
is a 2-line diff: write the module, import it here.
"""
from src.patterns.library.cert_expiry import CERT_EXPIRY
from src.patterns.library.deploy_regression import DEPLOY_REGRESSION
from src.patterns.library.dns_flap import DNS_FLAP
from src.patterns.library.hot_key import HOT_KEY
from src.patterns.library.image_pull_backoff import IMAGE_PULL_BACKOFF
from src.patterns.library.network_policy_denial import NETWORK_POLICY_DENIAL
from src.patterns.library.oom_cascade import OOM_CASCADE
from src.patterns.library.quota_exhaustion import QUOTA_EXHAUSTION
from src.patterns.library.retry_storm import RETRY_STORM
from src.patterns.library.thread_pool_exhaustion import THREAD_POOL_EXHAUSTION
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
    CERT_EXPIRY,
    HOT_KEY,
    THREAD_POOL_EXHAUSTION,
    DNS_FLAP,
    IMAGE_PULL_BACKOFF,
    QUOTA_EXHAUSTION,
    NETWORK_POLICY_DENIAL,
)


__all__ = [
    "CERT_EXPIRY",
    "DEPLOY_REGRESSION",
    "DNS_FLAP",
    "HOT_KEY",
    "IMAGE_PULL_BACKOFF",
    "LIBRARY",
    "MatchResult",
    "NETWORK_POLICY_DENIAL",
    "OOM_CASCADE",
    "QUOTA_EXHAUSTION",
    "RETRY_STORM",
    "Signal",
    "SignaturePattern",
    "TemporalRule",
    "THREAD_POOL_EXHAUSTION",
]
