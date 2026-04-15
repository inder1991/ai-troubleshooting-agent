"""Runner adapter for ``intent_parser`` (Phase-0 ``IntentParser``).

``IntentParser.parse`` is synchronous and returns a ``UserIntent``
dataclass; we wrap the call with ``asyncio.to_thread`` and serialize
the result via ``dataclasses.asdict``.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Any

from src.agents.intent_parser import IntentParser


class IntentParserRunner:
    def __init__(self) -> None:
        self._agent = IntentParser()

    async def run(
        self, inputs: dict[str, Any], *, context: dict[str, Any]
    ) -> dict[str, Any]:
        intent = await asyncio.to_thread(
            self._agent.parse,
            inputs["message"],
            inputs.get("pending_action"),
        )
        return asdict(intent)
