"""
FastAPI Main Application
Entry point for the API server
"""

from contextlib import asynccontextmanager
from pathlib import Path as _P
from dotenv import load_dotenv
load_dotenv(_P(__file__).resolve().parent.parent.parent / ".env")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from .pr_endpoints import router as pr_router
from datetime import datetime

from src.utils.fix_job_queue import FixJobQueue
from .routes_v4 import router_v4
from .routes_feedback import feedback_router
from .routes_catalog import router as catalog_router
from .routes_workflows import router as workflows_router
from . import db_session_endpoints as _db_session_endpoints  # noqa: F401 — ensure module is loaded
from .agent_endpoints import agent_router
from .routes_v5 import router as v5_router
from .routes_profiles import router as profiles_router
from .routes_global_integrations import router as global_integrations_router
from .routes_audit import router as audit_router
from .routes_closure import router as closure_router
from .network_endpoints import network_router
from .network_chat_endpoints import network_chat_router
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
from .collector_endpoints import collector_router, init_collector_endpoints
from .assistant_endpoints import assistant_router
from .network_metrics_endpoints import router as monitoring_metrics_router, init_monitoring
from .network_flow_endpoints import router as flow_analysis_router, init_flows
from .network_probe_endpoints import router as probe_router, init_probes
from .network_discovery_endpoints import router as autodiscovery_router, init_discovery as init_autodiscovery
from .network_drift_endpoints import router as drift_router, init_drift
from .network_event_endpoints import router as event_router, init_events
from .network_alert_endpoints import router as alert_rules_router, init_alerts
from .topology_v5 import router as topology_v5_router
from .routes_alerts import router as alerts_router
from .websocket import manager

# Cloud integration (multi-provider inventory)
from src.cloud.api.router import create_cloud_router
from src.cloud.cloud_store import CloudStore
from src.network.prometheus_exporter import MetricsCollector
from pathlib import Path
from src.config import APP_MODE, is_production_mode
from src.utils.logger import get_logger
from src.utils.redis_store import get_redis_client, RedisSessionStore

logger = get_logger("main")


