from __future__ import annotations
from typing import Any


class StubRunner:
    """Deterministic stub runner for E2E tests. Returns inputs as output."""

    async def run(
        self, inputs: dict[str, Any], *, context: dict[str, Any]
    ) -> dict[str, Any]:
        return {"echoed_inputs": inputs, "stub": True}
