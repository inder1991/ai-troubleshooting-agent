"""K8s causal invariant registry — structurally impossible causal links."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Invariant:
    id: str
    blocked_from_kind: str
    blocked_to_kind: str
    description: str


# Tier 1: Hard blocks — topology direction violations
CAUSAL_INVARIANTS: tuple[Invariant, ...] = (
    Invariant("INV-CP-001", "pod",         "etcd",           "Pod failure cannot cause etcd disk pressure"),
    Invariant("INV-CP-002", "service",     "node",           "Service misconfiguration cannot cause Node NotReady"),
    Invariant("INV-CP-003", "namespace",   "control_plane",  "Namespace deletion cannot crash control plane"),
    Invariant("INV-CP-004", "pvc",         "api_server",     "PVC pending cannot cause API server latency"),
    Invariant("INV-CP-005", "ingress",     "etcd",           "Ingress error cannot cause etcd issues"),
    Invariant("INV-CP-006", "pod",         "node",           "Pod failure cannot cause node failure"),
    Invariant("INV-CP-007", "configmap",   "node",           "ConfigMap change cannot cause node failure"),
    Invariant("INV-NET-001","pod",         "network_plugin", "Pod cannot degrade network plugin"),
    Invariant("INV-STG-001","pod",         "storage_class",  "Pod cannot degrade storage backend"),
    Invariant("INV-STG-002","deployment",  "pv",             "Deployment cannot cause PV failure"),
)

# Pre-built lookup for O(1) checking
_INVARIANT_LOOKUP: dict[tuple[str, str], Invariant] = {
    (inv.blocked_from_kind, inv.blocked_to_kind): inv
    for inv in CAUSAL_INVARIANTS
}


def check_hard_block(from_kind: str, to_kind: str) -> Optional[Invariant]:
    """Check if a causal link from_kind -> to_kind is blocked by an invariant.

    Returns the matching Invariant if blocked, None if allowed.
    """
    return _INVARIANT_LOOKUP.get((from_kind, to_kind))


# Tier 2: Soft rules — context-dependent annotations
@dataclass(frozen=True)
class SoftRule:
    rule_id: str
    description: str
    confidence_hint: float


SOFT_RULES: tuple[SoftRule, ...] = (
    SoftRule("SOFT-001", "Node failure as root cause unlikely — transient blip, no cascading effects observed", 0.2),
    SoftRule("SOFT-002", "CrashLoop unlikely caused by resource exhaustion — usage metrics normal", 0.3),
    SoftRule("SOFT-003", "PVC pending unlikely caused by storage failure — backend responding normally", 0.25),
    SoftRule("SOFT-004", "Certificate expiry not imminent — low urgency", 0.1),
)


def get_soft_rule(rule_id: str) -> Optional[SoftRule]:
    """Look up a soft rule by ID."""
    for rule in SOFT_RULES:
        if rule.rule_id == rule_id:
            return rule
    return None
