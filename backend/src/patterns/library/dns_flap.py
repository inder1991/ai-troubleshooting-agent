"""DNS flap — intermittent resolution failures."""
from src.patterns.schema import SignaturePattern, TemporalRule


DNS_FLAP = SignaturePattern(
    name="dns_flap",
    required_signals=("dns_failure", "error_rate_spike"),
    optional_signals=("connection_refused",),
    temporal_constraints=(
        TemporalRule(earlier="dns_failure", later="error_rate_spike", max_gap_s=300),
    ),
    confidence_floor=0.70,
    summary_template=(
        "DNS resolution is failing intermittently for dependencies of "
        "{service}; errors are correlated with resolution dips."
    ),
    suggested_remediation=(
        "Check CoreDNS / NodeLocalDNSCache pods; confirm upstream resolvers "
        "are healthy; consider negative-cache TTL tuning."
    ),
)
