"""Counterfactual remediation framework — P2 stub.

See ``docs/design/counterfactual-experiments.md``. No runtime code is
wired; this module only pins the public surface.

**Safety contract:** no method in this module will ever execute against
production. The real implementation (when it lands) must keep that
invariant; any attempt to execute-prod bypasses the type system and
should be rejected at code-review time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProposedRemediation:
    """What the system wants to try. Human-approved, never auto-executed."""

    action_kind: str  # "restart_pod" | "scale_deployment" | "rollback_deploy" | ...
    target: str
    params: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ReplayResult:
    """Outcome of staging replay. The UI renders this for human approval."""

    symptom_before: dict
    symptom_after: dict
    observed_resolution: bool
    confidence: float
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class BlastRadius:
    affected_services: tuple[str, ...]
    affected_tenants: tuple[str, ...]
    traffic_percentile: float  # 0.0 – 1.0


async def replay_in_staging(
    proposal: ProposedRemediation,
    *,
    captured_window_s: int = 1800,
) -> ReplayResult:
    raise NotImplementedError(
        "counterfactual replay is P2 design-only; see "
        "docs/design/counterfactual-experiments.md"
    )


def estimate_blast_radius(proposal: ProposedRemediation) -> BlastRadius:
    raise NotImplementedError(
        "blast-radius estimator is P2 design-only; see "
        "docs/design/counterfactual-experiments.md"
    )


# Action classes that are NEVER eligible for counterfactual experiment.
FORBIDDEN_ACTIONS: frozenset[str] = frozenset(
    {
        "drop_table",
        "truncate_table",
        "delete_pvc",
        "force_close_circuit",
        "bypass_policy_engine",
    }
)


def is_eligible(proposal: ProposedRemediation) -> bool:
    """Even when the framework is live, forbidden actions never qualify."""
    return proposal.action_kind not in FORBIDDEN_ACTIONS


__all__ = [
    "BlastRadius",
    "FORBIDDEN_ACTIONS",
    "ProposedRemediation",
    "ReplayResult",
    "estimate_blast_radius",
    "is_eligible",
    "replay_in_staging",
]
