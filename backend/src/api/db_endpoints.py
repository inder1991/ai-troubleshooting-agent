"""FastAPI router for database diagnostics — /api/db/*."""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

db_router = APIRouter(prefix="/api/db", tags=["database"])

# ── Stores (lazy singletons) ──

_profile_store = None
_run_store = None
_db_monitor = None
_metrics_store = None
_alert_engine = None
_db_adapter_registry = None


def _get_profile_store():
    global _profile_store
    if _profile_store is None:
        from src.database.profile_store import DBProfileStore

        db_path = os.environ.get("DB_DIAGNOSTICS_DB_PATH", "data/debugduck.db")
        _profile_store = DBProfileStore(db_path=db_path)
    return _profile_store


def _get_run_store():
    global _run_store
    if _run_store is None:
        from src.database.diagnostic_store import DiagnosticRunStore

        db_path = os.environ.get("DB_DIAGNOSTICS_DB_PATH", "data/debugduck.db")
        _run_store = DiagnosticRunStore(db_path=db_path)
    return _run_store


def _get_db_monitor():
    return _db_monitor


def _get_metrics_store():
    return _metrics_store


def _get_alert_engine():
    return _alert_engine


def _get_db_adapter_registry():
    global _db_adapter_registry
    if _db_adapter_registry is None:
        from src.database.adapters.registry import DatabaseAdapterRegistry
        _db_adapter_registry = DatabaseAdapterRegistry()
    return _db_adapter_registry


# ── Request models ──


class CreateProfileRequest(BaseModel):
    name: str
    engine: str
    host: str
    port: int
    database: str
    username: str
    password: str
    tags: dict[str, str] = {}


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    database: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None


class StartDiagnosticRequest(BaseModel):
    profile_id: str


# ── Profile CRUD ──


@db_router.post("/profiles", status_code=201)
def create_profile(req: CreateProfileRequest):
    store = _get_profile_store()
    profile = store.create(
        name=req.name,
        engine=req.engine,
        host=req.host,
        port=req.port,
        database=req.database,
        username=req.username,
        password=req.password,
        tags=req.tags,
    )
    profile.pop("password", None)
    return profile


@db_router.get("/profiles")
def list_profiles():
    return _get_profile_store().list_all()


@db_router.get("/profiles/{profile_id}")
def get_profile(profile_id: str):
    profile = _get_profile_store().get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    profile.pop("password", None)
    return profile


