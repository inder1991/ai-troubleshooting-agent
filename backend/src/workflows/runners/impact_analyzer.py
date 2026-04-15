"""Runner adapter for ``impact_analyzer`` (Phase-0 ``ImpactAnalyzer``).

Orchestrates two synchronous Phase-0 methods on one background thread
each, then merges their outputs into the manifest's declared shape:
``{blast_radius, severity_recommendation, business_impact}``.
"""

from __future__ import annotations

import asyncio
from typing import Any

from src.agents.impact_analyzer import ImpactAnalyzer


class ImpactAnalyzerRunner:
    def __init__(self) -> None:
        self._agent = ImpactAnalyzer()

    async def run(
        self, inputs: dict[str, Any], *, context: dict[str, Any]
    ) -> dict[str, Any]:
        service = inputs["service_name"]
        services = inputs.get("services", [service])
        blast_radius = inputs["blast_radius"]
        sev = await asyncio.to_thread(
            self._agent.recommend_severity, service, blast_radius
        )
        biz = await asyncio.to_thread(self._agent.infer_business_impact, services)
        return {
            "blast_radius": blast_radius,
            "severity_recommendation": sev.model_dump(mode="json"),
            "business_impact": biz,
        }
