"""Self-consistency wrapper — run the supervisor N times, vote on the winner.

Large language models are noisy. Even with temperature=0 the same prompt
can return slightly different orderings or tie-breaks depending on context
length, tokeniser edge cases, and server-side batching. Running the
supervisor multiple times with shuffled agent dispatch order, then voting,
is a cheap way to detect instability and penalise confidence.

Contract:
  - Opt-in; default off (triples LLM cost).
  - Same ``seed`` + ``n`` -> same shuffled orders (deterministic).
  - N/N agreement -> keep original confidence.
  - (N-1)/N agreement -> -20% confidence, still report the majority winner.
  - Otherwise -> mark inconclusive (confidence clamped to 0.30).
"""
from __future__ import annotations

import hashlib
import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Sequence


@dataclass(frozen=True)
class SingleRun:
    """Result of one supervisor run inside the self-consistency loop."""

    winner: str
    confidence: float
    agent_order: tuple[str, ...] = ()
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SelfConsistencyResult:
    n_runs: int
    runs: tuple[SingleRun, ...]
    final_winner: str | None
    final_confidence: float
    agreed_count: int
    penalty_pct: int
    verdict: str  # "consistent" | "majority" | "inconclusive"


def _seeded_shuffles(
    agents: Sequence[str],
    *,
    n: int,
    seed: str,
) -> list[tuple[str, ...]]:
    """Produce n deterministic shuffled orderings of ``agents``."""
    out: list[tuple[str, ...]] = []
    for i in range(n):
        # Stable per-run seed that's still investigation-scoped.
        h = hashlib.sha256(f"{seed}|{i}".encode()).hexdigest()
        rng = random.Random(h)
        order = list(agents)
        rng.shuffle(order)
        out.append(tuple(order))
    return out


# Confidence adjustments.
_MAJORITY_PENALTY_PCT: int = 20
_INCONCLUSIVE_FLOOR: float = 0.30


class SelfConsistency:
    """Runs ``supervisor_call(order) -> SingleRun`` N times and votes."""

    def __init__(self, *, n: int = 3) -> None:
        if n < 1:
            raise ValueError("n must be >= 1")
        self._n = n

    async def run(
        self,
        *,
        agents: Sequence[str],
        seed: str,
        supervisor_call: Callable[[tuple[str, ...]], Awaitable[SingleRun]],
    ) -> SelfConsistencyResult:
        orders = _seeded_shuffles(agents, n=self._n, seed=seed)
        runs: list[SingleRun] = []
        for order in orders:
            runs.append(await supervisor_call(order))
        return self._vote(tuple(runs))

    def _vote(self, runs: tuple[SingleRun, ...]) -> SelfConsistencyResult:
        counts = Counter(r.winner for r in runs)
        if not counts:
            return SelfConsistencyResult(
                n_runs=len(runs),
                runs=runs,
                final_winner=None,
                final_confidence=0.0,
                agreed_count=0,
                penalty_pct=0,
                verdict="inconclusive",
            )
        winner, count = counts.most_common(1)[0]
        # Pick an original confidence from a run that produced the winner.
        sample_run = next(r for r in runs if r.winner == winner)

        if count == len(runs):
            return SelfConsistencyResult(
                n_runs=len(runs),
                runs=runs,
                final_winner=winner,
                final_confidence=sample_run.confidence,
                agreed_count=count,
                penalty_pct=0,
                verdict="consistent",
            )
        if count == len(runs) - 1:
            penalised = sample_run.confidence * (1 - _MAJORITY_PENALTY_PCT / 100)
            return SelfConsistencyResult(
                n_runs=len(runs),
                runs=runs,
                final_winner=winner,
                final_confidence=round(penalised, 4),
                agreed_count=count,
                penalty_pct=_MAJORITY_PENALTY_PCT,
                verdict="majority",
            )
        return SelfConsistencyResult(
            n_runs=len(runs),
            runs=runs,
            final_winner=None,
            final_confidence=min(_INCONCLUSIVE_FLOOR, sample_run.confidence),
            agreed_count=count,
            penalty_pct=100,
            verdict="inconclusive",
        )
