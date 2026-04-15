"""Deterministic hypothesis elimination engine.

Applies kill rules to prune weak hypotheses and picks a winner
(or declares inconclusive) after all agents complete.
"""

from __future__ import annotations

from src.models.hypothesis import Hypothesis, HypothesisResult

CONFIDENCE_GAP_THRESHOLD = 30  # eliminate if >30 points behind leader
MIN_WINNER_CONFIDENCE = 40     # below this -> inconclusive
COMPETING_MARGIN = 10          # top 2 within this margin -> inconclusive


def evaluate_hypotheses(
    hypotheses: list[Hypothesis],
    agents_completed: int,
    phase: str,
) -> list[dict]:
    """Eliminate weak hypotheses. Returns elimination log.

    Rules (applied in order, NEVER kill all -- at least 1 must survive):

    1. Get active hypotheses only
    2. If <= 1 active -> return [] (nothing to eliminate)
    3. Find leader (highest confidence among active)
    4. For each non-leader active hypothesis, check in this order:
       a. Downstream effect
       b. No evidence
       c. Contradicted
       d. Confidence gap
    5. After all eliminations, if zero active remain, reactivate the
       one with highest confidence
    6. Set elimination_phase on each eliminated hypothesis
    7. Return elimination log
    """
    active = [h for h in hypotheses if h.status == "active"]
    if len(active) <= 1:
        return []

    leader = max(active, key=lambda h: h.confidence)
    active_ids = {h.hypothesis_id for h in active}

    elimination_log: list[dict] = []
    eliminated_this_round: list[Hypothesis] = []

    for h in active:
        if h.hypothesis_id == leader.hypothesis_id:
            continue

        reason: str | None = None
        gap = leader.confidence - h.confidence

        # a. Downstream effect
        if (
            h.root_cause_of is not None
            and h.root_cause_of in active_ids
            and gap > CONFIDENCE_GAP_THRESHOLD
        ):
            reason = (
                f"Downstream effect of {h.root_cause_of} "
                f"(confidence gap: {gap:.0f})"
            )

        # b. No evidence after enough agents
        if reason is None and len(h.evidence_for) == 0 and agents_completed >= 2:
            reason = f"No supporting evidence after {agents_completed} agents"

        # c. Contradicted
        if reason is None and len(h.evidence_against) > len(h.evidence_for):
            n = len(h.evidence_against)
            m = len(h.evidence_for)
            reason = (
                f"More contradicting ({n}) than supporting ({m}) evidence"
            )

        # d. Confidence gap
        if reason is None and gap > CONFIDENCE_GAP_THRESHOLD:
            reason = (
                f"Confidence gap: {h.confidence:.0f} vs leader "
                f"{leader.confidence:.0f}"
            )

        if reason is not None:
            h.status = "eliminated"
            h.elimination_reason = reason
            eliminated_this_round.append(h)
            elimination_log.append({
                "hypothesis_id": h.hypothesis_id,
                "reason": reason,
                "phase": phase,
                "confidence": h.confidence,
            })

    # 5. Never kill all -- reactivate best if none remain
    remaining_active = [h for h in hypotheses if h.status == "active"]
    if len(remaining_active) == 0:
        # pick the one with highest confidence among those just eliminated
        best = max(eliminated_this_round, key=lambda h: h.confidence)
        best.status = "active"
        best.elimination_reason = None
        elimination_log = [
            e for e in elimination_log
            if e["hypothesis_id"] != best.hypothesis_id
        ]

    # 6. Set elimination_phase
    for h in eliminated_this_round:
        if h.status == "eliminated":
            h.elimination_phase = phase

    return elimination_log


def pick_winner_or_inconclusive(
    hypotheses: list[Hypothesis],
) -> HypothesisResult:
    """Final decision after all agents complete.

    1. Get active hypotheses
    2. If none active -> inconclusive
    3. Sort active by confidence descending
    4. If best.confidence < MIN_WINNER_CONFIDENCE -> inconclusive
    5. If len(active) >= 2 AND gap <= COMPETING_MARGIN -> inconclusive
    6. Otherwise -> winner
    """
    active = sorted(
        [h for h in hypotheses if h.status == "active"],
        key=lambda h: h.confidence,
        reverse=True,
    )

    # Collect elimination log from hypotheses
    elimination_log: list[dict] = []
    for h in hypotheses:
        if h.status == "eliminated" and h.elimination_reason:
            elimination_log.append({
                "hypothesis_id": h.hypothesis_id,
                "reason": h.elimination_reason,
                "phase": h.elimination_phase,
                "confidence": h.confidence,
            })

    recommendations = [
        "Collect more log data from the affected time window",
        "Check network connectivity between services",
        "Review recent deployment and configuration changes",
        "Increase monitoring granularity for the affected services",
    ]

    if not active:
        return HypothesisResult(
            hypotheses=hypotheses,
            winner=None,
            status="inconclusive",
            elimination_log=elimination_log,
            recommendations=recommendations,
        )

    best = active[0]

    if best.confidence < MIN_WINNER_CONFIDENCE:
        return HypothesisResult(
            hypotheses=hypotheses,
            winner=None,
            status="inconclusive",
            elimination_log=elimination_log,
            recommendations=recommendations,
        )

    if len(active) >= 2 and (active[0].confidence - active[1].confidence) <= COMPETING_MARGIN:
        return HypothesisResult(
            hypotheses=hypotheses,
            winner=None,
            status="inconclusive",
            elimination_log=elimination_log,
            recommendations=recommendations,
        )

    # Winner
    best.status = "winner"
    return HypothesisResult(
        hypotheses=hypotheses,
        winner=best,
        status="resolved",
        elimination_log=elimination_log,
    )
