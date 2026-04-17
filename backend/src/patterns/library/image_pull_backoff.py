"""ImagePullBackOff — pods stuck waiting for image pull."""
from src.patterns.schema import SignaturePattern, TemporalRule


IMAGE_PULL_BACKOFF = SignaturePattern(
    name="image_pull_backoff",
    required_signals=("image_pull_backoff",),
    optional_signals=("pod_restart", "traffic_drop"),
    temporal_constraints=(),
    confidence_floor=0.85,
    summary_template=(
        "Pods for {service} are in ImagePullBackOff; the registry is "
        "rejecting or timing out on the image pull."
    ),
    suggested_remediation=(
        "Check the image tag and pull secret; confirm registry reachability "
        "and quota; roll back to last known-good image if the tag is stale."
    ),
)
