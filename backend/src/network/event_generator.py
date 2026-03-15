"""Mock event generator — creates realistic syslog/trap events for demo.

In production, these come from syslog_listener.py and trap_listener.py.
This mock runs alongside the SNMP scheduler to populate the events table.
"""

from __future__ import annotations

import asyncio
import random
from typing import Any
from src.config import is_demo_mode
from src.utils.logger import get_logger

logger = get_logger(__name__)

MOCK_EVENTS = [
    {"device_id": "rtr-core-01", "severity": "warning", "event_type": "syslog", "message": "BGP peer 169.254.100.2 flap detected — session reset"},
    {"device_id": "pa-core-fw-01", "severity": "info", "event_type": "syslog", "message": "SSL decrypt session count: 4521 (threshold: 5000)"},
    {"device_id": "cp-perim-fw-01", "severity": "info", "event_type": "syslog", "message": "Policy install completed successfully — 342 rules loaded"},
    {"device_id": "f5-lb-01", "severity": "warning", "event_type": "syslog", "message": "Pool member 10.1.10.52:8080 marked DOWN — health check failed"},
    {"device_id": "rtr-dc-edge-01", "severity": "critical", "event_type": "trap", "message": "GRE Tunnel200 state changed to DOWN — keepalive timeout"},
    {"device_id": "sw-access-01", "severity": "warning", "event_type": "syslog", "message": "VLAN 10 trunk pruned on interface Gi1/0/48 — STP topology change"},
    {"device_id": "pa-aws-fw-01", "severity": "info", "event_type": "syslog", "message": "HA sync completed with pa-aws-fw-02 — configuration in sync"},
    {"device_id": "rtr-dc-edge-02", "severity": "warning", "event_type": "syslog", "message": "ExpressRoute circuit er-circuit-01 latency 15ms (baseline: 3ms)"},
    {"device_id": "zs-proxy-01", "severity": "info", "event_type": "syslog", "message": "SSL inspection: 12 certificates bypassed (pinned domains)"},
    {"device_id": "rtr-core-02", "severity": "info", "event_type": "syslog", "message": "OSPF neighbor 10.255.0.1 state FULL on Te1/0/2"},
    {"device_id": "pa-core-fw-01", "severity": "critical", "event_type": "trap", "message": "Threat detected: CVE-2024-3400 exploit attempt from 198.51.100.33 — blocked"},
    {"device_id": "f5-lb-01", "severity": "warning", "event_type": "syslog", "message": "SSL certificate 'api-tls-cert' expires in 12 days"},
]


class MockEventGenerator:
    """Generates mock syslog/trap events at random intervals."""

    def __init__(self, metrics_store, interval_range=(15, 45)):
        self.store = metrics_store
        self.interval_range = interval_range
        self._running = False

    async def start(self):
        if not is_demo_mode():
            logger.info("Production mode — mock event generator disabled")
            return
        self._running = True
        logger.info("Mock event generator started")
        while self._running:
            event = random.choice(MOCK_EVENTS)
            self.store.write_event(
                device_id=event["device_id"],
                source_ip="",
                event_type=event["event_type"],
                severity=event["severity"],
                message=event["message"],
            )
            await asyncio.sleep(random.uniform(*self.interval_range))

    def stop(self):
        self._running = False
