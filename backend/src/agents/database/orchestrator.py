import asyncio
import logging
import os
from typing import Any
from src.database.models import DBFindingV2, EvidenceSource
from .tool_policy import ToolCallRecord

logger = logging.getLogger(__name__)


def validate_provenance(findings: list[DBFindingV2], call_log: list[ToolCallRecord]) -> list[DBFindingV2]:
    """Verify each finding's evidence_sources reference real tool calls."""
    valid_ids = {r.call_id for r in call_log if r.status == "success"}
    for finding in findings:
        unverified = [s for s in finding.evidence_sources if s.tool_call_id not in valid_ids]
        if unverified:
            finding.confidence_calibrated *= 0.5
            finding.meta["provenance_warning"] = f"{len(unverified)} evidence sources unverifiable"
    return findings


def calibrate_confidence(finding: DBFindingV2, call_log: list[ToolCallRecord]) -> float:
    """Adjust raw confidence based on evidence quality."""
    raw = finding.confidence_raw
    source_count = len(finding.evidence_sources)
    if source_count == 0:
        return raw * 0.3
    elif source_count == 1:
        raw *= 0.8
    truncated = sum(1 for s in finding.evidence_sources if s.truncated)
    if truncated > 0:
        raw *= 0.9
    if finding.meta.get("provenance_warning"):
        raw *= 0.5
    if finding.related_findings:
        raw = min(raw * 1.15, 0.99)
    return round(min(max(raw, 0.05), 0.99), 2)


class FindingsMerger:
    """Deduplicate and rank findings from multiple agents."""

    @staticmethod
    def merge(agent_results: list) -> list[DBFindingV2]:
        all_findings: list[DBFindingV2] = []
        seen_titles: set[str] = set()

        for result in agent_results:
            if isinstance(result, Exception):
                logger.warning("Agent failed: %s", result)
                continue
            findings, _call_log = result if isinstance(result, tuple) else (result, [])
            if not isinstance(findings, list):
                continue
            for finding in findings:
                if not isinstance(finding, DBFindingV2):
                    continue
                normalized = finding.title.lower().strip()
                if normalized not in seen_titles:
                    seen_titles.add(normalized)
                    all_findings.append(finding)

        severity_weight = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
        all_findings.sort(
            key=lambda f: severity_weight.get(f.severity, 0) * f.confidence_raw,
            reverse=True,
        )
        return all_findings


