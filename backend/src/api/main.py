"""
FastAPI Main Application
Entry point for the API server
"""

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from .pr_endpoints import router as pr_router
from datetime import datetime

from .routes_v4 import router_v4
from .agent_endpoints import agent_router
from .routes_v5 import router as v5_router
from .routes_profiles import router as profiles_router
from .routes_global_integrations import router as global_integrations_router
from .routes_audit import router as audit_router
from .routes_closure import router as closure_router
from .network_endpoints import network_router
from .monitor_endpoints import monitor_router
from .websocket import manager
from src.utils.logger import get_logger

logger = get_logger("main")


def _init_stores():
    """Initialize database tables and seed defaults on startup."""
    from src.integrations.profile_store import ProfileStore, GlobalIntegrationStore
    from src.integrations.audit_store import AuditLogger
    from src.integrations.credential_resolver import get_credential_resolver

    profile_store = ProfileStore()
    profile_store._ensure_tables()

    gi_store = GlobalIntegrationStore()
    gi_store._ensure_tables()
    gi_store.seed_defaults()

    audit = AuditLogger()
    audit._ensure_tables()

    # Validate that existing credentials can be decrypted
    resolver = get_credential_resolver()
    stale = []
    for gi in gi_store.list_all():
        if gi.auth_credential_handle:
            try:
                resolver.resolve(gi.id, "credential", gi.auth_credential_handle)
            except Exception:
                stale.append(gi.name)
    if stale:
        logger.warning(
            "ENCRYPTION KEY MISMATCH: Cannot decrypt credentials for: %s. "
            "These were saved with a different encryption key. "
            "Please re-save them in Settings > Integrations.",
            ", ".join(stale),
        )

    logger.info("Database tables initialized and defaults seeded")


def _reload_adapter_instances():
    """Reload adapter instances from DB into the in-memory registry on startup."""
    try:
        from .network_endpoints import _get_topology_store, _adapter_registry
        from src.network.adapters.factory import create_adapter

        store = _get_topology_store()
        instances = store.list_adapter_instances()
        bindings = store.list_device_bindings()

        for inst in instances:
            try:
                adapter = create_adapter(
                    inst.vendor,
                    api_endpoint=inst.api_endpoint,
                    api_key=inst.api_key,
                    extra_config=inst.extra_config,
                )
                _adapter_registry.register(inst.instance_id, adapter)
            except Exception as e:
                logger.warning("Failed to reload adapter %s: %s", inst.instance_id, e)

        for device_id, instance_id in bindings:
            _adapter_registry.bind_device(device_id, instance_id)

        logger.info("Reloaded %d adapter instances and %d device bindings from DB", len(instances), len(bindings))
    except Exception as e:
        logger.warning("Adapter reload skipped: %s", e)


def create_app() -> FastAPI:
    """Create and configure FastAPI application"""

    app = FastAPI(
        title="AI Multi-Agent Troubleshooting API",
        description="Intelligent troubleshooting with LangGraph orchestration",
        version="3.0.0",
        docs_url="/docs",
        redoc_url="/redoc"
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://localhost:5174",
            "http://localhost:3000",
            "http://localhost:3001"
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routes
    app.include_router(pr_router, prefix="/api")
    app.include_router(router_v4)
    app.include_router(agent_router)
    app.include_router(v5_router)
    app.include_router(profiles_router)
    app.include_router(global_integrations_router)
    app.include_router(audit_router)
    app.include_router(closure_router)
    app.include_router(network_router)
    app.include_router(monitor_router)

    @app.on_event("startup")
    async def startup():
        import os
        _init_stores()
        _reload_adapter_instances()
        # Start session TTL cleanup loop
        from .routes_v4 import start_cleanup_task
        start_cleanup_task()

        # ── Initialize InfluxDB + NetworkMonitor ──
        from .network_endpoints import _get_topology_store as _net_topo_store, _adapter_registry
        from .network_endpoints import _knowledge_graph as _net_kg
        from .monitor_endpoints import _get_topology_store as _mon_topo_store
        import src.api.monitor_endpoints as mon_ep

        influx_token = os.getenv("INFLUXDB_TOKEN", "")
        metrics_store = None
        if influx_token:
            from src.network.metrics_store import MetricsStore
            influx_url = os.getenv("INFLUXDB_URL", "http://localhost:8086")
            influx_org = os.getenv("INFLUXDB_ORG", "debugduck")
            influx_bucket = os.getenv("INFLUXDB_BUCKET", "network_metrics")
            metrics_store = MetricsStore(influx_url, influx_token, influx_org, influx_bucket)
            logger.info("InfluxDB MetricsStore initialized at %s", influx_url)
        else:
            logger.info("INFLUXDB_TOKEN not set — InfluxDB metrics disabled")

        try:
            from src.network.monitor import NetworkMonitor
            topo_store = _net_topo_store()
            kg = _net_kg
            monitor = NetworkMonitor(
                topo_store, kg, _adapter_registry,
                metrics_store=metrics_store,
            )
            mon_ep._monitor = monitor
            mon_ep._topology_store = topo_store
            mon_ep._knowledge_graph = kg
            import asyncio
            asyncio.create_task(monitor.start())
            logger.info("NetworkMonitor started")
        except Exception as e:
            logger.warning("NetworkMonitor startup failed: %s", e)

    # WebSocket endpoint
    @app.websocket("/ws/troubleshoot/{session_id}")
    async def websocket_endpoint(websocket: WebSocket, session_id: str):
        """WebSocket endpoint for real-time updates"""
        await manager.connect(session_id, websocket)
        
        try:
            # Send initial connection message
            await manager.send_message(session_id, {
                "type": "connected",
                "data": {
                    "message": "WebSocket connection established",
                    "session_id": session_id,
                    "timestamp": datetime.now().isoformat()
                }
            })
            
            # Keep connection alive and receive messages
            while True:
                try:
                    data = await websocket.receive_json()
                    
                    # Handle approval messages (V3 legacy — log warning)
                    if data.get("type") == "approval":
                        logger.warning("V3 approval no longer supported", extra={"session_id": session_id})

                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.error("WebSocket error", extra={"session_id": session_id, "error": str(e)})
                    break
        
        finally:
            manager.disconnect(session_id, websocket)
    
    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    print("🚀 Starting AI Multi-Agent Troubleshooting API...")
    print("📍 API: http://localhost:8000")
    print("📖 Docs: http://localhost:8000/docs")
    print("🔌 WebSocket: ws://localhost:8000/ws/troubleshoot/{session_id}")
    
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
