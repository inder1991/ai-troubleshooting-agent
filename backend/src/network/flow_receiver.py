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
    """Parses NetFlow v5 binary packets into FlowRecord objects."""

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

    def detect_and_parse(self, data: bytes, exporter_ip: str) -> list[FlowRecord]:
        if len(data) < 4:
            return []
        version = struct.unpack_from("!H", data)[0]
        if version == 5:
            return self.parse_v5(data, exporter_ip)
        logger.debug("Unsupported flow version: %d from %s", version, exporter_ip)
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

    def ingest(self, flow: FlowRecord) -> None:
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
        loop = asyncio.get_event_loop()

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
            count = await self.aggregator.flush()
            if count > 0:
                logger.info("Flushed %d flow records", count)

    async def stop(self) -> None:
        if self._flush_task:
            self._flush_task.cancel()
        for t in self._transports:
            t.close()
        await self.aggregator.flush()

    def update_device_map(self, device_ip_map: dict[str, str]) -> None:
        self.aggregator._device_ip_map = device_ip_map
