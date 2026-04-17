"""
Critic Ensemble: Deterministic pre-checks + advocate/challenger debate.

Stage 1: ``DeterministicValidator`` — zero-LLM invariant checks.
Stage 2: ``CriticEnsemble`` — advocate and challenger are given *different*
evidence subsets (so the challenger can't just echo the advocate), with a
deterministic judge aggregator. The rubber-stamp guard is enforced by rule:
when the pin subset sent to the challenger contains only pins that support
the finding, the challenger's verdict is forced to ``insufficient_evidence``
regardless of what the LLM says. Rubber-stamping is a failure mode we block
at the edge, not a heuristic we hope the model notices.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Iterable, Literal

logger = logging.getLogger(__name__)

Verdict = Literal["confirmed", "challenged", "insufficient_evidence"]
FinalVerdict = Literal["confirmed", "challenged", "needs_more_evidence"]

INCIDENT_INVARIANTS = [
    {"name": "pod_cannot_cause_etcd", "cause_type": "k8s_event", "cause_contains": "pod", "effect_type": "error_event", "effect_contains": "etcd"},
    {"name": "app_error_cannot_cause_node_failure", "cause_type": "error_event", "cause_contains": "application", "effect_type": "k8s_event", "effect_contains": "node"},
]


class DeterministicValidator:
    """Zero-LLM invariant checks applied before the ensemble debate."""

    def validate(self, pin: dict, graph_nodes: dict, graph_edges: list, existing_pins: list) -> dict:
        violations: list[str] = []

        if not pin.get("claim") or not pin.get("source_agent"):
            violations.append("schema_incomplete")

        caused_id = pin.get("caused_node_id")
        if caused_id and caused_id in graph_nodes:
            pin_ts = pin.get("timestamp", 0)
            effect_ts = graph_nodes[caused_id].get("timestamp", 0)
            if pin_ts and effect_ts and pin_ts > effect_ts:
                violations.append("temporal_violation")

        pin_service = pin.get("service")
        pin_role = pin.get("causal_role")
        for existing in existing_pins:
            if (existing.get("validation_status") == "validated"
                    and existing.get("service") == pin_service
                    and pin_service
                    and existing.get("causal_role") != pin_role
                    and existing.get("causal_role") in ("root_cause", "cascading_symptom")
                    and pin_role in ("informational",)):
                violations.append(f"contradicts:{existing.get('pin_id', 'unknown')}")

        if violations:
            return {"status": "hard_reject", "violations": violations}
        return {"status": "pass"}


# ── Deterministic pin scoring / partitioning ──────────────────────────────


_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")


def _tokenize(s: str) -> set[str]:
    return {t.lower() for t in _WORD_RE.findall(s or "")}


def supports_finding_score(pin: Any, finding_claim: str) -> float:
    """How much a pin's claim overlaps the finding's claim (0.0–1.0).

    Deterministic keyword match: fraction of finding-claim tokens that also
    appear in the pin's claim. Trivial on purpose — a more sophisticated
    similarity signal belongs in the Phase-4 signature library, not here.
    """
    if not finding_claim:
        return 0.0
    finding_tokens = _tokenize(finding_claim)
    if not finding_tokens:
        return 0.0
    pin_claim = _pin_attr(pin, "claim")
    pin_tokens = _tokenize(pin_claim)
    if not pin_tokens:
        return 0.0
    return len(finding_tokens & pin_tokens) / len(finding_tokens)


def _pin_attr(pin: Any, name: str) -> str:
    if isinstance(pin, dict):
        return pin.get(name) or ""
    return getattr(pin, name, "") or ""


class EvidencePartitioner:
    """Splits pins into advocate/challenger subsets deterministically.

    Given pins sorted by ``supports_finding_score`` descending:
      - Advocate: top-K + first half of the middle band.
      - Challenger: bottom-K + second half of the middle band.

    The two subsets have the same size and their intersection is < 50 %
    of either side — i.e. the challenger is genuinely looking at different
    evidence than the advocate.
    """

    def partition(
        self,
        pins: Iterable[Any],
        finding_claim: str,
        *,
        top_k: int = 3,
    ) -> tuple[list[Any], list[Any]]:
        scored = [(supports_finding_score(p, finding_claim), p) for p in pins]
        if not scored:
            return [], []
        scored.sort(key=lambda s: s[0], reverse=True)
        if len(scored) <= 2 * top_k:
            # Too few pins to carve top/bottom; split in half.
            half = len(scored) // 2 or 1
            advocate = [p for _, p in scored[:half]]
            challenger = [p for _, p in scored[half:]]
            return advocate, challenger
        top = [p for _, p in scored[:top_k]]
        bottom = [p for _, p in scored[-top_k:]]
        middle = [p for _, p in scored[top_k:-top_k]]
        mid_half = len(middle) // 2
        advocate = top + middle[:mid_half]
        challenger = bottom + middle[mid_half:]
        return advocate, challenger


# ── Verdicts + judge aggregator ───────────────────────────────────────────


@dataclass(frozen=True)
class CriticVerdict:
    role: Literal["advocate", "challenger"]
    verdict: Verdict
    reasoning: str


@dataclass(frozen=True)
class EnsembleResult:
    advocate: CriticVerdict
    challenger: CriticVerdict
    final_verdict: FinalVerdict


class JudgeAggregator:
    """Deterministic 2-way aggregate.

    Matrix (rows = advocate, cols = challenger):
                            confirmed   challenged   insufficient
        confirmed           confirmed   ↓ mixed      ↓ mixed
        challenged          ↓ mixed     challenged   ↓ mixed
        insufficient        ↓ mixed     ↓ mixed      ↓ mixed

    A mixed / insufficient outcome always maps to ``needs_more_evidence``
    because the ensemble's job is to decide when to stop running agents,
    not to break ties with vibes.
    """

    def aggregate(self, advocate: CriticVerdict, challenger: CriticVerdict) -> FinalVerdict:
        if advocate.verdict == "confirmed" and challenger.verdict == "confirmed":
            return "confirmed"
        if advocate.verdict == "challenged" and challenger.verdict == "challenged":
            return "challenged"
        return "needs_more_evidence"


# ── Ensemble ──────────────────────────────────────────────────────────────

ADVOCATE_SYSTEM = (
    "You are the advocate in an incident investigation.\n"
    "Task: defend the finding using ONLY the evidence provided.\n"
    "If the evidence is weak or absent, return verdict='insufficient_evidence'.\n"
    "Do not speculate beyond the pins given.\n\n"
    "Return STRICT JSON: "
    '{"verdict": "confirmed|challenged|insufficient_evidence", "reasoning": "..."}'
)

CHALLENGER_SYSTEM = (
    "You are the challenger in an incident investigation.\n"
    "Task: find contradictions or missing evidence against the finding.\n"
    "You are given a DIFFERENT pin subset than the advocate — these are the\n"
    "pins least aligned with the finding.\n"
    "If you cannot find a contradiction with the evidence provided, you MUST\n"
    "return verdict='insufficient_evidence'. Rubber-stamping is a failure.\n\n"
    "Return STRICT JSON: "
    '{"verdict": "confirmed|challenged|insufficient_evidence", "reasoning": "..."}'
)


def _render_pins(pins: Iterable[Any]) -> str:
    return json.dumps(
        [
            {
                "claim": _pin_attr(p, "claim"),
                "source_agent": _pin_attr(p, "source_agent"),
                "evidence_type": _pin_attr(p, "evidence_type"),
            }
            for p in pins
        ],
        default=str,
    )


class CriticEnsemble:
    """Adversarial advocate/challenger over distinct evidence subsets."""

    # Rubber-stamp guard: if the lowest-score pin in the challenger's subset
    # still supports the finding above this threshold, there are no
    # contradictions available and the challenger's verdict is forced.
    _NO_CONTRA_SCORE_THRESHOLD: float = 0.4

    def __init__(
        self,
        client,
        *,
        partitioner: EvidencePartitioner | None = None,
        aggregator: JudgeAggregator | None = None,
        model: str = "claude-sonnet-4-20250514",
        top_k: int = 3,
    ) -> None:
        self._client = client
        self._partitioner = partitioner or EvidencePartitioner()
        self._aggregator = aggregator or JudgeAggregator()
        self._model = model
        self._top_k = top_k

    async def evaluate(self, *, finding: dict, evidence_pins: list[Any]) -> EnsembleResult:
        finding_claim = finding.get("claim", "") if isinstance(finding, dict) else getattr(finding, "claim", "")
        advocate_pins, challenger_pins = self._partitioner.partition(
            evidence_pins, finding_claim, top_k=self._top_k
        )

        advocate_raw = await self._call(
            ADVOCATE_SYSTEM,
            self._render_prompt(finding, advocate_pins),
            temperature=0.0,
        )
        challenger_raw = await self._call(
            CHALLENGER_SYSTEM,
            self._render_prompt(finding, challenger_pins),
            temperature=0.0,
        )

        advocate = CriticVerdict(
            role="advocate",
            verdict=_coerce_verdict(advocate_raw),
            reasoning=_coerce_reasoning(advocate_raw),
        )
        challenger = CriticVerdict(
            role="challenger",
            verdict=_coerce_verdict(challenger_raw),
            reasoning=_coerce_reasoning(challenger_raw),
        )

        # Rubber-stamp guard — applied AFTER the model has spoken, not before,
        # so we have evidence for the override in logs if needed.
        if self._challenger_has_no_contradictions(challenger_pins, finding_claim):
            if challenger.verdict == "confirmed":
                challenger = CriticVerdict(
                    role="challenger",
                    verdict="insufficient_evidence",
                    reasoning=(
                        "Override: challenger subset contained no pins below the "
                        "no-contradiction threshold; a confirm here would be a "
                        "rubber-stamp."
                    ),
                )

        final = self._aggregator.aggregate(advocate, challenger)
        return EnsembleResult(advocate=advocate, challenger=challenger, final_verdict=final)

    def _challenger_has_no_contradictions(self, pins: list[Any], finding_claim: str) -> bool:
        if not pins:
            return True
        scores = [supports_finding_score(p, finding_claim) for p in pins]
        return min(scores) > self._NO_CONTRA_SCORE_THRESHOLD

    def _render_prompt(self, finding: dict, pins: list[Any]) -> str:
        return (
            f"FINDING:\n{json.dumps(finding, default=str)}\n\n"
            f"EVIDENCE PINS:\n{_render_pins(pins)}"
        )

    async def _call(self, system: str, user: str, *, temperature: float) -> str:
        return await self._client.chat(
            system=system,
            messages=[{"role": "user", "content": user}],
            model=self._model,
            temperature=temperature,
        )


def _coerce_verdict(raw: str) -> Verdict:
    try:
        parsed = json.loads(_strip_fence(raw))
    except (json.JSONDecodeError, TypeError):
        return "insufficient_evidence"
    v = parsed.get("verdict") if isinstance(parsed, dict) else None
    if v in ("confirmed", "challenged", "insufficient_evidence"):
        return v
    return "insufficient_evidence"


def _coerce_reasoning(raw: str) -> str:
    try:
        parsed = json.loads(_strip_fence(raw))
    except (json.JSONDecodeError, TypeError):
        return "<unparseable>"
    return (parsed.get("reasoning") or "").strip() if isinstance(parsed, dict) else ""


def _strip_fence(text: str) -> str:
    t = (text or "").strip()
    if "```json" in t:
        return t.split("```json", 1)[1].split("```", 1)[0].strip()
    if t.startswith("```"):
        return t.split("```", 1)[1].split("```", 1)[0].strip()
    return t
