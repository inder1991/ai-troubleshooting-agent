"""Network Monitor -- 30s collection engine for device status, metrics, drift, and discovery."""
import asyncio
import logging
import time
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
from .dns_monitor import DNSMonitor
from .models import DNSMonitorConfig

# Protocol-first collector imports
from .collectors.profile_loader import ProfileLoader
from .collectors.snmp_collector import SNMPProtocolCollector
from .collectors.autodiscovery import AutodiscoveryEngine
from .collectors.collector_registry import CollectorRegistry
from .collectors.instance_store import InstanceStore
from .collectors.ping_prober import PingProber
from .collectors.data_merger import merge_collected_data

from .event_bus import EventBus, RedisEventBus, MemoryEventBus, EventProcessor
from .collectors.trap_listener import SNMPTrapListener
from .collectors.syslog_listener import SyslogListener
from .collectors.event_store import EventStore

logger = logging.getLogger(__name__)

# Thresholds for status derivation
_LATENCY_DEGRADED_MS = 100.0
_PACKET_LOSS_DEGRADED = 0.10
_PROBE_TIMEOUT = 5


class NetworkMonitor:
    """Background collector that runs a probe/adapter/drift/discovery cycle."""

    def __init__(self, store: TopologyStore, kg, adapters,
                 prometheus_url: str | None = None, metrics_store=None,
                 dns_config: DNSMonitorConfig | None = None,
                 broadcast_callback=None,
                 event_bus: EventBus | None = None,
                 event_store: EventStore | None = None):
        self.store = store
        self.kg = kg
        self.adapters = adapters
        self.prometheus_url = prometheus_url
        self.metrics_store = metrics_store
        self.event_bus = event_bus
        self.event_store = event_store
        self.event_processor: EventProcessor | None = None
        self.trap_listener: SNMPTrapListener | None = None
        self.syslog_listener: SyslogListener | None = None
        self.drift_engine = DriftEngine(store)
        self.discovery_engine = DiscoveryEngine(store, kg)
        self.snmp_collector = SNMPCollector(metrics_store) if metrics_store else None
        self.alert_engine = AlertEngine(metrics_store, load_defaults=True) if metrics_store else None
        if self.alert_engine:
            from .notification_dispatcher import NotificationDispatcher
            self.alert_engine.set_dispatcher(NotificationDispatcher())
        self._latest_alerts: list[dict] = []

        # Protocol-first collector infrastructure
        self.profile_loader = ProfileLoader()
        self.profile_loader.load_all()
        self.protocol_snmp = SNMPProtocolCollector()
        self.collector_registry = CollectorRegistry()
        self.collector_registry.register(self.protocol_snmp)
        self.instance_store = InstanceStore()
        self.autodiscovery_engine = AutodiscoveryEngine(
            self.profile_loader, self.protocol_snmp
        )
        self.ping_prober = PingProber()
        self._autodiscovery_interval = 300  # 5 min
        self._last_autodiscovery: float = 0

        self.dns_monitor: DNSMonitor | None = None
        if dns_config and dns_config.enabled:
            self.dns_monitor = DNSMonitor(dns_config)
        self.cycle_interval = 30
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_cycle_at: float | None = None
        self._last_cycle_duration: float | None = None
        self._last_pass_duration: float = 0.0
        self._pass_count: int = 0
        self._broadcast_callback = broadcast_callback
        self.metrics_collector = None

    # ── Heartbeat ──

    @property
    def last_cycle_at(self) -> float | None:
        return self._last_cycle_at

    @property
    def last_cycle_duration(self) -> float | None:
        return self._last_cycle_duration

    def health_status(self) -> str:
        if self._last_cycle_at is None:
            return "unhealthy"
        age = time.monotonic() - self._last_cycle_at
        if age < 120:
            return "healthy"
        elif age < 300:
            return "degraded"
        return "unhealthy"

    def get_stats(self) -> dict:
        """Return monitor pass statistics."""
        return {
            "pass_count": self._pass_count,
            "last_pass_duration_s": self._last_pass_duration,
        }

    # ── Lifecycle ──

    async def start(self):
        # Start event bus and processor
        if self.event_bus:
            await self.event_bus.start()
            if self.event_store:
                self.event_processor = EventProcessor(
                    bus=self.event_bus,
                    event_store=self.event_store,
                    metrics_store=self.metrics_store,
                )
                await self.event_processor.start()

        # Start trap listener if enabled
        import os
        if os.getenv("TRAP_LISTENER_ENABLED") == "1" and self.event_bus:
            self.trap_listener = SNMPTrapListener(
                event_bus=self.event_bus,
                instance_store=self.instance_store,
            )
            await self.trap_listener.start()

        # Start syslog listener if enabled
        if os.getenv("SYSLOG_LISTENER_ENABLED") == "1" and self.event_bus:
            self.syslog_listener = SyslogListener(
                event_bus=self.event_bus,
                instance_store=self.instance_store,
            )
            await self.syslog_listener.start()

        self._task = asyncio.create_task(self._run_loop())
        logger.info("NetworkMonitor started (interval=%ds)", self.cycle_interval)

    async def stop(self):
        self._running = False
        try:
            await asyncio.wait_for(self._cleanup(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning("Shutdown timed out after 10s, forcing cleanup")
            # Cancel any remaining tasks
            if self._task and not self._task.done():
                self._task.cancel()
                try:
                    await self._task
                except (asyncio.CancelledError, Exception):
                    pass
        logger.info("NetworkMonitor stopped")

    async def _cleanup(self):
        """Stop all subsystems gracefully."""
        if self.trap_listener:
            await self.trap_listener.stop()
        if self.syslog_listener:
            await self.syslog_listener.stop()
        if self.event_processor:
            await self.event_processor.stop()
        if self.event_bus:
            await self.event_bus.stop()

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run_loop(self):
        while True:
            pass_start = time.monotonic()
            try:
                await self._collect_cycle()
            except Exception as e:
                logger.error("Monitor cycle failed: %s", e)
            pass_duration = time.monotonic() - pass_start
            self._last_pass_duration = pass_duration
            self._pass_count += 1
            logger.info("Monitor pass %d completed in %.2fs", self._pass_count, pass_duration)
            await asyncio.sleep(self.cycle_interval)

    # ── Collection Cycle ──

    async def _collect_cycle(self):
        t0 = time.monotonic()
        passes = [
            self._probe_pass(),
            self._adapter_pass(),
            self._protocol_pass(),
            self._drift_pass(),
            self._discovery_pass(),
            self._snmp_pass(),
            self._dns_pass(),
            self._ipam_utilization_pass(),
        ]
        # Autodiscovery runs on its own interval (not every 30s)
        if time.time() - self._last_autodiscovery >= self._autodiscovery_interval:
            passes.append(self._autodiscovery_pass())
        results = await asyncio.gather(*passes, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("Monitor pass %d failed: %s", i, result)
        # Alert pass reads data written by the others — must run after gather
        await self._alert_pass()
        await self._ipam_alert_pass()
        self.store.prune_metric_history(older_than_days=7)
        self._last_cycle_at = time.monotonic()
        self._last_cycle_duration = self._last_cycle_at - t0

        if self.metrics_collector:
            self.metrics_collector.record_cycle_duration(self._last_cycle_duration)
            self.metrics_collector.increment_cycle_total()
            self.metrics_collector.set_device_count(len(self.store.list_devices()))
            if self.alert_engine:
                self.metrics_collector.set_active_alerts(len(self.alert_engine.get_active_alerts()))

        # Broadcast monitor update to WebSocket clients
        if self._broadcast_callback:
            try:
                await self._broadcast_callback({
                    "type": "monitor_update",
                    "data": {
                        "active_alerts": len(self._latest_alerts),
                        "drift_count": len(self.store.list_active_drift_events()),
                        "candidate_count": len(self.store.list_discovery_candidates()),
                        "device_count": len(self.store.list_device_statuses()),
                        "cycle_duration": self._last_cycle_duration,
                        "status": self.health_status(),
                    },
                })
            except Exception as e:
                logger.debug("Broadcast failed: %s", e)

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
        async def _query_adapter(instance_id, adapter):
            try:
                await adapter.get_interfaces()
            except Exception as e:
                logger.debug("Adapter pass failed for %s: %s", instance_id, e)

        tasks = [
            _query_adapter(iid, adp)
            for iid, adp in self.adapters.all_instances().items()
        ]
        if tasks:
            await asyncio.gather(*tasks)

    async def _drift_pass(self):
        # device_bindings() returns {device_id: instance_id}
        # Invert to {instance_id: [device_ids]} for per-adapter iteration
        bindings = self.adapters.device_bindings()
        instance_devices: dict[str, list[str]] = defaultdict(list)
        for device_id, instance_id in bindings.items():
            instance_devices[instance_id].append(device_id)

        async def _check_one(device_id, adapter):
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

        tasks = [
            _check_one(device_id, adapter)
            for instance_id, adapter in self.adapters.all_instances().items()
            for device_id in instance_devices.get(instance_id, [])
        ]
        if tasks:
            await asyncio.gather(*tasks)

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

        # ARP table discovery via SNMP
        if self.snmp_collector:
            try:
                arp_candidates = await self.discovery_engine.discover_from_arp(self.snmp_collector)
                for c in arp_candidates:
                    self.store.upsert_discovery_candidate(
                        c["ip"], c.get("mac", ""), c.get("hostname", ""),
                        c["discovered_via"], c.get("source_device_id", ""),
                    )
            except Exception as e:
                logger.debug("ARP discovery failed: %s", e)

        # NetFlow discovery
        if self.metrics_store:
            try:
                flow_candidates = await self.discovery_engine.discover_from_flows(self.metrics_store)
                for c in flow_candidates:
                    self.store.upsert_discovery_candidate(
                        c["ip"], c.get("mac", ""), c.get("hostname", ""),
                        c["discovered_via"], c.get("source_device_id", ""),
                    )
            except Exception as e:
                logger.debug("Flow discovery failed: %s", e)

    async def _protocol_pass(self):
        """Profile-based SNMP/gNMI collection for protocol-monitored devices."""
        try:
            devices = self.instance_store.list_devices()
            if not devices:
                return
            # Build (device, profile) pairs for SNMP collection
            snmp_pairs = []
            for dev in devices:
                if dev.status == "down":
                    continue
                profile = self.profile_loader.get(dev.matched_profile or "generic")
                if not profile:
                    profile = self.profile_loader.get("generic")
                if profile:
                    has_snmp = any(p.protocol == "snmp" and p.enabled for p in dev.protocols)
                    if has_snmp:
                        snmp_pairs.append((dev, profile))

            if snmp_pairs:
                results = await self.protocol_snmp.collect_batch(snmp_pairs)
                for data in results:
                    self.instance_store.update_device_status(
                        data.device_id, "up", data.timestamp
                    )

            # Ping pass for protocol-monitored devices
            ping_results = await self.ping_prober.probe_batch(devices)
            for device_id, ping in ping_results.items():
                self.instance_store.update_device_ping(
                    device_id, ping.model_dump_json()
                )
                if not ping.reachable:
                    self.instance_store.update_device_status(device_id, "unreachable")
        except Exception as e:
            logger.debug("Protocol pass failed: %s", e)

    async def _autodiscovery_pass(self):
        """Subnet scanning for new devices (runs every 5 min, not 30s)."""
        try:
            configs = self.instance_store.list_discovery_configs()
            if not configs:
                return
            discovered = await self.autodiscovery_engine.run_discovery_cycle(configs)
            for device in discovered:
                existing = self.instance_store.get_device_by_ip(device.management_ip)
                if not existing:
                    self.instance_store.upsert_device(device)
                    logger.info("Autodiscovered new device: %s (%s)",
                              device.hostname, device.management_ip)
            # Update discovery config stats
            for config in configs:
                config.last_scan = time.time()
                self.instance_store.upsert_discovery_config(config)
            self._last_autodiscovery = time.time()
        except Exception as e:
            logger.debug("Autodiscovery pass failed: %s", e)

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

    async def _dns_pass(self):
        if not self.dns_monitor:
            return
        try:
            metrics = await self.dns_monitor.run_pass()
            # Write metrics to InfluxDB if metrics_store available
            if self.metrics_store:
                for m in metrics:
                    await self.metrics_store.write_dns_metric(
                        server_id=m["server_id"],
                        server_ip=m["server_ip"],
                        hostname=m["hostname"],
                        record_type=m["record_type"],
                        latency_ms=m["latency_ms"],
                        success=m["success"],
                        metric_type="query",
                    )
            # Store drift events
            for m in metrics:
                drift = m.get("drift")
                if drift:
                    self.store.upsert_drift_event(
                        "dns",
                        f"{m['server_id']}:{m['hostname']}",
                        "dns_record_mismatch",
                        f"{m['hostname']}/{m['record_type']}",
                        ", ".join(drift.get("expected", [])),
                        ", ".join(drift.get("actual", [])),
                        "critical" if m.get("critical") else "warning",
                    )
        except Exception as e:
            logger.debug("DNS pass failed: %s", e)

    async def _alert_pass(self):
        if not self.alert_engine:
            return
        device_ids = [d["device_id"] for d in self.store.list_device_statuses()]
        self._latest_alerts = await self.alert_engine.evaluate_all(device_ids)
        # Check escalation policies for unacknowledged alerts
        dispatcher = getattr(self.alert_engine, '_dispatcher', None)
        if dispatcher:
            try:
                escalated = await dispatcher.check_escalations(
                    self.alert_engine.get_active_alerts()
                )
                if escalated:
                    logger.info("Escalated %d alerts", len(escalated))
            except Exception as e:
                logger.warning("Escalation check failed: %s", e)

    async def _ipam_utilization_pass(self):
        """Snapshot subnet utilization to InfluxDB."""
        if not self.metrics_store:
            return
        try:
            subnets = self.store.list_subnets()
            for subnet in subnets:
                util = self.store.get_subnet_utilization(subnet.id)
                await self.metrics_store.write_ipam_utilization(
                    subnet_id=subnet.id,
                    utilization_pct=util.get("utilization_pct", 0),
                    total=util.get("total", 0),
                    assigned=util.get("assigned", 0),
                    available=util.get("available", 0),
                )
        except Exception as e:
            logger.debug("IPAM utilization pass failed: %s", e)

    async def _ipam_alert_pass(self):
        """Evaluate IPAM-specific alert rules using direct SQLite utilization data."""
        if not self.alert_engine:
            return
        try:
            subnets = self.store.list_subnets()
            for subnet in subnets:
                util = self.store.get_subnet_utilization(subnet.id)
                pct = util.get("utilization_pct", 0)
                # Evaluate against IPAM rules
                for rule in self.alert_engine.rules:
                    if rule.entity_type != "subnet" or not rule.enabled:
                        continue
                    if rule.entity_filter != "*" and rule.entity_filter != subnet.id:
                        continue
                    if rule.metric != "utilization_pct":
                        continue
                    triggered = self.alert_engine._check_condition(pct, rule.condition, rule.threshold)
                    if triggered:
                        alert_key = f"{rule.id}:{subnet.id}"
                        now = time.time()
                        # Check cooldown
                        last = self.alert_engine._last_fired.get(alert_key, 0)
                        if now - last < rule.cooldown_seconds:
                            continue
                        alert = {
                            "key": alert_key,
                            "rule_id": rule.id,
                            "rule_name": rule.name,
                            "entity_id": subnet.id,
                            "severity": rule.severity,
                            "metric": rule.metric,
                            "value": pct,
                            "threshold": rule.threshold,
                            "condition": rule.condition,
                            "fired_at": now,
                            "acknowledged": False,
                            "message": f"{rule.name}: {subnet.cidr} at {pct}% utilization",
                        }
                        self.alert_engine._active_alerts[alert_key] = alert
                        self.alert_engine._last_fired[alert_key] = now
                        self._latest_alerts.append(alert)
                        # Dispatch notification
                        if self.alert_engine._dispatcher:
                            try:
                                await self.alert_engine._dispatcher.dispatch(alert)
                            except Exception:
                                pass
                        # Persist to store
                        if self.alert_engine._store:
                            try:
                                self.alert_engine._store.add_alert_history(alert)
                            except Exception:
                                pass
        except Exception as e:
            logger.debug("IPAM alert pass failed: %s", e)

    # ── Snapshot API ──

    def get_snapshot(self) -> dict:
        dns_data = {
            "servers": [],
            "nxdomain_counts": {},
            "enabled": False,
        }
        if self.dns_monitor:
            dns_data = {
                "servers": [s.model_dump() for s in self.dns_monitor.config.servers],
                "nxdomain_counts": self.dns_monitor.get_nxdomain_counts(),
                "enabled": self.dns_monitor.config.enabled,
            }
        return {
            "devices": self.store.list_device_statuses(),
            "links": self.store.list_link_metrics(),
            "drifts": self.store.list_active_drift_events(),
            "candidates": self.store.list_discovery_candidates(),
            "alerts": self.alert_engine.get_active_alerts() if self.alert_engine else [],
            "dns": dns_data,
        }
