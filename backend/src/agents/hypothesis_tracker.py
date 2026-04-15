import re
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


_SIMILARITY_THRESHOLD = 0.75


def _normalize(text: str) -> str:
    t = text.lower().strip()
    t = re.sub(r"[^a-z0-9\s]", "", t)
    t = re.sub(r"\b(the|a|an|is|was|in|if|of|for)\b", "", t)
    return re.sub(r"\s+", " ", t).strip()


def _jaccard(a: str, b: str) -> float:
    """Token-level Jaccard similarity between two normalized strings."""
    sa, sb = set(a.split()), set(b.split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


class HypothesisTracker:
    def __init__(self, max_re_dispatches: int = 2):
        self._max = max_re_dispatches
        self._tried: dict[tuple[str, str], bool] = {}
        self._raw: list[tuple[str, str]] = []

    def _is_duplicate(self, agent: str, norm_hyp: str) -> bool:
        """Check exact match or fuzzy similarity against recorded hypotheses for this agent."""
        for (a, h) in self._tried:
            if a != agent:
                continue
            if h == norm_hyp:
                return True
            if _jaccard(h, norm_hyp) >= _SIMILARITY_THRESHOLD:
                return True
        return False

    def should_dispatch(self, agent: str, hypothesis: str, budget_exhausted: bool = False) -> bool:
        if budget_exhausted:
            logger.info(f"Re-dispatch blocked: budget exhausted (hypothesis: {hypothesis[:60]})")
            return False
        if len(self._tried) >= self._max:
            logger.info(f"Re-dispatch blocked: max {self._max} re-dispatches reached")
            return False
        norm = _normalize(hypothesis)
        if self._is_duplicate(agent, norm):
            logger.info(f"Re-dispatch blocked: duplicate (agent={agent}, hypothesis={hypothesis[:60]})")
            return False
        return True

    def record(self, agent: str, hypothesis: str) -> None:
        key = (agent, _normalize(hypothesis))
        self._tried[key] = True
        self._raw.append((agent, hypothesis))

    def investigation_graph(self) -> list[tuple[str, str]]:
        return list(self._raw)
