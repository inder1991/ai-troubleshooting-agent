# backend/src/network/flow_receiver.py
"""NetFlow v5/v9 and sFlow receiver with aggregation pipeline."""

from __future__ import annotations

import asyncio
import logging
import socket
import struct
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .metrics_store import FlowRecord

logger = logging.getLogger(__name__)

APP_PORTS = {
    443: "HTTPS", 53: "DNS", 80: "HTTP", 22: "SSH", 8443: "Zoom",
    3389: "RDP", 5060: "SIP", 3306: "MySQL", 5432: "PostgreSQL",
    6379: "Redis", 27017: "MongoDB", 8080: "HTTP-Alt", 25: "SMTP",
    143: "IMAP", 110: "POP3", 993: "IMAPS", 995: "POP3S",
    8883: "MQTT", 5672: "AMQP", 9092: "Kafka", 2049: "NFS",
    445: "SMB", 1433: "MSSQL", 389: "LDAP", 636: "LDAPS",
    123: "NTP", 161: "SNMP", 514: "Syslog", 69: "TFTP",
}


@dataclass
class NetFlowV5Header:
    version: int
    count: int
    sys_uptime: int
    unix_secs: int
    unix_nsecs: int
    flow_sequence: int

    @classmethod
    def from_bytes(cls, data: bytes) -> NetFlowV5Header | None:
        if len(data) < 24:
            return None
        version, count, uptime, secs, nsecs, seq = struct.unpack_from("!HHIIII", data)
        return cls(version, count, uptime, secs, nsecs, seq)


@dataclass
class NetFlowV5Record:
    src_ip: str
    dst_ip: str
    next_hop: str
    input_snmp: int
    output_snmp: int
    packets: int
    bytes: int
    first: int
    last: int
    src_port: int
    dst_port: int
    tcp_flags: int
    protocol: int
    tos: int
    src_as: int
    dst_as: int

    V5_RECORD_SIZE = 48


