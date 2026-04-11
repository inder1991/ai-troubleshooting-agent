from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel

from src.integrations.cicd.base import ResolveResult
from src.integrations.cicd.resolver import resolve_cicd_clients
from src.utils.logger import get_logger

logger = get_logger(__name__)


class PipelineCapabilityInput(BaseModel):
    cluster_id: str
    time_window_minutes: int = 60
    git_repo: str | None = None
    service_hint: str | None = None


class PipelineAgent:
    """ReAct-style agent with three CI/CD tools.

    Tools:
      - list_recent_deploys(hours)  -> list of DeployEvent dicts
      - get_deploy_details(event_id) -> Build/SyncDiff dict
      - search_logs(query)           -> placeholder for Phase B
      - finish(finding, root_cause)  -> terminal action

    Max 4 iterations. On max_iterations, returns a stub finding with
    terminated_reason='max_iterations'.
    """

    def __init__(self, llm: Any, max_iterations: int = 4) -> None:
        self.llm = llm
        self.max_iterations = max_iterations

    async def run(self, inputs: PipelineCapabilityInput | dict[str, Any]) -> dict[str, Any]:
        if not isinstance(inputs, PipelineCapabilityInput):
            inputs = PipelineCapabilityInput(**inputs)

        resolved: ResolveResult = await resolve_cicd_clients(inputs.cluster_id)
        clients = resolved.jenkins + resolved.argocd

        ctx: dict[str, Any] = {
            "inputs": inputs.model_dump(),
            "observations": [],
            "resolved_instances": [
                {"source": c.source, "name": c.name} for c in clients
            ],
        }

        for _ in range(self.max_iterations):
            step = await self.llm.invoke(ctx)
            action = step.get("action")
            args = step.get("args", {}) or {}

            if action == "finish":
                return {
                    "finding": args.get("finding", ""),
                    "root_cause": args.get("root_cause"),
                    "deeplinks": args.get("deeplinks", []),
                    "terminated_reason": "finished",
                    "resolver_errors": [
                        {"name": e.name, "source": e.source, "message": e.message}
                        for e in resolved.errors
                    ],
                }

            obs = await self._run_tool(action, args, inputs, clients)
            ctx["observations"].append({"action": action, "args": args, "obs": obs})

        return {
            "finding": "Unable to conclude within iteration budget.",
            "root_cause": None,
            "deeplinks": [],
            "terminated_reason": "max_iterations",
            "resolver_errors": [
                {"name": e.name, "source": e.source, "message": e.message}
                for e in resolved.errors
            ],
        }

    async def _run_tool(
        self,
        action: str,
        args: dict[str, Any],
        inputs: PipelineCapabilityInput,
        clients: list,
    ) -> Any:
        if action == "list_recent_deploys":
            hours = int(args.get("hours", inputs.time_window_minutes / 60 or 1))
            until = datetime.now(tz=timezone.utc)
            since = until - timedelta(hours=hours)
            out: list[dict] = []
            for c in clients:
                try:
                    evs = await c.list_deploy_events(
                        since, until, target_filter=inputs.service_hint
                    )
                    out.extend(e.model_dump(mode="json") for e in evs)
                except Exception as exc:
                    logger.warning(
                        "list_recent_deploys failed for %s/%s: %s",
                        c.source, c.name, exc,
                    )
            return out

        if action == "get_deploy_details":
            event_id = args.get("event_id", "")
            if not event_id:
                return {"error": "event_id required"}
            until = datetime.now(tz=timezone.utc)
            since = until - timedelta(hours=24)
            for c in clients:
                try:
                    evs = await c.list_deploy_events(since, until)
                    match = next((e for e in evs if e.source_id == event_id), None)
                    if match is None:
                        continue
                    art = await c.get_build_artifacts(match)
                    return art.model_dump(mode="json")
                except Exception as exc:
                    logger.warning(
                        "get_deploy_details failed for %s/%s: %s",
                        c.source, c.name, exc,
                    )
            return {"error": f"event {event_id} not found on any instance"}

        if action == "search_logs":
            return {"error": "search_logs not wired to live source in Phase A"}

        return {"error": f"unknown action {action}"}
