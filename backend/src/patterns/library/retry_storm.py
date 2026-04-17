"""Retry storm — downstream failure + high retry rate amplifies upstream load."""
from src.patterns.schema import SignaturePattern, TemporalRule


RETRY_STORM = SignaturePattern(
    name="retry_storm",
    required_signals=(
        "error_rate_spike",
        "retry_storm",
    ),
    optional_signals=(
        "latency_spike",
        "circuit_open",
        "connection_refused",
    ),
    temporal_constraints=(
        TemporalRule(earlier="error_rate_spike", later="retry_storm", max_gap_s=300),
    ),
    confidence_floor=0.70,
    summary_template=(
        "Errors on {service} triggered a retry storm; retry volume is "
        "amplifying the failure rather than recovering it."
    ),
    suggested_remediation=(
        "Circuit-break the downstream dependency and shed load at the edge. "
        "Consider exponential backoff with jitter on the calling code."
    ),
)
