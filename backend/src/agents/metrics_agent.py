import asyncio
import json
import os
import statistics
from datetime import datetime, timezone
from typing import Any

import requests

from src.agents.react_base import ReActAgent
from src.models.schemas import MetricAnomaly, DataPoint, TimeRange, MetricsAnalysisResult, TokenUsage
from src.utils.event_emitter import EventEmitter
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MetricsAgent(ReActAgent):
    """ReAct agent for Prometheus metrics analysis with spike detection."""

    def __init__(self, max_iterations: int = 5, connection_config=None):
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
                "description": "List Prometheus metric names matching a search term. Optionally filter to only metrics that have data for a specific namespace.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "search": {"type": "string", "description": "Metric name substring to search for (e.g. 'container_cpu', 'http_request')"},
                        "namespace": {"type": "string", "description": "Kubernetes namespace to scope discovery to. When provided, only returns metrics that have data in this namespace."},
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

EXECUTION STRATEGY — Batch & Refine (3 turns):

═══ TURN 1 — Discovery ═══
Emit ALL of these tool calls in a SINGLE response:
  • list_available_metrics  — discover what exists. ALWAYS pass the namespace parameter to scope results to the target namespace. Use broad search terms like "container", "kube_pod", "http" to find infrastructure metrics.
  • get_default_metrics     — get recommended PromQL for the service
  • get_saturation_metrics  — ONLY if error_hints were provided
If Prometheus is unreachable on any call, report the error immediately and stop.

═══ TURN 2 — Signal Acquisition ═══
Using the metric names and queries returned in Turn 1, emit ALL data-fetching calls in a SINGLE response:
  • query_prometheus_range  (x4-8) — one per default/saturation/suggested query, scoped to the incident time window
  • query_prometheus_offset (x2-4) — 24h baseline for the most important metrics (CPU, memory, error rate, latency)
Do NOT call these one at a time. Batch every range and offset query into one response.

═══ TURN 3 — Synthesis ═══
Analyze all returned data. If any metric warrants spike detection, call detect_spikes for those metrics, then output your final JSON.
If no spike detection is needed, output the final JSON directly.

CRITICAL LABEL RULE: Every PromQL query MUST include namespace= and pod=~ or service= labels to scope to the target service. Never execute a query without these labels.

SIGNAL OVER NOISE: Prioritize anomalies but ALWAYS include baseline metrics. Your final JSON must contain:
- All anomalous metrics (with severity critical/high/medium)
- Key baseline metrics (CPU, memory, connection pools) even if normal — mark them severity "low" with confidence_score 100 and correlation_to_incident "Within normal range — rules out resource exhaustion"
This ensures the UI always shows the metrics landscape, not just anomalies.

SATURATION TRIGGERS (when error_hints provided):
- OOMKilled -> query memory saturation ratio
- ConnectionPoolTimeout -> query connection pool utilization
- Timeout errors -> query CPU throttling rate

CORRELATED SIGNALS: Group anomalies into signal pairs in your final JSON:

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

