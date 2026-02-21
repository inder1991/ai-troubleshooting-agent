import json
import re
import hashlib
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import requests

from src.models.schemas import (
    ErrorPattern, LogEvidence, LogAnalysisResult,
    NegativeFinding, Breadcrumb, TokenUsage, EvidencePin
)
from src.utils.llm_client import AnthropicClient
from src.utils.event_emitter import EventEmitter
from src.utils.logger import get_logger

import os

logger = get_logger(__name__)


class LogAnalysisAgent:
    """Hybrid log agent: deterministic collection + single LLM analysis call."""

    def __init__(self, connection_config=None):
        self.agent_name = "log_agent"
        self._connection_config = connection_config
        # Resolve Elasticsearch URL from config, falling back to env var
        if connection_config and connection_config.elasticsearch_url:
            self.es_url = connection_config.elasticsearch_url
        else:
            self.es_url = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
        self._es_headers = self._build_es_headers(connection_config)
        self._verify_ssl = getattr(connection_config, "verify_ssl", False) if connection_config else False
        self.llm_client = AnthropicClient(agent_name="log_agent")
        self.breadcrumbs: list[Breadcrumb] = []
        self.negative_findings: list[NegativeFinding] = []
        self.evidence_pins: list[EvidencePin] = []
        self._raw_logs: list[dict] = []
        self._patterns: list[dict] = []
        self._service_flow: list[dict] = []
        self._event_emitter: EventEmitter | None = None

    def _build_es_headers(self, connection_config) -> dict:
        """Build HTTP headers for Elasticsearch requests, including auth."""
        headers = {"Content-Type": "application/json"}
        if not connection_config:
            logger.warning("No connection_config passed to log_agent — ES requests will be unauthenticated")
            return headers
        auth_method = getattr(connection_config, "elasticsearch_auth_method", "none")
        credentials = getattr(connection_config, "elasticsearch_credentials", "")
        logger.info("ES auth config", extra={
            "agent_name": self.agent_name,
            "action": "es_auth_resolve",
            "extra": {
                "auth_method": auth_method,
                "has_credentials": bool(credentials),
                "es_url": getattr(connection_config, "elasticsearch_url", ""),
            },
        })
        if auth_method in ("token", "bearer_token", "api_token") and credentials:
            headers["Authorization"] = f"Bearer {credentials}"
        elif auth_method == "api_key" and credentials:
            headers["Authorization"] = f"ApiKey {credentials}"
        elif auth_method in ("basic", "basic_auth") and credentials:
            import base64
            headers["Authorization"] = f"Basic {base64.b64encode(credentials.encode()).decode()}"
        return headers

    async def run(self, context: dict, event_emitter: EventEmitter | None = None) -> dict:
        """Two-phase hybrid execution."""
        service_name = context.get("service_name", "unknown")
        logger.info("Starting log analysis", extra={"agent_name": self.agent_name, "action": "start", "extra": service_name})

        self._event_emitter = event_emitter

        if event_emitter:
            await event_emitter.emit(self.agent_name, "started", "log_agent starting analysis")

        # Phase 1: Deterministic collection
        collection = await self._collect(context, event_emitter)

        # Phase 2: Single LLM analysis call
        analysis = await self._analyze_with_llm(collection, context, event_emitter)

        if event_emitter:
            await event_emitter.emit(self.agent_name, "success", "log_agent completed analysis")

        result = self._build_result(collection, analysis)
        logger.info("Log analysis complete", extra={"agent_name": self.agent_name, "action": "complete", "extra": {"patterns": len(self._patterns), "raw_logs": len(self._raw_logs), "confidence": analysis.get("overall_confidence", 0)}})
        return result

    def get_token_usage(self) -> TokenUsage:
        return self.llm_client.get_total_usage()

    # ─── Helpers for evidence tracking ─────────────────────────────────────

    def add_breadcrumb(
        self, action: str, source_type: str, source_reference: str, raw_evidence: str
    ) -> None:
        self.breadcrumbs.append(
            Breadcrumb(
                agent_name=self.agent_name,
                action=action,
                source_type=source_type,
                source_reference=source_reference,
                raw_evidence=raw_evidence,
                timestamp=datetime.now(timezone.utc),
            )
        )

    def add_negative_finding(
        self, what_was_checked: str, result: str, implication: str, source_reference: str
    ) -> None:
        self.negative_findings.append(
            NegativeFinding(
                agent_name=self.agent_name,
                what_was_checked=what_was_checked,
                result=result,
                implication=implication,
                source_reference=source_reference,
            )
        )

    # ─── Phase 1: Deterministic Collection ─────────────────────────────────

    async def _collect(self, context: dict, event_emitter: EventEmitter | None) -> dict:
        """Run a fixed sequence of ES queries — no LLM involved."""

        # Step 1: Resolve index
        if event_emitter:
            await event_emitter.emit(
                self.agent_name, "tool_call",
                "Discovering available ES indices...",
                details={"tool": "list_available_indices"},
            )
        index, indices_found = await self._resolve_index(context, event_emitter)

        # Step 2: Search ERROR logs
        if event_emitter:
            await event_emitter.emit(
                self.agent_name, "tool_call",
                f"Searching '{index}' for ERROR logs...",
                details={"tool": "search_elasticsearch", "index": index},
            )

        service = context.get("service_name", "*")
        timeframe = context.get("timeframe", "now-1h")
        logs = await self._search_elasticsearch({
            "index": index,
            "query": service,
            "time_range": timeframe,
            "size": 200,
            "level_filter": "ERROR",
        })

        # Step 3: Broaden if no results
        if not self._raw_logs:
            if event_emitter:
                await event_emitter.emit(
                    self.agent_name, "tool_call",
                    f"No ERROR logs found, broadening to WARN in '{index}'...",
                    details={"tool": "search_elasticsearch", "index": index},
                )
            logs = await self._search_elasticsearch({
                "index": index,
                "query": service,
                "time_range": timeframe,
                "size": 200,
                "level_filter": "WARN",
            })

        if not self._raw_logs:
            if event_emitter:
                await event_emitter.emit(
                    self.agent_name, "tool_call",
                    f"No WARN logs found, searching all levels in '{index}'...",
                    details={"tool": "search_elasticsearch", "index": index},
                )
            logs = await self._search_elasticsearch({
                "index": index,
                "query": service,
                "time_range": timeframe,
                "size": 200,
                "level_filter": "",
            })

        # Step 4: Group into patterns
        if self._raw_logs:
            if event_emitter:
                await event_emitter.emit(
                    self.agent_name, "tool_call",
                    "Grouping logs into error patterns...",
                    details={"tool": "analyze_patterns"},
                )
            self._patterns = self._parse_patterns_from_logs(self._raw_logs)
            logger.info("Patterns grouped", extra={"agent_name": self.agent_name, "action": "patterns_grouped", "extra": {"pattern_count": len(self._patterns), "total_logs": len(self._raw_logs)}})
            self.add_breadcrumb(
                action="analyzed_patterns",
                source_type="log",
                source_reference="in-memory log collection",
                raw_evidence=f"Grouped {len(self._raw_logs)} logs into {len(self._patterns)} patterns",
            )

        # Step 4b: Collect error breadcrumbs for critical/high patterns
        error_breadcrumbs: dict[str, list[dict]] = {}
        if self._patterns:
            error_breadcrumbs = await self._collect_error_breadcrumbs(self._patterns, index)

        # Step 5: Search by trace_id for flow reconstruction
        trace_id = context.get("trace_id")
        service_flow: list[dict] = []
        if trace_id:
            if event_emitter:
                await event_emitter.emit(
                    self.agent_name, "tool_call",
                    f"Reconstructing service flow from trace {trace_id}...",
                    details={"tool": "search_by_trace_id"},
                )
            trace_result = await self._search_by_trace_id({
                "index": index,
                "trace_id": trace_id,
                "size": 100,
            })
            try:
                trace_data = json.loads(trace_result)
                trace_logs = trace_data.get("logs", [])
                if trace_logs:
                    service_flow = self._reconstruct_service_flow(trace_logs)
                    self._service_flow = service_flow
                    services = list(dict.fromkeys(s["service"] for s in service_flow))
                    logger.info("Service flow reconstructed", extra={"agent_name": self.agent_name, "action": "flow_reconstructed", "extra": {"steps": len(service_flow), "services": services}})
            except (json.JSONDecodeError, AttributeError):
                pass

        # Step 6: Get log context around first error
        context_logs: list[dict] = []
        if self._patterns:
            first_pattern = self._patterns[0]
            sample = first_pattern.get("sample_log", {})
            ts = sample.get("timestamp")
            svc = sample.get("service") or service
            if ts and svc:
                ctx_result = await self._get_log_context({
                    "index": index,
                    "timestamp": ts,
                    "service": svc,
                    "minutes_before": 5,
                    "minutes_after": 2,
                })
                try:
                    ctx_data = json.loads(ctx_result)
                    context_logs = ctx_data.get("logs", [])
                except (json.JSONDecodeError, AttributeError):
                    pass

        # Derive stats from collected data
        error_count = sum(1 for l in self._raw_logs if (l.get("level") or "").upper() in ("ERROR", "FATAL", "CRITICAL"))
        warn_count = sum(1 for l in self._raw_logs if (l.get("level") or "").upper() in ("WARN", "WARNING"))
        pattern_count = len(self._patterns)

        # Infer service dependencies from patterns and flow
        target_service = context.get("service_name", "")
        inferred_dependencies = self._infer_service_dependencies(self._patterns, service_flow, target_service=target_service)

        # Build cross-service correlations
        cross_service_correlations = self._build_cross_service_correlations(self._raw_logs)

        return {
            "indices_found": indices_found,
            "index_used": index,
            "raw_logs": self._raw_logs,
            "patterns": self._patterns,
            "service_flow": service_flow,
            "context_logs": context_logs,
            "inferred_dependencies": inferred_dependencies,
            "error_breadcrumbs": error_breadcrumbs,
            "cross_service_correlations": cross_service_correlations,
            "stats": {
                "total_logs": len(self._raw_logs),
                "error_count": error_count,
                "warn_count": warn_count,
                "pattern_count": pattern_count,
                "unique_services": len(set(l.get("service", "unknown") for l in self._raw_logs)),
            },
        }

    async def _resolve_index(self, context: dict, event_emitter: EventEmitter | None) -> tuple[str, list[dict]]:
        """Determine which ES index to use."""
        user_index = (context.get("elk_index") or "").strip()
        all_indices: list[dict] = []

        if user_index and user_index != "*":
            # User provided an index — verify it exists
            exists = await self._check_index_exists(user_index)
            if exists:
                logger.info("Index resolved", extra={"agent_name": self.agent_name, "action": "index_resolved", "extra": {"index": user_index, "method": "user_provided"}})
                return user_index, []

            # Try as pattern
            result_str = await self._list_available_indices({"pattern": user_index + "*"})
            try:
                data = json.loads(result_str)
                indices = data.get("indices", [])
                if indices:
                    return indices[0]["index"], indices
            except (json.JSONDecodeError, KeyError):
                pass

        # Discovery: list all indices
        result_str = await self._list_available_indices({"pattern": "*"})
        try:
            data = json.loads(result_str)
            all_indices = data.get("indices", [])
        except (json.JSONDecodeError, AttributeError):
            pass

        if not all_indices:
            return user_index if user_index else "*", []

        service = context.get("service_name", "")
        best = self._pick_best_index(all_indices, service)
        chosen = best or "*"
        logger.info("Index resolved", extra={"agent_name": self.agent_name, "action": "index_resolved", "extra": {"index": chosen, "method": "discovered"}})
        return chosen, all_indices

    def _pick_best_index(self, indices: list[dict], service: str) -> str | None:
        """Score indices by relevance and return the best one."""
        if not indices:
            return None

        scored: list[tuple[int, str]] = []
        service_lower = service.lower()

        for idx in indices:
            name = idx.get("index", "")
            score = 0
            # Name contains service
            if service_lower and service_lower in name.lower():
                score += 10
            # Common log index patterns
            for keyword in ("log", "filebeat", "logstash", "app"):
                if keyword in name.lower():
                    score += 3
            # Has documents
            try:
                doc_count = int(idx.get("docs.count", 0))
                if doc_count > 0:
                    score += 2
            except (ValueError, TypeError):
                pass
            scored.append((score, name))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1] if scored else None

    async def _check_index_exists(self, index: str) -> bool:
        """Check if an index exists in Elasticsearch."""
        try:
            resp = requests.head(
                f"{self.es_url}/{index}",
                headers=self._es_headers,
                timeout=10,
                verify=self._verify_ssl,
            )
            return resp.status_code == 200
        except Exception:
            return False

    # ─── Flow Reconstruction (NEW) ─────────────────────────────────────────

    def _reconstruct_service_flow(self, trace_logs: list[dict]) -> list[dict]:
        """Build temporal flow from trace-correlated logs."""
        sorted_logs = sorted(trace_logs, key=lambda l: l.get("timestamp", ""))

        flow_steps = []
        seen_services: set[str] = set()

        for log in sorted_logs:
            service = log.get("service", "unknown") or "unknown"
            level = (log.get("level") or "INFO").upper()
            message = log.get("message", "")

            if level in ("ERROR", "FATAL", "CRITICAL"):
                status = "error"
            elif "timeout" in message.lower():
                status = "timeout"
            else:
                status = "ok"

            is_new = service not in seen_services
            seen_services.add(service)

            flow_steps.append({
                "service": service,
                "timestamp": log.get("timestamp", ""),
                "operation": self._extract_operation(message),
                "status": status,
                "status_detail": self._extract_status_detail(message, level),
                "message": message[:200],
                "is_new_service": is_new,
            })

        return flow_steps

    def _extract_operation(self, message: str) -> str:
        """Extract operation name from log message."""
        http_match = re.search(r'(GET|POST|PUT|DELETE|PATCH)\s+(/\S+)', message)
        if http_match:
            return f"{http_match.group(1)} {http_match.group(2)[:50]}"
        func_match = re.search(r'(?:calling|invoking|executing)\s+(\S+)', message, re.IGNORECASE)
        if func_match:
            return func_match.group(1)[:50]
        return message[:40]

    def _extract_status_detail(self, message: str, level: str) -> str:
        """Extract a short status detail like '200 OK' or 'NullPointerException'."""
        status_match = re.search(r'\b(\d{3})\s+([\w\s]+?)(?:\s|$|,)', message)
        if status_match:
            return f"{status_match.group(1)} {status_match.group(2).strip()}"
        if level in ("ERROR", "FATAL"):
            exc = self._extract_exception_type(message)
            return exc if exc != "UnknownError" else "Error"
        return "OK"

    # ─── Phase 2: Single LLM Analysis ──────────────────────────────────────

    SYSTEM_PROMPT = """You are a Senior SRE Incident Commander analyzing a production incident.

Your role:
1. Identify the ROOT CAUSE — not just symptoms. Trace the causal chain.
2. Identify PATIENT ZERO — the first service/component where the failure originated.
3. Map SERVICE DEPENDENCIES — which services are affected and in what order.
4. Provide REASONING CHAIN — step-by-step analytical thinking.
5. Suggest PROMQL QUERIES — specific Prometheus queries to validate the hypothesis.

Analysis framework:
- Patterns are pre-sorted by operational severity for TRIAGE PRIORITY, but severity ordering does NOT imply causation.
- Deprecation warnings, header migration notices, and info-level noise are NOT outage causes — skip them. A high-frequency deprecation warning is P4; a single OOMKilled is P1.
- Assign incident priority (P1/P2/P3/P4) based on OPERATIONAL IMPACT and ERROR CRITICALITY, not frequency.
- Check if errors are symptoms of an upstream failure.
- Look for temporal correlation between patterns.
- Consider cascade effects: A fails → B times out → C retries → D overwhelmed.
- Distinguish between root causes and collateral damage.
- Use the Error Breadcrumbs to understand WHAT OPERATION was in progress when the error occurred.
- TEMPORAL CAUSATION CHECK: Before assigning causal_role, compare first_seen timestamps
  in the Chronological Timeline section. A pattern whose first_seen is AFTER another
  pattern's first_seen cannot be that earlier pattern's root cause. If a critical-severity
  pattern started after a high-severity one, the high-severity pattern may be the actual
  root cause cascading upward into more severe symptoms.
- For the identified Patient Zero, suggest 3 specific PromQL queries that a Metrics Agent should run to validate the hypothesis (e.g., redis_connection_pool_active_connections, container_memory_working_set_bytes).
6. CLASSIFY CAUSAL ROLE — For each error pattern, assign one of:
   - "root_cause": The primary failure that started the cascade (typically 1 pattern)
   - "cascading_failure": Downstream symptoms caused by the root cause propagating through service calls
   - "correlated_anomaly": Concurrent patterns not proven to be causally linked

Respond with JSON only. No markdown fences."""

    async def _analyze_with_llm(self, collection: dict, context: dict, event_emitter: EventEmitter | None) -> dict:
        """One LLM call with all collected data."""
        if not collection.get("patterns") and not collection.get("raw_logs"):
            return {
                "primary_pattern": {},
                "secondary_patterns": [],
                "overall_confidence": 20,
                "root_cause_hypothesis": "No log data found to analyze",
                "flow_analysis": "",
                "patient_zero": None,
                "inferred_dependencies": [],
                "reasoning_chain": [],
            }

        if event_emitter:
            await event_emitter.emit(self.agent_name, "progress", "Analyzing patterns with AI...")

        prompt = self._build_analysis_prompt(collection, context)

        response = await self.llm_client.chat(
            prompt=prompt,
            system=self.SYSTEM_PROMPT,
            max_tokens=4096,
            temperature=0.0,
        )

        analysis = self._parse_llm_response(response.text)
        logger.info("LLM analysis complete", extra={"agent_name": self.agent_name, "action": "llm_analysis", "extra": {"confidence": analysis.get("overall_confidence", 0)}, "tokens": {"input": response.input_tokens, "output": response.output_tokens}})
        return analysis

    def _build_analysis_prompt(self, collection: dict, context: dict) -> str:
        """Build focused prompt with all deterministic data."""
        service = context.get("service_name", "unknown")
        timeframe = context.get("timeframe", "now-1h")
        stats = collection.get("stats", {})

        parts = [
            f"# Incident Analysis: {service}",
            f"Time window: {timeframe}",
            f"Stats: {stats.get('total_logs', 0)} logs, {stats.get('error_count', 0)} errors, "
            f"{stats.get('warn_count', 0)} warnings, {stats.get('pattern_count', 0)} patterns, "
            f"{stats.get('unique_services', 0)} services",
            f"Index: {collection.get('index_used', 'unknown')}",
            "",
        ]

        parts.append(f"\nINVESTIGATION TARGET: The user is investigating '{service}'. "
                     f"Even if errors originate in dependent services, explain how they relate back to {service}. "
                     f"If {service} is a caller of a failing downstream service, make that relationship explicit in inferred_dependencies.")

        parts += [
            "",
            "## Error Patterns (deterministic grouping, sorted by severity then frequency)",
        ]

        for i, p in enumerate(collection.get("patterns", [])[:10]):
            parts.append(
                f"\n### P{i+1}: {p.get('exception_type', '?')} ({p.get('frequency', 0)}x)"
            )
            parts.append(f"Severity: {p.get('severity', 'medium')}")
            parts.append(f"Message: {p.get('error_message', '')[:200]}")
            parts.append(f"Services: {', '.join(p.get('affected_components', []))}")
            parts.append(f"Time range: {p.get('first_seen', '?')} → {p.get('last_seen', '?')}")
            if p.get("correlation_ids"):
                parts.append(f"Trace IDs: {', '.join(p['correlation_ids'][:3])}")
            if p.get("filtered_stack_trace"):
                parts.append(f"Stack trace (app frames only):\n{p['filtered_stack_trace']}")
            elif p.get("stack_traces"):
                parts.append(f"Stack trace (sample):\n{p['stack_traces'][0][:500]}")
            elif p.get("inline_stack_trace"):
                parts.append(f"Stack trace (extracted from message):\n{p['inline_stack_trace']}")
            if p.get("preceding_context"):
                parts.append("Preceding context (3 logs before first error):")
                for ctx_line in p["preceding_context"]:
                    parts.append(f"  {ctx_line}")

        # Chronological Timeline
        chronological = sorted(
            collection.get("patterns", [])[:10],
            key=lambda p: p.get("first_seen", "9999")
        )
        if len(chronological) > 1:
            parts.append("\n## Chronological Timeline (patterns ordered by first occurrence)")
            parts.append("NOTE: A pattern that started AFTER another cannot be its root cause.")
            all_patterns = collection.get("patterns", [])
            for p in chronological:
                sev_idx = all_patterns.index(p) + 1 if p in all_patterns else "?"
                svc_list = ", ".join(p.get("affected_components", []))
                parts.append(
                    f"  [{p.get('first_seen', '?')}] P{sev_idx}: "
                    f"{p.get('exception_type', '?')} ({p.get('severity', '?')}, "
                    f"{p.get('frequency', 0)}x) -- {svc_list}"
                )

        # Known Architecture (from configuration/prior analysis)
        known_deps = context.get("known_dependencies", [])
        if known_deps:
            parts.append("\n## Known Architecture (from configuration/prior analysis)")
            for dep in known_deps[:20]:
                rel = dep.get("relationship", dep.get("evidence", "calls"))
                parts.append(f"  {dep.get('source', '?')} -> {dep.get('target', '?')} ({rel})")

        # Architecture Map
        parts.append("\n## Architecture Map")
        parts.append(f"Service under investigation: {service}")
        svc_counts: dict[str, int] = defaultdict(int)
        for log in collection.get("raw_logs", []):
            svc_counts[log.get("service", "unknown")] += 1
        if svc_counts:
            parts.append("Services observed in logs (with log counts):")
            for svc_name, count in sorted(svc_counts.items(), key=lambda x: -x[1]):
                parts.append(f"  - {svc_name}: {count} log entries")

        # Cross-Service Correlation
        correlations = collection.get("cross_service_correlations", [])
        if correlations:
            parts.append("\n## Cross-Service Correlation")
            for corr in correlations[:5]:
                chain = " -> ".join(corr["services"])
                error_part = ""
                if corr.get("error_service") and corr.get("error_type"):
                    error_part = f" (FAILED in {corr['error_service']}: {corr['error_type']})"
                parts.append(f"  Trace '{corr['trace_id'][:20]}...': {chain}{error_part}")

        # Service flow
        flow = collection.get("service_flow", [])
        if flow:
            parts.append("\n## Service Flow (temporal reconstruction)")
            for step in flow[:20]:
                parts.append(
                    f"  [{step.get('timestamp', '')}] {step.get('service', '?')} — "
                    f"{step.get('operation', '?')} — {step.get('status', '?')} "
                    f"({step.get('status_detail', '')})"
                )

        # Inferred dependencies
        deps = collection.get("inferred_dependencies", [])
        if deps:
            parts.append("\n## Inferred Dependencies (from log analysis)")
            for d in deps:
                parts.append(f"  {d['source']} -> {', '.join(d['targets'])}")

        # Error Breadcrumbs
        error_breadcrumbs = collection.get("error_breadcrumbs", {})
        if error_breadcrumbs:
            parts.append("\n## Error Breadcrumbs (logs preceding each critical/high error)")
            for pattern_key, crumbs in error_breadcrumbs.items():
                pattern_label = pattern_key
                for p in collection.get("patterns", []):
                    if p.get("pattern_key") == pattern_key:
                        pattern_label = f"{p['exception_type']} ({p['frequency']}x)"
                        break
                parts.append(f"\n### Breadcrumbs for {pattern_label}:")
                for cl in crumbs[-10:]:
                    parts.append(
                        f"  [{cl.get('timestamp', '')}] {cl.get('level', '')} "
                        f"[{cl.get('service', '?')}] {cl.get('message', '')[:120]}"
                    )

        # Context logs
        ctx_logs = collection.get("context_logs", [])
        if ctx_logs:
            parts.append("\n## Context Logs (around first error)")
            for cl in ctx_logs[:15]:
                parts.append(f"  [{cl.get('timestamp', '')}] {cl.get('level', '')} {cl.get('message', '')[:120]}")

        # Inferred Impact
        parts.append("\n## Inferred Impact")
        affected_services = set()
        for p in collection.get("patterns", []):
            affected_services.update(p.get("affected_components", []))
        parts.append(f"Affected services: {', '.join(sorted(affected_services)) if affected_services else 'unknown'}")
        if deps:
            downstream = set()
            for d in deps:
                downstream.update(d["targets"])
            if downstream:
                parts.append(f"Downstream impact: {', '.join(sorted(downstream))}")

        # Business Impact (if available from context)
        business_impact = context.get("business_impact", [])
        if business_impact:
            parts.append("\n## Business Impact")
            for cap in business_impact:
                parts.append(
                    f"  - {cap['capability']}: Risk={cap['risk_level'].upper()}, "
                    f"Services: {', '.join(cap['affected_services'])}"
                )

        parts.append("")
        parts.append("""Analyze and respond with JSON:
{
    "primary_pattern": {
        "pattern_id": "p1",
        "exception_type": "...",
        "error_message": "...",
        "frequency": 47,
        "severity": "critical|high|medium|low",
        "affected_components": ["..."],
        "confidence_score": 87,
        "priority_rank": 1,
        "priority_reasoning": "Why this is the top priority",
        "causal_role": "root_cause|cascading_failure|correlated_anomaly (validate against first_seen timestamps)"
    },
    "secondary_patterns": [{"...same fields as primary_pattern incl causal_role..."}],
    "overall_confidence": 85,
    "root_cause_hypothesis": "One-paragraph root cause explanation",
    "flow_analysis": "How the failure propagated across services",
    "patient_zero": {
        "service": "service-name",
        "evidence": "Why this service is the origin",
        "first_error_time": "ISO timestamp"
    },
    "inferred_dependencies": [
        {"source": "svc-a", "target": "svc-b", "evidence": "why"}
    ],
    "reasoning_chain": [
        {"step": 1, "observation": "what was observed", "inference": "what it means"},
        {"step": 2, "observation": "...", "inference": "..."}
    ],
    "suggested_promql_queries": [
        {"metric": "...", "query": "PromQL query string", "rationale": "Why this validates the hypothesis"}
    ]
}""")

        return "\n".join(parts)

    def _parse_llm_response(self, text: str) -> dict:
        """Parse LLM's JSON response."""
        try:
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(text)
        except (json.JSONDecodeError, AttributeError):
            return {
                "primary_pattern": {},
                "secondary_patterns": [],
                "overall_confidence": 30,
                "root_cause_hypothesis": "Failed to parse LLM response",
                "flow_analysis": "",
                "patient_zero": None,
                "inferred_dependencies": [],
                "reasoning_chain": [],
                "suggested_promql_queries": [],
            }

        return {
            "primary_pattern": data.get("primary_pattern", {}),
            "secondary_patterns": data.get("secondary_patterns", []),
            "overall_confidence": data.get("overall_confidence", 50),
            "root_cause_hypothesis": data.get("root_cause_hypothesis", ""),
            "flow_analysis": data.get("flow_analysis", ""),
            "patient_zero": data.get("patient_zero", None),
            "inferred_dependencies": data.get("inferred_dependencies", []),
            "reasoning_chain": data.get("reasoning_chain", []),
            "suggested_promql_queries": data.get("suggested_promql_queries", []),
        }

    # ─── Build Result ──────────────────────────────────────────────────────

    @staticmethod
    def _find_det_pattern(llm_pattern: dict, det_patterns: list[dict]) -> dict | None:
        """Match an LLM pattern to a deterministic pattern by pattern_id or exception_type."""
        # Try pattern_id -> index (e.g., "p1" -> patterns[0])
        pid = llm_pattern.get("pattern_id", "")
        if pid and pid.startswith("p"):
            try:
                idx = int(pid[1:]) - 1
                if 0 <= idx < len(det_patterns):
                    return det_patterns[idx]
            except ValueError:
                pass
        # Fallback to exception_type match
        exc = llm_pattern.get("exception_type", "")
        for p in det_patterns:
            if p.get("exception_type") == exc:
                return p
        return None

    def _build_result(self, collection: dict, analysis: dict) -> dict:
        """Combine deterministic data + LLM analysis into output format."""
        det_patterns = collection.get("patterns", [])

        # Merge deterministic pattern data into LLM primary pattern
        primary = analysis.get("primary_pattern", {})
        if primary and "causal_role" not in primary:
            primary["causal_role"] = "root_cause"
        if primary and det_patterns:
            det_match = self._find_det_pattern(primary, det_patterns)
            if det_match:
                primary.setdefault("first_seen", det_match.get("first_seen", ""))
                primary.setdefault("last_seen", det_match.get("last_seen", ""))
                primary["stack_traces"] = det_match.get("stack_traces", [])
                primary["correlation_ids"] = det_match.get("correlation_ids", [])
                primary["sample_log_ids"] = det_match.get("sample_log_ids", [])

        # Same for secondary patterns — match by exception_type instead of positional index
        for sp in analysis.get("secondary_patterns", []):
            det_match = self._find_det_pattern(sp, det_patterns)
            if det_match:
                sp.setdefault("first_seen", det_match.get("first_seen", ""))
                sp.setdefault("last_seen", det_match.get("last_seen", ""))
                sp["stack_traces"] = det_match.get("stack_traces", [])
                sp["correlation_ids"] = det_match.get("correlation_ids", [])
                sp["sample_log_ids"] = det_match.get("sample_log_ids", [])

        # Merge dependency sources: deterministic + LLM
        det_deps = collection.get("inferred_dependencies", [])
        llm_deps = analysis.get("inferred_dependencies", [])

        return {
            "primary_pattern": primary,
            "secondary_patterns": analysis.get("secondary_patterns", []),
            "overall_confidence": analysis.get("overall_confidence", 50),
            "root_cause_hypothesis": analysis.get("root_cause_hypothesis", ""),
            "flow_analysis": analysis.get("flow_analysis", ""),
            "patient_zero": analysis.get("patient_zero", None),
            "inferred_dependencies": det_deps + llm_deps,
            "reasoning_chain": analysis.get("reasoning_chain", []),
            "suggested_promql_queries": analysis.get("suggested_promql_queries", []),
            "breadcrumbs": [b.model_dump(mode="json") for b in self.breadcrumbs],
            "negative_findings": [n.model_dump(mode="json") for n in self.negative_findings],
            "tokens_used": self.get_token_usage().model_dump(),
            "raw_logs_count": len(self._raw_logs),
            "patterns_found": len(self._patterns),
            "evidence_pins": [p.model_dump(mode="json") for p in self.evidence_pins],
            "service_flow": collection.get("service_flow", []),
            "flow_source": "elasticsearch",
            "flow_confidence": 70 if collection.get("service_flow") else 0,
        }

    # ─── ES Tool Implementations (reused from original) ────────────────────

    async def _search_elasticsearch(self, params: dict) -> str:
        """Query Elasticsearch and return matching logs."""
        index = params.get("index", "app-logs-*")
        query = params.get("query", "*")
        time_range = params.get("time_range", "now-1h")
        size = params.get("size", 200)
        level_filter = params.get("level_filter", "ERROR")

        es_query: dict[str, Any] = {
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
                verify=self._verify_ssl,
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

            logger.info("ES search complete", extra={"agent_name": self.agent_name, "action": "es_search", "extra": {"index": index, "hits": len(hits), "level_filter": level_filter}})

            summary = {
                "total": len(hits),
                "logs": logs[:50],
                "truncated": len(hits) > 50,
            }
            return json.dumps(summary, default=str)

        except requests.exceptions.ConnectionError:
            logger.warning("ES connection failed", extra={"agent_name": self.agent_name, "action": "es_error", "extra": f"Cannot connect to {self.es_url}"})
            if self._event_emitter:
                await self._event_emitter.emit(
                    self.agent_name, "warning",
                    f"Cannot connect to Elasticsearch at {self.es_url}",
                )
            return json.dumps({"error": f"Cannot connect to Elasticsearch at {self.es_url}"})
        except Exception as e:
            logger.error("ES search failed", extra={"agent_name": self.agent_name, "action": "es_error", "extra": str(e)})
            if self._event_emitter:
                await self._event_emitter.emit(
                    self.agent_name, "error",
                    f"Elasticsearch query failed: {e}",
                )
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
                verify=self._verify_ssl,
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
                verify=self._verify_ssl,
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

    async def _list_available_indices(self, params: dict) -> str:
        """List Elasticsearch indices matching a pattern."""
        pattern = params.get("pattern", "*")
        try:
            resp = requests.get(
                f"{self.es_url}/_cat/indices/{pattern}",
                params={"format": "json", "h": "index,docs.count,store.size,health,status"},
                headers=self._es_headers,
                timeout=15,
                verify=self._verify_ssl,
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
            logger.warning("ES connection failed", extra={"agent_name": self.agent_name, "action": "es_error", "extra": f"Cannot connect to {self.es_url}"})
            if self._event_emitter:
                await self._event_emitter.emit(
                    self.agent_name, "warning",
                    f"Cannot connect to Elasticsearch at {self.es_url}",
                )
            return json.dumps({"error": f"Cannot connect to Elasticsearch at {self.es_url}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ─── Pattern Detection (unchanged) ─────────────────────────────────────

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

            # Collect timestamps for first_seen/last_seen
            timestamps = sorted(l.get("timestamp", "") for l in group_logs if l.get("timestamp"))

            # Collect unique stack traces (deduplicated, max 3)
            stack_traces = []
            seen_stacks: set[str] = set()
            for l in group_logs:
                st = l.get("stack_trace", "")
                if st and st not in seen_stacks:
                    seen_stacks.add(st)
                    stack_traces.append(st[:2000])
                    if len(stack_traces) >= 3:
                        break

            # Collect unique correlation/trace IDs
            correlation_ids = list(set(
                l.get("trace_id", "") for l in group_logs if l.get("trace_id")
            ))[:10]

            # Sample log IDs for linking back
            sample_log_ids = [l.get("id", "") for l in group_logs[:5] if l.get("id")]

            # Collect 3 log lines immediately preceding the first error in this pattern group
            sorted_group = sorted(group_logs, key=lambda l: l.get("timestamp", ""))
            preceding_context = []
            first_error_idx = next(
                (i for i, l in enumerate(sorted_group)
                 if (l.get("level") or "").upper() in ("ERROR", "FATAL", "CRITICAL")),
                None
            )
            if first_error_idx is not None and first_error_idx > 0:
                start = max(0, first_error_idx - 3)
                for ctx_log in sorted_group[start:first_error_idx]:
                    preceding_context.append(
                        f"[{ctx_log.get('level', '?')}] {ctx_log.get('message', '')[:150]}"
                    )

            patterns.append({
                "pattern_key": key,
                "exception_type": exception_type,
                "error_message": group_logs[0].get("message", "")[:200],
                "frequency": len(group_logs),
                "affected_components": services,
                "sample_log": group_logs[0],
                # Enrichment fields
                "first_seen": timestamps[0] if timestamps else "",
                "last_seen": timestamps[-1] if timestamps else "",
                "stack_traces": stack_traces,
                "filtered_stack_trace": self._filter_stack_trace(stack_traces[0]) if stack_traces else "",
                "correlation_ids": correlation_ids,
                "sample_log_ids": sample_log_ids,
                "preceding_context": preceding_context,
            })

            # Inline stack trace extraction fallback
            if not stack_traces:
                for l in group_logs[:5]:
                    inline = self._extract_inline_stack_trace(l.get("message", ""))
                    if inline:
                        patterns[-1]["inline_stack_trace"] = self._filter_stack_trace(inline)
                        break

        # Classify severity for each pattern
        for p in patterns:
            p["severity"] = self._classify_pattern_severity(p["exception_type"], p["error_message"])

        # Sort by severity rank (critical first), then frequency descending within same rank
        patterns.sort(key=lambda p: (self.SEVERITY_RANK.get(p["severity"], 2), -p["frequency"]))
        return patterns

    def _build_cross_service_correlations(self, raw_logs: list[dict]) -> list[dict]:
        """Identify traces that span multiple services, annotating where errors occur."""
        trace_info: dict[str, dict] = defaultdict(
            lambda: {"services": set(), "error_service": None, "error_type": None}
        )
        for log in raw_logs:
            tid = log.get("trace_id", "")
            if not tid:
                continue
            trace_info[tid]["services"].add(log.get("service", "unknown"))
            if (log.get("level") or "").upper() in ("ERROR", "FATAL", "CRITICAL"):
                trace_info[tid]["error_service"] = log.get("service", "unknown")
                trace_info[tid]["error_type"] = self._extract_exception_type(log.get("message", ""))
        return [
            {"trace_id": tid, "services": sorted(info["services"]),
             "error_service": info["error_service"], "error_type": info["error_type"]}
            for tid, info in trace_info.items() if len(info["services"]) >= 2
        ][:10]

    def _infer_service_dependencies(self, patterns: list[dict], service_flow: list[dict], target_service: str = "") -> list[dict]:
        """Infer service dependencies from error patterns and service flow."""
        deps: dict[str, set[str]] = defaultdict(set)

        # From patterns: if service A mentions service B in error messages
        all_services: set[str] = set()
        for p in patterns:
            all_services.update(p.get("affected_components", []))

        for p in patterns:
            msg = p.get("error_message", "").lower()
            for svc in all_services:
                svc_lower = svc.lower()
                pattern_services = [s.lower() for s in p.get("affected_components", [])]
                if svc_lower in msg and svc_lower not in pattern_services:
                    for caller in p.get("affected_components", []):
                        deps[caller].add(svc)

        # From service flow: sequential calls imply dependency
        for i in range(len(service_flow) - 1):
            src = service_flow[i].get("service", "")
            dst = service_flow[i + 1].get("service", "")
            if src and dst and src != dst:
                deps[src].add(dst)

        # Ensure target_service appears in the dependency chain
        if target_service:
            target_lower = target_service.lower()
            pattern_services = set()
            for p in patterns:
                pattern_services.update(s.lower() for s in p.get("affected_components", []))

            if target_lower not in pattern_services:
                # Target service is the caller — it depends on the error-producing services
                for svc in all_services:
                    if svc.lower() != target_lower:
                        deps[target_service].add(svc)
            else:
                # Target service IS in the patterns — add edges to services mentioned in its errors
                for p in patterns:
                    msg = p.get("error_message", "").lower()
                    if target_lower in [s.lower() for s in p.get("affected_components", [])]:
                        for svc in all_services:
                            if svc.lower() != target_lower and svc.lower() in msg:
                                deps[target_service].add(svc)

        return [
            {"source": src, "targets": sorted(targets)}
            for src, targets in deps.items()
        ]

    async def _collect_error_breadcrumbs(
        self, patterns: list[dict], index: str, max_patterns: int = 3, max_breadcrumb_logs: int = 10
    ) -> dict[str, list[dict]]:
        """For top critical/high patterns, fetch logs preceding the first ERROR to reveal the operation in progress."""
        breadcrumbs_by_pattern: dict[str, list[dict]] = {}
        for pattern in patterns[:max_patterns]:
            if pattern.get("severity", "medium") not in ("critical", "high"):
                continue
            trace_ids = pattern.get("correlation_ids", [])
            if trace_ids:
                trace_result = await self._search_by_trace_id({
                    "index": index, "trace_id": trace_ids[0], "size": 50,
                })
                try:
                    trace_logs = json.loads(trace_result).get("logs", [])
                except (json.JSONDecodeError, AttributeError):
                    continue
                if not trace_logs:
                    continue
                sorted_logs = sorted(trace_logs, key=lambda l: l.get("timestamp", ""))
                error_idx = next(
                    (i for i, l in enumerate(sorted_logs)
                     if (l.get("level") or "").upper() in ("ERROR", "FATAL", "CRITICAL")),
                    None
                )
                if error_idx is not None:
                    start = max(0, error_idx - max_breadcrumb_logs)
                    preceding = sorted_logs[start:error_idx + 1]
                else:
                    preceding = sorted_logs[-max_breadcrumb_logs:]
                breadcrumbs_by_pattern[pattern["pattern_key"]] = preceding
            else:
                # Fallback: use _get_log_context() with pattern's first_seen timestamp
                first_seen = pattern.get("first_seen", "")
                services = pattern.get("affected_components", [])
                if first_seen and services:
                    ctx_result = await self._get_log_context({
                        "index": index,
                        "timestamp": first_seen,
                        "service": services[0],
                        "minutes_before": 3,
                        "minutes_after": 1,
                    })
                    try:
                        ctx_logs = json.loads(ctx_result).get("logs", [])
                    except (json.JSONDecodeError, AttributeError):
                        ctx_logs = []
                    if ctx_logs:
                        sorted_ctx = sorted(ctx_logs, key=lambda l: l.get("timestamp", ""))
                        error_idx = next(
                            (i for i, l in enumerate(sorted_ctx)
                             if (l.get("level") or "").upper() in ("ERROR", "FATAL", "CRITICAL")),
                            None
                        )
                        if error_idx is not None:
                            start = max(0, error_idx - max_breadcrumb_logs)
                            preceding = sorted_ctx[start:error_idx + 1]
                        else:
                            preceding = sorted_ctx[-max_breadcrumb_logs:]
                        breadcrumbs_by_pattern[pattern["pattern_key"]] = preceding
        return breadcrumbs_by_pattern

    def _extract_pattern_key(self, message: str) -> str:
        """Extract a fingerprint from a log message for grouping."""
        normalized = re.sub(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.\d]*[Z]?', '<TIMESTAMP>', message)
        normalized = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '<UUID>', normalized)
        normalized = re.sub(r'\b\d+\b', '<NUM>', normalized)
        exc_match = re.search(r'([A-Z][a-zA-Z]*(?:Exception|Error|Timeout|Failure))', message)
        if exc_match:
            return exc_match.group(1)
        return hashlib.md5(normalized.encode()).hexdigest()[:12]

    # ─── Severity Classification ─────────────────────────────────────────

    SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    SEVERITY_KEYWORDS = {
        "critical": {"ConnectError", "OOMKilled", "CrashLoopBackOff", "DatabaseError",
                     "DataCorruption", "OutOfMemoryError", "SegmentationFault"},
        "high": {"Timeout", "RedisTimeout", "ConnectionPoolExhausted", "CircuitBreakerOpen",
                 "ServiceUnavailable", "ConnectionTimeout", "SocketTimeout", "GatewayTimeout"},
        "medium": {"RetryExhausted", "RateLimited", "AuthenticationError",
                   "CertificateError", "PermissionError", "TLSError"},
        "low": {"DeprecationWarning", "HeaderWarning"},
    }

    def _classify_pattern_severity(self, exception_type: str, error_message: str) -> str:
        """Classify a pattern's operational severity deterministically."""
        for severity, types in self.SEVERITY_KEYWORDS.items():
            if exception_type in types:
                return severity
        if re.search(r'\b5\d{2}\b', error_message):
            return "critical"
        if exception_type == "UnknownError":
            msg_lower = error_message.lower()
            if any(kw in msg_lower for kw in ("deprecated", "migration", "deprecation", "overdue")):
                return "low"
        return "medium"

    # Framework noise prefixes to filter out of stack traces
    FRAMEWORK_NOISE_PREFIXES = (
        "org.springframework", "org.apache.tomcat", "org.apache.catalina",
        "io.netty", "java.lang.reflect", "sun.reflect", "jdk.internal",
        "org.apache.coyote", "org.apache.http", "reactor.core",
        "io.micrometer", "com.sun", "java.util.concurrent",
        "org.hibernate.internal", "com.zaxxer.hikari",
    )

    # Regex matching file path + line number references (Java, Python, Go, JS/TS, etc.)
    _FILE_LINE_RE = re.compile(
        r'(?:'
        r'\.\w+:\d+\)'       # Java: (FileName.java:45)
        r'|File ".+", line \d+'  # Python: File "/app/svc.py", line 12
        r'|\S+\.go:\d+'      # Go: /app/main.go:42
        r'|\S+\.[jt]sx?:\d+' # JS/TS: app.ts:10
        r')'
    )

    def _filter_stack_trace(self, raw_trace: str, max_lines: int = 15) -> str:
        """Keep application frames, file:line references, and exception causes. Saves ~60% tokens."""
        if not raw_trace:
            return ""
        lines = raw_trace.strip().splitlines()
        kept: list[str] = []
        skipped_framework = 0
        for line in lines:
            stripped = line.strip()
            # Always keep exception/cause lines
            if any(kw in stripped for kw in ("Exception", "Error", "Caused by", "Timeout", "Failure")):
                # Flush framework skip counter before this line
                if skipped_framework > 0:
                    kept.append(f"  ... ({skipped_framework} framework frames omitted)")
                    skipped_framework = 0
                kept.append(line)
                continue
            # Always keep lines with file path + line number (regardless of framework)
            if self._FILE_LINE_RE.search(stripped):
                # If it's a framework frame, still keep it but only the file:line part
                if stripped.startswith("at "):
                    frame = stripped[3:]
                    if any(frame.startswith(prefix) for prefix in self.FRAMEWORK_NOISE_PREFIXES):
                        skipped_framework += 1
                        continue
                # Application frame or non-"at" line with file reference — keep as-is
                if skipped_framework > 0:
                    kept.append(f"  ... ({skipped_framework} framework frames omitted)")
                    skipped_framework = 0
                kept.append(line)
                continue
            # Handle "at " lines without file references
            if stripped.startswith("at "):
                frame = stripped[3:]
                if any(frame.startswith(prefix) for prefix in self.FRAMEWORK_NOISE_PREFIXES):
                    skipped_framework += 1
                    continue
                # Application frame without file ref — still keep
                if skipped_framework > 0:
                    kept.append(f"  ... ({skipped_framework} framework frames omitted)")
                    skipped_framework = 0
                kept.append(line)
                continue
            # Keep "... N more" summary lines
            if stripped.startswith("..."):
                if skipped_framework > 0:
                    kept.append(f"  ... ({skipped_framework} framework frames omitted)")
                    skipped_framework = 0
                kept.append(line)
                continue
            # Keep non-"at" lines (message headers, Python traceback format, etc.)
            if skipped_framework > 0:
                kept.append(f"  ... ({skipped_framework} framework frames omitted)")
                skipped_framework = 0
            kept.append(line)
        # Flush any remaining skipped count
        if skipped_framework > 0:
            kept.append(f"  ... ({skipped_framework} framework frames omitted)")
        if not kept:
            # Fallback: return first few + last few lines of original
            return "\n".join(lines[:3] + ["  ... (filtered)"] + lines[-2:])
        return "\n".join(kept[:max_lines])

    def _extract_exception_type(self, message: str) -> str:
        """Extract the exception class name from a log message."""
        exc_match = re.search(r'([A-Z][a-zA-Z]*(?:Exception|Error|Timeout|Failure))', message)
        if exc_match:
            return exc_match.group(1)
        if "timeout" in message.lower():
            return "Timeout"
        if "connection" in message.lower():
            return "ConnectionError"
        return "UnknownError"

    _INLINE_STACK_PATTERNS = [
        re.compile(r'(Traceback \(most recent call last\):.*?\n\S[^\n]*)', re.DOTALL),
        re.compile(r'((?:[A-Z]\w*(?:Exception|Error|Timeout|Failure)[^\n]*\n)(?:\s+at \S+.*\n?)+)', re.MULTILINE),
        re.compile(r'(goroutine \d+ \[.*?\]:.*?)(?=\ngoroutine |\Z)', re.DOTALL),
        re.compile(r'((?:^\tat .+$\n?){2,})', re.MULTILINE),
    ]

    def _extract_inline_stack_trace(self, message: str) -> str:
        """Extract stack trace embedded in a log message body."""
        if not message or len(message) < 50:
            return ""
        for pattern in self._INLINE_STACK_PATTERNS:
            match = pattern.search(message)
            if match:
                raw = match.group(1).strip()
                if len(raw) > 100:
                    return raw[:2000]
        return ""