class FlowParser:
    """Parses NetFlow v5/v9 and IPFIX binary packets into FlowRecord objects."""

    _MAX_TEMPLATES = 500
    _TEMPLATE_TTL = 3600  # seconds

    def __init__(self):
        # Template cache: {(exporter_ip, source_id): {template_id: [(field_type, field_len), ...]}}
        self._v9_templates: dict[tuple[str, int], dict[int, list[tuple[int, int]]]] = {}
        self._template_timestamps: dict[tuple, float] = {}

    def _store_template(self, key: tuple, template: Any) -> None:
        """Store a template and record its timestamp, evicting oldest if over capacity."""
        self._v9_templates[key] = template
        self._template_timestamps[key] = time.time()
        # Evict oldest entries if cache exceeds max size
        if len(self._v9_templates) > self._MAX_TEMPLATES:
            sorted_keys = sorted(
                self._template_timestamps,
                key=lambda k: self._template_timestamps[k],
            )
            evict_count = len(self._v9_templates) - self._MAX_TEMPLATES
            for k in sorted_keys[:evict_count]:
                self._v9_templates.pop(k, None)
                self._template_timestamps.pop(k, None)

    def _get_template(self, key: tuple) -> Any | None:
        """Look up a template, returning None if expired or missing."""
        template = self._v9_templates.get(key)
        if template is None:
            return None
        ts = self._template_timestamps.get(key)
        if ts is None or (time.time() - ts) > self._TEMPLATE_TTL:
            # Expired — evict
            self._v9_templates.pop(key, None)
            self._template_timestamps.pop(key, None)
            return None
        return template

    def parse_v5(self, data: bytes, exporter_ip: str) -> list[FlowRecord]:
        header = NetFlowV5Header.from_bytes(data)
        if header is None or header.version != 5:
            return []

        records = []
        offset = 24  # v5 header size
        base_time = datetime.fromtimestamp(header.unix_secs, tz=timezone.utc)

        for _ in range(header.count):
            if offset + 48 > len(data):
                break
            fields = struct.unpack_from("!IIIHHIIIIHHBBBBHHBBH", data, offset)
            offset += 48

            src_ip = socket.inet_ntoa(struct.pack("!I", fields[0]))
            dst_ip = socket.inet_ntoa(struct.pack("!I", fields[1]))

            records.append(FlowRecord(
                src_ip=src_ip,
                dst_ip=dst_ip,
                src_port=fields[9],
                dst_port=fields[10],
                protocol=fields[12],
                bytes=fields[6],
                packets=fields[5],
                start_time=base_time,
                end_time=base_time,
                tcp_flags=fields[11],
                tos=fields[13],
                input_snmp=fields[3],
                output_snmp=fields[4],
                src_as=fields[14],
                dst_as=fields[15],
                exporter_ip=exporter_ip,
            ))

        return records

    def parse_v9(self, data: bytes, exporter_ip: str) -> list[FlowRecord]:
        """Parse NetFlow v9 packet — handles both template and data flowsets."""
        if len(data) < 20:
            return []
        version, count, sys_uptime, unix_secs, sequence, source_id = struct.unpack_from("!HHIIII", data)
        if version != 9:
            return []

        base_time = datetime.fromtimestamp(unix_secs, tz=timezone.utc)
        cache_key = (exporter_ip, source_id)
        offset = 20
        records: list[FlowRecord] = []

        while offset < len(data) - 3:
            if offset + 4 > len(data):
                break
            flowset_id, flowset_length = struct.unpack_from("!HH", data, offset)
            if flowset_length < 4:
                break
            flowset_end = offset + flowset_length

            if flowset_id == 0:
                self._parse_v9_templates(data, offset + 4, flowset_end, cache_key)
            elif flowset_id == 1:
                pass  # Options Template — skip
            elif flowset_id >= 256:
                new_records = self._parse_v9_data(data, offset + 4, flowset_end,
                                                   flowset_id, cache_key, base_time, exporter_ip)
                records.extend(new_records)

            offset = flowset_end

        return records

    def _parse_v9_templates(self, data: bytes, start: int, end: int,
                            cache_key: tuple[str, int]) -> None:
        offset = start
        while offset < end - 3:
            if offset + 4 > end:
                break
            template_id, field_count = struct.unpack_from("!HH", data, offset)
            offset += 4
            fields: list[tuple[int, int]] = []
            for _ in range(field_count):
                if offset + 4 > end:
                    break
                ftype, flen = struct.unpack_from("!HH", data, offset)
                fields.append((ftype, flen))
                offset += 4
            # Use composite key (cache_key, template_id) for per-template TTL tracking
            composite_key = (cache_key, template_id)
            # Maintain backward-compatible nested dict structure
            if cache_key not in self._v9_templates:
                self._v9_templates[cache_key] = {}
            self._v9_templates[cache_key][template_id] = fields
            self._template_timestamps[composite_key] = time.time()
            # Evict oldest if total template count exceeds max
            total = sum(len(v) for v in self._v9_templates.values())
            if total > self._MAX_TEMPLATES:
                sorted_keys = sorted(
                    self._template_timestamps,
                    key=lambda k: self._template_timestamps[k],
                )
                while total > self._MAX_TEMPLATES and sorted_keys:
                    oldest = sorted_keys.pop(0)
                    ck, tid = oldest
                    if ck in self._v9_templates and tid in self._v9_templates[ck]:
                        del self._v9_templates[ck][tid]
                        if not self._v9_templates[ck]:
                            del self._v9_templates[ck]
                        total -= 1
                    self._template_timestamps.pop(oldest, None)

    def _parse_v9_data(self, data: bytes, start: int, end: int,
                       template_id: int, cache_key: tuple[str, int],
                       base_time: datetime, exporter_ip: str) -> list[FlowRecord]:
        templates = self._v9_templates.get(cache_key, {})
        template = templates.get(template_id)
        if not template:
            logger.debug("No template %d for exporter %s", template_id, cache_key[0])
            return []

        # Check TTL on the template
        composite_key = (cache_key, template_id)
        ts = self._template_timestamps.get(composite_key)
        if ts is not None and (time.time() - ts) > self._TEMPLATE_TTL:
            # Expired — evict and reject
            del self._v9_templates[cache_key][template_id]
            if not self._v9_templates[cache_key]:
                del self._v9_templates[cache_key]
            self._template_timestamps.pop(composite_key, None)
            logger.debug("Template %d for exporter %s expired", template_id, cache_key[0])
            return []

        record_size = sum(flen for _, flen in template)
        if record_size == 0:
            return []

        records: list[FlowRecord] = []
        offset = start

        while offset + record_size <= end:
            field_values: dict[int, Any] = {}
            pos = offset
            for ftype, flen in template:
                if pos + flen > end:
                    break
                raw = data[pos:pos + flen]
                if flen == 1:
                    field_values[ftype] = raw[0]
                elif flen == 2:
                    field_values[ftype] = struct.unpack_from("!H", raw)[0]
                elif flen == 4:
                    field_values[ftype] = struct.unpack_from("!I", raw)[0]
                elif flen == 8:
                    field_values[ftype] = struct.unpack_from("!Q", raw)[0]
                else:
                    field_values[ftype] = raw
                pos += flen

            src_ip_int = field_values.get(8, 0)
            dst_ip_int = field_values.get(12, 0)
            src_ip = socket.inet_ntoa(struct.pack("!I", src_ip_int)) if isinstance(src_ip_int, int) else "0.0.0.0"
            dst_ip = socket.inet_ntoa(struct.pack("!I", dst_ip_int)) if isinstance(dst_ip_int, int) else "0.0.0.0"

            records.append(FlowRecord(
                src_ip=src_ip,
                dst_ip=dst_ip,
                src_port=field_values.get(7, 0),
                dst_port=field_values.get(11, 0),
                protocol=field_values.get(4, 0),
                bytes=field_values.get(1, 0),
                packets=field_values.get(2, 0),
                start_time=base_time,
                end_time=base_time,
                tcp_flags=field_values.get(6, 0),
                tos=field_values.get(5, 0),
                input_snmp=field_values.get(10, 0),
                output_snmp=field_values.get(14, 0),
                src_as=field_values.get(16, 0),
                dst_as=field_values.get(17, 0),
                exporter_ip=exporter_ip,
            ))
            offset += record_size

        return records

    def parse_ipfix(self, data: bytes, exporter_ip: str) -> list[FlowRecord]:
        """Parse IPFIX (NetFlow v10) packet."""
        if len(data) < 16:
            return []
        version, length, export_time, sequence, domain_id = struct.unpack_from("!HHIII", data)
        if version != 10:
            return []

        base_time = datetime.fromtimestamp(export_time, tz=timezone.utc)
        cache_key = (exporter_ip, domain_id)
        offset = 16
        records: list[FlowRecord] = []

        while offset < len(data) - 3:
            if offset + 4 > len(data):
                break
            set_id, set_length = struct.unpack_from("!HH", data, offset)
            if set_length < 4:
                break
            set_end = offset + set_length

            if set_id == 2:
                self._parse_v9_templates(data, offset + 4, set_end, cache_key)
            elif set_id == 3:
                pass  # Options Template — skip
            elif set_id >= 256:
                new_records = self._parse_v9_data(data, offset + 4, set_end,
                                                   set_id, cache_key, base_time, exporter_ip)
                records.extend(new_records)

            offset = set_end

        return records

    def detect_and_parse(self, data: bytes, exporter_ip: str) -> list[FlowRecord]:
        if len(data) < 4:
            return []
        version = struct.unpack_from("!H", data)[0]
        if version == 5:
            return self.parse_v5(data, exporter_ip)
        elif version == 9:
            return self.parse_v9(data, exporter_ip)
        elif version == 10:
            return self.parse_ipfix(data, exporter_ip)
        else:
            logger.debug("Unsupported flow version: %d", version)
            return []