OUTPUT FORMAT — Final answer as JSON:
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
        if context.get("affected_services"):
            parts.append(f"Affected services (query metrics for ALL of these): {context['affected_services']}")
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
            parts.append("NOTE: Suggested queries already contain correct labels (namespace, service, pod). "
                         "Do NOT override their existing labels. Only add namespace= if it is completely missing.")
            parts.append("VALIDATION: Before executing suggested queries, use list_available_metrics to check if the metric exists. "
                         "If a suggested metric does not exist, skip it and look for a similar available metric to query instead.")

        parts.append("")
        parts.append(
            "BEGIN TURN 1: Call list_available_metrics + get_default_metrics"
            + (" + get_saturation_metrics" if context.get("error_hints") else "")
            + " in parallel NOW."
        )
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

        # Include all queried time series data — even normal metrics provide context

        result = {
            "anomalies": data.get("anomalies", []),
            "correlated_signals": data.get("correlated_signals", []),
            "time_series_data": dict(self._time_series_cache),
            "overall_confidence": data.get("overall_confidence", 50),
            "breadcrumbs": [b.model_dump(mode="json") for b in self.breadcrumbs],
            "negative_findings": [n.model_dump(mode="json") for n in self.negative_findings],
            "tokens_used": self.get_token_usage().model_dump(),
        }
        logger.info("Metrics agent complete", extra={"agent_name": self.agent_name, "action": "complete", "extra": {"anomalies": len(result["anomalies"]), "confidence": result["overall_confidence"]}})
        return result

    # --- Tool implementations ---

    @staticmethod
    def _resolve_time(value: str) -> float:
        """Convert a time value to Unix timestamp.

        Accepts: Unix timestamps, ISO 8601, relative expressions (now, now-3h, now-30m).
        """
        import re as _re
        v = value.strip()
        # Already a number
        try:
            return float(v)
        except ValueError:
            pass
        # Relative: "now", "now-3h", "now-1h30m"
        if v.lower().startswith("now"):
            now = datetime.now(timezone.utc).timestamp()
            suffix = v[3:].strip()
            if not suffix:
                return now
            m = _re.match(r'^-\s*(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$', suffix)
            if m:
                hours = int(m.group(1) or 0)
                minutes = int(m.group(2) or 0)
                seconds = int(m.group(3) or 0)
                return now - hours * 3600 - minutes * 60 - seconds
            # Fallback: try just hours
            m2 = _re.match(r'^-\s*(\d+)\s*h$', suffix, _re.IGNORECASE)
            if m2:
                return now - int(m2.group(1)) * 3600
            return now
        # ISO 8601
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return dt.timestamp()
        except ValueError:
            pass
        # Last resort: return current time
        return datetime.now(timezone.utc).timestamp()

    @staticmethod
    async def _async_get(url: str, params: dict = None, timeout: int = 30):
        """Run requests.get in a thread pool to avoid blocking the event loop."""
        return await asyncio.to_thread(requests.get, url, params=params, timeout=timeout)

    async def _query_range(self, params: dict) -> str:
        query = params["query"]
        start = self._resolve_time(params["start"])
        end = self._resolve_time(params["end"])
        step = params.get("step", "60s")

        try:
            resp = await self._async_get(
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
            resp = await self._async_get(
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
        """List Prometheus metric names matching a search term, optionally scoped to a namespace."""
        search = params.get("search", "")
        namespace = params.get("namespace", "")
        try:
            api_params = {}
            if namespace:
                api_params["match[]"] = '{namespace="' + namespace + '"}'

            resp = await self._async_get(
                f"{self.prometheus_url}/api/v1/label/__name__/values",
                params=api_params,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            all_names = data.get("data", [])
            if search:
                matching = [n for n in all_names if search.lower() in n.lower()]
            else:
                matching = all_names

            scope_desc = f" in namespace '{namespace}'" if namespace else ""
            self.add_breadcrumb(
                action="list_available_metrics",
                source_type="metric",
                source_reference=f"Prometheus at {self.prometheus_url}",
                raw_evidence=f"Found {len(matching)} metrics matching '{search}'{scope_desc} (total: {len(all_names)})",
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
            now_ts = datetime.now(timezone.utc).timestamp()
            baseline_ts = now_ts - offset_hours * 3600

            # Current value
            resp_now = await self._async_get(
                f"{self.prometheus_url}/api/v1/query",
                params={"query": query, "time": now_ts},
                timeout=30,
            )
            resp_now.raise_for_status()
            now_results = resp_now.json().get("data", {}).get("result", [])

            # Baseline value at N hours ago (using time parameter instead of PromQL offset)
            resp_base = await self._async_get(
                f"{self.prometheus_url}/api/v1/query",
                params={"query": query, "time": baseline_ts},
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

    # ══════════════════════════════════════════════════════════════════════
    #  Two-Pass Mode (1 LLM call)
    # ══════════════════════════════════════════════════════════════════════

    async def run_two_pass(self, context: dict, event_emitter: EventEmitter | None = None) -> dict:
        """Execute metrics analysis in exactly 1 LLM call.

        Phase 0:  Pre-fetch — discover metrics, build query list, execute ALL
                  Prometheus queries + offset comparisons + spike detection.
                  Zero LLM calls, pure API + math.
        Call 1:   Analyze — LLM sees all time-series data, spikes, baselines,
                  and produces final anomalies JSON.
        """
        service_name = context.get("service_name", "unknown")
        namespace = context.get("namespace", "default")
        time_window = context.get("time_window", {})
        error_hints = context.get("error_hints", [])
        suggested_promql = context.get("suggested_promql_queries", [])
        error_patterns = context.get("error_patterns", [])

        logger.info("Metrics agent two-pass starting", extra={
            "agent_name": self.agent_name, "action": "two_pass_start",
            "extra": {
                "service": service_name, "namespace": namespace,
                "error_hints": len(error_hints), "suggested_queries": len(suggested_promql),
            },
        })

        if event_emitter:
            await event_emitter.emit(self.agent_name, "started", "Metrics agent starting two-pass analysis")

        # ── Phase 0a: Discover metrics & build query list ────────────────
        if event_emitter:
            await event_emitter.emit(self.agent_name, "tool_call", "Discovering available metrics")

        # Parallel: list metrics + get default queries + get saturation queries
        async def _discover_metrics():
            searches = ["container", "kube_pod", "http", "node_"]
            results = {}
            for term in searches:
                raw = await self._list_available_metrics({"search": term, "namespace": namespace})
                data = json.loads(raw)
                if "error" not in data:
                    results[term] = data.get("metrics", [])
            return results

        # _get_default_metrics and _get_saturation_metrics are sync (pure logic),
        # so call them directly. Only _discover_metrics needs await.
        discovery_result = await _discover_metrics()

        default_queries_raw = self._get_default_metrics(
            {"namespace": namespace, "service_name": service_name}
        )
        saturation_queries_raw = (
            self._get_saturation_metrics({
                "namespace": namespace,
                "service_name": service_name,
                "error_hints": error_hints,
            })
            if error_hints else None
        )

        # Parse default queries (returns JSON string from _get_default_metrics)
        all_queries: list[dict] = []
        try:
            default_queries = json.loads(default_queries_raw) if isinstance(default_queries_raw, str) else []
            all_queries.extend(default_queries)
        except (json.JSONDecodeError, TypeError):
            pass

        # Parse saturation queries
        saturation_queries = []
        if saturation_queries_raw:
            try:
                sat_data = json.loads(saturation_queries_raw) if isinstance(saturation_queries_raw, str) else {}
                saturation_queries = sat_data.get("saturation_queries", [])
                all_queries.extend(saturation_queries)
            except (json.JSONDecodeError, TypeError):
                pass

        # Add suggested PromQL queries from log agent
        for sq in suggested_promql:
            query_str = sq.get("query", "") if isinstance(sq, dict) else str(sq)
            if query_str:
                all_queries.append({
                    "name": f"suggested_{len(all_queries)}",
                    "query": query_str,
                    "description": sq.get("rationale", "Suggested by log agent") if isinstance(sq, dict) else "Suggested query",
                })

        # Flatten available metric names for validation
        available_metrics = set()
        if isinstance(discovery_result, dict):
            for metrics_list in discovery_result.values():
                available_metrics.update(metrics_list)

        logger.info("Phase 0a complete", extra={
            "agent_name": self.agent_name, "action": "discovery_complete",
            "extra": {
                "available_metrics": len(available_metrics),
                "queries_to_run": len(all_queries),
                "saturation_queries": len(saturation_queries),
            },
        })

        # ── Phase 0b: Execute all queries in parallel ────────────────────
        if event_emitter:
            await event_emitter.emit(
                self.agent_name, "tool_call",
                f"Executing {len(all_queries)} Prometheus queries in parallel"
            )

        # Determine time range
        start_time = time_window.get("start", "now-3h")
        end_time = time_window.get("end", "now")

        # Range queries
        async def _exec_range_query(q: dict) -> tuple[str, str]:
            name = q.get("name", "unknown")
            result = await self._query_range({
                "query": q["query"],
                "start": start_time,
                "end": end_time,
                "step": "60s",
            })
            return name, result

        # Offset queries (for top-4 key metrics: CPU, memory, error_rate, latency)
        key_metric_names = {"cpu_usage", "memory_usage", "error_rate", "latency_p99"}
        offset_queries = [q for q in all_queries if q.get("name") in key_metric_names]

        async def _exec_offset_query(q: dict) -> tuple[str, str]:
            name = q.get("name", "unknown")
            result = await self._query_offset({"query": q["query"], "offset_hours": 24})
            return f"{name}_offset", result

        # Run all range + offset queries in parallel
        range_tasks = [_exec_range_query(q) for q in all_queries]
        offset_tasks = [_exec_offset_query(q) for q in offset_queries]
        all_results = await asyncio.gather(*(range_tasks + offset_tasks), return_exceptions=True)

        range_data: dict[str, dict] = {}
        offset_data: dict[str, dict] = {}
        for item in all_results:
            if isinstance(item, tuple):
                name, raw = item
                try:
                    parsed = json.loads(raw)
                    if name.endswith("_offset"):
                        offset_data[name] = parsed
                    else:
                        range_data[name] = parsed
                except (json.JSONDecodeError, TypeError):
                    pass

        # ── Phase 0c: Run spike detection on all cached time series ──────
        spike_results: dict[str, list] = {}
        for metric_key in list(self._time_series_cache.keys()):
            spikes = self._detect_spikes(self._time_series_cache[metric_key], baseline_threshold=2.0)
            if spikes:
                spike_results[metric_key] = spikes

        logger.info("Phase 0b+c complete", extra={
            "agent_name": self.agent_name, "action": "queries_complete",
            "extra": {
                "range_queries": len(range_data),
                "offset_queries": len(offset_data),
                "spikes_detected": len(spike_results),
            },
        })

        # ── Call 1: Analyze (the only LLM call) ─────────────────────────
        if event_emitter:
            await event_emitter.emit(self.agent_name, "tool_call", "LLM Call 1: Analyzing all metrics data")

        analyze_prompt = self._build_metrics_analyze_prompt(
            context, all_queries, range_data, offset_data, spike_results, available_metrics
        )
        analyze_response = await self.llm_client.chat(
            prompt=analyze_prompt,
            system=self._two_pass_metrics_system_prompt(),
            max_tokens=4096,
        )

        if event_emitter:
            await event_emitter.emit(self.agent_name, "success", "Metrics agent completed analysis")

        result = self._parse_final_response(analyze_response.text)
        result["mode"] = "two_pass"
        result["llm_calls"] = 1
        logger.info("Two-pass metrics analysis complete", extra={
            "agent_name": self.agent_name, "action": "complete",
            "extra": {"anomalies": len(result.get("anomalies", []))},
        })
        return result

    # ── Two-pass prompt builders ─────────────────────────────────────────

    def _two_pass_metrics_system_prompt(self) -> str:
        return (
            "You are a Metrics Analysis Agent for SRE troubleshooting.\n\n"
            "You are given ALL pre-fetched Prometheus data: time-series results, "
            "24h baseline comparisons, and automated spike detection results.\n\n"
            "Your job: analyze this data and produce the final anomalies JSON.\n\n"
            "SIGNAL OVER NOISE: Prioritize anomalies but ALWAYS include baseline metrics. "
            "Your final JSON must contain:\n"
            "- All anomalous metrics (with severity critical/high/medium)\n"
            "- Key baseline metrics (CPU, memory, connection pools) even if normal — "
            "mark them severity 'low' with confidence_score 100 and "
            "correlation_to_incident 'Within normal range'\n\n"
            "CORRELATED SIGNALS: Group anomalies into signal pairs:\n"
            '- "group_name": descriptive label\n'
            '- "signal_type": "RED" or "USE"\n'
            '- "metrics": [metric names]\n'
            '- "narrative": causal explanation\n\n'
            "Only create groups where at least one metric shows an anomaly.\n\n"
            "OUTPUT FORMAT — Respond with ONLY JSON (no markdown, no extra text):\n"
            "{\n"
            '    "anomalies": [\n'
            "        {\n"
            '            "metric_name": "...",\n'
            '            "promql_query": "the query used",\n'
            '            "baseline_value": 200.0,\n'
            '            "peak_value": 510.0,\n'
            '            "spike_start": "2025-12-26T14:02:00Z",\n'
            '            "spike_end": "2025-12-26T14:15:00Z",\n'
            '            "severity": "critical|high|medium|low",\n'
            '            "correlation_to_incident": "explanation",\n'
            '            "confidence_score": 90\n'
            "        }\n"
            "    ],\n"
            '    "correlated_signals": [],\n'
            '    "overall_confidence": 85\n'
            "}\n"
        )

    def _build_metrics_analyze_prompt(
        self,
        context: dict,
        queries: list[dict],
        range_data: dict[str, dict],
        offset_data: dict[str, dict],
        spike_results: dict[str, list],
        available_metrics: set[str],
    ) -> str:
        parts = [
            "# Metrics Analysis — All Data Pre-Fetched\n",
            f"## Service: {context.get('service_name', 'unknown')}",
            f"## Namespace: {context.get('namespace', 'default')}",
        ]

        tw = context.get("time_window", {})
        if tw:
            parts.append(f"## Incident Window: {tw.get('start', '?')} to {tw.get('end', '?')}")

        if context.get("error_patterns"):
            parts.append(f"\n## Error Patterns from Log Agent\n{json.dumps(context['error_patterns'], indent=2)}")
        if context.get("error_hints"):
            parts.append(f"\n## Error Hints: {context['error_hints']}")

        # Queries executed
        parts.append(f"\n## Queries Executed ({len(queries)})")
        for q in queries:
            parts.append(f"  - **{q.get('name', '?')}**: `{q.get('query', '?')}` — {q.get('description', '')}")

        # Range query results
        parts.append(f"\n## Time-Series Results ({len(range_data)} queries)")
        for name, data in range_data.items():
            if "error" in data:
                parts.append(f"\n### {name}: ERROR — {data['error']}")
            else:
                parts.append(
                    f"\n### {name}: {data.get('total_points', 0)} points, "
                    f"min={data.get('min_value', '?')}, max={data.get('max_value', '?')}, "
                    f"avg={data.get('avg_value', '?')}"
                )

        # Offset (baseline comparison) results
        if offset_data:
            parts.append(f"\n## 24h Baseline Comparisons ({len(offset_data)})")
            for name, data in offset_data.items():
                if "error" in data:
                    parts.append(f"  - {name}: ERROR — {data['error']}")
                else:
                    parts.append(
                        f"  - **{name}**: current={data.get('current_value', '?')}, "
                        f"baseline={data.get('baseline_value', '?')}, "
                        f"deviation={data.get('deviation_percent', '?')}% {data.get('direction', '')}"
                    )

        # Spike detection results
        if spike_results:
            parts.append(f"\n## Automated Spike Detection ({len(spike_results)} metrics with spikes)")
            for metric_key, spikes in spike_results.items():
                parts.append(f"\n### {metric_key}: {len(spikes)} spike(s)")
                for s in spikes:
                    parts.append(
                        f"  - Peak: {s['peak_value']} (baseline mean: {s['baseline_mean']}, "
                        f"deviation: {s['deviation_factor']}x stddev), "
                        f"confidence: {s['confidence_score']}%"
                    )
        else:
            parts.append("\n## Automated Spike Detection: No spikes detected in any metric")

        parts.append("\n## Your Task")
        parts.append(
            "Analyze ALL the data above. Produce the final anomalies JSON. "
            "Include both anomalous AND normal baseline metrics in your output."
        )

        return "\n".join(parts)
