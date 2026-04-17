"""NetworkPolicy denial — pod traffic blocked by policy."""
from src.patterns.schema import SignaturePattern, TemporalRule


NETWORK_POLICY_DENIAL = SignaturePattern(
    name="network_policy_denial",
    required_signals=("network_policy_denial", "connection_refused"),
    optional_signals=("error_rate_spike",),
    temporal_constraints=(
        TemporalRule(
            earlier="network_policy_denial",
            later="connection_refused",
            max_gap_s=60,
        ),
    ),
    confidence_floor=0.80,
    summary_template=(
        "A NetworkPolicy is denying traffic to {service}; connections from "
        "expected peers are being refused at the CNI layer."
    ),
    suggested_remediation=(
        "Review recent NetworkPolicy changes in the namespace; confirm the "
        "podSelector/namespaceSelector covers the intended peers; revert if "
        "a recent policy edit is the trigger."
    ),
)
