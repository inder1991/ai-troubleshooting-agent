# backend/src/network/flow_receiver.py
"""NetFlow v5/v9 and sFlow receiver with aggregation pipeline."""

from __future__ import annotations

import asyncio
import logging
import socket
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .metrics_store import FlowRecord

logger = logging.getLogger(__name__)


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

    def __init__(self):
        # Template cache: {(exporter_ip, source_id): {template_id: [(field_type, field_len), ...]}}
        self._v9_templates: dict[tuple[str, int], dict[int, list[tuple[int, int]]]] = {}

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
        if cache_key not in self._v9_templates:
            self._v9_templates[cache_key] = {}
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
            self._v9_templates[cache_key][template_id] = fields

    def _parse_v9_data(self, data: bytes, start: int, end: int,
                       template_id: int, cache_key: tuple[str, int],
                       base_time: datetime, exporter_ip: str) -> list[FlowRecord]:
        templates = self._v9_templates.get(cache_key, {})
        template = templates.get(template_id)
        if not template:
            logger.debug("No template %d for exporter %s", template_id, cache_key[0])
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
        self, metrics_store: Any, topology_store: Any,
        device_ip_map: dict[str, str] | None = None,
    ) -> None:
        self.metrics = metrics_store
        self.topo_store = topology_store
        self._buffer: list[FlowRecord] = []
        self._device_ip_map = device_ip_map or {}

    MAX_BUFFER_SIZE = 100_000

    def set_device_map(self, device_ip_map: dict[str, str]) -> None:
        self._device_ip_map = device_ip_map

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

    def __init__(self, metrics_store: Any, topology_store: Any) -> None:
        self.metrics = metrics_store
        self.topo_store = topology_store
        self.parser = FlowParser()
        self.aggregator = FlowAggregator(metrics_store, topology_store)
        self._transports: list[asyncio.BaseTransport] = []
        self._flush_task: asyncio.Task | None = None

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
