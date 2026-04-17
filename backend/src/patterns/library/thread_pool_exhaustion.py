"""Thread pool exhaustion — saturated executor + queuing."""
from src.patterns.schema import SignaturePattern, TemporalRule


THREAD_POOL_EXHAUSTION = SignaturePattern(
    name="thread_pool_exhaustion",
    required_signals=("thread_pool_exhausted", "latency_spike"),
    optional_signals=("error_rate_spike",),
    temporal_constraints=(
        TemporalRule(
            earlier="thread_pool_exhausted",
            later="latency_spike",
            max_gap_s=120,
        ),
    ),
    confidence_floor=0.75,
    summary_template=(
        "{service}'s executor pool is saturated; tasks are queuing and "
        "tail latency is following the queue."
    ),
    suggested_remediation=(
        "Scale the pool, add back-pressure at the ingress, or isolate the "
        "slow downstream on its own executor."
    ),
)
