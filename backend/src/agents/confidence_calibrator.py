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

Priors:
  ``ConfidenceCalibrator.update_prior`` / ``get_prior`` persist per-agent
  priors to Postgres (table ``agent_priors``). A prior is an EMA-style
  rolling estimate of the fraction of this agent's findings the user later
  labelled correct. Priors are currently read/written but not yet fed into
  ``compute_confidence`` — the two are deliberately decoupled until the
  feedback endpoint (Task 2.5) and supervisor wiring land. That keeps
  Task 2.3's determinism guarantee intact during this transition.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select

from src.database.engine import get_session
from src.database.models import AgentPrior

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


# ── Priors ────────────────────────────────────────────────────────────────

DEFAULT_PRIOR: float = 0.65
# EMA smoothing factor for prior updates: larger alpha = more responsive,
# smaller = more stable. 0.1 keeps a decade of samples visible.
_PRIOR_ALPHA: float = 0.1


class ConfidenceCalibrator:
    """Async wrapper over the agent_priors table.

    Stateless — each call opens its own session. The caller is responsible
    for choosing when to update (typically on a feedback signal).
    """

    async def get_prior(self, agent_name: str) -> float:
        async with get_session() as session:
            row = await session.execute(
                select(AgentPrior.prior).where(AgentPrior.agent_name == agent_name)
            )
            val = row.scalar_one_or_none()
            return float(val) if val is not None else DEFAULT_PRIOR

    async def update_prior(self, agent_name: str, was_correct: bool) -> float:
        """UPSERT the per-agent prior using an EMA toward the latest signal.

        Returns the new prior after the update.
        """
        target = 1.0 if was_correct else 0.0
        async with get_session() as session:
            async with session.begin():
                existing = await session.execute(
                    select(AgentPrior.prior, AgentPrior.sample_count).where(
                        AgentPrior.agent_name == agent_name
                    )
                )
                row = existing.first()
                if row is None:
                    current = DEFAULT_PRIOR
                    sample_count = 0
                else:
                    current = float(row.prior)
                    sample_count = int(row.sample_count)
                new_prior = (1 - _PRIOR_ALPHA) * current + _PRIOR_ALPHA * target
                stmt = pg_insert(AgentPrior).values(
                    agent_name=agent_name,
                    prior=new_prior,
                    sample_count=sample_count + 1,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=[AgentPrior.agent_name],
                    set_={
                        "prior": stmt.excluded.prior,
                        "sample_count": stmt.excluded.sample_count,
                        "updated_at": func.now(),
                    },
                )
                await session.execute(stmt)
        return new_prior