class FlowAggregator:
    """Buffers flow records and flushes aggregated metrics."""

    def __init__(
        self, metrics_store: Any = None, topology_store: Any = None,
        device_ip_map: dict[str, str] | None = None,
        event_bus: Any | None = None,
        buffer_size: int = 100_000,
        biflow_timeout: float = 120.0,
    ) -> None:
        self.metrics = metrics_store
        self.topo_store = topology_store
        self._buffer: list[FlowRecord] = []
        self._device_ip_map = device_ip_map or {}
        self._conversations: dict[tuple[str, str], dict] = {}
        self._applications: dict[str, dict] = {}
        self._asn_stats: dict[int, dict] = {}
        self._event_bus = event_bus
        self._biflows: dict[tuple, dict] = {}
        self._biflow_timeout = biflow_timeout

    MAX_BUFFER_SIZE = 100_000
    MAX_CONVERSATIONS = 10_000
    MAX_APPLICATIONS = 500
    MAX_ASN_ENTRIES = 1_000
    MAX_BIFLOWS = 50_000

    # -- Biflow Stitching --------------------------------------------------

    def _biflow_key(self, flow: FlowRecord) -> tuple:
        """Canonical 5-tuple key: sorted so forward and reverse match."""
        a = (flow.src_ip, flow.src_port)
        b = (flow.dst_ip, flow.dst_port)
        if a <= b:
            return (a[0], a[1], b[0], b[1], flow.protocol)
        return (b[0], b[1], a[0], a[1], flow.protocol)

    def stitch_biflow(self, flow: FlowRecord) -> None:
        """Add a flow to the biflow stitching table."""
        key = self._biflow_key(flow)
        now = time.time()

        if key not in self._biflows:
            if len(self._biflows) >= self.MAX_BIFLOWS:
                # Evict oldest
                oldest_key = min(self._biflows, key=lambda k: self._biflows[k]["last_seen"])
                del self._biflows[oldest_key]
            self._biflows[key] = {
                "src_ip": key[0], "src_port": key[1],
                "dst_ip": key[2], "dst_port": key[3],
                "protocol": key[4],
                "forward_bytes": 0, "forward_packets": 0,
                "reverse_bytes": 0, "reverse_packets": 0,
                "first_seen": now, "last_seen": now,
            }

        bf = self._biflows[key]
        bf["last_seen"] = now

        # Determine direction: forward if flow matches canonical order
        is_forward = (flow.src_ip, flow.src_port) <= (flow.dst_ip, flow.dst_port)
        if is_forward:
            bf["forward_bytes"] += flow.bytes
            bf["forward_packets"] += flow.packets
        else:
            bf["reverse_bytes"] += flow.bytes
            bf["reverse_packets"] += flow.packets

    def get_biflows(self, limit: int = 100) -> list[dict]:
        """Return biflows sorted by total bytes descending."""
        result = []
        for bf in self._biflows.values():
            total = bf["forward_bytes"] + bf["reverse_bytes"]
            result.append({**bf, "total_bytes": total})
        result.sort(key=lambda x: x["total_bytes"], reverse=True)
        return result[:limit]

    def evict_expired_biflows(self) -> int:
        """Remove biflows older than timeout. Returns count evicted."""
        now = time.time()
        expired = [k for k, v in self._biflows.items()
                   if now - v["last_seen"] > self._biflow_timeout]
        for k in expired:
            del self._biflows[k]
        return len(expired)

    def set_device_map(self, device_ip_map: dict[str, str]) -> None:
        self._device_ip_map = device_ip_map

    def set_event_bus(self, bus: Any) -> None:
        self._event_bus = bus

    def get_conversations(self, limit: int = 50) -> list[dict]:
        """Return top conversations sorted by bytes descending."""
        items = [
            {"src_ip": k[0], "dst_ip": k[1], **v}
            for k, v in self._conversations.items()
        ]
        items.sort(key=lambda x: x["bytes"], reverse=True)
        return items[:limit]

    def get_applications(self, limit: int = 30) -> list[dict]:
        """Return application breakdown sorted by bytes descending, with percentage."""
        total_bytes = sum(v["bytes"] for v in self._applications.values()) or 1
        items = [
            {
                "application": k,
                "bytes": v["bytes"],
                "packets": v["packets"],
                "flows": v["flows"],
                "percentage": round(v["bytes"] / total_bytes * 100, 2),
            }
            for k, v in self._applications.items()
        ]
        items.sort(key=lambda x: x["bytes"], reverse=True)
        return items[:limit]

    def get_asn_breakdown(self, limit: int = 30) -> list[dict]:
        """Return ASN breakdown sorted by bytes descending."""
        items = [
            {"asn": k, **v}
            for k, v in self._asn_stats.items()
        ]
        items.sort(key=lambda x: x["bytes"], reverse=True)
        return items[:limit]

    def ingest(self, flow: FlowRecord) -> None:
        if len(self._buffer) >= self.MAX_BUFFER_SIZE:
            logger.warning("Flow buffer full (%d records), dropping oldest", self.MAX_BUFFER_SIZE)
            self._buffer = self._buffer[self.MAX_BUFFER_SIZE // 2:]
        self._buffer.append(flow)

    async def flush(self) -> int:
        if not self._buffer:
            return 0

        batch = self._buffer[:]
        self._buffer.clear()

        # Apply sampling rate compensation
        for flow in batch:
            if flow.sampling_interval > 1:
                flow.bytes *= flow.sampling_interval
                flow.packets *= flow.sampling_interval

        # Write individual flows
        for flow in batch:
            await self.metrics.write_flow(flow)

        # Aggregate per (src_device, dst_device)
        link_agg: dict[tuple[str, str], dict] = {}
        for flow in batch:
            src_dev = self._device_ip_map.get(flow.exporter_ip, flow.src_ip)
            dst_dev = flow.dst_ip  # Best-effort mapping
            key = (src_dev, dst_dev)
            if key not in link_agg:
                link_agg[key] = {"bytes": 0, "packets": 0}
            link_agg[key]["bytes"] += flow.bytes
            link_agg[key]["packets"] += flow.packets

        for (src, dst), agg in link_agg.items():
            await self.metrics.write_link_metric(src, dst, **agg)
            try:
                self.topo_store.upsert_link_metric(
                    src, dst, latency_ms=0, bandwidth_bps=agg["bytes"] * 8 // 30,
                    error_rate=0, utilization=0,
                )
            except Exception:
                pass

        # -- Conversation aggregation ----------------------------------------
        conversations: dict[tuple[str, str], dict] = {}
        for flow in batch:
            key = (flow.src_ip, flow.dst_ip)
            if key not in conversations:
                conversations[key] = {"bytes": 0, "packets": 0, "flows": 0, "latency_sum": 0.0}
            conversations[key]["bytes"] += flow.bytes
            conversations[key]["packets"] += flow.packets
            conversations[key]["flows"] += 1
            conversations[key]["latency_sum"] += (flow.end_time - flow.start_time).total_seconds()
        if len(conversations) > self.MAX_CONVERSATIONS:
            sorted_convos = sorted(conversations.items(), key=lambda x: x[1]["bytes"])
            conversations = dict(sorted_convos[len(sorted_convos) - self.MAX_CONVERSATIONS:])
        self._conversations = conversations

        # -- Application breakdown -------------------------------------------
        applications: dict[str, dict] = {}
        for flow in batch:
            app_name = APP_PORTS.get(flow.dst_port, "Other")
            if app_name not in applications:
                applications[app_name] = {"bytes": 0, "packets": 0, "flows": 0}
            applications[app_name]["bytes"] += flow.bytes
            applications[app_name]["packets"] += flow.packets
            applications[app_name]["flows"] += 1
        if len(applications) > self.MAX_APPLICATIONS:
            sorted_apps = sorted(applications.items(), key=lambda x: x[1]["bytes"])
            applications = dict(sorted_apps[len(sorted_apps) - self.MAX_APPLICATIONS:])
        self._applications = applications

        # -- ASN stats -------------------------------------------------------
        asn_stats: dict[int, dict] = {}
        for flow in batch:
            for asn in (flow.src_as, flow.dst_as):
                if asn == 0:
                    continue
                if asn not in asn_stats:
                    asn_stats[asn] = {"bytes": 0, "packets": 0, "flows": 0}
                asn_stats[asn]["bytes"] += flow.bytes
                asn_stats[asn]["packets"] += flow.packets
                asn_stats[asn]["flows"] += 1
        if len(asn_stats) > self.MAX_ASN_ENTRIES:
            sorted_asns = sorted(asn_stats.items(), key=lambda x: x[1]["bytes"])
            asn_stats = dict(sorted_asns[len(sorted_asns) - self.MAX_ASN_ENTRIES:])
        self._asn_stats = asn_stats

        # -- Publish to event bus --------------------------------------------
        if self._event_bus:
            try:
                aggregate = {
                    "flow_count": len(batch),
                    "total_bytes": sum(f.bytes for f in batch),
                    "total_packets": sum(f.packets for f in batch),
                    "top_conversations": self.get_conversations(limit=10),
                    "top_applications": self.get_applications(limit=10),
                    "top_asns": self.get_asn_breakdown(limit=10),
                }
                self._event_bus.publish("flows", aggregate)
            except Exception as e:
                logger.warning("Failed to publish flow aggregate to event bus: %s", e)

        return len(batch)


class FlowReceiverProtocol(asyncio.DatagramProtocol):
    """Async UDP protocol for receiving flow packets."""

    def __init__(self, parser: FlowParser, aggregator: FlowAggregator) -> None:
        self.parser = parser
        self.aggregator = aggregator
        self._count = 0

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        exporter_ip = addr[0]
        records = self.parser.detect_and_parse(data, exporter_ip)
        for r in records:
            self.aggregator.ingest(r)
        self._count += len(records)


class FlowReceiver:
    """Manages UDP listeners for NetFlow/sFlow."""

    _MAX_TEMPLATES = 500
    _TEMPLATE_TTL = 3600  # seconds

    def __init__(self, metrics_store: Any, topology_store: Any,
                 event_bus: Any | None = None) -> None:
        self.metrics = metrics_store
        self.topo_store = topology_store
        self.parser = FlowParser()
        self.aggregator = FlowAggregator(metrics_store, topology_store, event_bus=event_bus)
        self._transports: list[asyncio.BaseTransport] = []
        self._flush_task: asyncio.Task | None = None
        # Expose template cache attributes (delegate to parser for real usage)
        self._v9_templates = self.parser._v9_templates
        self._template_timestamps = self.parser._template_timestamps

    def _store_template(self, key: tuple, template: Any) -> None:
        """Store a template with timestamp, evicting oldest if over capacity."""
        self._v9_templates[key] = template
        self._template_timestamps[key] = time.time()
        if len(self._v9_templates) > self._MAX_TEMPLATES:
            sorted_keys = sorted(
                self._template_timestamps,
                key=lambda k: self._template_timestamps[k],
            )
            evict_count = len(self._v9_templates) - self._MAX_TEMPLATES
            for k in sorted_keys[:evict_count]:
                self._v9_templates.pop(k, None)
                self._template_timestamps.pop(k, None)

    def _get_template(self, key: tuple) -> Any | None:
        """Look up a template, returning None if expired or missing."""
        template = self._v9_templates.get(key)
        if template is None:
            return None
        ts = self._template_timestamps.get(key)
        if ts is None or (time.time() - ts) > self._TEMPLATE_TTL:
            self._v9_templates.pop(key, None)
            self._template_timestamps.pop(key, None)
            return None
        return template

    async def start(self, ports: dict[str, int] | None = None) -> None:
        ports = ports or {"netflow": 2055}
        loop = asyncio.get_running_loop()

        for name, port in ports.items():
            try:
                transport, _ = await loop.create_datagram_endpoint(
                    lambda: FlowReceiverProtocol(self.parser, self.aggregator),
                    local_addr=("0.0.0.0", port),
                )
                self._transports.append(transport)
                logger.info("Flow receiver listening on UDP port %d (%s)", port, name)
            except Exception as e:
                logger.warning("Failed to bind UDP port %d (%s): %s", port, name, e)

        self._flush_task = asyncio.create_task(self._flush_loop())

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(30)
            try:
                count = await self.aggregator.flush()
                if count > 0:
                    logger.info("Flushed %d flow records", count)
            except Exception as e:
                logger.error("Flow aggregation flush failed: %s", e)

    async def stop(self) -> None:
        if self._flush_task:
            self._flush_task.cancel()
        for t in self._transports:
            t.close()
        await self.aggregator.flush()

    def update_device_map(self, device_ip_map: dict[str, str]) -> None:
        self.aggregator.set_device_map(device_ip_map)
