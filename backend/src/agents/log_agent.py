import json
import re
import hashlib
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import requests

from src.agents.react_base import ReActAgent
from src.models.schemas import (
    ErrorPattern, LogEvidence, LogAnalysisResult,
    NegativeFinding, Breadcrumb, TokenUsage
)
from src.utils.event_emitter import EventEmitter

import os


class LogAnalysisAgent(ReActAgent):
    """ReAct agent for log analysis with error pattern detection and prioritization."""

    def __init__(self, max_iterations: int = 8, connection_config=None):
        super().__init__(agent_name="log_agent", max_iterations=max_iterations)
        self._connection_config = connection_config
        # Resolve Elasticsearch URL from config, falling back to env var
        if connection_config and connection_config.elasticsearch_url:
            self.es_url = connection_config.elasticsearch_url
        else:
            self.es_url = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
        self._es_headers = self._build_es_headers(connection_config)
        self._raw_logs: list[dict] = []
        self._patterns: list[dict] = []

    def _build_es_headers(self, connection_config) -> dict:
        """Build HTTP headers for Elasticsearch requests, including auth."""
        headers = {"Content-Type": "application/json"}
        if not connection_config:
            return headers
        auth_method = getattr(connection_config, "elasticsearch_auth_method", "none")
        credentials = getattr(connection_config, "elasticsearch_credentials", "")
        if auth_method == "token" and credentials:
            headers["Authorization"] = f"Bearer {credentials}"
        elif auth_method == "api_key" and credentials:
            headers["Authorization"] = f"ApiKey {credentials}"
        elif auth_method == "basic" and credentials:
            import base64
            headers["Authorization"] = f"Basic {base64.b64encode(credentials.encode()).decode()}"
        return headers

    async def _define_tools(self) -> list[dict]:
        return [
            {
                "name": "search_elasticsearch",
                "description": "Search Elasticsearch for logs matching a query. Returns matching log entries.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "string", "description": "ES index pattern, e.g. 'app-logs-*'"},
                        "query": {"type": "string", "description": "Lucene query string"},
                        "time_range": {"type": "string", "description": "Time range, e.g. 'now-1h'"},
                        "size": {"type": "integer", "description": "Max results to return", "default": 200},
                        "level_filter": {"type": "string", "description": "Log level filter: ERROR, WARN, INFO", "default": "ERROR"},
                    },
                    "required": ["index", "query"],
                },
            },
            {
                "name": "search_by_trace_id",
                "description": "Search for all logs associated with a specific trace/correlation ID.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "string"},
                        "trace_id": {"type": "string"},
                        "size": {"type": "integer", "default": 100},
                    },
                    "required": ["index", "trace_id"],
                },
            },
            {
                "name": "get_log_context",
                "description": "Get surrounding log entries (before and after) for a specific log ID to understand the sequence of events.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "string"},
                        "timestamp": {"type": "string", "description": "ISO timestamp of the target log entry"},
                        "service": {"type": "string", "description": "Service name to filter by"},
                        "minutes_before": {"type": "integer", "default": 5},
                        "minutes_after": {"type": "integer", "default": 2},
                    },
                    "required": ["index", "timestamp", "service"],
                },
            },
            {
                "name": "analyze_patterns",
                "description": "Group collected logs into error patterns by exception type and message similarity. Call this after collecting logs.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "list_available_indices",
                "description": "List all Elasticsearch indices matching a pattern. Call this to discover what log indices exist before searching, so you can target the correct index.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "Index pattern (e.g. 'app-logs-*')", "default": "*"},
                    },
                    "required": [],
                },
            },
        ]

    async def _build_system_prompt(self) -> str:
        return """You are a Log Analysis Agent for SRE troubleshooting. You use the ReAct pattern:
THINK about what to search for, ACT by calling tools, OBSERVE results, then decide next steps.

CRITICAL STEPS — follow this order:
1. Call list_available_indices FIRST to discover what log indices exist. Do NOT assume index names.
2. Pick the index that looks most relevant (could be logstash-*, filebeat-*, app-logs-*, or any other pattern).
3. Search for ERROR logs for the target service. Use the service name in the query string (e.g. "checkout-service AND error" or just the service name).
4. If a search returns zero results, try different approaches:
   - Try a broader query (just the service name, or "*")
   - Try a different index
   - Try without the level_filter (set level_filter to empty string) to see what fields exist
   - Try searching for the service name in different fields
5. Also check WARN logs that preceded errors
6. Search by trace_id if one is available
7. Group errors into distinct patterns using analyze_patterns
8. Prioritize patterns by: frequency, severity, likely root cause vs symptom

If Elasticsearch is unreachable, report the error immediately instead of attempting further queries.

After gathering enough data, provide your final analysis as JSON with this structure:
{
    "primary_pattern": {
        "pattern_id": "p1",
        "exception_type": "ExceptionName",
        "error_message": "The error message",
        "frequency": 47,
        "severity": "critical|high|medium|low",
        "affected_components": ["service-name"],
        "confidence_score": 87,
        "priority_rank": 1,
        "priority_reasoning": "Why this is the top priority"
    },
    "secondary_patterns": [...],
    "overall_confidence": 85
}

Always provide evidence: include raw log snippets in your reasoning.
Always report what you searched and didn't find (negative evidence)."""

    async def _build_initial_prompt(self, context: dict) -> str:
        service = context.get("service_name", "unknown")
        parts = [
            f"Analyze logs for service: {service}",
            f"IMPORTANT: First discover available indices with list_available_indices, then search for '{service}' in the most relevant index.",
        ]
        if context.get("elk_index") and context["elk_index"] != "*":
            parts.append(f"Suggested Elasticsearch index hint: {context['elk_index']} (verify with list_available_indices first)")
        if context.get("timeframe"):
            parts.append(f"Time range: {context['timeframe']}")
        if context.get("trace_id"):
            parts.append(f"Trace ID to investigate: {context['trace_id']}")
        if context.get("error_filter"):
            parts.append(f"Error filter: {context['error_filter']}")
        return "\n".join(parts)

    async def _handle_tool_call(self, tool_name: str, tool_input: dict) -> str:
        if tool_name == "search_elasticsearch":
            return await self._search_elasticsearch(tool_input)
        elif tool_name == "search_by_trace_id":
            return await self._search_by_trace_id(tool_input)
        elif tool_name == "get_log_context":
            return await self._get_log_context(tool_input)
        elif tool_name == "analyze_patterns":
            return self._analyze_patterns_tool()
        elif tool_name == "list_available_indices":
            return await self._list_available_indices(tool_input)
        else:
            return f"Unknown tool: {tool_name}"

    def _parse_final_response(self, text: str) -> dict:
        """Parse LLM's final JSON response into LogAnalysisResult."""
        # Try to extract JSON from the response
        try:
            # Look for JSON block in the text
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(text)
        except (json.JSONDecodeError, AttributeError):
            return {
                "error": "Failed to parse response",
                "raw_response": text,
                "breadcrumbs": [b.model_dump() for b in self.breadcrumbs],
                "negative_findings": [n.model_dump() for n in self.negative_findings],
            }

        # Build structured result
        return {
            "primary_pattern": data.get("primary_pattern", {}),
            "secondary_patterns": data.get("secondary_patterns", []),
            "overall_confidence": data.get("overall_confidence", 50),
            "breadcrumbs": [b.model_dump(mode="json") for b in self.breadcrumbs],
            "negative_findings": [n.model_dump(mode="json") for n in self.negative_findings],
            "tokens_used": self.get_token_usage().model_dump(),
            "raw_logs_count": len(self._raw_logs),
            "patterns_found": len(self._patterns),
        }

    # --- Tool implementations ---

    async def _search_elasticsearch(self, params: dict) -> str:
        """Query Elasticsearch and return matching logs."""
        index = params.get("index", "app-logs-*")
        query = params.get("query", "*")
        time_range = params.get("time_range", "now-1h")
        size = params.get("size", 200)
        level_filter = params.get("level_filter", "ERROR")

        es_query = {
            "size": size,
            "sort": [{"@timestamp": {"order": "desc"}}],
            "query": {
                "bool": {
                    "must": [
                        {"query_string": {"query": query}},
                    ],
                    "filter": [
                        {"range": {"@timestamp": {"gte": time_range, "lte": "now"}}},
                    ],
                }
            },
        }

        if level_filter:
            # Search across common log level field names and case variants
            level_lower = level_filter.lower()
            level_upper = level_filter.upper()
            es_query["query"]["bool"]["must"].append({
                "bool": {
                    "should": [
                        {"match": {"level": level_upper}},
                        {"match": {"level": level_lower}},
                        {"match": {"log.level": level_lower}},
                        {"match": {"log.level": level_upper}},
                        {"match": {"severity": level_upper}},
                        {"match": {"severity": level_lower}},
                        {"match": {"loglevel": level_upper}},
                        {"match": {"loglevel": level_lower}},
                    ],
                    "minimum_should_match": 1,
                }
            })

        try:
            resp = requests.post(
                f"{self.es_url}/{index}/_search",
                json=es_query,
                headers=self._es_headers,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            hits = data.get("hits", {}).get("hits", [])

            if not hits:
                self.add_negative_finding(
                    what_was_checked=f"{level_filter} logs in {index} matching '{query}' (last {time_range})",
                    result="Zero results found",
                    implication=f"No {level_filter} logs match this query in the given time range",
                    source_reference=f"{index}, query: {query}",
                )
                return json.dumps({"total": 0, "logs": []})

            logs = []
            for hit in hits:
                src = hit.get("_source", {})
                log_entry = {
                    "id": hit.get("_id", ""),
                    "index": hit.get("_index", ""),
                    "timestamp": src.get("@timestamp", ""),
                    "level": src.get("level", ""),
                    "message": src.get("message", ""),
                    "service": (
                        src.get("service", {}).get("name", "") if isinstance(src.get("service"), dict)
                        else src.get("service", "")
                    ) or src.get("kubernetes", {}).get("container", {}).get("name", "")
                      or src.get("kubernetes", {}).get("labels", {}).get("app", ""),
                    "trace_id": src.get("trace_id", src.get("traceId", "")),
                    "stack_trace": src.get("stack_trace", src.get("stackTrace", "")),
                }
                logs.append(log_entry)
                self._raw_logs.append(log_entry)

            self.add_breadcrumb(
                action=f"searched_elasticsearch_{level_filter}",
                source_type="log",
                source_reference=f"{index}, query: {query}",
                raw_evidence=f"Found {len(hits)} {level_filter} log entries",
            )

            # Return summary to keep within context limits
            summary = {
                "total": len(hits),
                "logs": logs[:50],  # First 50 for LLM analysis
                "truncated": len(hits) > 50,
            }
            return json.dumps(summary, default=str)

        except requests.exceptions.ConnectionError:
            return json.dumps({"error": f"Cannot connect to Elasticsearch at {self.es_url}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    async def _search_by_trace_id(self, params: dict) -> str:
        """Search for all logs associated with a trace ID."""
        index = params.get("index", "app-logs-*")
        trace_id = params["trace_id"]
        size = params.get("size", 100)

        es_query = {
            "size": size,
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
                headers=self._es_headers,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            hits = data.get("hits", {}).get("hits", [])

            if not hits:
                self.add_negative_finding(
                    what_was_checked=f"Logs for trace_id '{trace_id}' in {index}",
                    result="Zero results found",
                    implication="No logs found for this trace ID — may use a different correlation field",
                    source_reference=f"{index}, trace_id: {trace_id}",
                )
                return json.dumps({"total": 0, "logs": []})

            logs = []
            for hit in hits:
                src = hit.get("_source", {})
                log_entry = {
                    "id": hit.get("_id", ""),
                    "index": hit.get("_index", ""),
                    "timestamp": src.get("@timestamp", ""),
                    "level": src.get("level", ""),
                    "message": src.get("message", ""),
                    "service": src.get("service", ""),
                }
                logs.append(log_entry)

            self.add_breadcrumb(
                action="searched_by_trace_id",
                source_type="log",
                source_reference=f"{index}, trace_id: {trace_id}",
                raw_evidence=f"Found {len(hits)} logs for trace_id {trace_id}",
            )

            return json.dumps({"total": len(hits), "logs": logs}, default=str)

        except Exception as e:
            return json.dumps({"error": str(e)})

    async def _get_log_context(self, params: dict) -> str:
        """Get surrounding logs for context."""
        index = params.get("index", "app-logs-*")
        timestamp = params["timestamp"]
        service = params["service"]
        minutes_before = params.get("minutes_before", 5)
        minutes_after = params.get("minutes_after", 2)

        es_query = {
            "size": 50,
            "sort": [{"@timestamp": {"order": "asc"}}],
            "query": {
                "bool": {
                    "must": [
                        {"match": {"service": service}},
                    ],
                    "filter": [
                        {"range": {
                            "@timestamp": {
                                "gte": f"{timestamp}||-{minutes_before}m",
                                "lte": f"{timestamp}||+{minutes_after}m",
                            }
                        }},
                    ],
                }
            },
        }

        try:
            resp = requests.post(
                f"{self.es_url}/{index}/_search",
                json=es_query,
                headers=self._es_headers,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            hits = data.get("hits", {}).get("hits", [])

            logs = []
            for hit in hits:
                src = hit.get("_source", {})
                logs.append({
                    "timestamp": src.get("@timestamp", ""),
                    "level": src.get("level", ""),
                    "message": src.get("message", ""),
                })

            self.add_breadcrumb(
                action="get_log_context",
                source_type="log",
                source_reference=f"{index}, service: {service}, around {timestamp}",
                raw_evidence=f"Retrieved {len(logs)} context logs",
            )

            return json.dumps({"total": len(logs), "logs": logs}, default=str)

        except Exception as e:
            return json.dumps({"error": str(e)})

    def _analyze_patterns_tool(self) -> str:
        """Group collected raw logs into error patterns."""
        if not self._raw_logs:
            return json.dumps({"patterns": [], "message": "No logs collected yet. Search first."})

        self._patterns = self._parse_patterns_from_logs(self._raw_logs)

        self.add_breadcrumb(
            action="analyzed_patterns",
            source_type="log",
            source_reference="in-memory log collection",
            raw_evidence=f"Grouped {len(self._raw_logs)} logs into {len(self._patterns)} patterns",
        )

        return json.dumps({
            "total_logs": len(self._raw_logs),
            "patterns_found": len(self._patterns),
            "patterns": self._patterns,
        }, default=str)

    async def _list_available_indices(self, params: dict) -> str:
        """List Elasticsearch indices matching a pattern."""
        pattern = params.get("pattern", "*")
        try:
            resp = requests.get(
                f"{self.es_url}/_cat/indices/{pattern}",
                params={"format": "json", "h": "index,docs.count,store.size,health,status"},
                headers=self._es_headers,
                timeout=15,
            )
            resp.raise_for_status()
            indices = resp.json()

            # Filter out system indices
            visible = [idx for idx in indices if not idx.get("index", "").startswith(".")]

            self.add_breadcrumb(
                action="list_available_indices",
                source_type="log",
                source_reference=f"Elasticsearch at {self.es_url}",
                raw_evidence=f"Found {len(visible)} indices matching '{pattern}'",
            )

            return json.dumps({
                "total_indices": len(visible),
                "indices": visible[:50],
            })

        except requests.exceptions.ConnectionError:
            return json.dumps({"error": f"Cannot connect to Elasticsearch at {self.es_url}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    # --- Pattern detection ---

    def _parse_patterns_from_logs(self, logs: list[dict]) -> list[dict]:
        """Group logs by exception type and similar error messages."""
        pattern_groups: dict[str, list[dict]] = defaultdict(list)

        for log in logs:
            message = log.get("message", "")
            key = self._extract_pattern_key(message)
            pattern_groups[key].append(log)

        patterns = []
        for key, group_logs in pattern_groups.items():
            exception_type = self._extract_exception_type(group_logs[0].get("message", ""))
            services = list(set(l.get("service", "unknown") for l in group_logs))
            patterns.append({
                "pattern_key": key,
                "exception_type": exception_type,
                "error_message": group_logs[0].get("message", "")[:200],
                "frequency": len(group_logs),
                "affected_components": services,
                "sample_log": group_logs[0],
            })

        # Sort by frequency descending
        patterns.sort(key=lambda p: p["frequency"], reverse=True)
        return patterns

    def _extract_pattern_key(self, message: str) -> str:
        """Extract a fingerprint from a log message for grouping."""
        # Remove timestamps, IDs, numbers
        normalized = re.sub(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.\d]*[Z]?', '<TIMESTAMP>', message)
        normalized = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '<UUID>', normalized)
        normalized = re.sub(r'\b\d+\b', '<NUM>', normalized)
        # Extract exception type if present
        exc_match = re.search(r'([A-Z][a-zA-Z]*(?:Exception|Error|Timeout|Failure))', message)
        if exc_match:
            return exc_match.group(1)
        return hashlib.md5(normalized.encode()).hexdigest()[:12]

    def _extract_exception_type(self, message: str) -> str:
        """Extract the exception class name from a log message."""
        exc_match = re.search(r'([A-Z][a-zA-Z]*(?:Exception|Error|Timeout|Failure))', message)
        if exc_match:
            return exc_match.group(1)
        # Fall back to first meaningful word
        if "timeout" in message.lower():
            return "Timeout"
        if "connection" in message.lower():
            return "ConnectionError"
        return "UnknownError"
