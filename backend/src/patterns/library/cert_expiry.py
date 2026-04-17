"""Cert expiry — TLS cert hits its validity window end."""
from src.patterns.schema import SignaturePattern, TemporalRule


CERT_EXPIRY = SignaturePattern(
    name="cert_expiry",
    required_signals=("cert_expiry", "error_rate_spike"),
    optional_signals=("connection_refused",),
    temporal_constraints=(
        TemporalRule(earlier="cert_expiry", later="error_rate_spike", max_gap_s=1800),
    ),
    confidence_floor=0.85,
    summary_template=(
        "TLS cert for {service} expired; downstream clients are rejecting "
        "the handshake."
    ),
    suggested_remediation=(
        "Issue a new cert and roll out; add expiry monitoring at T-14d."
    ),
)
