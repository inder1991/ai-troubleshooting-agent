"""Deploy regression — deploy -> error/latency spike within minutes."""
from src.patterns.schema import SignaturePattern, TemporalRule


DEPLOY_REGRESSION = SignaturePattern(
    name="deploy_regression",
    required_signals=(
        "deploy",
        "error_rate_spike",
    ),
    optional_signals=(
        "latency_spike",
        "pod_restart",
    ),
    temporal_constraints=(
        TemporalRule(earlier="deploy", later="error_rate_spike", max_gap_s=900),
    ),
    confidence_floor=0.80,
    summary_template=(
        "Deploy of {service} immediately preceded an error-rate spike; "
        "regression strongly suggests a bad change shipped."
    ),
    suggested_remediation=(
        "Roll back the deploy. Bisect the commit range if rollback is not viable. "
        "Keep the broken build artefact for post-mortem."
    ),
)