class DiagnosticOrchestrator:
    """Orchestrates LLM-powered diagnostic agents with heuristic fallback."""

    def __init__(self):
        self.all_call_records: list[ToolCallRecord] = []

    async def run(self, state: dict) -> dict:
        """Run the full diagnostic pipeline."""
        self.all_call_records = []
        emitter = state.get("_emitter")
        adapter = state.get("_adapter")
        engine = state.get("engine", "postgresql")

        # Check if LLM is available
        has_llm = bool(os.environ.get("ANTHROPIC_API_KEY"))

        if not has_llm and emitter:
            await emitter.emit("supervisor", "warning",
                "No ANTHROPIC_API_KEY set — using heuristic analysis only")

        # Build context for agents
        context = {
            "profile_name": state.get("profile_name", "unknown"),
            "host": state.get("host", ""),
            "port": state.get("port", 5432),
            "database": state.get("database", ""),
            "engine": engine,
            "focus": state.get("focus", []),
            "sampling_mode": state.get("sampling_mode", "standard"),
            "investigation_mode": state.get("investigation_mode", "standalone"),
        }

        # Run 3 agents in parallel
        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    self._run_agent("query_analyst", adapter, emitter, engine, context, has_llm, state),
                    self._run_agent("health_analyst", adapter, emitter, engine, context, has_llm, state),
                    self._run_agent("schema_analyst", adapter, emitter, engine, context, has_llm, state),
                    return_exceptions=True,
                ),
                timeout=120,
            )
        except asyncio.TimeoutError:
            logger.error("All agents timed out")
            if emitter:
                await emitter.emit("supervisor", "error", "Diagnostic agents timed out after 120s")
            results = []

        # Merge findings
        all_findings = FindingsMerger.merge(results)

        # Collect all call records
        for result in results:
            if isinstance(result, tuple) and len(result) == 2:
                _findings, call_log = result
                self.all_call_records.extend(call_log)

        # Validate provenance
        all_findings = validate_provenance(all_findings, self.all_call_records)

        # Calibrate confidence
        for f in all_findings:
            f.confidence_calibrated = calibrate_confidence(f, self.all_call_records)

        # Emit merged finding data for frontend panels
        if emitter:
            await self._emit_panel_data(emitter, all_findings, adapter)

        # Synthesize root cause
        from .synthesizer_llm import root_cause_synthesizer
        synthesis = await root_cause_synthesizer(state, all_findings, emitter)

        return synthesis

    async def _run_agent(self, name: str, adapter: Any, emitter: Any, engine: str, context: dict, has_llm: bool, state: dict) -> tuple:
        """Run single agent: LLM if available, heuristic fallback."""
        if emitter:
            await emitter.emit(name, "started", f"Starting {name.replace('_', ' ')}")

        if has_llm:
            try:
                from .llm_agents import run_llm_agent
                findings, call_log = await asyncio.wait_for(
                    run_llm_agent(name, adapter, emitter, engine, context),
                    timeout=60,
                )
                if findings:
                    if emitter:
                        await emitter.emit(name, "success",
                            f"LLM analysis complete — {len(findings)} findings")
                    return findings, call_log
                # LLM returned no findings — fall through to heuristic
            except (asyncio.TimeoutError, ConnectionError) as e:
                logger.warning("LLM agent %s failed: %s, using heuristic", name, e)
                if emitter:
                    await emitter.emit(name, "warning",
                        f"LLM timed out, using heuristic analysis: {e}")
            except Exception as e:
                logger.warning("LLM agent %s unexpected error: %s, using heuristic", name, e)
                if emitter:
                    await emitter.emit(name, "warning",
                        f"LLM analysis failed, using heuristic analysis: {e}")

        # Heuristic fallback
        findings = await self._heuristic_agent(name, state, emitter)
        if emitter:
            await emitter.emit(name, "success",
                f"Heuristic analysis complete — {len(findings)} findings")
        return findings, []

    async def _heuristic_agent(self, name: str, state: dict, emitter: Any) -> list:
        """Run the original heuristic agent from graph_v2.py."""
        from . import graph_v2

        heuristic_fn = getattr(graph_v2, name, None)
        if not heuristic_fn:
            return []

        try:
            result = await heuristic_fn(state)
            # The heuristic functions return dicts like {"query_findings": [...]}
            findings_key = f"{name.split('_')[0]}_findings"
            raw_findings = result.get(findings_key, result.get("findings", []))
            # Convert dicts to DBFindingV2 objects
            return [
                DBFindingV2(**f) if isinstance(f, dict) else f
                for f in raw_findings
            ]
        except Exception as e:
            logger.error("Heuristic %s failed: %s", name, e)
            return []

    async def _emit_panel_data(self, emitter: Any, all_findings: list, adapter: Any) -> None:
        """Emit structured data for frontend panels (connection pool, slow queries, etc)."""
        # Emit finding events for each agent so frontend panels light up
        query_findings = [f for f in all_findings if f.agent == "query_analyst"]
        health_findings = [f for f in all_findings if f.agent == "health_analyst"]
        schema_findings = [f for f in all_findings if f.agent == "schema_analyst"]

        # Query panel data
        if query_findings:
            slow_queries = [
                {"pid": 0, "duration_ms": 0, "query": f.detail[:300]}
                for f in query_findings if f.category == "slow_query"
            ]
            await emitter.emit("query_analyst", "finding", f"{len(query_findings)} query issues", details={
                "slow_queries": slow_queries if slow_queries else None,
            })

        # Health panel data — fetch fresh data for panels
        try:
            pool = await adapter.get_connection_pool()
            perf = await adapter.get_performance_stats()
            repl = await adapter.get_replication_status()

            conn_data = pool.model_dump() if hasattr(pool, 'model_dump') else {"active": 0, "idle": 0, "waiting": 0, "max_connections": 0}
            perf_data = perf.model_dump() if hasattr(perf, 'model_dump') else {}
            repl_data = None
            if hasattr(repl, 'replicas') and repl.replicas:
                repl_data = {
                    "primary": {"host": adapter.host, "lag_ms": 0},
                    "replicas": [{"host": r.name, "lag_ms": int(r.lag_seconds * 1000), "status": r.state} for r in repl.replicas],
                }

            await emitter.emit("health_analyst", "finding", f"{len(health_findings)} health issues", details={
                "connections": conn_data,
                "performance": {
                    "cache_hit_ratio": perf_data.get("cache_hit_ratio", 0),
                    "transactions_per_sec": perf_data.get("transactions_per_sec", 0),
                    "deadlocks": perf_data.get("deadlocks", 0),
                    "uptime_seconds": perf_data.get("uptime_seconds", 0),
                },
                "replication": repl_data,
            })
        except Exception as e:
            logger.warning("Failed to emit health panel data: %s", e)

        # Schema panel data
        if schema_findings:
            bloat_data = []
            indexes_data = []
            try:
                schema = await adapter.get_schema_snapshot()
                for tbl_dict in schema.tables[:10]:
                    tbl_name = tbl_dict.get("name", "") if isinstance(tbl_dict, dict) else ""
                    try:
                        detail = await adapter.get_table_detail(tbl_name)
                        bloat_data.append({"name": tbl_name, "bloat_ratio": detail.bloat_ratio, "dead_tuples": 0, "size_mb": round(detail.total_size_bytes / 1048576, 1)})
                        for idx in detail.indexes:
                            indexes_data.append({"name": idx.name, "table": tbl_name, "scans": getattr(idx, 'scan_count', 0), "size_mb": round(idx.size_bytes / 1048576, 1), "unused": getattr(idx, 'scan_count', 0) == 0})
                    except (asyncio.TimeoutError, ConnectionError) as e:
                        logger.warning("Failed to get table detail for %s: %s", tbl_name, e)
                    except Exception as e:
                        logger.warning("Unexpected error getting table detail for %s: %s", tbl_name, e)
            except (asyncio.TimeoutError, ConnectionError) as e:
                logger.warning("Failed to fetch schema snapshot for panel data: %s", e)
            except Exception as e:
                logger.warning("Unexpected error fetching schema snapshot: %s", e)

            await emitter.emit("schema_analyst", "finding", f"{len(schema_findings)} schema issues", details={
                "indexes": indexes_data if indexes_data else None,
                "table_bloat": bloat_data if bloat_data else None,
            })
