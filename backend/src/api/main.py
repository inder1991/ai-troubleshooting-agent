"""
FastAPI Main Application
Entry point for the API server
"""

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
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
from .dns_endpoints import router as dns_router
from .flow_endpoints import flow_router, init_flow_endpoints
from .export_endpoints import export_router, init_export_endpoints
from .snmp_endpoints import snmp_router, init_snmp_endpoints
from .topology_query_endpoints import topology_query_router, init_topology_query_endpoints
from .resource_endpoints import resource_router, init_resource_endpoints
from .cloud_endpoints import cloud_router, init_cloud_endpoints
from .security_endpoints import security_router, init_security_endpoints
from .discovery_endpoints import discovery_router, init_discovery_endpoints
from .search_endpoints import search_router, init_search_endpoints
from .db_endpoints import db_router
from .websocket import manager
from src.network.prometheus_exporter import MetricsCollector
from src.utils.logger import get_logger

logger = get_logger("main")

# Module-level Prometheus metrics collector
metrics_collector = MetricsCollector()

# Rate limiter — 60 requests/minute per client IP by default
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])


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

    # Rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
    app.include_router(flow_router)
    app.include_router(network_router)
    app.include_router(monitor_router)
    app.include_router(dns_router)
    app.include_router(export_router)
    app.include_router(snmp_router)
    app.include_router(topology_query_router)
    app.include_router(resource_router)
    app.include_router(cloud_router)
    app.include_router(security_router)
    app.include_router(discovery_router)
    app.include_router(search_router)
    app.include_router(db_router)

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
                broadcast_callback=manager.broadcast,
            )
            mon_ep._monitor = monitor
            mon_ep._topology_store = topo_store
            mon_ep._knowledge_graph = kg
            import asyncio
            asyncio.create_task(monitor.start())
            logger.info("NetworkMonitor started")
        except Exception as e:
            logger.warning("NetworkMonitor startup failed: %s", e)

        # ── Initialize SNMP endpoints ──
        init_snmp_endpoints(kg)

        # ── Initialize Topology Query endpoints ──
        init_topology_query_endpoints(kg)

        # ── Initialize Flow endpoints ──
        flow_receiver_instance = None
        if os.getenv("FLOW_RECEIVER_ENABLED") == "1" and metrics_store:
            try:
                from src.network.flow_receiver import FlowReceiver
                topo_store = _net_topo_store()
                flow_receiver_instance = FlowReceiver(metrics_store, topo_store)
                device_map = {d.management_ip: d.id for d in topo_store.list_devices() if d.management_ip}
                flow_receiver_instance.update_device_map(device_map)
                flow_port = int(os.getenv("FLOW_RECEIVER_PORT", "2055"))
                await flow_receiver_instance.start(ports={"netflow": flow_port})
                logger.info("FlowReceiver started on port %d", flow_port)
            except Exception as e:
                logger.warning("FlowReceiver startup failed: %s", e)
                flow_receiver_instance = None
        init_flow_endpoints(metrics_store, flow_receiver_instance)

        # ── Initialize Export endpoints ──
        try:
            topo_store = _net_topo_store()
            init_export_endpoints(topo_store)
            logger.info("Export endpoints initialized")
        except Exception as e:
            logger.warning("Export endpoints init failed: %s", e)

        # ── Initialize Resource CRUD endpoints ──
        try:
            topo_store = _net_topo_store()
            init_resource_endpoints(topo_store)
            logger.info("Resource CRUD endpoints initialized")
        except Exception as e:
            logger.warning("Resource CRUD endpoints init failed: %s", e)

        # ── Initialize Cloud CRUD endpoints ──
        try:
            topo_store = _net_topo_store()
            init_cloud_endpoints(topo_store)
            logger.info("Cloud CRUD endpoints initialized")
        except Exception as e:
            logger.warning("Cloud CRUD endpoints init failed: %s", e)

        # ── Initialize Security CRUD endpoints ──
        try:
            topo_store = _net_topo_store()
            init_security_endpoints(topo_store)
            logger.info("Security CRUD endpoints initialized")
        except Exception as e:
            logger.warning("Security CRUD endpoints init failed: %s", e)

        # ── Initialize Discovery endpoints ──
        try:
            topo_store = _net_topo_store()
            discovery_engine = None
            try:
                from src.network.discovery_engine import DiscoveryEngine
                discovery_engine = DiscoveryEngine(topo_store, kg)
                logger.info("DiscoveryEngine initialized")
            except Exception as e:
                logger.warning("DiscoveryEngine not available: %s", e)
            init_discovery_endpoints(topo_store, discovery_engine)
            logger.info("Discovery endpoints initialized")
        except Exception as e:
            logger.warning("Discovery endpoints init failed: %s", e)

        # ── Initialize Search endpoints ──
        try:
            topo_store = _net_topo_store()
            init_search_endpoints(topo_store)
            logger.info("Search endpoints initialized")
        except Exception as e:
            logger.warning("Search endpoints init failed: %s", e)

    @app.on_event("shutdown")
    async def shutdown():
        from src.api import flow_endpoints
        if flow_endpoints._flow_receiver:
            await flow_endpoints._flow_receiver.stop()
            logger.info("FlowReceiver stopped")

        import src.api.monitor_endpoints as mon_ep
        if mon_ep._monitor:
            await mon_ep._monitor.stop()
        if mon_ep._monitor and mon_ep._monitor.metrics_store:
            await mon_ep._monitor.metrics_store.close()
            logger.info("InfluxDB MetricsStore closed")

    # Prometheus metrics endpoint
    @app.get("/metrics", response_class=PlainTextResponse)
    def prometheus_metrics():
        return metrics_collector.generate_metrics()

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
