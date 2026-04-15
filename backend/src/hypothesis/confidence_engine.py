"""Deterministic, non-linear confidence scoring engine.

LLM NEVER sets confidence. This module computes it from evidence signals
using agent reliability weights, signal type weights, and contradiction penalties.
"""

import math

from src.models.hypothesis import Hypothesis, EvidenceSignal

AGENT_RELIABILITY: dict[str, float] = {
    "log_agent":     1.0,
    "k8s_agent":     0.9,
    "metrics_agent": 0.8,
    "tracing_agent": 0.6,
    "code_agent":    0.5,
    "change_agent":  0.5,
}

SIGNAL_TYPE_WEIGHT: dict[str, float] = {
    "log":    0.30,
    "k8s":    0.25,
    "metric": 0.20,
    "trace":  0.10,
    "code":   0.10,
    "change": 0.05,
}

CONTRADICTION_PENALTY_PER_SIGNAL = 0.4
EVIDENCE_STEEPNESS = 3.0  # k parameter for exponential curve


def compute_confidence(hypothesis: Hypothesis, total_agents_completed: int) -> float:
    """Deterministic, non-linear confidence scoring. LLM never sets this.

    Formula:
      # Evidence score (non-linear -- diminishing returns)
      weighted_sum = sum(signal_type_weight * strength * agent_reliability * freshness)
      evidence_score = 1 - exp(-EVIDENCE_STEEPNESS * weighted_sum)

      # Agent agreement (more agents corroborating = higher)
      supporting_agents = unique agents in evidence_for
      agent_agreement = len(supporting_agents) / max(total_agents_completed, 1)

      # Contradiction penalty (capped at 1.0)
      contradiction_sum = sum(CONTRADICTION_PENALTY * agent_reliability * strength)
        for each against signal
      contradiction_score = min(contradiction_sum, 1.0)

      # Final
      raw = evidence_score * 50 + agent_agreement * 30 - contradiction_score * 20
      return clamped to [0.0, 100.0], rounded to 1 decimal

    Key properties:
    - Zero evidence -> 0 confidence
    - Diminishing returns (5 weak signals < 1 strong signal)
    - Multi-agent corroboration boosts confidence
    - Contradictions reduce confidence
    - Agent reliability weighted (log_agent > tracing_agent)
    - Never exceeds 100, never below 0
    """
    # --- Evidence score (non-linear, diminishing returns) ---
    weighted_sum = 0.0
    for signal in hypothesis.evidence_for:
        type_w = SIGNAL_TYPE_WEIGHT.get(signal.signal_type, 0.1)
        agent_r = AGENT_RELIABILITY.get(signal.source_agent, 0.5)
        weighted_sum += type_w * signal.strength * agent_r * signal.freshness

    if weighted_sum <= 0.0:
        evidence_score = 0.0
    else:
        evidence_score = 1.0 - math.exp(-EVIDENCE_STEEPNESS * weighted_sum)

    # --- Agent agreement ---
    supporting_agents = {s.source_agent for s in hypothesis.evidence_for}
    agent_agreement = len(supporting_agents) / max(total_agents_completed, 1)

    # --- Contradiction penalty ---
    contradiction_sum = 0.0
    for signal in hypothesis.evidence_against:
        agent_r = AGENT_RELIABILITY.get(signal.source_agent, 0.5)
        contradiction_sum += CONTRADICTION_PENALTY_PER_SIGNAL * agent_r * signal.strength
    contradiction_score = min(contradiction_sum, 1.0)

    # --- Final score ---
    raw = evidence_score * 50.0 + agent_agreement * 30.0 - contradiction_score * 20.0
    clamped = max(0.0, min(100.0, raw))
    return round(clamped, 1)
