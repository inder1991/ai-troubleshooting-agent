"""Quota exhaustion — namespace ResourceQuota hit."""
from src.patterns.schema import SignaturePattern, TemporalRule


QUOTA_EXHAUSTION = SignaturePattern(
    name="quota_exhaustion",
    required_signals=("quota_exceeded",),
    optional_signals=("pod_restart", "image_pull_backoff"),
    temporal_constraints=(),
    confidence_floor=0.80,
    summary_template=(
        "Namespace quota exhausted for {service}; new pod creation is "
        "being rejected by the admission controller."
    ),
    suggested_remediation=(
        "Raise the ResourceQuota or free capacity by removing stuck pods / "
        "stale deployments. Audit which workloads are eating headroom."
    ),
)
