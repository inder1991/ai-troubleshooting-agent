"""CriticRetriever — fetches cross-source evidence for independent verification.

Given a finding, query tools the originating agent did *not* use. A logs-
derived finding gets checked against metrics + k8s; a metrics-derived
finding against logs + k8s, and so on. The goal is to surface evidence that
could contradict the finding from a different data plane — confirmation
bias is the usual failure mode of single-agent pipelines.

Tool selection is rule-based (a static map from originating domain to
complementary domains). Each tool is called with a deterministic query
built from the finding's keywords + time window. LLM is not in the loop
here — the retriever's job is "go fetch," not "decide."
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol


class ToolRegistry(Protocol):
    """Minimal structural contract for the tool registry the retriever uses."""

    async def call(self, tool_name: str, *, params: dict) -> list[dict]:
        ...


# Originating tool → complementary tools to query for cross-source verification.
# Keep this map small and explicit. Phase 3 widens it via the tool-registry
# expansion (Task 3.7–3.10); until then, the retriever cross-checks within
# the four agent domains we already have.
_CROSS_SOURCE_TOOLS: dict[str, tuple[str, ...]] = {
    "logs.search": ("metrics.query", "k8s.events"),
    "metrics.query": ("logs.search", "k8s.events"),
    "k8s.events": ("logs.search", "metrics.query"),
    "traces.search": ("logs.search", "metrics.query"),
}


@dataclass(frozen=True)
class RetrievedPin:
    """Lightweight container — not a full EvidencePin to avoid a circular
    dep on models.schemas and to keep the retriever testable in isolation."""

    claim: str
    raw_snippet: str
    source_tool: str
    timestamp: datetime


def _keywords_from_claim(claim: str, *, limit: int = 5) -> list[str]:
    """Top-N alphabetic tokens with length >= 4, deduplicated in insertion order.

    Deterministic: same claim → same keyword list. The 'top-N by insertion'
    rule matters so the queries are stable across runs, not re-ordered by
    Python's set iteration.
    """
    seen: list[str] = []
    for raw in claim.split():
        token = "".join(c for c in raw if c.isalnum()).lower()
        if len(token) < 4:
            continue
        if token not in seen:
            seen.append(token)
            if len(seen) >= limit:
                break
    return seen


class CriticRetriever:
    """Pulls independent evidence from tools the originating agent didn't use."""

    def __init__(
        self,
        tools: ToolRegistry,
        *,
        window: timedelta = timedelta(minutes=10),
        max_results_per_tool: int = 5,
    ) -> None:
        self._tools = tools
        self._window = window
        self._max_results_per_tool = max_results_per_tool

    async def fetch_independent_evidence(self, finding: Any) -> list[RetrievedPin]:
        originating_tool = _attr(finding, "source_tool")
        cross_tools = _CROSS_SOURCE_TOOLS.get(originating_tool, ())
        if not cross_tools:
            return []
        keywords = _keywords_from_claim(_attr(finding, "claim"))
        if not keywords:
            return []
        ts = _attr(finding, "timestamp")
        if not isinstance(ts, datetime):
            return []
        start = ts - self._window
        end = ts + self._window

        pins: list[RetrievedPin] = []
        for tool in cross_tools:
            params = {
                "keywords": keywords,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "limit": self._max_results_per_tool,
            }
            try:
                rows = await self._tools.call(tool, params=params)
            except Exception:
                # Retriever is best-effort: a tool failing shouldn't block
                # the ensemble. Failures are logged by the tool registry.
                continue
            for row in rows or []:
                pins.append(
                    RetrievedPin(
                        claim=_row_claim(row),
                        raw_snippet=_row_snippet(row),
                        source_tool=tool,
                        timestamp=_row_timestamp(row, default=ts),
                    )
                )
        return pins


def _attr(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _row_claim(row: dict) -> str:
    # Best-effort normalisation across tool response shapes.
    return (
        row.get("message")
        or row.get("claim")
        or row.get("summary")
        or row.get("description")
        or ""
    )


def _row_snippet(row: dict) -> str:
    return (
        row.get("raw")
        or row.get("message")
        or row.get("description")
        or ""
    )


def _row_timestamp(row: dict, *, default: datetime) -> datetime:
    ts = row.get("@timestamp") or row.get("timestamp")
    if isinstance(ts, datetime):
        return ts
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return default
    return default
