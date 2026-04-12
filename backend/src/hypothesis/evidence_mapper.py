"""Versioned, priority-ordered rules engine that maps signals to hypothesis categories.

Ambiguous signals stay unattributed. LLM never decides evidence mapping.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.models.hypothesis import EvidenceSignal, Hypothesis


@dataclass
class EvidenceRule:
    rule_id: str
    version: int
    signal_name: str
    maps_to: list[str]       # hypothesis categories this signal supports
    priority: int = 0        # higher priority wins on conflict


# Default rules — versioned, priority-ordered
EVIDENCE_RULES: list[EvidenceRule] = [
    # K8s signals — high confidence mapping
    EvidenceRule("k8s-001", 1, "oom_kill",               ["memory"],                priority=10),
    EvidenceRule("k8s-002", 1, "crashloop_backoff",      ["memory", "connection"],  priority=5),
    EvidenceRule("k8s-003", 1, "pod_restart",            ["memory", "connection"],  priority=3),
    EvidenceRule("k8s-004", 1, "resource_limit_exceeded",["memory", "cpu"],         priority=8),
    EvidenceRule("k8s-005", 1, "image_pull_failure",     ["config"],                priority=10),
    EvidenceRule("k8s-006", 1, "eviction",               ["memory", "disk"],        priority=7),
    EvidenceRule("k8s-007", 1, "probe_failure",          [],                        priority=0),  # ambiguous
    EvidenceRule("k8s-008", 1, "scheduling_failure",     [],                        priority=0),  # ambiguous

    # Metric signals
    EvidenceRule("met-001", 1, "high_memory_usage",          ["memory"],      priority=9),
    EvidenceRule("met-002", 1, "high_cpu",                   ["cpu"],         priority=9),
    EvidenceRule("met-003", 1, "cpu_throttling",             ["cpu"],         priority=8),
    EvidenceRule("met-004", 1, "connection_pool_saturation", ["connection"],  priority=9),
    EvidenceRule("met-005", 1, "disk_usage_high",            ["disk"],        priority=9),
    EvidenceRule("met-006", 1, "error_rate_spike",           [],              priority=0),  # ambiguous
    EvidenceRule("met-007", 1, "latency_spike",              [],              priority=0),  # ambiguous
    EvidenceRule("met-008", 1, "network_errors",             ["network"],     priority=7),

    # Log signals
    EvidenceRule("log-001", 1, "oom_error",             ["memory"],                priority=10),
    EvidenceRule("log-002", 1, "timeout_error",         ["connection", "database"],priority=5),
    EvidenceRule("log-003", 1, "connection_refused",    ["connection", "network"], priority=7),
    EvidenceRule("log-004", 1, "slow_query",            ["database"],              priority=8),
    EvidenceRule("log-005", 1, "connection_pool_error", ["connection"],            priority=9),
]

# Contradiction rules: signal_name → categories it contradicts
CONTRADICTION_RULES: dict[str, list[str]] = {
    "low_memory_usage":    ["memory"],
    "low_cpu":             ["cpu"],
    "healthy_connections": ["connection"],
    "no_disk_pressure":    ["disk"],
}


class EvidenceMapper:
    """Maps evidence signals to hypotheses using deterministic rules only."""

    def __init__(self, rules: list[EvidenceRule] | None = None):
        self._rules = sorted(rules or EVIDENCE_RULES, key=lambda r: -r.priority)
        # Build lookup: signal_name → highest priority rule
        self._rule_index: dict[str, EvidenceRule] = {}
        for rule in self._rules:
            if rule.signal_name not in self._rule_index:
                self._rule_index[rule.signal_name] = rule  # first = highest priority

    def map_signal(self, signal: EvidenceSignal, hypotheses: list[Hypothesis]) -> list[str]:
        """Return hypothesis_ids this signal supports.

        1. Look up signal_name in rule index
        2. If no rule found or maps_to is empty -> return [] (unattributed/ambiguous)
        3. Get categories from the rule's maps_to
        4. Return hypothesis_ids whose category is in maps_to
        """
        rule = self._rule_index.get(signal.signal_name)
        if rule is None or not rule.maps_to:
            return []
        categories = set(rule.maps_to)
        return [h.hypothesis_id for h in hypotheses if h.category in categories]

    def map_contradiction(self, signal: EvidenceSignal, hypotheses: list[Hypothesis]) -> list[str]:
        """Return hypothesis_ids this signal CONTRADICTS.

        1. Look up signal_name in CONTRADICTION_RULES
        2. If not found -> return []
        3. Return hypothesis_ids whose category is in the contradiction list
        """
        contra_categories = CONTRADICTION_RULES.get(signal.signal_name)
        if not contra_categories:
            return []
        categories = set(contra_categories)
        return [h.hypothesis_id for h in hypotheses if h.category in categories]

    def apply(self, signals: list[EvidenceSignal], hypotheses: list[Hypothesis]) -> None:
        """Batch map signals to hypotheses. Populates evidence_for and evidence_against.

        Deduplication: don't add a signal if its signal_id already exists
        in the hypothesis's evidence list. Only map to active hypotheses.
        """
        active = [h for h in hypotheses if h.status == "active"]

        for signal in signals:
            # Supporting evidence
            supporting_ids = set(self.map_signal(signal, active))
            for h in active:
                if h.hypothesis_id in supporting_ids:
                    if not any(e.signal_id == signal.signal_id for e in h.evidence_for):
                        h.evidence_for.append(signal)

            # Contradicting evidence
            contra_ids = set(self.map_contradiction(signal, active))
            for h in active:
                if h.hypothesis_id in contra_ids:
                    if not any(e.signal_id == signal.signal_id for e in h.evidence_against):
                        h.evidence_against.append(signal)
