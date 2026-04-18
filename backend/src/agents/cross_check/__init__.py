"""Cross-agent cross-check utilities.

Each cross-checker looks at outputs from TWO or more agents and produces
``DivergenceFinding`` records when the views disagree. Unlike the agents
themselves, checkers are pure functions — no LLM, no I/O. Supervisor
invokes them at EvalGate time and surfaces findings to the user.
"""

from .metrics_logs import check_metrics_logs_divergence
from .tracing_metrics import check_tracing_metrics_divergence

__all__ = [
    "check_metrics_logs_divergence",
    "check_tracing_metrics_divergence",
]
