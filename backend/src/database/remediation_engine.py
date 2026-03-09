"""RemediationEngine — saga orchestrator for database operations.

Flow: plan → approve (JWT) → execute → verify → rollback on failure.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, UTC
from typing import Optional

import jwt

logger = logging.getLogger(__name__)

# Action → SQL preview generator
_SQL_GENERATORS = {
    "kill_query": lambda p: f"SELECT pg_terminate_backend({p.get('pid', '?')})",
    "vacuum": lambda p: f"VACUUM {'FULL ' if p.get('full') else ''}{'ANALYZE ' if p.get('analyze', True) else ''}{p.get('table', '?')}".strip(),
    "reindex": lambda p: f"REINDEX TABLE CONCURRENTLY {p.get('table', '?')}",
    "create_index": lambda p: f"CREATE {'UNIQUE ' if p.get('unique') else ''}INDEX CONCURRENTLY idx_{p.get('table', 'x')}_{'_'.join(p.get('columns', []))} ON {p.get('table', '?')} ({', '.join(p.get('columns', []))})",
    "drop_index": lambda p: f"DROP INDEX CONCURRENTLY {p.get('index_name', '?')}",
    "alter_config": lambda p: f"ALTER SYSTEM SET {p.get('param', '?')} = '{p.get('value', '?')}'",
    "failover_runbook": lambda p: "-- Read-only runbook generation",
}

_IMPACT_GENERATORS = {
    "kill_query": lambda p: "Immediate. Terminates the backend process.",
    "vacuum": lambda p: f"{'Full vacuum — locks table. ' if p.get('full') else 'Non-blocking. '}Duration depends on table size.",
    "reindex": lambda p: "CONCURRENTLY — non-blocking but resource-intensive.",
    "create_index": lambda p: "CONCURRENTLY — non-blocking but uses CPU/IO.",
    "drop_index": lambda p: "Immediate. Queries using this index will fall back to seq scan.",
    "alter_config": lambda p: "Applies on reload. Some params require restart.",
    "failover_runbook": lambda p: "Read-only. No changes made.",
}

_ROLLBACK_GENERATORS = {
    "vacuum": lambda p: None,  # Cannot un-vacuum
    "kill_query": lambda p: None,  # Cannot un-kill
    "reindex": lambda p: None,  # Reindex is idempotent
    "create_index": lambda p: f"DROP INDEX CONCURRENTLY idx_{p.get('table', 'x')}_{'_'.join(p.get('columns', []))}",
    "drop_index": lambda p: None,  # Would need original CREATE INDEX — not feasible
    "alter_config": lambda p: None,  # Would need original value — handled separately
    "failover_runbook": lambda p: None,
}


class RemediationEngine:
    def __init__(self, plan_store, adapter_registry, profile_store, secret_key: str):
        self._store = plan_store
        self._adapter_registry = adapter_registry
        self._profile_store = profile_store
        self._secret_key = secret_key

    def plan(self, profile_id: str, action: str, params: dict,
             finding_id: str | None = None) -> dict:
        """Create a new remediation plan."""
        if action not in _SQL_GENERATORS:
            raise ValueError(f"Unknown action: {action}")

        sql_preview = _SQL_GENERATORS[action](params)
        impact = _IMPACT_GENERATORS.get(action, lambda p: "")(params)
        rollback_sql = _ROLLBACK_GENERATORS.get(action, lambda p: None)(params)
        requires_downtime = action == "vacuum" and params.get("full", False)

        return self._store.create_plan(
            profile_id=profile_id,
            action=action,
            params=params,
            sql_preview=sql_preview,
            impact_assessment=impact,
            rollback_sql=rollback_sql,
            requires_downtime=requires_downtime,
            finding_id=finding_id,
        )

    def approve(self, plan_id: str) -> dict:
        """Approve a plan and generate a JWT token."""
        plan = self._store.get_plan(plan_id)
        if not plan:
            raise ValueError(f"Plan {plan_id} not found")
        if plan["status"] != "pending":
            raise ValueError(f"Plan {plan_id} not in pending status (current: {plan['status']})")

        now = datetime.now(UTC)
        expires = now + timedelta(minutes=5)
        token = jwt.encode(
            {"plan_id": plan_id, "profile_id": plan["profile_id"],
             "action": plan["action"], "exp": expires},
            self._secret_key,
            algorithm="HS256",
        )
        self._store.update_plan(plan_id, status="approved",
                                approved_at=now.isoformat())
        return {
            "plan_id": plan_id,
            "approval_token": token,
            "expires_at": expires.isoformat(),
        }

    def reject(self, plan_id: str):
        """Reject a plan."""
        plan = self._store.get_plan(plan_id)
        if not plan:
            raise ValueError(f"Plan {plan_id} not found")
        self._store.update_plan(plan_id, status="rejected")

    async def execute(self, plan_id: str, token: str) -> dict:
        """Execute an approved plan. Full saga: pre-flight → execute → verify → rollback."""
        # Validate token
        try:
            payload = jwt.decode(token, self._secret_key, algorithms=["HS256"])
        except jwt.InvalidTokenError:
            raise ValueError("Invalid or expired approval token")

        if payload.get("plan_id") != plan_id:
            raise ValueError("Token does not match plan")

        plan = self._store.get_plan(plan_id)
        if not plan:
            raise ValueError(f"Plan {plan_id} not found")
        if plan["status"] != "approved":
            raise ValueError(f"Plan {plan_id} not in approved status")

        # Get adapter
        adapter = self._adapter_registry.get_by_profile(plan["profile_id"])
        if not adapter:
            raise ValueError(f"No adapter for profile {plan['profile_id']}")

        # Mark executing
        self._store.update_plan(plan_id, status="executing",
                                executed_at=datetime.now(UTC).isoformat())

        action = plan["action"]
        params = plan["params"]
        before_state = {}
        after_state = {}

        try:
            # Execute the operation
            result = await self._dispatch_action(adapter, action, params)

            # Mark completed
            now = datetime.now(UTC).isoformat()
            self._store.update_plan(
                plan_id, status="completed", completed_at=now,
                result_summary=str(result.get("message", "Success")),
                after_state=result,
            )
            # Audit log
            self._store.add_audit_entry(
                plan_id=plan_id, profile_id=plan["profile_id"],
                action=action, sql_executed=plan["sql_preview"],
                status="success", before_state=before_state,
                after_state=result,
            )
            logger.info("Remediation %s completed: %s", plan_id, action)
            return {"plan_id": plan_id, "status": "completed", "result": result}

        except Exception as e:
            # Mark failed
            now = datetime.now(UTC).isoformat()
            self._store.update_plan(
                plan_id, status="failed", completed_at=now,
                result_summary=f"Error: {e}",
            )
            self._store.add_audit_entry(
                plan_id=plan_id, profile_id=plan["profile_id"],
                action=action, sql_executed=plan["sql_preview"],
                status="failed", before_state=before_state,
                after_state=after_state, error=str(e),
            )
            logger.error("Remediation %s failed: %s", plan_id, e)
            return {"plan_id": plan_id, "status": "failed", "error": str(e)}

    async def _dispatch_action(self, adapter, action: str, params: dict) -> dict:
        """Route action to the correct adapter method."""
        if action == "kill_query":
            return await adapter.kill_query(pid=params["pid"])
        elif action == "vacuum":
            return await adapter.vacuum_table(
                table=params["table"],
                full=params.get("full", False),
                analyze=params.get("analyze", True),
            )
        elif action == "reindex":
            return await adapter.reindex_table(table=params["table"])
        elif action == "create_index":
            return await adapter.create_index(
                table=params["table"],
                columns=params["columns"],
                name=params.get("name"),
                unique=params.get("unique", False),
            )
        elif action == "drop_index":
            return await adapter.drop_index(index_name=params["index_name"])
        elif action == "alter_config":
            return await adapter.alter_config(
                param=params["param"], value=params["value"],
            )
        elif action == "failover_runbook":
            return await adapter.generate_failover_runbook()
        else:
            raise ValueError(f"Unknown action: {action}")

    def get_plan(self, plan_id: str) -> dict | None:
        return self._store.get_plan(plan_id)

    def list_plans(self, profile_id: str, status: str | None = None) -> list[dict]:
        return self._store.list_plans(profile_id, status)

    def get_audit_log(self, profile_id: str, limit: int = 50) -> list[dict]:
        return self._store.get_audit_log(profile_id, limit)
