import json
import os
import re
from datetime import datetime, timezone
from typing import Any

import requests

from src.agents.react_base import ReActAgent
from src.models.schemas import SpanInfo, TraceAnalysisResult, TokenUsage
from src.utils.logger import get_logger

logger = get_logger(__name__)


class TracingAgent(ReActAgent):
    """ReAct agent for distributed tracing — Jaeger first, ELK fallback."""

    def __init__(self, max_iterations: int = 8, connection_config=None):
        super().__init__(agent_name="tracing_agent", max_iterations=max_iterations)
        self._connection_config = connection_config
        # Resolve URLs from config, falling back to env vars
        if connection_config and connection_config.jaeger_url:
            self.tracing_url = connection_config.jaeger_url
        else:
            self.tracing_url = os.getenv("TRACING_URL", "http://localhost:16686")
        if connection_config and connection_config.elasticsearch_url:
            self.es_url = connection_config.elasticsearch_url
        else:
            self.es_url = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")

    async def _define_tools(self) -> list[dict]:
        return [
            {
                "name": "list_traced_services",
                "description": "List all services reporting traces to Jaeger. Call this first to discover available services before querying traces.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            {
                "name": "query_jaeger",
                "description": "Fetch a trace from Jaeger/Tempo by trace ID. Returns spans with timing and service info.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "trace_id": {"type": "string"},
                    },
                    "required": ["trace_id"],
                },
            },
            {
                "name": "search_elk_trace",
                "description": "Search Elasticsearch for logs matching a trace/correlation ID to reconstruct the call chain. Use when Jaeger has no data.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "trace_id": {"type": "string"},
                        "index": {"type": "string", "default": "app-logs-*"},
                    },
                    "required": ["trace_id"],
                },
            },
        ]

    async def _build_system_prompt(self) -> str:
        return """You are a Distributed Tracing Agent for SRE troubleshooting. You use the ReAct pattern.

IMPORTANT: Call list_traced_services first to discover available services and verify Jaeger connectivity. If Jaeger is unreachable, report the error immediately and fall back to Elasticsearch.

Strategy:
1. FIRST: Call list_traced_services to verify Jaeger connectivity and discover services
2. THEN: Try Jaeger to get the trace (query_jaeger tool)
3. IF Jaeger returns no data or errors: FALL BACK to Elasticsearch (search_elk_trace tool)
4. Never skip the Jaeger step — always try it first

Your goals:
1. Map the complete request flow across services
2. Identify where the failure occurred and the cascade path
3. Detect retries and latency bottlenecks
4. Build a service dependency graph
5. Report negative findings when services show no errors

After analysis, provide your final answer as JSON:
{
    "trace_id": "abc-123",
    "total_duration_ms": 31500.0,
    "total_services": 5,
    "total_spans": 12,
    "call_chain": [{"span_id": "s1", "service_name": "...", "operation_name": "...", "duration_ms": 100, "status": "ok|error|timeout", "error_message": null, "parent_span_id": null, "tags": {}}],
    "failure_point": {"span_id": "...", ...},
    "cascade_path": ["postgres", "inventory-service", "order-service"],
    "latency_bottlenecks": [...],
    "retry_detected": false,
    "service_dependency_graph": {"api-gateway": ["order-service"], "order-service": ["inventory-service"]},
    "trace_source": "jaeger|elasticsearch",
    "overall_confidence": 85
}"""

    async def _build_initial_prompt(self, context: dict) -> str:
        parts = [f"Trace the request flow for trace_id: {context.get('trace_id', 'unknown')}"]
        if context.get("service_name"):
            parts.append(f"Affected service: {context['service_name']}")
        if context.get("error_patterns"):
            parts.append(f"Known error: {json.dumps(context['error_patterns'])}")
        return "\n".join(parts)

    async def _handle_tool_call(self, tool_name: str, tool_input: dict) -> str:
        if tool_name == "list_traced_services":
            return await self._list_traced_services()
        elif tool_name == "query_jaeger":
            return await self._query_jaeger(tool_input)
        elif tool_name == "search_elk_trace":
            return await self._search_elk_trace(tool_input)
        return f"Unknown tool: {tool_name}"

    def _parse_final_response(self, text: str) -> dict:
        try:
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(text)
        except (json.JSONDecodeError, AttributeError):
            return {"error": "Failed to parse response", "raw_response": text}

        result = {
            **data,
            "breadcrumbs": [b.model_dump(mode="json") for b in self.breadcrumbs],
            "negative_findings": [n.model_dump(mode="json") for n in self.negative_findings],
            "tokens_used": self.get_token_usage().model_dump(),
        }
        logger.info("Tracing agent complete", extra={"agent_name": self.agent_name, "action": "complete", "extra": {"spans": data.get("total_spans", 0), "confidence": data.get("overall_confidence", 0)}})
        return result

    # --- Tool implementations ---

    async def _list_traced_services(self) -> str:
        """List all services reporting traces to Jaeger."""
        try:
            resp = requests.get(
                f"{self.tracing_url}/api/services",
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            services = data.get("data", [])
            # Filter out internal Jaeger services
            services = [s for s in services if s != "jaeger-query"]

            self.add_breadcrumb(
                action="list_traced_services",
                source_type="trace_span",
                source_reference=f"Jaeger at {self.tracing_url}",
                raw_evidence=f"Found {len(services)} traced services",
            )

            return json.dumps({
                "reachable": True,
                "total_services": len(services),
                "services": services,
            })

        except requests.exceptions.ConnectionError:
            return json.dumps({
                "reachable": False,
                "error": f"Cannot connect to Jaeger at {self.tracing_url}",
                "suggestion": "Will fall back to Elasticsearch trace reconstruction",
            })
        except Exception as e:
            return json.dumps({"reachable": False, "error": str(e)})

    async def _query_jaeger(self, params: dict) -> str:
        trace_id = params["trace_id"]
        try:
            resp = requests.get(
                f"{self.tracing_url}/api/traces/{trace_id}",
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            if self._should_fallback_to_elk(data):
                self.add_negative_finding(
                    what_was_checked=f"Jaeger trace for trace_id '{trace_id}'",
                    result="No spans found in Jaeger",
                    implication="Trace not available in Jaeger — will try ELK reconstruction",
                    source_reference=f"Jaeger API, trace_id: {trace_id}",
                )
                return json.dumps({"status": "no_data", "message": "No trace data in Jaeger. Use search_elk_trace to reconstruct from logs."})

            spans = self._parse_jaeger_spans(data)
            self.add_breadcrumb(
                action="queried_jaeger",
                source_type="trace_span",
                source_reference=f"Jaeger, trace_id: {trace_id}",
                raw_evidence=f"Found {len(spans)} spans across {len(set(s['service_name'] for s in spans))} services",
            )

            return json.dumps({"status": "success", "source": "jaeger", "spans": spans}, default=str)

        except requests.exceptions.ConnectionError:
            self.add_negative_finding(
                what_was_checked=f"Jaeger at {self.tracing_url}",
                result="Connection failed",
                implication="Jaeger unavailable — will try ELK reconstruction",
                source_reference=f"Jaeger API at {self.tracing_url}",
            )
            return json.dumps({"status": "connection_error", "message": "Cannot connect to Jaeger. Use search_elk_trace."})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    async def _search_elk_trace(self, params: dict) -> str:
        trace_id = params["trace_id"]
        index = params.get("index", "app-logs-*")

        es_query = {
            "size": 200,
            "sort": [{"@timestamp": {"order": "asc"}}],
            "query": {
                "bool": {
                    "should": [
                        {"match": {"trace_id": trace_id}},
                        {"match": {"traceId": trace_id}},
                        {"match": {"correlation_id": trace_id}},
                        {"match": {"request_id": trace_id}},
                        {"match": {"x-request-id": trace_id}},
                    ],
                    "minimum_should_match": 1,
                }
            },
        }

        try:
            resp = requests.post(
                f"{self.es_url}/{index}/_search",
                json=es_query,
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            hits = data.get("hits", {}).get("hits", [])

            if not hits:
                self.add_negative_finding(
                    what_was_checked=f"ELK logs for trace_id '{trace_id}' in {index}",
                    result="Zero logs found",
                    implication="No logs found for this trace ID in any correlation field",
                    source_reference=f"Elasticsearch, index: {index}, trace_id: {trace_id}",
                )
                return json.dumps({"status": "no_data", "total": 0, "logs": []})

            logs = []
            for hit in hits:
                src = hit.get("_source", {})
                logs.append({
                    "timestamp": src.get("@timestamp", ""),
                    "service": src.get("service", src.get("kubernetes", {}).get("container", {}).get("name", "")),
                    "message": src.get("message", ""),
                    "level": src.get("level", ""),
                    "trace_id": trace_id,
                })

            self.add_breadcrumb(
                action="searched_elk_trace",
                source_type="log",
                source_reference=f"Elasticsearch, index: {index}, trace_id: {trace_id}",
                raw_evidence=f"Found {len(logs)} logs across {len(set(l['service'] for l in logs))} services",
            )

            chain = self._reconstruct_chain_from_logs(logs)
            return json.dumps({
                "status": "success",
                "source": "elasticsearch",
                "total_logs": len(logs),
                "reconstructed_chain": chain,
                "note": "Chain reconstructed from logs — timings are approximate",
            }, default=str)

        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    # --- Pure logic ---

    @staticmethod
    def _should_fallback_to_elk(jaeger_response) -> bool:
        """Check if Jaeger response has no useful data."""
        if jaeger_response is None:
            return True
        data = jaeger_response.get("data", [])
        if not data:
            return True
        for trace in data:
            spans = trace.get("spans", [])
            if spans:
                return False
        return True

    @staticmethod
    def _parse_jaeger_spans(jaeger_response: dict) -> list[dict]:
        """Parse Jaeger API response into a list of span dicts."""
        spans = []
        data = jaeger_response.get("data", [])
        for trace in data:
            processes = trace.get("processes", {})
            for span in trace.get("spans", []):
                process_id = span.get("processID", "")
                service_name = processes.get(process_id, {}).get("serviceName", "unknown")
                duration_us = span.get("duration", 0)

                error = False
                error_msg = None
                for tag in span.get("tags", []):
                    if tag.get("key") == "error" and tag.get("value"):
                        error = True
                    if tag.get("key") == "error.message":
                        error_msg = tag.get("value")

                status = "error" if error else "ok"
                if duration_us > 30_000_000:  # > 30s
                    status = "timeout"

                spans.append({
                    "span_id": span.get("spanID", ""),
                    "service_name": service_name,
                    "operation_name": span.get("operationName", ""),
                    "duration_ms": round(duration_us / 1000, 2),
                    "status": status,
                    "error_message": error_msg,
                    "parent_span_id": span.get("references", [{}])[0].get("spanID") if span.get("references") else None,
                    "tags": {t["key"]: str(t.get("value", "")) for t in span.get("tags", [])},
                })

        return spans

    @staticmethod
    def _reconstruct_chain_from_logs(logs: list[dict]) -> list[dict]:
        """Reconstruct a call chain from Elasticsearch logs (sorted by timestamp)."""
        if not logs:
            return []

        sorted_logs = sorted(logs, key=lambda l: l.get("timestamp", ""))
        chain = []
        seen_services = set()

        for log in sorted_logs:
            service = log.get("service", "unknown")
            level = log.get("level", "INFO")
            message = log.get("message", "")

            status = "ok"
            if level in ("ERROR", "FATAL"):
                status = "error"
            elif "timeout" in message.lower():
                status = "timeout"

            chain.append({
                "service_name": service,
                "timestamp": log.get("timestamp", ""),
                "message": message[:200],
                "status": status,
                "is_new_service": service not in seen_services,
            })
            seen_services.add(service)

        return chain
