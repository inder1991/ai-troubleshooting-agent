"""Deterministic confidence calibration for agent findings.

Confidence is a pure function of evidence inputs. No LLM input, no random
variation. This replaces the previous Bayesian calibrator whose critic_score
input made confidence LLM-circular (the LLM's own self-rating drove the
'objective' confidence surfaced to the user).

The inputs are exactly six dimensions the supervisor can measure without
asking a model:
  - evidence_pin_count: how many pins back the finding
  - source_diversity: distinct data sources (logs, metrics, k8s, traces, code)
  - baseline_delta_pct: deviation from 24h baseline as a percentage
  - contradiction_count: conflicting findings from other agents/critics
  - signature_match: whether this matches a Phase-4 signature pattern
  - topology_path_length: whether we traversed a service-topology path

Weights live here (not a YAML) so the policy is auditable with the code.
"""
from __future__ import annotations

from dataclasses import dataclass

# Contribution weights. They are deliberately expressed as a convex-ish
# combination with a small signature/topology bonus and a contradiction
# penalty. Keeping these in one place makes tuning a diff, not a config hunt.
_W_PIN: float = 0.30       # evidence volume
_W_DIVERSITY: float = 0.30  # cross-source corroboration
_W_DELTA: float = 0.25      # baseline deviation strength
_W_FLOOR: float = 0.10      # per-finding floor so nonzero evidence isn't zero
_W_SIG_BONUS: float = 0.15  # signature-library match
_W_TOPO_BONUS: float = 0.05 # traversed a topology path
_W_CONTRA_PENALTY: float = 0.25  # per contradicting finding, capped
_W_CONTRA_CAP: float = 0.60      # max total contradiction penalty

# Saturation / normalisation points.
_PIN_SATURATION: float = 4.0       # 4+ pins saturates evidence volume
_DIVERSITY_SATURATION: float = 3.0  # 3 sources saturates diversity
_DELTA_FLOOR_PCT: float = 15.0      # below-noise floor: contributes 0
_DELTA_SATURATION_PCT: float = 100.0  # 100% delta above floor saturates


@dataclass(frozen=True)
class ConfidenceInputs:
    evidence_pin_count: int
    source_diversity: int
    baseline_delta_pct: float
    contradiction_count: int
    signature_match: bool
    topology_path_length: int


def compute_confidence(i: ConfidenceInputs) -> float:
    """Deterministic confidence score in [0.0, 1.0].

    Not Bayesian. Not LLM-driven. Given the same inputs this returns the same
    number, always. If a future tweak needs different weights, change them in
    this module and update the tests — the formula is the contract.
    """
    pin_score = min(i.evidence_pin_count / _PIN_SATURATION, 1.0)
    diversity = min(i.source_diversity / _DIVERSITY_SATURATION, 1.0)
    # Below the floor, baseline delta contributes nothing. Above saturation, 1.
    delta = min(
        max((i.baseline_delta_pct - _DELTA_FLOOR_PCT) / (_DELTA_SATURATION_PCT - _DELTA_FLOOR_PCT), 0.0),
        1.0,
    )
    sig_bonus = _W_SIG_BONUS if i.signature_match else 0.0
    topo_bonus = _W_TOPO_BONUS if i.topology_path_length > 0 else 0.0
    base = (
        _W_PIN * pin_score
        + _W_DIVERSITY * diversity
        + _W_DELTA * delta
        + _W_FLOOR
        + sig_bonus
    )
    contra_penalty = min(i.contradiction_count * _W_CONTRA_PENALTY, _W_CONTRA_CAP)
    return max(0.0, min(1.0, base - contra_penalty + topo_bonus))
