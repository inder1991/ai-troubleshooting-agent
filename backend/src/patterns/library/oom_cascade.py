"""OOM cascade — memory pressure -> OOMKill -> pod restart -> error spike."""
from src.patterns.schema import SignaturePattern, TemporalRule


OOM_CASCADE = SignaturePattern(
    name="oom_cascade",
    required_signals=(
        "memory_pressure",
        "oom_killed",
        "pod_restart",
    ),
    optional_signals=(
        "error_rate_spike",
        "latency_spike",
    ),
    temporal_constraints=(
        TemporalRule(earlier="memory_pressure", later="oom_killed", max_gap_s=600),
        TemporalRule(earlier="oom_killed", later="pod_restart", max_gap_s=120),
    ),
    confidence_floor=0.75,
    summary_template=(
        "Memory pressure on {service} escalated to OOMKill + pod restart; "
        "error spike consistent with restart-driven cold-start."
    ),
    suggested_remediation=(
        "Raise container memory limit, or profile the process for a leak. "
        "Temporary mitigation: scale replicas to spread load."
    ),
)