@db_router.put("/profiles/{profile_id}")
def update_profile(profile_id: str, req: UpdateProfileRequest):
    store = _get_profile_store()
    existing = store.get(profile_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Profile not found")
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    updated = store.update(profile_id, **updates)
    if updated:
        updated.pop("password", None)
    return updated


@db_router.delete("/profiles/{profile_id}")
def delete_profile(profile_id: str):
    store = _get_profile_store()
    if not store.get(profile_id):
        raise HTTPException(status_code=404, detail="Profile not found")
    store.delete(profile_id)
    return {"status": "deleted"}


# ── Health ──


@db_router.get("/profiles/{profile_id}/health")
async def get_health(profile_id: str):
    profile = _get_profile_store().get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    # Try to connect and get health snapshot
    try:
        if profile["engine"] == "postgresql":
            from src.database.adapters.postgres import PostgresAdapter

            adapter = PostgresAdapter(
                host=profile["host"],
                port=profile["port"],
                database=profile["database"],
                username=profile["username"],
                password=profile["password"],
            )
            await adapter.connect()
            try:
                health = await adapter.health_check()
                stats = await adapter.get_performance_stats()
                pool = await adapter.get_connection_pool()
                repl = await adapter.get_replication_status()
                return {
                    "profile_id": profile_id,
                    "status": health.status,
                    "latency_ms": health.latency_ms,
                    "version": health.version,
                    "performance": stats.model_dump(),
                    "connections": pool.model_dump(),
                    "replication": repl.model_dump(),
                }
            finally:
                await adapter.disconnect()
        else:
            return {
                "profile_id": profile_id,
                "status": "unsupported",
                "error": f"Engine '{profile['engine']}' not yet supported",
            }
    except Exception as e:
        return {
            "profile_id": profile_id,
            "status": "error",
            "error": str(e),
        }


# ── Diagnostics ──


async def _run_diagnostic(run_id: str, profile: dict):
    """Background task: run the LangGraph diagnostic graph."""
    run_store = _get_run_store()
    try:
        if profile["engine"] == "postgresql":
            from src.database.adapters.postgres import PostgresAdapter

            adapter = PostgresAdapter(
                host=profile["host"],
                port=profile["port"],
                database=profile["database"],
                username=profile["username"],
                password=profile["password"],
            )
            await adapter.connect()
        else:
            from src.database.adapters.mock_adapter import MockDatabaseAdapter

            adapter = MockDatabaseAdapter(
                engine=profile["engine"],
                host=profile["host"],
                port=profile["port"],
                database=profile["database"],
            )
            await adapter.connect()

        try:
            from src.agents.database.graph import build_db_diagnostic_graph

            graph = build_db_diagnostic_graph()
            initial_state = {
                "run_id": run_id,
                "profile_id": profile["id"],
                "engine": profile["engine"],
                "status": "running",
                "findings": [],
                "symptoms": [],
                "dispatched_agents": [],
                "summary": "",
                "_adapter": adapter,
                "_run_store": run_store,
            }

            result = graph.invoke(initial_state)

            # Persist findings
            for finding in result.get("findings", []):
                run_store.add_finding(run_id, finding)
            run_store.update(
                run_id,
                status="completed",
                summary=result.get("summary", ""),
                completed_at=datetime.utcnow().isoformat(),
            )
            logger.info("Diagnostic run %s completed: %s", run_id, result.get("summary"))
        finally:
            await adapter.disconnect()

    except Exception as e:
        logger.error("Diagnostic run %s failed: %s", run_id, e)
        run_store.update(
            run_id,
            status="failed",
            summary=f"Error: {e}",
            completed_at=datetime.utcnow().isoformat(),
        )


@db_router.post("/diagnostics/start")
async def start_diagnostic(req: StartDiagnosticRequest, background_tasks: BackgroundTasks):
    profile = _get_profile_store().get(req.profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    run_store = _get_run_store()
    run = run_store.create(profile_id=req.profile_id)

    # Launch graph in background
    background_tasks.add_task(_run_diagnostic, run["run_id"], profile)

    return run


@db_router.get("/diagnostics/history")
def list_diagnostic_runs(profile_id: str):
    return _get_run_store().list_by_profile(profile_id)


@db_router.get("/diagnostics/{run_id}")
def get_diagnostic_run(run_id: str):
    run = _get_run_store().get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


# ── Monitor endpoints ──


@db_router.get("/monitor/status")
def monitor_status():
    monitor = _get_db_monitor()
    if monitor:
        return monitor.get_snapshot()
    return {"running": False, "interval": 30, "profiles": []}


@db_router.get("/monitor/metrics/{profile_id}/{metric}")
async def monitor_metrics(profile_id: str, metric: str, duration: str = "1h", resolution: str = "1m"):
    ms = _get_metrics_store()
    if not ms:
        return []
    return await ms.query_db_metrics(profile_id, metric, duration, resolution)


@db_router.post("/monitor/start")
async def monitor_start():
    monitor = _get_db_monitor()
    if not monitor:
        raise HTTPException(status_code=503, detail="DBMonitor not initialized")
    await monitor.start()
    return {"status": "started"}


@db_router.post("/monitor/stop")
async def monitor_stop():
    monitor = _get_db_monitor()
    if not monitor:
        raise HTTPException(status_code=503, detail="DBMonitor not initialized")
    await monitor.stop()
    return {"status": "stopped"}


# ── Alert endpoints ──


@db_router.get("/alerts/rules")
def list_alert_rules():
    engine = _get_alert_engine()
    if not engine:
        from src.database.db_alert_rules import DEFAULT_DB_ALERT_RULES
        return [
            {"id": r.id, "name": r.name, "severity": r.severity,
             "metric": r.metric, "condition": r.condition,
             "threshold": r.threshold, "enabled": r.enabled}
            for r in DEFAULT_DB_ALERT_RULES
        ]
    rules = engine.list_rules()
    return [
        r for r in rules
        if getattr(r, 'entity_type', '') == 'database'
           or (isinstance(r, dict) and r.get('entity_type') == 'database')
    ]


@db_router.post("/alerts/rules")
def create_alert_rule(rule: dict):
    engine = _get_alert_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="AlertEngine not initialized")
    rule["entity_type"] = "database"
    from src.network.alert_engine import AlertRule
    new_rule = AlertRule(**rule)
    engine.add_rule(new_rule)
    return {"id": new_rule.id, "status": "created"}


@db_router.delete("/alerts/rules/{rule_id}")
def delete_alert_rule(rule_id: str):
    engine = _get_alert_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="AlertEngine not initialized")
    engine.remove_rule(rule_id)
    return {"status": "deleted"}


@db_router.get("/alerts/active")
def active_alerts():
    engine = _get_alert_engine()
    if not engine:
        return []
    all_alerts = engine.get_active_alerts()
    return [a for a in all_alerts if a.get("entity_id", "").startswith("db:")]


@db_router.get("/alerts/history")
def alert_history_endpoint(profile_id: Optional[str] = None, severity: Optional[str] = None, limit: int = 50):
    engine = _get_alert_engine()
    if not engine:
        return []
    history = engine.get_alert_history(
        entity_id=f"db:{profile_id}" if profile_id else None,
        severity=severity, limit=limit,
    )
    return history


# ── Schema endpoints ──


@db_router.get("/schema/{profile_id}")
async def get_schema(profile_id: str):
    profile = _get_profile_store().get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    registry = _get_db_adapter_registry()
    adapter = registry.get_by_profile(profile_id)

    if not adapter:
        try:
            if profile["engine"] == "postgresql":
                from src.database.adapters.postgres import PostgresAdapter
                adapter = PostgresAdapter(
                    host=profile["host"], port=profile["port"],
                    database=profile["database"],
                    username=profile["username"], password=profile["password"],
                )
                await adapter.connect()
            else:
                raise HTTPException(status_code=400, detail=f"Unsupported engine: {profile['engine']}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e))

    try:
        schema = await adapter.get_schema_snapshot()
        return schema.model_dump()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@db_router.get("/schema/{profile_id}/table/{table_name}")
async def get_table_detail_endpoint(profile_id: str, table_name: str):
    profile = _get_profile_store().get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    registry = _get_db_adapter_registry()
    adapter = registry.get_by_profile(profile_id)

    if not adapter:
        try:
            if profile["engine"] == "postgresql":
                from src.database.adapters.postgres import PostgresAdapter
                adapter = PostgresAdapter(
                    host=profile["host"], port=profile["port"],
                    database=profile["database"],
                    username=profile["username"], password=profile["password"],
                )
                await adapter.connect()
            else:
                raise HTTPException(status_code=400, detail=f"Unsupported engine: {profile['engine']}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e))

    try:
        detail = await adapter.get_table_detail(table_name)
        return detail.model_dump()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