async def _pending_action_timeout_loop(app_ref):
    """Check for expired pending actions and re-emit with cleared expiry."""
    import asyncio
    import json

    while True:
        await asyncio.sleep(30)
        try:
            redis_client = getattr(app_ref.state, 'redis', None)
            if not redis_client:
                continue
            cursor = 0
            while True:
                cursor, keys = await redis_client.scan(cursor, match="pending_action:*", count=100)
                for key in keys:
                    raw = await redis_client.get(key)
                    if not raw:
                        continue
                    from src.models.pending_action import PendingAction
                    data = json.loads(raw if isinstance(raw, str) else raw.decode())
                    pa = PendingAction.from_dict(data)
                    if pa.is_expired():
                        session_id = key.decode().split(":")[-1] if isinstance(key, bytes) else key.split(":")[-1]
                        pa.expires_at = None
                        await redis_client.set(
                            key if isinstance(key, str) else key.decode(),
                            json.dumps(pa.to_dict()),
                            ex=86400,
                        )
                        logger.info("Pending action timed out for session %s, reset to indefinite", session_id)
                if cursor == 0:
                    break
        except Exception:
            pass


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
    import os

    # Forward-referenced — the actual functions are defined further down in
    # this closure. Lifespan only invokes them at serve-time, by which point
    # they're bound in scope.
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await startup()
        try:
            yield
        finally:
            await shutdown()

    app = FastAPI(
        title="AI Multi-Agent Troubleshooting API",
        description="Intelligent troubleshooting with LangGraph orchestration",
        version="3.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # API key authentication middleware (only when API_KEYS env var is set)
    if os.environ.get("API_KEYS", "").strip():
        from .auth import APIKeyMiddleware
        app.add_middleware(APIKeyMiddleware)

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

    # K8s-canonical health probes (/healthz + /readyz) — see src/api/health.py.
    # Mounted first so probes work even if a downstream router fails to load.
    from .health import router as health_router
    app.include_router(health_router)

    # Include routes
    app.include_router(pr_router, prefix="/api")
    app.include_router(router_v4)
    app.include_router(feedback_router)
    app.include_router(catalog_router)
    # Workflow endpoints 404 internally when WORKFLOWS_ENABLED is false, so
    # mounting unconditionally is safe and keeps the router wired in one place.
    app.include_router(workflows_router)
    app.include_router(agent_router)
    app.include_router(v5_router)
    app.include_router(profiles_router)
    app.include_router(global_integrations_router)
    app.include_router(audit_router)
    app.include_router(closure_router)
    app.include_router(flow_router)
    app.include_router(network_router)
    app.include_router(network_chat_router)
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
    app.include_router(collector_router)
    app.include_router(assistant_router)
    app.include_router(monitoring_metrics_router)
    app.include_router(flow_analysis_router)
    app.include_router(probe_router)
    app.include_router(autodiscovery_router)
    app.include_router(drift_router)
    app.include_router(event_router)
    app.include_router(alert_rules_router)
    app.include_router(topology_v5_router)
    app.include_router(alerts_router)

    # Cloud integration router (multi-provider inventory)
    _cloud_store = CloudStore()
    _cloud_integration_router = create_cloud_router(_cloud_store)
    app.include_router(_cloud_integration_router)

    async def startup():
        import os
        _mode = "PRODUCTION" if is_production_mode() else "DEMO"
        logger.info("DebugDuck starting in %s mode (DEBUGDUCK_MODE=%s)", _mode, os.environ.get("DEBUGDUCK_MODE", "<unset>"))

        # ── Agent contract registry (Phase 1 Task 7) ──
        from src.contracts.service import init_registry as _init_contract_registry
        _init_contract_registry()
        logger.info("Agent ContractRegistry initialized")

        # ── Workflow subsystem (Phase 2 Task 19) ──
        # Flag-gated; integrity errors (missing runner for a Phase-0 contract)
        # are *fatal* — they propagate and refuse to boot the app.
        from src.config import settings as _settings
        if _settings.WORKFLOWS_ENABLED:
            from src.contracts.service import get_registry as _get_contract_registry
            from src.workflows import runners as _wf_runners
            from src.workflows.repository import WorkflowRepository
            from src.workflows.service import WorkflowService
            from src.api.routes_workflows import set_workflow_service

            contracts = _get_contract_registry()
            runners = _wf_runners.init_runners()
            missing = runners.verify_covers(contracts)
            if missing:
                raise RuntimeError(
                    f"Phase 2 startup: missing runners for contracts {missing}"
                )

            wf_db_path = os.environ.get(
                "WORKFLOWS_DB_PATH",
                os.environ.get("DEBUGDUCK_DB_PATH", "./data/debugduck.db"),
            )
            repo = WorkflowRepository(wf_db_path)
            await repo.init()
            service = WorkflowService(
                repo=repo, contracts=contracts, runners=runners
            )
            set_workflow_service(service)
            logger.info(
                "WorkflowService initialized (db=%s, runners=%d)",
                wf_db_path,
                len(contracts.list_all_versions()),
            )

        # ── Initialize Redis session store ──
        try:
            app.state.redis = await get_redis_client()
            app.state.session_store = RedisSessionStore(app.state.redis)
            logger.info("Redis session store initialized")
        except Exception as e:
            logger.warning("Redis session store init failed (falling back to in-memory): %s", e)
            app.state.redis = None
            app.state.session_store = None

        # ── Background timeout handler for expired pending actions ──
        import asyncio as _aio
        _aio.create_task(_pending_action_timeout_loop(app))

        _init_stores()
        _reload_adapter_instances()

        # Initialize DiagnosticStore
        try:
            from src.observability.store import get_store
            store = get_store()
            await store.initialize()
            logger.info("DiagnosticStore initialized")
        except Exception as e:
            logger.warning("DiagnosticStore initialization failed: %s", e)

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

        # ── Initialize Event Bus ──
        event_bus = None
        event_store = None
        try:
            import os as _os
            from src.network.event_bus import RedisEventBus, MemoryEventBus
            from src.network.collectors.event_store import EventStore

            redis_url = _os.getenv("REDIS_URL")
            if redis_url:
                event_bus = RedisEventBus(redis_url)
                logger.info("Event bus: Redis Streams at %s", redis_url)
            else:
                event_bus = MemoryEventBus()
                logger.info("Event bus: in-process MemoryEventBus (set REDIS_URL for Redis)")

            event_store = EventStore()
            logger.info("EventStore initialized")
        except Exception as e:
            logger.warning("Event bus init failed: %s", e)

        # ── Production mode: clear leftover demo data from previous runs ──
        if is_production_mode():
            try:
                topo_store = _net_topo_store()
                removed = topo_store.clear_all_fixtures()
                if removed:
                    logger.info("Production mode: cleared %d demo rows from topology store", removed)
                # Clear stale metrics so alert engine doesn't fire on old demo data
                metrics_db = Path(__file__).parent.parent / "data" / "metrics.db"
                if metrics_db.exists():
                    metrics_db.unlink()
                    logger.info("Production mode: cleared stale metrics.db")
            except Exception as e:
                logger.warning("Production mode cleanup failed: %s", e)

        # ── Load enterprise network fixtures into topology store ──
        try:
            from src.network.fixture_loader import load_enterprise_fixtures
            topo_store = _net_topo_store()
            fixture_result = load_enterprise_fixtures(topo_store)
            if fixture_result.get("loaded"):
                logger.info("Enterprise fixtures: %d entities loaded", fixture_result.get("total", 0))
                # Rebuild KG from store so fixtures are visible in topology/path diagnosis
                if _net_kg:
                    _net_kg.load_from_store()
                    logger.info("Knowledge graph rebuilt with fixture data")
        except Exception as e:
            logger.warning("Enterprise fixture loading failed: %s", e)

        try:
            from src.network.monitor import NetworkMonitor
            topo_store = _net_topo_store()
            kg = _net_kg
            monitor = NetworkMonitor(
                topo_store, kg, _adapter_registry,
                metrics_store=metrics_store,
                broadcast_callback=manager.broadcast,
                event_bus=event_bus,
                event_store=event_store,
            )
            mon_ep._monitor = monitor
            mon_ep._topology_store = topo_store
            mon_ep._knowledge_graph = kg
            import asyncio
            asyncio.create_task(monitor.start())
            logger.info("NetworkMonitor started")
        except Exception as e:
            logger.warning("NetworkMonitor startup failed: %s", e)

        # ── Initialize Protocol Collector endpoints ──
        try:
            if mon_ep._monitor:
                m = mon_ep._monitor
                init_collector_endpoints(
                    instance_store=m.instance_store,
                    profile_loader=m.profile_loader,
                    snmp_collector=m.protocol_snmp,
                    autodiscovery=m.autodiscovery_engine,
                    ping_prober=m.ping_prober,
                    event_store=event_store,
                    metrics_store=metrics_store,
                    topology_store=topo_store,
                )
                logger.info("Collector endpoints initialized (%d profiles loaded)",
                          len(m.profile_loader.list_profiles()))
        except Exception as e:
            logger.warning("Collector endpoints init failed: %s", e)

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
                flow_receiver_instance = FlowReceiver(metrics_store, topo_store, event_bus=event_bus)
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

        # ── Initialize SQLite Metrics Store + Schedulers ──
        try:
            import asyncio as _asyncio
            from src.network.sqlite_metrics_store import SQLiteMetricsStore
            from src.network.snmp_scheduler import SNMPPollingScheduler

            _sqlite_metrics = SQLiteMetricsStore()
            _snmp_sched = SNMPPollingScheduler(_sqlite_metrics, interval_seconds=60)

            # Build device list from topology store — demo mode only
            _device_list = []
            _is_prod = is_production_mode()
            if _is_prod:
                logger.info("Production mode: skipping fixture device loading for schedulers")
            else:
                try:
                    topo_store = _net_topo_store()
                    devices = topo_store.list_devices()
                    if devices:
                        _device_list = [
                            {"id": d.id, "name": d.name, "vendor": d.vendor, "management_ip": d.management_ip, "ha_role": getattr(d, 'ha_role', '')}
                            for d in devices if d.management_ip
                        ]
                        _snmp_sched.set_devices(_device_list)
                except Exception:
                    pass

            # ── SQLite Alert Engine ──
            _sqlite_alert_engine = None
            try:
                from src.network.sqlite_alert_engine import SQLiteAlertEngine
                _sqlite_alert_engine = SQLiteAlertEngine(_sqlite_metrics)
                _sqlite_alert_engine.set_devices(_device_list)
                _asyncio.create_task(_sqlite_alert_engine.start(interval=30))
                logger.info("SQLiteAlertEngine started (%d rules, %d devices)",
                           len(_sqlite_alert_engine.get_rules()), len(_device_list))
            except Exception as e:
                logger.warning("SQLiteAlertEngine startup failed: %s", e)

            init_monitoring(_sqlite_metrics, _snmp_sched, alert_engine=_sqlite_alert_engine)

            # ── Alert endpoints ──
            try:
                init_alerts(_sqlite_metrics, _sqlite_alert_engine)
                logger.info("Alert endpoints initialized")
            except Exception as e:
                logger.warning("Alert endpoints init failed: %s", e)

            # ── Event endpoints ──
            try:
                init_events(_sqlite_metrics, event_store)
                logger.info("Event endpoints initialized")
            except Exception as e:
                logger.warning("Event endpoints init failed: %s", e)

            # Share SQLite metrics store with network_endpoints for topology health overlay
            import src.api.network_endpoints as _net_ep
            _net_ep._sqlite_metrics_store = _sqlite_metrics

            if not _is_prod:
                _asyncio.create_task(_snmp_sched.start())
                logger.info("SQLite MetricsStore + SNMP scheduler started")
            else:
                logger.info("SQLite MetricsStore initialized (SNMP scheduler disabled in production)")

            # ── Discovery Scheduler ──
            if not _is_prod:
                try:
                    from src.network.discovery_scheduler import DiscoveryScheduler
                    _discovery_sched = DiscoveryScheduler(interval_seconds=300)
                    _discovery_sched.set_devices(_device_list)
                    init_autodiscovery(_discovery_sched)
                    _asyncio.create_task(_discovery_sched.start())
                    logger.info("DiscoveryScheduler started (%d devices)", len(_device_list))
                except Exception as e:
                    logger.warning("DiscoveryScheduler startup failed: %s", e)

            # ── Config Drift Engine ──
            try:
                from src.network.config_drift import ConfigDriftEngine
                _drift_engine = ConfigDriftEngine()
                init_drift(_drift_engine)
                logger.info("ConfigDriftEngine initialized")
            except Exception as e:
                logger.warning("ConfigDriftEngine startup failed: %s", e)

            # ── Flow Store (SQLite-based flow aggregation) ──
            try:
                from src.network.flow_store import FlowStore
                _flow_store = FlowStore()
                init_flows(_flow_store)
                logger.info("FlowStore initialized")
            except Exception as e:
                logger.warning("FlowStore init failed: %s", e)

            # ── Mock Event Generator (syslog/trap demo data — demo only) ──
            if not _is_prod:
                try:
                    from src.network.event_generator import MockEventGenerator
                    _event_gen = MockEventGenerator(_sqlite_metrics)
                    _asyncio.create_task(_event_gen.start())
                    logger.info("MockEventGenerator started")
                except Exception as e:
                    logger.warning("MockEventGenerator startup failed: %s", e)

            # ── Ping Probe Scheduler ──
            if not _is_prod:
                try:
                    from src.network.ping_scheduler import PingProbeScheduler
                    _ping_sched = PingProbeScheduler(_sqlite_metrics, interval_seconds=30)
                    init_probes(_sqlite_metrics, _ping_sched)

                    # Load probe targets from topology store devices
                    try:
                        topo_store = _net_topo_store()
                        devices = topo_store.list_devices()
                        if devices:
                            _ping_sched.set_targets([
                                {"ip": d.management_ip, "name": d.id}
                                for d in devices if d.management_ip
                            ])
                    except Exception:
                        pass

                    _asyncio.create_task(_ping_sched.start())
                    logger.info("PingProbeScheduler started")
                except Exception as e:
                    logger.warning("PingProbeScheduler startup failed: %s", e)

        except Exception as e:
            logger.warning("SQLite metrics / SNMP scheduler startup failed: %s", e)

        # ── Start Fix Job Queue ──
        try:
            await FixJobQueue.get_instance().start()
            logger.info("FixJobQueue started")
        except Exception as e:
            logger.warning("FixJobQueue startup failed: %s", e)

        # ── Initialize DB Monitor ──
        try:
            import asyncio
            from src.database.db_monitor import DBMonitor
            from src.database.db_alert_rules import DEFAULT_DB_ALERT_RULES
            import src.api.db_endpoints as db_ep

            db_profile_store = db_ep._get_profile_store()
            db_registry = db_ep._get_db_adapter_registry()

            db_alert_engine = None
            try:
                if monitor and hasattr(monitor, 'alert_engine') and monitor.alert_engine:
                    db_alert_engine = monitor.alert_engine
                    for rule in DEFAULT_DB_ALERT_RULES:
                        try:
                            db_alert_engine.add_rule(rule)
                        except Exception:
                            pass
            except Exception:
                pass

            db_monitor = DBMonitor(
                profile_store=db_profile_store,
                adapter_registry=db_registry,
                metrics_store=metrics_store,
                alert_engine=db_alert_engine,
                broadcast_callback=manager.broadcast,
            )
            db_ep._db_monitor = db_monitor
            db_ep._metrics_store = metrics_store
            db_ep._alert_engine = db_alert_engine
            db_ep._db_adapter_registry = db_registry

            asyncio.create_task(db_monitor.start())
            logger.info("DBMonitor started")
        except Exception as e:
            logger.warning("DBMonitor startup failed: %s", e)

        # ── Remediation Engine ──
        try:
            from src.database.remediation_store import RemediationStore
            from src.database.remediation_engine import RemediationEngine
            db_path = os.environ.get("DB_DIAGNOSTICS_DB_PATH", "data/debugduck.db")
            remediation_store = RemediationStore(db_path=db_path)
            remediation_engine = RemediationEngine(
                plan_store=remediation_store,
                adapter_registry=db_registry,
                profile_store=db_profile_store,
                secret_key=os.environ.get("REMEDIATION_SECRET_KEY", "debugduck-remediation-secret"),
            )
            db_ep._remediation_engine = remediation_engine
            logger.info("RemediationEngine initialized")
        except Exception as e:
            logger.warning("RemediationEngine startup failed: %s", e)

        # Stage K.13 — persist seeded prompt registry so every agent prompt
        # has a stable content-addressed version_id row in prompt_versions.
        # Best-effort: a DB issue logs + continues so the app still boots.
        try:
            from src.prompts.registry import PromptRegistry
            _reg = PromptRegistry()
            for prompt in _reg.list_all():
                try:
                    await _reg.ensure_persisted(prompt.agent)
                except Exception as _reg_exc:
                    logger.warning(
                        "prompt registry ensure_persisted failed for %s: %s",
                        prompt.agent, _reg_exc,
                    )
            logger.info("Prompt registry seeded (%d agents)", len(_reg.list_all()))
        except Exception as e:
            logger.warning("Prompt registry bootstrap failed: %s", e)

        # Stage K.14 — resume orphaned investigations whose owning pod
        # went away mid-flight. Best-effort: every failure logged and
        # swallowed so a resume issue never blocks the API coming up.
        if os.environ.get("DIAGNOSTIC_RESUME_ON_STARTUP", "off").strip().lower() == "on":
            try:
                from src.workflows.resume import resume_all_in_progress
                # acquire_lock + dispatch_resume are deferred: the real
                # wiring requires a route-layer SupervisorAgent factory.
                # For this stage we just log candidates.
                async def _log_only_lock(run_id: str) -> bool:
                    logger.info(
                        "resume candidate (lock not acquired, logging only): %s",
                        run_id,
                    )
                    return False

                async def _noop_dispatch(run):
                    return None

                taken = await resume_all_in_progress(
                    acquire_lock=_log_only_lock,
                    dispatch_resume=_noop_dispatch,
                )
                logger.info(
                    "Resume scan complete (%d orphaned runs logged; "
                    "dispatch disabled until supervisor factory lands)",
                    len(taken),
                )
            except Exception as e:
                logger.warning("Resume scan failed: %s", e)

    async def shutdown():
        # ── Close shared per-backend http client pool (Task 3.3) ──
        try:
            from src.integrations.http_clients import close_all as _close_http_clients
            await _close_http_clients()
            logger.info("Shared http client pool closed")
        except Exception as e:
            logger.warning("http_clients.close_all failed: %s", e)

        # ── Close Redis connection ──
        if getattr(app.state, "redis", None):
            try:
                await app.state.redis.aclose()
                logger.info("Redis connection closed")
            except Exception as e:
                logger.warning("Redis shutdown failed: %s", e)

        # ── Shutdown Fix Job Queue ──
        try:
            await FixJobQueue.get_instance().shutdown()
            logger.info("FixJobQueue shut down")
        except Exception as e:
            logger.warning("FixJobQueue shutdown failed: %s", e)

        import src.api.monitor_endpoints as mon_ep
        if mon_ep._monitor:
            # Event bus cleanup is handled by monitor.stop()
            pass

        import src.api.db_endpoints as db_ep
        if db_ep._db_monitor:
            await db_ep._db_monitor.stop()
            logger.info("DBMonitor stopped")

        from src.api import flow_endpoints
        if flow_endpoints._flow_receiver:
            await flow_endpoints._flow_receiver.stop()
            logger.info("FlowReceiver stopped")

        if mon_ep._monitor:
            await mon_ep._monitor.stop()
        if mon_ep._monitor and mon_ep._monitor.metrics_store:
            await mon_ep._monitor.metrics_store.close()
            logger.info("InfluxDB MetricsStore closed")

    # Prometheus metrics endpoint
    @app.get("/metrics", response_class=PlainTextResponse)
    def prometheus_metrics():
        return metrics_collector.generate_metrics()

    # ── Health Check Endpoints ──

    @app.get("/health")
    def health_check():
        """Overall health check.  Returns 200 when all subsystems are OK,
        503 when any check fails."""
        import os
        import sqlite3
        from fastapi.responses import JSONResponse

        checks: dict[str, str] = {}

        # Database check — try to open the default SQLite DB
        db_path = os.environ.get("DEBUGDUCK_DB_PATH", "./data/debugduck.db")
        try:
            conn = sqlite3.connect(db_path)
            conn.execute("SELECT 1")
            conn.close()
            checks["database"] = "ok"
        except Exception:
            checks["database"] = "error"

        # Event bus check — lightweight; just verify module is importable
        try:
            # If the monitor is running we can ask it; otherwise assume OK
            import src.api.monitor_endpoints as mon_ep
            if mon_ep._monitor and hasattr(mon_ep._monitor, "event_bus") and mon_ep._monitor.event_bus:
                checks["event_bus"] = "ok"
            else:
                checks["event_bus"] = "ok"  # not configured is still "ok"
        except Exception:
            checks["event_bus"] = "ok"

        all_ok = all(v == "ok" for v in checks.values())
        status_code = 200 if all_ok else 503

        return JSONResponse(
            status_code=status_code,
            content={"status": "healthy" if all_ok else "unhealthy", "checks": checks},
        )

    @app.get("/health/ready")
    def health_ready():
        """Readiness probe — is the app ready to serve traffic?"""
        import os
        import sqlite3
        from fastapi.responses import JSONResponse

        try:
            db_path = os.environ.get("DEBUGDUCK_DB_PATH", "./data/debugduck.db")
            conn = sqlite3.connect(db_path)
            conn.execute("SELECT 1")
            conn.close()
            return JSONResponse(status_code=200, content={"ready": True})
        except Exception:
            return JSONResponse(status_code=503, content={"ready": False})

    @app.get("/health/live")
    def health_live():
        """Liveness probe — always returns 200 to indicate the process is alive."""
        return {"alive": True}

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

            # Replay any events emitted before WS connected
            try:
                from .routes_v4 import sessions as _sessions
                session_data = _sessions.get(session_id)
                # Fall back to Redis session store if not in memory
                if not session_data and getattr(app.state, "session_store", None):
                    session_data = await app.state.session_store.load(session_id)
                if session_data:
                    emitter = session_data.get("emitter")
                    if emitter and hasattr(emitter, 'get_all_events'):
                        for event in emitter.get_all_events():
                            await manager.send_message(session_id, {
                                "type": "task_event",
                                "data": event.model_dump(mode="json"),
                            })
            except Exception as e:
                logger.warning("Event replay failed: %s", e)
            
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
