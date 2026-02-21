import json
import os
import statistics
from datetime import datetime, timezone
from typing import Any

import requests

from src.agents.react_base import ReActAgent
from src.models.schemas import MetricAnomaly, DataPoint, TimeRange, MetricsAnalysisResult, TokenUsage
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MetricsAgent(ReActAgent):
    """ReAct agent for Prometheus metrics analysis with spike detection."""

    def __init__(self, max_iterations: int = 8, connection_config=None):
        super().__init__(
            agent_name="metrics_agent",
            max_iterations=max_iterations,
            connection_config=connection_config,
        )
        self._connection_config = connection_config
        # Resolve Prometheus URL from config, falling back to env var
        if connection_config and connection_config.prometheus_url:
            self.prometheus_url = connection_config.prometheus_url
        else:
            self.prometheus_url = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
        self._time_series_cache: dict[str, list[dict]] = {}

    async def _define_tools(self) -> list[dict]:
        return [
            {
                "name": "query_prometheus_range",
                "description": "Execute a PromQL range query against Prometheus. Returns time-series data points.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "PromQL query expression"},
                        "start": {"type": "string", "description": "Start time (ISO format or relative like '2025-12-26T14:00:00Z')"},
                        "end": {"type": "string", "description": "End time (ISO format or 'now')"},
                        "step": {"type": "string", "description": "Query resolution step, e.g. '60s', '5m'", "default": "60s"},
                    },
                    "required": ["query", "start", "end"],
                },
            },
            {
                "name": "query_prometheus_instant",
                "description": "Execute an instant PromQL query for current metric values.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "PromQL query expression"},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "detect_spikes",
                "description": "Analyze previously queried time-series data for anomalies/spikes. Call after query_prometheus_range.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "metric_name": {"type": "string", "description": "Name of the metric to analyze (must have been queried before)"},
                        "threshold_stddev": {"type": "number", "description": "Number of standard deviations from mean to consider a spike", "default": 2.0},
                    },
                    "required": ["metric_name"],
                },
            },
            {
                "name": "get_default_metrics",
                "description": "Get a list of recommended PromQL queries for a given namespace and service.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "namespace": {"type": "string"},
                        "service_name": {"type": "string"},
                    },
                    "required": ["namespace", "service_name"],
                },
            },
            {
                "name": "list_available_metrics",
                "description": "List Prometheus metric names matching a search term. Call this to discover what metrics are available before writing PromQL queries.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "search": {"type": "string", "description": "Metric name substring to search for (e.g. 'http_request')"},
                    },
                    "required": ["search"],
                },
            },
            {
                "name": "query_prometheus_offset",
                "description": "Compare a metric's current value to its value N hours ago. Returns current, baseline, and deviation. Use this for temporal baseline comparison.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "PromQL query expression"},
                        "offset_hours": {"type": "integer", "description": "Hours to look back for baseline", "default": 24},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "get_saturation_metrics",
                "description": "Get USE-method saturation queries triggered by specific error patterns. Call when log analysis reports resource-related errors (OOM, connection pool, disk, thread exhaustion).",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "namespace": {"type": "string"},
                        "service_name": {"type": "string"},
                        "error_hints": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Error keywords from log analysis (e.g. 'oom', 'connectionpool', 'disk', 'timeout')",
                        },
                    },
                    "required": ["namespace", "service_name", "error_hints"],
                },
            },
        ]

    async def _build_system_prompt(self) -> str:
        return """You are a Metrics Analysis Agent for SRE troubleshooting. You use the ReAct pattern.

IMPORTANT: Call list_available_metrics first to discover what metrics exist before writing PromQL queries. If the Prometheus endpoint is unreachable, report the error immediately instead of attempting further queries.

Your goals:
1. Discover available metrics using list_available_metrics
2. Query Prometheus for CPU, memory, error rate, and latency metrics for the affected service
3. Use get_default_metrics to get recommended queries, then execute them
4. Detect anomalies and spikes in the time-series data
5. Correlate metric anomalies with the incident time window
6. Report negative findings for metrics that show no anomalies
7. Use query_prometheus_offset to establish a 24h baseline for each anomalous metric

CRITICAL LABEL RULE: Every PromQL query you execute MUST include namespace= and pod=~ or service= labels to scope to the target service. Never execute a query without these labels — it will return data for the wrong services.

CRITICAL: Only report metrics that show anomalies. If you queried 20 metrics and only 2 show spikes, your final JSON must contain ONLY those 2 anomalies. Suppress all normal-range metrics. An SRE during an incident needs signal, not noise.

When log analysis provides error_hints, use get_saturation_metrics to query targeted resource metrics. For example:
- OOMKilled -> query memory saturation ratio
- ConnectionPoolTimeout -> query connection pool utilization
- Timeout errors -> query CPU throttling rate

After identifying anomalies, group them into correlated signal pairs in your final JSON:

"correlated_signals": [
    {
        "group_name": "Traffic & Errors",
        "signal_type": "RED",
        "metrics": ["http_requests_total", "http_errors_total"],
        "narrative": "Error rate spiked to 12% while request volume remained constant - not a traffic spike"
    },
    {
        "group_name": "Saturation -> Latency",
        "signal_type": "USE",
        "metrics": ["container_memory_working_set_bytes", "http_request_duration_seconds_p99"],
        "narrative": "Memory hit 95% of limit 2 min before P99 latency jumped 3x - resource exhaustion caused the slowdown"
    }
]

Only create groups where at least one metric in the pair shows an anomaly.

After analysis, provide your final answer as JSON:
{
    "anomalies": [
        {
            "metric_name": "container_memory_usage",
            "promql_query": "the query used",
            "baseline_value": 200.0,
            "peak_value": 510.0,
            "spike_start": "2025-12-26T14:02:00Z",
            "spike_end": "2025-12-26T14:15:00Z",
            "severity": "critical|high|medium|low",
            "correlation_to_incident": "Memory spike preceded first error by 13 minutes",
            "confidence_score": 90
        }
    ],
    "correlated_signals": [],
    "overall_confidence": 85
}"""

    async def _build_initial_prompt(self, context: dict) -> str:
        parts = [f"Analyze metrics for service: {context.get('service_name', 'unknown')}"]
        if context.get("namespace"):
            parts.append(f"Namespace: {context['namespace']}")
        if context.get("time_window"):
            tw = context["time_window"]
            parts.append(f"Incident time window: {tw.get('start', 'unknown')} to {tw.get('end', 'unknown')}")
        if context.get("error_patterns"):
            parts.append(f"Error patterns found by Log Agent: {json.dumps(context['error_patterns'])}")
        if context.get("error_hints"):
            parts.append(f"Error hints from log analysis: {context['error_hints']}")
            parts.append("IMPORTANT: Use get_saturation_metrics with these error hints to query targeted resource saturation metrics.")
        if context.get("suggested_promql_queries"):
            parts.append("Suggested PromQL queries from Log Agent root cause analysis:")
            for sq in context["suggested_promql_queries"]:
                parts.append(f"  - {sq.get('query', '')} (rationale: {sq.get('rationale', '')})")
            parts.append("IMPORTANT: Execute these suggested queries in addition to your standard analysis.")
            ns = context.get("namespace", "default")
            svc = context.get("service_name", "unknown")
            parts.append(f'NOTE: If any suggested query lacks namespace= or pod~/service= labels, add them before executing. '
                         f'Use namespace="{ns}" and pod=~"{svc}.*" or service="{svc}" as appropriate.')
        return "\n".join(parts)

    async def _handle_tool_call(self, tool_name: str, tool_input: dict) -> str:
        if tool_name == "query_prometheus_range":
            return await self._query_range(tool_input)
        elif tool_name == "query_prometheus_instant":
            return await self._query_instant(tool_input)
        elif tool_name == "detect_spikes":
            return self._detect_spikes_tool(tool_input)
        elif tool_name == "get_default_metrics":
            return self._get_default_metrics(tool_input)
        elif tool_name == "list_available_metrics":
            return await self._list_available_metrics(tool_input)
        elif tool_name == "query_prometheus_offset":
            return await self._query_offset(tool_input)
        elif tool_name == "get_saturation_metrics":
            return self._get_saturation_metrics(tool_input)
        return f"Unknown tool: {tool_name}"

    def _parse_final_response(self, text: str) -> dict:
        import re
        try:
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(text)
        except (json.JSONDecodeError, AttributeError):
            return {"error": "Failed to parse response", "raw_response": text}

        # Only include time_series_data for anomalous metrics
        anomaly_names = {a.get("metric_name", "") for a in data.get("anomalies", [])}

        def _ts_key_matches_anomaly(cache_key: str, names: set[str]) -> bool:
            kl = cache_key.lower()
            for name in names:
                nl = name.lower()
                # Bidirectional substring: "cpu_usage" matches "cpu_query" via shared root
                if nl in kl or kl in nl:
                    return True
                # Also match on shared root words (e.g. "cpu" in both "cpu_usage" and "cpu_query")
                k_parts = set(kl.replace("_", " ").replace("-", " ").split())
                n_parts = set(nl.replace("_", " ").replace("-", " ").split())
                if k_parts & n_parts:
                    return True
            return False

        filtered_ts = {k: v for k, v in self._time_series_cache.items()
                       if _ts_key_matches_anomaly(k, anomaly_names)} if anomaly_names else {}

        result = {
            "anomalies": data.get("anomalies", []),
            "correlated_signals": data.get("correlated_signals", []),
            "time_series_data": filtered_ts,
            "overall_confidence": data.get("overall_confidence", 50),
            "breadcrumbs": [b.model_dump(mode="json") for b in self.breadcrumbs],
            "negative_findings": [n.model_dump(mode="json") for n in self.negative_findings],
            "tokens_used": self.get_token_usage().model_dump(),
        }
        logger.info("Metrics agent complete", extra={"agent_name": self.agent_name, "action": "complete", "extra": {"anomalies": len(result["anomalies"]), "confidence": result["overall_confidence"]}})
        return result

    # --- Tool implementations ---

    async def _query_range(self, params: dict) -> str:
        query = params["query"]
        start = params["start"]
        end = params["end"]
        step = params.get("step", "60s")

        try:
            resp = requests.get(
                f"{self.prometheus_url}/api/v1/query_range",
                params={"query": query, "start": start, "end": end, "step": step},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("status") != "success":
                return json.dumps({"error": data.get("error", "Unknown error")})

            results = data.get("data", {}).get("result", [])
            if not results:
                self.add_negative_finding(
                    what_was_checked=f"Prometheus query: {query}",
                    result="No time-series data returned",
                    implication="This metric may not exist for the target or time range",
                    source_reference=f"Prometheus, query: {query}",
                )
                return json.dumps({"total_series": 0, "data_points": []})

            # Cache data points for spike detection
            all_points = []
            for series in results:
                values = series.get("values", [])
                points = [{"timestamp": v[0], "value": float(v[1])} for v in values]
                all_points.extend(points)

            metric_key = query[:80]
            self._time_series_cache[metric_key] = all_points

            self.add_breadcrumb(
                action="queried_prometheus_range",
                source_type="metric",
                source_reference=f"Prometheus, query: {query}",
                raw_evidence=f"Retrieved {len(all_points)} data points from {len(results)} series",
            )

            summary = {
                "total_series": len(results),
                "total_points": len(all_points),
                "metric_key": metric_key,
                "sample_points": all_points[:20],
                "min_value": min(p["value"] for p in all_points) if all_points else 0,
                "max_value": max(p["value"] for p in all_points) if all_points else 0,
                "avg_value": statistics.mean(p["value"] for p in all_points) if all_points else 0,
            }
            return json.dumps(summary, default=str)

        except requests.exceptions.ConnectionError:
            return json.dumps({"error": f"Cannot connect to Prometheus at {self.prometheus_url}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    async def _query_instant(self, params: dict) -> str:
        query = params["query"]
        try:
            resp = requests.get(
                f"{self.prometheus_url}/api/v1/query",
                params={"query": query},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("data", {}).get("result", [])

            if not results:
                self.add_negative_finding(
                    what_was_checked=f"Instant query: {query}",
                    result="No data returned",
                    implication="Metric not available or no matching series",
                    source_reference=f"Prometheus instant, query: {query}",
                )

            return json.dumps({"results": results}, default=str)

        except Exception as e:
            return json.dumps({"error": str(e)})

    def _detect_spikes_tool(self, params: dict) -> str:
        metric_name = params["metric_name"]
        threshold = params.get("threshold_stddev", 2.0)

        # Find matching cached data
        matching_key = None
        for key in self._time_series_cache:
            if metric_name.lower() in key.lower():
                matching_key = key
                break

        if not matching_key:
            return json.dumps({"error": f"No cached data for metric '{metric_name}'. Run query_prometheus_range first."})

        data_points = self._time_series_cache[matching_key]
        spikes = self._detect_spikes(data_points, threshold)

        return json.dumps({
            "metric": metric_name,
            "total_points": len(data_points),
            "spikes_found": len(spikes),
            "spikes": spikes,
        }, default=str)

    def _get_default_metrics(self, params: dict) -> str:
        namespace = params["namespace"]
        service = params["service_name"]
        job = params.get("job", "")
        app_label = params.get("app_label", "")
        return json.dumps(self._build_default_queries(namespace, service, job=job, app_label=app_label))

    async def _list_available_metrics(self, params: dict) -> str:
        """List Prometheus metric names matching a search term."""
        search = params.get("search", "")
        try:
            resp = requests.get(
                f"{self.prometheus_url}/api/v1/label/__name__/values",
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            all_names = data.get("data", [])
            if search:
                matching = [n for n in all_names if search.lower() in n.lower()]
            else:
                matching = all_names

            self.add_breadcrumb(
                action="list_available_metrics",
                source_type="metric",
                source_reference=f"Prometheus at {self.prometheus_url}",
                raw_evidence=f"Found {len(matching)} metrics matching '{search}' (total: {len(all_names)})",
            )

            return json.dumps({
                "total_metrics": len(all_names),
                "matching": len(matching),
                "metrics": matching[:100],
            })

        except requests.exceptions.ConnectionError:
            return json.dumps({"error": f"Cannot connect to Prometheus at {self.prometheus_url}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    async def _query_offset(self, params: dict) -> str:
        """Compare a metric's current value to its value N hours ago."""
        query = params["query"]
        offset_hours = params.get("offset_hours", 24)

        try:
            # Current value
            resp_now = requests.get(
                f"{self.prometheus_url}/api/v1/query",
                params={"query": query},
                timeout=30,
            )
            resp_now.raise_for_status()
            now_results = resp_now.json().get("data", {}).get("result", [])

            # Baseline value with offset
            offset_query = f"{query} offset {offset_hours}h"
            resp_base = requests.get(
                f"{self.prometheus_url}/api/v1/query",
                params={"query": offset_query},
                timeout=30,
            )
            resp_base.raise_for_status()
            base_results = resp_base.json().get("data", {}).get("result", [])

            current_val = float(now_results[0]["value"][1]) if now_results else 0.0
            baseline_val = float(base_results[0]["value"][1]) if base_results else 0.0

            if baseline_val == 0:
                deviation_pct = 100.0 if current_val > 0 else 0.0
            else:
                deviation_pct = round(((current_val - baseline_val) / baseline_val) * 100, 1)

            direction = "above" if current_val >= baseline_val else "below"

            self.add_breadcrumb(
                action="query_prometheus_offset",
                source_type="metric",
                source_reference=f"Prometheus, query: {query}, offset: {offset_hours}h",
                raw_evidence=f"Current: {current_val}, Baseline ({offset_hours}h ago): {baseline_val}, Deviation: {deviation_pct}%",
            )

            return json.dumps({
                "query": query,
                "offset_hours": offset_hours,
                "current_value": current_val,
                "baseline_value": baseline_val,
                "deviation_percent": deviation_pct,
                "direction": direction,
            })

        except requests.exceptions.ConnectionError:
            return json.dumps({"error": f"Cannot connect to Prometheus at {self.prometheus_url}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _get_saturation_metrics(self, params: dict) -> str:
        """Return USE-method saturation queries based on error hints."""
        namespace = params["namespace"]
        service_name = params["service_name"]
        error_hints = params.get("error_hints", [])

        ERROR_TO_SATURATION = {
            "oom": [
                {
                    "name": "memory_saturation",
                    "query": f'container_memory_working_set_bytes{{namespace="{namespace}", pod=~"{service_name}.*"}} / container_spec_memory_limit_bytes{{namespace="{namespace}", pod=~"{service_name}.*"}}',
                    "description": "Memory utilization ratio (>0.9 = saturated)",
                },
            ],
            "connectionpool": [
                {
                    "name": "connection_pool_usage",
                    "query": f'sum(db_pool_active_connections{{namespace="{namespace}", service="{service_name}"}}) / sum(db_pool_max_connections{{namespace="{namespace}", service="{service_name}"}})',
                    "description": "Connection pool utilization",
                },
            ],
            "disk": [
                {
                    "name": "disk_saturation",
                    "query": f'1 - (node_filesystem_avail_bytes{{namespace="{namespace}"}} / node_filesystem_size_bytes{{namespace="{namespace}"}})',
                    "description": "Disk utilization ratio",
                },
            ],
            "timeout": [
                {
                    "name": "cpu_throttling",
                    "query": f'rate(container_cpu_cfs_throttled_seconds_total{{namespace="{namespace}", pod=~"{service_name}.*"}}[5m])',
                    "description": "CPU throttling rate",
                },
            ],
        }

        queries = []
        for hint in error_hints:
            hint_lower = hint.lower()
            for key, saturation_queries in ERROR_TO_SATURATION.items():
                if key in hint_lower:
                    queries.extend(saturation_queries)

        self.add_breadcrumb(
            action="get_saturation_metrics",
            source_type="metric",
            source_reference=f"USE method, hints: {error_hints}",
            raw_evidence=f"Generated {len(queries)} saturation queries for hints: {error_hints}",
        )

        return json.dumps({"saturation_queries": queries, "error_hints": error_hints})

    # --- Pure logic ---

    def _build_default_queries(self, namespace: str, service_name: str,
                               job: str = "", app_label: str = "") -> list[dict]:
        """Build default PromQL queries for a service."""
        extra_labels = ""
        if job:
            extra_labels += f', job="{job}"'
        if app_label:
            extra_labels += f', app="{app_label}"'

        return [
            {
                "name": "cpu_usage",
                "query": f'rate(container_cpu_usage_seconds_total{{namespace="{namespace}", pod=~"{service_name}.*"{extra_labels}}}[5m])',
                "description": "CPU usage rate",
            },
            {
                "name": "memory_usage",
                "query": f'container_memory_working_set_bytes{{namespace="{namespace}", pod=~"{service_name}.*"{extra_labels}}}',
                "description": "Memory working set",
            },
            {
                "name": "error_rate",
                "query": f'rate(http_requests_total{{namespace="{namespace}", service="{service_name}"{extra_labels}, code=~"5.."}}[5m])',
                "description": "HTTP 5xx error rate",
            },
            {
                "name": "latency_p99",
                "query": f'histogram_quantile(0.99, rate(http_request_duration_seconds_bucket{{namespace="{namespace}", service="{service_name}"{extra_labels}}}[5m]))',
                "description": "P99 request latency",
            },
            {
                "name": "restart_count",
                "query": f'kube_pod_container_status_restarts_total{{namespace="{namespace}", pod=~"{service_name}.*"{extra_labels}}}',
                "description": "Container restart count",
            },
            {
                "name": "crashloop_pods",
                "query": f'kube_pod_container_status_waiting_reason{{namespace="{namespace}", pod=~"{service_name}.*", reason="CrashLoopBackOff"}}',
                "description": "Pods in CrashLoopBackOff state",
            },
            {
                "name": "oom_killed",
                "query": f'kube_pod_container_status_last_terminated_reason{{namespace="{namespace}", pod=~"{service_name}.*", reason="OOMKilled"}}',
                "description": "OOM-killed container count",
            },
            {
                "name": "pending_pods",
                "query": f'kube_pod_status_phase{{namespace="{namespace}", pod=~"{service_name}.*", phase="Pending"}}',
                "description": "Pods stuck in Pending state",
            },
        ]

    def _detect_spikes(self, data_points: list[dict], baseline_threshold: float = 2.0) -> list[dict]:
        """Detect anomalous spikes in time-series data using median + MAD (robust to outliers)."""
        if len(data_points) < 3:
            return []

        values = [p["value"] for p in data_points]
        mean_val = statistics.mean(values)
        median_val = statistics.median(values)
        # Use MAD (median absolute deviation) for robust outlier detection
        abs_devs = [abs(v - median_val) for v in values]
        mad = statistics.median(abs_devs)

        stddev_val = statistics.stdev(values) if len(values) > 1 else 0
        # Use MAD-based detection only when there's meaningful variance;
        # for low-variance data, fall back to stddev which is less sensitive
        coefficient_of_variation = stddev_val / abs(mean_val) if mean_val != 0 else 0

        if mad == 0 or coefficient_of_variation < 0.2:
            # Low variance data - use stddev-based detection
            baseline_center = mean_val
            spread = stddev_val
            if spread == 0:
                return []
        else:
            # High variance data - use MAD for robust outlier detection
            # (1.4826 converts MAD to approximate stddev for normal distributions)
            baseline_center = median_val
            spread = mad * 1.4826

        threshold = baseline_center + (baseline_threshold * spread)

        spikes = []
        in_spike = False
        spike_start = None
        spike_peak = 0
        spike_peak_ts = None

        for point in data_points:
            if point["value"] > threshold:
                if not in_spike:
                    in_spike = True
                    spike_start = point["timestamp"]
                    spike_peak = point["value"]
                    spike_peak_ts = point["timestamp"]
                elif point["value"] > spike_peak:
                    spike_peak = point["value"]
                    spike_peak_ts = point["timestamp"]
            else:
                if in_spike:
                    deviation_factor = round((spike_peak - baseline_center) / spread, 2) if spread > 0 else 0
                    confidence = min(95, int(50 + (deviation_factor * 10)))
                    spikes.append({
                        "spike_start": spike_start,
                        "spike_end": point["timestamp"],
                        "peak_value": spike_peak,
                        "peak_timestamp": spike_peak_ts,
                        "baseline_mean": round(mean_val, 2),
                        "baseline_stddev": round(spread, 2),
                        "deviation_factor": deviation_factor,
                        "confidence_score": confidence,
                    })
                    in_spike = False

        # Handle spike at end of data
        if in_spike:
            deviation_factor = round((spike_peak - baseline_center) / spread, 2) if spread > 0 else 0
            confidence = min(95, int(50 + (deviation_factor * 10)))
            spikes.append({
                "spike_start": spike_start,
                "spike_end": data_points[-1]["timestamp"],
                "peak_value": spike_peak,
                "peak_timestamp": spike_peak_ts,
                "baseline_mean": round(mean_val, 2),
                "baseline_stddev": round(spread, 2),
                "deviation_factor": deviation_factor,
                "confidence_score": confidence,
            })

        return spikes
