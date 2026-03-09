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
            .tag("src_as", str(flow.src_as))
            .tag("dst_as", str(flow.dst_as))
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

    async def write_ipam_utilization(
        self, subnet_id: str, utilization_pct: float,
        total: int, assigned: int, available: int,
    ) -> None:
        point = (
            Point("ipam_utilization")
            .tag("subnet_id", subnet_id)
            .field("utilization_pct", float(utilization_pct))
            .field("total", total)
            .field("assigned", assigned)
            .field("available", available)
            .time(datetime.now(timezone.utc), WritePrecision.S)
        )
        await self._safe_write(point)

    async def write_dns_metric(
        self, server_id: str, server_ip: str, hostname: str,
        record_type: str, latency_ms: float, success: bool,
        metric_type: str = "query",
    ) -> None:
        point = (
            Point("dns_health")
            .tag("server_id", server_id)
            .tag("server_ip", server_ip)
            .tag("hostname", hostname)
            .tag("record_type", record_type)
            .tag("metric_type", metric_type)
            .field("latency_ms", float(latency_ms))
            .field("success", 1 if success else 0)
            .time(datetime.now(timezone.utc), WritePrecision.S)
        )
        await self._safe_write(point)

    async def write_db_metric(
        self, profile_id: str, engine: str, metric: str, value: float,
    ) -> None:
        """Write a single DB metric point."""
        try:
            point = (
                Point("db_metrics")
                .tag("profile_id", profile_id)
                .tag("engine", engine)
                .tag("metric_type", metric)
                .field("value", float(value))
            )
            await self._write_api.write(bucket=self.bucket, record=point)
        except Exception as e:
            logger.warning("Failed to write DB metric: %s", e)

    async def write_db_metrics_batch(
        self, profile_id: str, engine: str, metrics: dict[str, float],
    ) -> None:
        """Write multiple DB metrics at once."""
        try:
            points = []
            for metric, value in metrics.items():
                points.append(
                    Point("db_metrics")
                    .tag("profile_id", profile_id)
                    .tag("engine", engine)
                    .tag("metric_type", metric)
                    .field("value", float(value))
                )
            await self._write_api.write(bucket=self.bucket, record=points)
        except Exception as e:
            logger.warning("Failed to write DB metrics batch: %s", e)

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

    async def query_conversations(
        self, window: str = "5m", limit: int = 50,
    ) -> list[dict]:
        """Top conversations by bytes."""
        window = self._validate_duration(window)
        limit = self._validate_limit(limit)
        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -{window})
          |> filter(fn: (r) => r._measurement == "flow_summary")
          |> filter(fn: (r) => r._field == "bytes")
          |> group(columns: ["src_ip", "dst_ip"])
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
                    "bytes": r.get_value(),
                }
                for table in tables for r in table.records
            ]
        except Exception as e:
            logger.warning("InfluxDB conversations query failed: %s", e)
            return []

    async def query_applications(
        self, window: str = "1h", limit: int = 30,
    ) -> list[dict]:
        """Application breakdown by bytes — groups by dst_port then maps to app name."""
        from .flow_receiver import APP_PORTS
        window = self._validate_duration(window)
        limit = self._validate_limit(limit)
        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -{window})
          |> filter(fn: (r) => r._measurement == "flow_summary")
          |> pivot(rowKey: ["_time", "src_ip", "dst_ip"], columnKey: ["_field"], valueColumn: "_value")
          |> group()
          |> keep(columns: ["dst_port", "bytes", "packets"])
        '''
        try:
            tables = await self._query_api.query(query)
            app_agg: dict[str, dict] = {}
            for table in tables:
                for r in table.records:
                    dst_port = int(r.values.get("dst_port", 0))
                    app_name = APP_PORTS.get(dst_port, "Other")
                    if app_name not in app_agg:
                        app_agg[app_name] = {"bytes": 0, "packets": 0, "flows": 0}
                    app_agg[app_name]["bytes"] += int(r.values.get("bytes", 0))
                    app_agg[app_name]["packets"] += int(r.values.get("packets", 0))
                    app_agg[app_name]["flows"] += 1
            total_bytes = sum(v["bytes"] for v in app_agg.values()) or 1
            result = [
                {
                    "application": k,
                    "bytes": v["bytes"],
                    "packets": v["packets"],
                    "flows": v["flows"],
                    "percentage": round(v["bytes"] / total_bytes * 100, 2),
                }
                for k, v in app_agg.items()
            ]
            result.sort(key=lambda x: x["bytes"], reverse=True)
            return result[:limit]
        except Exception as e:
            logger.warning("InfluxDB applications query failed: %s", e)
            return []

    async def query_asn_breakdown(
        self, window: str = "1h", limit: int = 30,
    ) -> list[dict]:
        """ASN breakdown by bytes — uses src_as and dst_as tags."""
        window = self._validate_duration(window)
        limit = self._validate_limit(limit)
        # Query src_as contribution
        query_src = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -{window})
          |> filter(fn: (r) => r._measurement == "flow_summary")
          |> filter(fn: (r) => r._field == "bytes")
          |> filter(fn: (r) => r.src_as != "0")
          |> group(columns: ["src_as"])
          |> sum()
          |> group()
          |> sort(columns: ["_value"], desc: true)
        '''
        # Query dst_as contribution
        query_dst = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -{window})
          |> filter(fn: (r) => r._measurement == "flow_summary")
          |> filter(fn: (r) => r._field == "bytes")
          |> filter(fn: (r) => r.dst_as != "0")
          |> group(columns: ["dst_as"])
          |> sum()
          |> group()
          |> sort(columns: ["_value"], desc: true)
        '''
        try:
            asn_agg: dict[int, dict] = {}
            # Aggregate src_as
            tables = await self._query_api.query(query_src)
            for table in tables:
                for r in table.records:
                    asn = int(r.values.get("src_as", 0))
                    if asn == 0:
                        continue
                    if asn not in asn_agg:
                        asn_agg[asn] = {"bytes": 0, "packets": 0, "flows": 0}
                    asn_agg[asn]["bytes"] += int(r.get_value())
                    asn_agg[asn]["flows"] += 1
            # Aggregate dst_as
            tables = await self._query_api.query(query_dst)
            for table in tables:
                for r in table.records:
                    asn = int(r.values.get("dst_as", 0))
                    if asn == 0:
                        continue
                    if asn not in asn_agg:
                        asn_agg[asn] = {"bytes": 0, "packets": 0, "flows": 0}
                    asn_agg[asn]["bytes"] += int(r.get_value())
                    asn_agg[asn]["flows"] += 1
            result = [{"asn": k, **v} for k, v in asn_agg.items()]
            result.sort(key=lambda x: x["bytes"], reverse=True)
            return result[:limit]
        except Exception as e:
            logger.warning("InfluxDB ASN query failed: %s", e)
            return []

    async def query_flow_volume_timeline(
        self, window: str = "1h", interval: str = "1m",
    ) -> list[dict]:
        """Time-bucketed flow volume for sparklines."""
        window = self._validate_duration(window)
        interval = self._validate_duration(interval)
        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -{window})
          |> filter(fn: (r) => r._measurement == "flow_summary")
          |> filter(fn: (r) => r._field == "bytes")
          |> group()
          |> aggregateWindow(every: {interval}, fn: sum, createEmpty: true)
          |> yield(name: "volume")
        '''
        try:
            tables = await self._query_api.query(query)
            return [
                {
                    "time": r.get_time().isoformat(),
                    "bytes": r.get_value() or 0,
                }
                for table in tables for r in table.records
            ]
        except Exception as e:
            logger.warning("InfluxDB flow volume query failed: %s", e)
            return []

    async def query_dns_metrics(
        self, server_id: str = "", hostname: str = "",
        range_str: str = "1h", resolution: str = "30s",
    ) -> list[dict]:
        range_str = self._validate_duration(range_str)
        resolution = self._validate_duration(resolution)
        filters = ['r._measurement == "dns_health"']
        if server_id:
            server_id = self._validate_id(server_id)
            filters.append(f'r.server_id == "{server_id}"')
        if hostname:
            filters.append(f'r.hostname == "{hostname}"')
        filter_expr = " and ".join(filters)
        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -{range_str})
          |> filter(fn: (r) => {filter_expr})
          |> filter(fn: (r) => r._field == "latency_ms")
          |> aggregateWindow(every: {resolution}, fn: mean, createEmpty: false)
          |> yield(name: "mean")
        '''
        try:
            tables = await self._query_api.query(query)
            return [
                {
                    "time": r.get_time().isoformat(),
                    "value": r.get_value(),
                    "hostname": r.values.get("hostname", ""),
                    "server_id": r.values.get("server_id", ""),
                }
                for table in tables for r in table.records
            ]
        except Exception as e:
            logger.warning("InfluxDB DNS query failed: %s", e)
            return []

    async def query_ipam_utilization(
        self, subnet_id: str, range_str: str = "7d", resolution: str = "1h",
    ) -> list[dict]:
        range_str = self._validate_duration(range_str)
        resolution = self._validate_duration(resolution)
        subnet_id = self._validate_id(subnet_id)
        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -{range_str})
          |> filter(fn: (r) => r._measurement == "ipam_utilization")
          |> filter(fn: (r) => r.subnet_id == "{subnet_id}")
          |> filter(fn: (r) => r._field == "utilization_pct")
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
            logger.warning("InfluxDB IPAM query failed: %s", e)
            return []

    async def query_db_metrics(
        self, profile_id: str, metric: str, duration: str = "1h",
        resolution: str = "1m",
    ) -> list[dict]:
        """Query time-series DB metrics."""
        duration = self._validate_duration(duration)
        resolution = self._validate_duration(resolution)
        profile_id = self._validate_id(profile_id)
        metric = self._validate_id(metric)
        flux = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -{duration})
          |> filter(fn: (r) => r._measurement == "db_metrics")
          |> filter(fn: (r) => r.profile_id == "{profile_id}")
          |> filter(fn: (r) => r.metric_type == "{metric}")
          |> aggregateWindow(every: {resolution}, fn: mean, createEmpty: false)
          |> yield(name: "mean")
        '''
        try:
            tables = await self._query_api.query(flux, org=self.org)
            return [
                {"time": r.get_time().isoformat(), "value": r.get_value()}
                for table in tables for r in table.records
            ]
        except Exception as e:
            logger.warning("Failed to query DB metrics: %s", e)
            return []
