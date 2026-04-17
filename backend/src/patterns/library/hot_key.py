"""Hot key — one partition / key takes disproportionate traffic."""
from src.patterns.schema import SignaturePattern, TemporalRule


HOT_KEY = SignaturePattern(
    name="hot_key",
    required_signals=("hot_key", "latency_spike"),
    optional_signals=("error_rate_spike",),
    temporal_constraints=(
        TemporalRule(earlier="hot_key", later="latency_spike", max_gap_s=300),
    ),
    confidence_floor=0.70,
    summary_template=(
        "A hot key in {service} is driving per-partition saturation; "
        "latency is concentrated on the hot shard."
    ),
    suggested_remediation=(
        "Shard the key, introduce a request coalescer, or add a local cache "
        "layer in front of the hot read path."
    ),
)
