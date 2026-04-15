"""Workflow save-path service.

Thin orchestration over :class:`WorkflowRepository` and the compiler: creates
workflows, submits DAG versions (parse → compile → persist), and reads them
back. Task 8.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from src.contracts.registry import ContractRegistry
from src.workflows.compiler import compile_dag
from src.workflows.models import WorkflowDag
from src.workflows.repository import WorkflowRepository


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkflowService:
    def __init__(self, repo: WorkflowRepository, contracts: ContractRegistry) -> None:
        self._repo = repo
        self._contracts = contracts

    async def create_workflow(
        self,
        *,
        name: str,
        description: str | None,
        created_by: str | None,
    ) -> dict[str, Any]:
        wf_id = await self._repo.create_workflow(
            name=name, description=description, created_by=created_by
        )
        row = await self._repo.get_workflow(wf_id)
        assert row is not None
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "created_at": row["created_at"],
        }

    async def list_workflows(self) -> list[dict[str, Any]]:
        rows = await self._repo.list_workflows()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "description": r["description"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    async def get_workflow(self, id: str) -> dict[str, Any] | None:
        row = await self._repo.get_workflow(id)
        if row is None:
            return None
        latest = await self._repo.get_latest_version(id)
        latest_summary: dict[str, Any] | None = None
        if latest is not None:
            latest_summary = {
                "version": latest["version"],
                "created_at": latest["created_at"],
            }
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "created_at": row["created_at"],
            "latest_version": latest_summary,
        }

    async def create_version(
        self, workflow_id: str, dag_dict: dict[str, Any]
    ) -> dict[str, Any]:
        dag = WorkflowDag.model_validate(dag_dict)
        compiled = compile_dag(dag, self._contracts)

        latest = await self._repo.get_latest_version(workflow_id)
        next_version = (latest["version"] + 1) if latest else 1

        version_id = await self._repo.create_version(
            workflow_id,
            next_version,
            dag_json=json.dumps(dag_dict),
            compiled_json=json.dumps(asdict(compiled), default=str),
        )
        row = await self._repo.get_version(workflow_id, next_version)
        assert row is not None
        return {
            "version_id": version_id,
            "version": next_version,
            "created_at": row["created_at"],
            "workflow_id": workflow_id,
        }

    async def get_version(
        self, workflow_id: str, version: int
    ) -> dict[str, Any] | None:
        row = await self._repo.get_version(workflow_id, version)
        if row is None:
            return None
        return {
            "workflow_id": row["workflow_id"],
            "version": row["version"],
            "dag": json.loads(row["dag_json"]),
            "compiled": json.loads(row["compiled_json"]),
            "created_at": row["created_at"],
        }
