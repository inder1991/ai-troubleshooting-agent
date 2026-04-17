"""Prompt registry — versioned system prompts per agent.

Every agent loads its system prompt through ``PromptRegistry.get(agent)``,
which:
  1. Computes sha256(system_prompt + json(tool_schemas)) as the version_id.
  2. Ensures a row exists in ``prompt_versions`` for that (agent, sha).
  3. Returns a ``PinnedPrompt`` with version_id attached.

Agents stamp ``prompt_version_id`` on their output so every finding in
``backend_call_audit`` / the UI can answer "which prompt produced this?"
without a code-diff scavenger hunt.

Prompts themselves live inline in this module (not in JSON / YAML) so
the diff that changes a prompt IS the audit trail. The DB registry only
tracks versions; editing prompts is a code change.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.database.engine import get_session
from src.database.models import PromptVersion


@dataclass(frozen=True)
class PinnedPrompt:
    """What an agent gets back from the registry."""

    agent: str
    version_id: str
    system_prompt: str
    tool_schemas: dict[str, Any] | None


# Seed registry. Each prompt ends with an explicit 'I don't know' escape
# so Task 4.24's linter test stays green — and so agents don't hallucinate
# when evidence is thin.
_PROMPTS: dict[str, tuple[str, dict[str, Any] | None]] = {
    "log_agent": (
        "You are the log_agent. Your job is to surface error/warn log lines "
        "relevant to the incident and summarise their structure.\n\n"
        "You have access to ELK/OpenSearch search tools. Use the narrowest "
        "query that answers the question.\n\n"
        "If the evidence is thin or ambiguous, return an explicit "
        "'inconclusive' finding. Do not guess.",
        None,
    ),
    "metrics_agent": (
        "You are the metrics_agent. Your job is to surface deviations from "
        "the 24h baseline in the golden signals (RPS, error rate, p50/p95/p99 "
        "latency, saturation).\n\n"
        "You have Prometheus query tools. Every query MUST include a namespace "
        "selector.\n\n"
        "If metrics are within baseline noise, say so — return 'inconclusive' "
        "rather than manufacturing a finding.",
        None,
    ),
    "k8s_agent": (
        "You are the k8s_agent. Your job is to report the current state of "
        "the cluster (pods, events, deployments) relevant to the incident.\n\n"
        "You have K8s API tools. Limit listings with namespace + label "
        "selector.\n\n"
        "If the cluster looks nominal for the affected namespace, return an "
        "'inconclusive' finding. Do not invent pod-level causes without "
        "evidence.",
        None,
    ),
    "tracing_agent": (
        "You are the tracing_agent. Your job is to identify slow/failing "
        "spans and pinpoint the dependency at which latency is introduced.\n\n"
        "If traces are sparse or the incident window has no sampled traces, "
        "return 'inconclusive'. Don't extrapolate from a single span.",
        None,
    ),
    "code_agent": (
        "You are the code_agent. Your job is to map a stack trace or error "
        "message back to the source lines at the deployed SHA.\n\n"
        "Every frame you surface MUST pass stack-trace validation against "
        "the deployed SHA. If a frame is stale, say so.\n\n"
        "If you cannot locate the source with high confidence, return "
        "'inconclusive'. Don't quote line numbers you aren't sure about.",
        None,
    ),
    "change_agent": (
        "You are the change_agent. Your job is to correlate the incident "
        "window with recent deploys, config flips, and feature-flag flips.\n\n"
        "If no change lands in the incident window, return 'inconclusive' "
        "explicitly. Don't stretch to claim a deploy three hours before the "
        "spike caused it without temporal evidence.",
        None,
    ),
    "supervisor": (
        "You are the supervisor. Your job is to orchestrate specialist "
        "agents, weigh their evidence pins, and produce a ranked set of "
        "hypotheses.\n\n"
        "Scoring, ranking, and root-cause identification are RULE-BASED. "
        "You do not choose the winner by feel — deterministic code does.\n\n"
        "If the deterministic confidence is below the 'confident' threshold, "
        "return 'inconclusive' with the top candidates, not a guess.",
        None,
    ),
}


def _compute_version_id(system_prompt: str, tool_schemas: dict | None) -> str:
    payload = json.dumps(
        {"prompt": system_prompt, "tools": tool_schemas or {}},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


class PromptRegistry:
    """Process-wide pinned prompt store. Lazy DB upsert."""

    def __init__(self) -> None:
        self._pinned: dict[str, PinnedPrompt] = {}
        self._db_sync_lock = asyncio.Lock()
        self._persisted_ids: set[str] = set()

    def get(self, agent: str) -> PinnedPrompt:
        """Return (creating if necessary) the pinned prompt for ``agent``."""
        if agent not in _PROMPTS:
            raise KeyError(f"no prompt registered for agent {agent!r}")
        if agent in self._pinned:
            return self._pinned[agent]
        system_prompt, tool_schemas = _PROMPTS[agent]
        version_id = _compute_version_id(system_prompt, tool_schemas)
        pinned = PinnedPrompt(
            agent=agent,
            version_id=version_id,
            system_prompt=system_prompt,
            tool_schemas=tool_schemas,
        )
        self._pinned[agent] = pinned
        return pinned

    def list_all(self) -> list[PinnedPrompt]:
        return [self.get(a) for a in _PROMPTS]

    async def ensure_persisted(self, agent: str) -> PinnedPrompt:
        """Write the pinned prompt row to Postgres (idempotent upsert)."""
        pinned = self.get(agent)
        if pinned.version_id in self._persisted_ids:
            return pinned
        async with self._db_sync_lock:
            if pinned.version_id in self._persisted_ids:
                return pinned
            async with get_session() as session:
                async with session.begin():
                    stmt = pg_insert(PromptVersion).values(
                        version_id=pinned.version_id,
                        agent=pinned.agent,
                        system_prompt=pinned.system_prompt,
                        tool_schemas=pinned.tool_schemas,
                        sha256=pinned.version_id,
                    )
                    stmt = stmt.on_conflict_do_nothing(
                        index_elements=[PromptVersion.version_id]
                    )
                    await session.execute(stmt)
            self._persisted_ids.add(pinned.version_id)
        return pinned


__all__ = ["PinnedPrompt", "PromptRegistry"]
