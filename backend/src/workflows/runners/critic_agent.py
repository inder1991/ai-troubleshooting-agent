"""Runner adapter for ``critic_agent`` (Phase-0 ``CriticAgent``).

Reshapes the raw ``inputs`` dict into the ``Finding`` + ``DiagnosticState``
Pydantic models expected by ``CriticAgent.validate``, then flattens the
returned ``CriticVerdict`` Pydantic model back into a JSON-safe dict.
"""

from __future__ import annotations

from typing import Any

from src.agents.critic_agent import CriticAgent
from src.models.schemas import DiagnosticState, Finding


class CriticAgentRunner:
    def __init__(self) -> None:
        self._agent = CriticAgent()

    async def run(
        self, inputs: dict[str, Any], *, context: dict[str, Any]
    ) -> dict[str, Any]:
        finding = Finding(**inputs["finding"])
        state = DiagnosticState(**inputs["state"])
        verdict = await self._agent.validate(finding, state)
        return verdict.model_dump(mode="json")
