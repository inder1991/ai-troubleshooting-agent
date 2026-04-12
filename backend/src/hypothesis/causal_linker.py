"""Causal linker — builds validated causal links between evidence signals
and wires hypothesis graphs without collapsing."""

from __future__ import annotations

from src.models.hypothesis import CausalLink, EvidenceSignal, Hypothesis

CAUSAL_RULES: list[tuple[str, str, float]] = [
    # (cause_signal_name, effect_signal_name, max_lag_seconds)
    ("oom_kill",                   "pod_restart",          60),
    ("oom_kill",                   "crashloop_backoff",    300),
    ("oom_kill",                   "latency_spike",        300),
    ("pod_restart",                "latency_spike",        300),
    ("pod_restart",                "error_rate_spike",     300),
    ("connection_pool_saturation", "timeout_error",        120),
    ("connection_pool_saturation", "latency_spike",        300),
    ("high_cpu",                   "latency_spike",        300),
    ("high_cpu",                   "cpu_throttling",       60),
    ("disk_usage_high",            "slow_query",           600),
    ("deployment_change",          "error_rate_spike",     1800),
    ("config_change",              "error_rate_spike",     600),
    ("eviction",                   "pod_restart",          60),
    ("probe_failure",              "pod_restart",          120),
]

# Index rules by (cause, effect) for O(1) lookup
_RULE_INDEX: dict[tuple[str, str], float] = {
    (cause, effect): max_lag for cause, effect, max_lag in CAUSAL_RULES
}


class CausalLinker:
    """Builds validated causal links between signals and wires hypothesis graphs."""

    def build_links(self, signals: list[EvidenceSignal]) -> list[CausalLink]:
        """Build validated causal links between signals.

        For each ordered pair of signals, check against CAUSAL_RULES:
        1. Match rule by signal names
        2. Validate temporal order and time delta
        3. Check same entity
        4. Compute confidence
        5. Return sorted by confidence descending, capped at 20
        """
        links: list[CausalLink] = []

        for i, sig_a in enumerate(signals):
            for j, sig_b in enumerate(signals):
                if i == j:
                    continue

                max_lag = _RULE_INDEX.get((sig_a.signal_name, sig_b.signal_name))
                if max_lag is None:
                    continue

                # Both must have timestamps
                if sig_a.timestamp is None or sig_b.timestamp is None:
                    continue

                # Temporal order: cause before effect
                delta = (sig_b.timestamp - sig_a.timestamp).total_seconds()
                if delta <= 0:
                    continue

                # Within max lag
                if delta > max_lag:
                    continue

                # Entity check
                entity_a = self._extract_entity(sig_a)
                entity_b = self._extract_entity(sig_b)
                same_entity = (
                    entity_a is not None
                    and entity_b is not None
                    and entity_a == entity_b
                ) or entity_a is None or entity_b is None

                # Confidence
                base = 0.9 if same_entity else 0.5
                time_proximity = 1.0 - (delta / max_lag * 0.3)
                confidence = base * time_proximity
                confidence = max(0.0, min(1.0, confidence))

                validation = (
                    f"{sig_a.signal_name} -> {sig_b.signal_name}: "
                    f"delta={delta:.0f}s (max {max_lag:.0f}s), "
                    f"same_entity={same_entity}"
                )

                links.append(
                    CausalLink(
                        cause_signal=sig_a.signal_id,
                        effect_signal=sig_b.signal_id,
                        confidence=confidence,
                        time_delta_seconds=delta,
                        same_entity=same_entity,
                        validation=validation,
                    )
                )

        links.sort(key=lambda lk: lk.confidence, reverse=True)
        return links[:20]

    def build_hypothesis_graph(
        self, hypotheses: list[Hypothesis], links: list[CausalLink]
    ) -> None:
        """Link hypotheses via causal chains WITHOUT collapsing.

        For each causal link, find the owning hypotheses for cause and effect
        signals and record the relationship. Both stay active.
        """
        # Build signal_id -> hypothesis_id mapping
        sig_to_hyp: dict[str, str] = {}
        for h in hypotheses:
            for ev in h.evidence_for:
                sig_to_hyp[ev.signal_id] = h.hypothesis_id

        hyp_by_id: dict[str, Hypothesis] = {h.hypothesis_id: h for h in hypotheses}

        for link in links:
            cause_hid = sig_to_hyp.get(link.cause_signal)
            effect_hid = sig_to_hyp.get(link.effect_signal)

            if cause_hid is None or effect_hid is None:
                continue
            if cause_hid == effect_hid:
                continue

            cause_h = hyp_by_id[cause_hid]
            effect_h = hyp_by_id[effect_hid]

            if cause_h.status != "active" or effect_h.status != "active":
                continue

            if effect_hid not in cause_h.downstream_effects:
                cause_h.downstream_effects.append(effect_hid)

            if effect_h.root_cause_of is None:
                effect_h.root_cause_of = cause_hid

    @staticmethod
    def _extract_entity(signal: EvidenceSignal) -> str | None:
        """Extract entity identifier from signal raw_data."""
        for key in ("involved_object", "pod_name", "service_name", "pod"):
            val = signal.raw_data.get(key)
            if val:
                return str(val)
        return None
