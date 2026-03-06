"""Network Monitor -- 30s collection engine for device status, metrics, drift, and discovery."""
import asyncio
import logging
from collections import defaultdict

try:
    from icmplib import async_ping
except ImportError:  # pragma: no cover — optional at import time, patched in tests
    async_ping = None  # type: ignore[assignment]

from .topology_store import TopologyStore
from .drift_engine import DriftEngine
from .discovery_engine import DiscoveryEngine
from .snmp_collector import SNMPCollector, SNMPDeviceConfig
from .alert_engine import AlertEngine

logger = logging.getLogger(__name__)

# Thresholds for status derivation
_LATENCY_DEGRADED_MS = 100.0
_PACKET_LOSS_DEGRADED = 0.10
_PROBE_TIMEOUT = 5


class NetworkMonitor:
    """Background collector that runs a probe/adapter/drift/discovery cycle."""

    def __init__(self, store: TopologyStore, kg, adapters,
                 prometheus_url: str | None = None, metrics_store=None):
        self.store = store
        self.kg = kg
        self.adapters = adapters
        self.prometheus_url = prometheus_url
        self.metrics_store = metrics_store
        self.drift_engine = DriftEngine(store)
        self.discovery_engine = DiscoveryEngine(store, kg)
        self.snmp_collector = SNMPCollector(metrics_store) if metrics_store else None
        self.alert_engine = AlertEngine(metrics_store, load_defaults=True) if metrics_store else None
        if self.alert_engine:
            from .notification_dispatcher import NotificationDispatcher
            self.alert_engine.set_dispatcher(NotificationDispatcher())
        self._latest_alerts: list[dict] = []
        self.cycle_interval = 30
        self._task: asyncio.Task | None = None

    # ── Lifecycle ──

    async def start(self):
        self._task = asyncio.create_task(self._run_loop())
        logger.info("NetworkMonitor started (interval=%ds)", self.cycle_interval)

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("NetworkMonitor stopped")

    async def _run_loop(self):
        while True:
            try:
                await self._collect_cycle()
            except Exception as e:
                logger.error("Monitor cycle failed: %s", e)
            await asyncio.sleep(self.cycle_interval)

    # ── Collection Cycle ──

    async def _collect_cycle(self):
        await self._probe_pass()
        await self._adapter_pass()
        await self._drift_pass()
        await self._discovery_pass()
        await self._snmp_pass()
        await self._alert_pass()
        self.store.prune_metric_history(older_than_days=7)

    async def _probe_pass(self):
        devices = self.store.list_devices()
        tasks = []
        for d in devices:
            if not d.management_ip:
                continue
            tasks.append(self._probe_one(d.id, d.management_ip))
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _probe_one(self, device_id: str, ip: str):
        try:
            result = await asyncio.wait_for(
                async_ping(ip, count=3, timeout=2),
                timeout=_PROBE_TIMEOUT,
            )
            latency = result.avg_rtt
            loss = result.packet_loss
            alive = result.is_alive

            if not alive:
                status = "down"
            elif latency > _LATENCY_DEGRADED_MS or loss > _PACKET_LOSS_DEGRADED:
                status = "degraded"
            else:
                status = "up"

            self.store.upsert_device_status(device_id, status, latency, loss, "icmp")
            self.store.append_metric("device", device_id, "latency_ms", latency)
            self.store.append_metric("device", device_id, "packet_loss", loss)

        except Exception as e:
            logger.debug("Probe failed for %s (%s): %s", device_id, ip, e)
            self.store.upsert_device_status(device_id, "down", 0.0, 1.0, "icmp")

    async def _adapter_pass(self):
        for instance_id, adapter in self.adapters.all_instances().items():
            try:
                await adapter.get_interfaces()
            except Exception as e:
                logger.debug("Adapter pass failed for %s: %s", instance_id, e)

    async def _drift_pass(self):
        # device_bindings() returns {device_id: instance_id}
        # Invert to {instance_id: [device_ids]} for per-adapter iteration
        bindings = self.adapters.device_bindings()
        instance_devices: dict[str, list[str]] = defaultdict(list)
        for device_id, instance_id in bindings.items():
            instance_devices[instance_id].append(device_id)

        for instance_id, adapter in self.adapters.all_instances().items():
            for device_id in instance_devices.get(instance_id, []):
                try:
                    events = await self.drift_engine.check_device(device_id, adapter)
                    for event in events:
                        self.store.upsert_drift_event(
                            event["entity_type"], event["entity_id"],
                            event["drift_type"], event["field"],
                            event["expected"], event["actual"], event["severity"],
                        )
                except Exception as e:
                    logger.debug("Drift check failed for %s: %s", device_id, e)

    async def _discovery_pass(self):
        try:
            candidates = await self.discovery_engine.discover_from_adapters(self.adapters)
            for c in candidates:
                self.store.upsert_discovery_candidate(
                    c["ip"], c.get("mac", ""), c.get("hostname", ""),
                    c["discovered_via"], c.get("source_device_id", ""),
                )
        except Exception as e:
            logger.debug("Adapter discovery failed: %s", e)

        try:
            probe_candidates = await self.discovery_engine.probe_known_subnets()
            for c in probe_candidates:
                self.store.upsert_discovery_candidate(
                    c["ip"], c.get("mac", ""), c.get("hostname", ""),
                    c["discovered_via"], c.get("source_device_id", ""),
                )
        except Exception as e:
            logger.debug("Probe discovery failed: %s", e)

    async def _snmp_pass(self):
        if not self.snmp_collector:
            return
        configs = []
        for d in self.store.list_devices():
            if not d.management_ip:
                continue
            # Check if SNMP is enabled via device attributes or KG node
            node_data = {}
            if hasattr(self.kg, 'graph') and d.id in self.kg.graph:
                node_data = dict(self.kg.graph.nodes[d.id])
            if node_data.get("snmp_enabled"):
                configs.append(SNMPDeviceConfig(
                    device_id=d.id, ip=d.management_ip,
                    version=node_data.get("snmp_version", "v2c"),
                    community=node_data.get("snmp_community", "public"),
                    port=int(node_data.get("snmp_port", 161)),
                ))
        if configs:
            await self.snmp_collector.poll_all(configs)

    async def _alert_pass(self):
        if not self.alert_engine:
            return
        device_ids = [d["device_id"] for d in self.store.list_device_statuses()]
        self._latest_alerts = await self.alert_engine.evaluate_all(device_ids)

    # ── Snapshot API ──

    def get_snapshot(self) -> dict:
        return {
            "devices": self.store.list_device_statuses(),
            "links": self.store.list_link_metrics(),
            "drifts": self.store.list_active_drift_events(),
            "candidates": self.store.list_discovery_candidates(),
            "alerts": self.alert_engine.get_active_alerts() if self.alert_engine else [],
        }
