"""InfluxDB time-series metrics store for network monitoring."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any

from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
from influxdb_client import Point, WritePrecision

logger = logging.getLogger(__name__)


@dataclass
class FlowRecord:
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    protocol: int
    bytes: int
    packets: int
    start_time: datetime
    end_time: datetime
    tcp_flags: int = 0
    tos: int = 0
    input_snmp: int = 0
    output_snmp: int = 0
    src_as: int = 0
    dst_as: int = 0
    exporter_ip: str = ""


class MetricsStore:
    """Async InfluxDB wrapper for network metrics. Fails gracefully on write errors."""

    def __init__(self, url: str, token: str, org: str, bucket: str) -> None:
        self.org = org
        self.bucket = bucket
        self._client = InfluxDBClientAsync(url=url, token=token, org=org)
        self._write_api = self._client.write_api()
        self._query_api = self._client.query_api()

    async def health_check(self) -> bool:
        try:
            return await self._client.ping()
        except Exception:
            logger.warning("InfluxDB health check failed")
            return False

    async def close(self) -> None:
        await self._client.close()

    # -- Writes ----------------------------------------------------------

    async def _safe_write(self, point: Point) -> None:
        try:
            await self._write_api.write(bucket=self.bucket, record=point)
        except Exception as e:
            logger.warning("InfluxDB write failed: %s", e)

    async def write_device_metric(
        self, device_id: str, metric: str, value: float
    ) -> None:
        point = (
            Point("device_health")
            .tag("device_id", device_id)
            .tag("metric_type", metric)
            .field("value", float(value))
            .time(datetime.now(timezone.utc), WritePrecision.S)
        )
        await self._safe_write(point)

    async def write_link_metric(
        self, src: str, dst: str, **fields: Any
    ) -> None:
        point = (
            Point("link_traffic")
            .tag("src_device", src)
            .tag("dst_device", dst)
            .time(datetime.now(timezone.utc), WritePrecision.S)
        )
        for k, v in fields.items():
            point = point.field(k, float(v))
        await self._safe_write(point)

    async def write_flow(self, flow: FlowRecord) -> None:
        point = (
            Point("flow_summary")
            .tag("src_ip", flow.src_ip)
            .tag("dst_ip", flow.dst_ip)
            .tag("protocol", str(flow.protocol))
            .tag("exporter", flow.exporter_ip)
            .field("src_port", flow.src_port)
            .field("dst_port", flow.dst_port)
            .field("bytes", flow.bytes)
            .field("packets", flow.packets)
            .field("duration", (flow.end_time - flow.start_time).total_seconds())
            .time(flow.end_time, WritePrecision.S)
        )
        await self._safe_write(point)

    async def write_alert_event(
        self, device_id: str, rule_id: str, severity: str,
        value: float, threshold: float, message: str,
    ) -> None:
        point = (
            Point("alert_events")
            .tag("device_id", device_id)
            .tag("rule_id", rule_id)
            .tag("severity", severity)
            .field("value", value)
            .field("threshold", threshold)
            .field("message", message)
            .time(datetime.now(timezone.utc), WritePrecision.S)
        )
        await self._safe_write(point)

    # -- Input Validation ------------------------------------------------

    _DURATION_RE = re.compile(r"^\d+[smhd]$")
    _SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9_:.\-/]+$")

    @classmethod
    def _validate_duration(cls, s: str) -> str:
        if not cls._DURATION_RE.match(s):
            raise ValueError(f"Invalid duration: {s}")
        return s

    @classmethod
    def _validate_id(cls, s: str) -> str:
        if not cls._SAFE_ID_RE.match(s):
            raise ValueError(f"Invalid identifier: {s}")
        return s

    @classmethod
    def _validate_limit(cls, n: int) -> int:
        return max(1, min(n, 1000))

    # -- Queries ---------------------------------------------------------

    async def query_device_metrics(
        self, device_id: str, metric: str,
        range_str: str = "1h", resolution: str = "30s",
    ) -> list[dict]:
        range_str = self._validate_duration(range_str)
        resolution = self._validate_duration(resolution)
        device_id = self._validate_id(device_id)
        metric = self._validate_id(metric)
        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -{range_str})
          |> filter(fn: (r) => r._measurement == "device_health")
          |> filter(fn: (r) => r.device_id == "{device_id}")
          |> filter(fn: (r) => r.metric_type == "{metric}")
          |> aggregateWindow(every: {resolution}, fn: mean, createEmpty: false)
          |> yield(name: "mean")
        '''
        try:
            tables = await self._query_api.query(query)
            return [
                {"time": r.get_time().isoformat(), "value": r.get_value()}
                for table in tables for r in table.records
            ]
        except Exception as e:
            logger.warning("InfluxDB query failed: %s", e)
            return []

    async def query_top_talkers(
        self, window: str = "5m", limit: int = 20
    ) -> list[dict]:
        window = self._validate_duration(window)
        limit = self._validate_limit(limit)
        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -{window})
          |> filter(fn: (r) => r._measurement == "flow_summary")
          |> filter(fn: (r) => r._field == "bytes")
          |> group(columns: ["src_ip", "dst_ip", "protocol"])
          |> sum()
          |> group()
          |> sort(columns: ["_value"], desc: true)
          |> limit(n: {limit})
        '''
        try:
            tables = await self._query_api.query(query)
            return [
                {
                    "src_ip": r.values.get("src_ip", ""),
                    "dst_ip": r.values.get("dst_ip", ""),
                    "protocol": r.values.get("protocol", ""),
                    "bytes": r.get_value(),
                }
                for table in tables for r in table.records
            ]
        except Exception as e:
            logger.warning("InfluxDB query failed: %s", e)
            return []

    async def query_traffic_matrix(self, window: str = "15m") -> list[dict]:
        window = self._validate_duration(window)
        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -{window})
          |> filter(fn: (r) => r._measurement == "link_traffic")
          |> filter(fn: (r) => r._field == "bytes")
          |> group(columns: ["src_device", "dst_device"])
          |> sum()
        '''
        try:
            tables = await self._query_api.query(query)
            return [
                {
                    "src": r.values.get("src_device", ""),
                    "dst": r.values.get("dst_device", ""),
                    "bytes": r.get_value(),
                }
                for table in tables for r in table.records
            ]
        except Exception as e:
            logger.warning("InfluxDB query failed: %s", e)
            return []

    async def query_protocol_breakdown(self, window: str = "1h") -> list[dict]:
        window = self._validate_duration(window)
        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -{window})
          |> filter(fn: (r) => r._measurement == "flow_summary")
          |> filter(fn: (r) => r._field == "bytes")
          |> group(columns: ["protocol"])
          |> sum()
          |> group()
          |> sort(columns: ["_value"], desc: true)
        '''
        try:
            tables = await self._query_api.query(query)
            return [
                {"protocol": r.values.get("protocol", ""), "bytes": r.get_value()}
                for table in tables for r in table.records
            ]
        except Exception as e:
            logger.warning("InfluxDB query failed: %s", e)
            return []
