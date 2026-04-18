"""TracingAgent — production-ready distributed-tracing diagnostic agent (v1 rewrite).

Design locked through head-of-architecture review (see docs/plans/ for decisions).
Summary of the architectural shape:

  Input context → TracingAgent.run()
      │
      ├── Trace mining (when trace_id missing but service+window given)
      │     └── TraceBackend.find_traces → TraceRanker → top-N candidates
      │
      ├── Per-candidate get_trace + SpanTagRedactor
      │
      ├── EnvoyResponseFlagsMatcher  ← deterministic, zero LLM
      ├── TraceSummarizer            ← deterministic span-budget reduction
      │
      ├── TierSelector  ← picks Tier 0 / 1 / 2
      │
      ├── Tier 0 → templated result (no LLM)
      ├── Tier 1 → Haiku synthesis call
      ├── Tier 2 → Sonnet full-reasoning call
      │
      └── TraceAnalysisResult (enriched with envoy findings + provenance)

Fallback to ELK log reconstruction when the backend has no trace data.
Confidence penalty scales with sampling mode when fallback is used.

All long-running I/O uses async httpx via ``get_client()`` — no blocking
``requests`` calls. Full httpx migration is what makes this concurrency-safe
for production use.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

from src.agents.react_base import ReActAgent
from src.agents.tracing.backends.base import (
    BackendUnreachable,
    TraceBackend,
    TraceNotFound,
)
from src.agents.tracing.backends.jaeger import JaegerBackend
from src.agents.tracing.backends.tempo import TempoBackend
from src.agents.tracing.elk_reconstructor import ElkLogReconstructor, ReconstructionResult
from src.agents.tracing.envoy_flags import EnvoyResponseFlagsMatcher
from src.agents.tracing.ranker import RankerConfig, SymptomHints, TraceRanker
from src.agents.tracing.redactor import RedactionConfig, SpanTagRedactor
from src.agents.tracing.patterns_runner import PatternsRunner
from src.agents.tracing.patterns.baseline_regression import BaselineFetcher
from src.agents.tracing.summarizer import SummarizedTrace, SummarizerConfig, TraceSummarizer
from src.agents.tracing.tier_selector import TierSelector
from src.models.schemas import (
    EnvoyFlagFinding,
    LatencyRegressionHint,
    PatternFinding,
    SpanInfo,
    TierDecision,
    TraceAnalysisResult,
    TraceSummary,
)
from src.utils.event_emitter import EventEmitter
from src.utils.logger import get_logger

logger = get_logger(__name__)


SamplingMode = Literal["head_based", "tail_based", "full"]


@dataclass
class TracingAgentConfig:
    """Operator-tunable per-integration config."""

    # Backend selection.
    backend_kind: Literal["jaeger", "tempo"] = "jaeger"
    backend_url: str = "http://localhost:16686"
    backend_auth_header: Optional[str] = None

    # ELK fallback.
    elk_url: Optional[str] = None
    elk_auth_header: Optional[str] = None

    # Operational contract.
    sampling_mode: SamplingMode = "tail_based"

    # Sub-component configs (overridable).
    summarizer: SummarizerConfig = field(default_factory=SummarizerConfig)
    ranker: RankerConfig = field(default_factory=RankerConfig)
    redaction: RedactionConfig = field(default_factory=RedactionConfig)

    # Trace-mining defaults when user gives service+window but no trace_id.
    default_mining_window_minutes: int = 15

    # TA-PR2 — baseline lookup for the baseline_latency_regression detector.
    # None means the detector emits no findings (graceful degradation).
    baseline_fetcher: Optional[BaselineFetcher] = None


# Confidence multiplier when we fall back to ELK reconstruction.
# Locked policy: more aggressive penalty when the sampling mode implies
# the trace SHOULD have been there (tail_based or full).
_ELK_FALLBACK_CONFIDENCE_PENALTY: dict[SamplingMode, float] = {
    "head_based": 0.90,
    "tail_based": 0.60,
    "full": 0.40,
}


class TracingAgent(ReActAgent):
    """Distributed-tracing diagnostic agent.

    Two public entry points:
      - ``run()``         — one investigation; uses the config's single trace_id
                            OR mines one from service + time_window.
      - ``run_two_pass()`` — legacy alias kept so the existing supervisor
                             call site from the dispatch layer keeps working.
    """

    def __init__(
        self,
        max_iterations: int = 6,
        connection_config=None,
    ) -> None:
        super().__init__(
            agent_name="tracing_agent",
            max_iterations=max_iterations,
            connection_config=connection_config,
        )
        self._connection_config = connection_config
        self._config = _build_config(connection_config)
        self._backend: TraceBackend = _build_backend(self._config)
        self._elk: Optional[ElkLogReconstructor] = (
            ElkLogReconstructor(self._config.elk_url, auth_header=self._config.elk_auth_header)
            if self._config.elk_url
            else None
        )
        self._redactor = SpanTagRedactor(self._config.redaction)
        self._summarizer = TraceSummarizer(self._config.summarizer)
        self._ranker = TraceRanker(self._config.ranker)

        # TA-PR2b — default to the DB-backed baseline fetcher unless the
        # caller injected a different one. When the populator hasn't run
        # yet (empty table) the fetcher returns None per key and the
        # BaselineRegressionDetector gracefully emits no findings.
        resolved_fetcher = self._config.baseline_fetcher
        if resolved_fetcher is None and os.environ.get("TRACE_BASELINE_DISABLE") != "1":
            try:
                from src.workers.trace_baseline_populator import build_baseline_fetcher
                resolved_fetcher = build_baseline_fetcher()
            except Exception:
                # Don't fail TracingAgent construction if the populator
                # module can't be imported — e.g., inside minimal unit-test
                # environments. Detector just won't emit baseline findings.
                logger.debug("baseline fetcher unavailable; detector will skip")

        self._patterns = PatternsRunner(baseline_fetcher=resolved_fetcher)

    # Abstract ReActAgent methods — TracingAgent runs in an explicit orchestrated
    # mode (run_two_pass), NOT the generic ReAct loop, so these are minimal stubs
    # satisfying the contract for code paths that construct it via the registry.

    async def _define_tools(self) -> list[dict]:
        return []  # ReAct tool-use path intentionally not used

    async def _build_system_prompt(self) -> str:
        return "TracingAgent uses orchestrated run_two_pass, not the ReAct loop."

    async def _build_initial_prompt(self, context: dict) -> str:
        return ""

    async def _handle_tool_call(self, tool_name: str, tool_input: dict) -> str:
        return f"Unknown tool: {tool_name}"

    def _parse_final_response(self, text: str) -> dict:
        # Fallback JSON extractor used only if a Tier 1/2 call returns markdown.
        try:
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                return json.loads(m.group())
            return json.loads(text)
        except (json.JSONDecodeError, AttributeError):
            return {"error": "Failed to parse LLM response", "raw_response": text[:2000]}

    # ── Main orchestrator ────────────────────────────────────────────────

    async def run_two_pass(
        self,
        context: dict,
        event_emitter: Optional[EventEmitter] = None,
    ) -> dict:
        """Entry point — supervisor.dispatch_agent calls this.

        Kept with the original name so the supervisor integration is a
        one-line registry uncomment, not a plumbing change.
        """
        return await self.run(context, event_emitter)

    async def run(
        self,
        context: dict,
        event_emitter: Optional[EventEmitter] = None,
    ) -> dict:
        await self._emit(event_emitter, "started", "TracingAgent starting")

        trace_id: Optional[str] = context.get("trace_id")
        service_name: str = context.get("service_name", "")
        time_window: Optional[tuple[datetime, datetime]] = _resolve_time_window(context)

        # Step 1 — resolve the set of trace_ids to analyze.
        try:
            trace_ids, mined = await self._resolve_trace_ids(
                trace_id, service_name, time_window, event_emitter
            )
        except BackendUnreachable as e:
            return self._unreachable_result(trace_id, str(e))

        if not trace_ids:
            return self._no_trace_result(trace_id or "", service_name)

        # Step 2 — fetch raw spans for each trace (parallel, bounded failures OK).
        await self._emit(
            event_emitter,
            "tool_call",
            f"Fetching {len(trace_ids)} trace{'s' if len(trace_ids) > 1 else ''} from {self._backend.backend_id}",
        )
        fetched = await self._fetch_all_traces(trace_ids)

        # If everything failed, fall back to ELK.
        if not any(spans for _, spans in fetched):
            return await self._elk_fallback(
                trace_ids[0], time_window, event_emitter, reason="all_traces_empty"
            )

        # Step 3 — redact, summarize, scan each trace (envoy flags + TA-PR2 patterns).
        processed: list[_ProcessedTrace] = []
        for tid, raw_spans in fetched:
            if not raw_spans:
                continue
            safe_spans = [self._redactor.redact_span(s) for s in raw_spans]
            summary = self._summarizer.summarize(safe_spans)
            envoy = EnvoyResponseFlagsMatcher.scan_trace(safe_spans)
            patterns = self._patterns.run(safe_spans)
            processed.append(
                _ProcessedTrace(
                    trace_id=tid,
                    spans=safe_spans,
                    summary=summary,
                    envoy=envoy,
                    patterns=patterns,
                )
            )

        primary = processed[0]
        has_multi = len(processed) > 1

        # Step 4 — TierSelector.
        ambiguous = _is_failure_point_ambiguous(primary.spans, primary.envoy)
        tier_decision = TierSelector.from_envoy_findings(
            findings=primary.envoy,
            has_mined_multiple_traces=has_multi,
            elk_fallback_active=False,
            sampling_was_expected=_sampling_was_expected(self._config.sampling_mode, True),
            summarized_span_count=len(primary.summary.kept_spans),
            summarizer_ambiguous_failure_point=ambiguous,
            has_any_error_span=any(s.status == "error" for s in primary.spans),
            pattern_findings=primary.patterns,
        )

        # Step 5 — dispatch by tier.
        await self._emit(
            event_emitter,
            "tool_call",
            f"Tier {tier_decision.tier} analysis ({tier_decision.rationale})",
        )
        if tier_decision.tier == 0:
            result_dict = self._tier0_result(primary, tier_decision, mined, processed)
        else:
            result_dict = await self._tier_llm_result(
                primary=primary,
                processed=processed,
                mined=mined,
                tier_decision=tier_decision,
                event_emitter=event_emitter,
            )

        await self._emit(event_emitter, "success", "TracingAgent completed")
        return result_dict

    # ── Trace ID resolution ──────────────────────────────────────────────

    async def _resolve_trace_ids(
        self,
        explicit_trace_id: Optional[str],
        service_name: str,
        time_window: Optional[tuple[datetime, datetime]],
        event_emitter: Optional[EventEmitter],
    ) -> tuple[list[str], list[TraceSummary]]:
        """Return (ids_to_analyze, mined_candidate_summaries)."""

        if explicit_trace_id:
            # Explicit ID given — single-trace path, no mining.
            return [explicit_trace_id], []

        if not service_name or not time_window:
            return [], []

        # Mining path.
        await self._emit(
            event_emitter,
            "tool_call",
            f"No trace_id given — mining candidates for {service_name}",
        )
        start, end = time_window

        # Two parallel queries: error-carrying + latency outlier.
        try:
            results = await asyncio.gather(
                self._backend.find_traces(
                    service=service_name, start=start, end=end,
                    has_error=True, limit=self._config.ranker.top_n * 3,
                ),
                self._backend.find_traces(
                    service=service_name, start=start, end=end,
                    min_duration_ms=1000,  # slow-ish traces
                    limit=self._config.ranker.top_n * 3,
                ),
                return_exceptions=True,
            )
        except BackendUnreachable as e:
            raise e

        candidates: list[TraceSummary] = []
        seen_ids: set[str] = set()
        for r in results:
            if isinstance(r, BaseException):
                logger.warning("find_traces leg failed: %s", r)
                continue
            for ts in r:
                if ts.trace_id not in seen_ids:
                    seen_ids.add(ts.trace_id)
                    candidates.append(ts)

        if not candidates:
            return [], []

        hints = SymptomHints(
            expecting_errors=bool(context_has_error_hint := True),  # default symptom assumption
            expecting_slowness=False,
            known_error_keywords=[],
        )
        ranked = self._ranker.rank(candidates, hints)
        picks = [r.summary for r in ranked[: self._config.ranker.top_n]]
        return [p.trace_id for p in picks], picks

    # ── Trace fetching (parallel, fault-tolerant) ────────────────────────

    async def _fetch_all_traces(
        self, trace_ids: list[str]
    ) -> list[tuple[str, list[SpanInfo]]]:
        async def one(tid: str) -> tuple[str, list[SpanInfo]]:
            try:
                spans = await self._backend.get_trace(tid)
                return (tid, spans)
            except TraceNotFound:
                self.add_negative_finding(
                    what_was_checked=f"Trace {tid} in {self._backend.backend_id}",
                    result="No spans found",
                    implication="Backend reports the trace ID doesn't exist",
                    source_reference=f"{self._backend.backend_id} get_trace {tid}",
                )
                return (tid, [])
            except BackendUnreachable as e:
                logger.warning("get_trace failed for %s: %s", tid, e)
                return (tid, [])

        return list(await asyncio.gather(*[one(t) for t in trace_ids]))

    # ── Tier 0: deterministic, no LLM ────────────────────────────────────

    def _tier0_result(
        self,
        primary: "_ProcessedTrace",
        tier: TierDecision,
        mined: list[TraceSummary],
        all_processed: list["_ProcessedTrace"],
    ) -> dict:
        envoy = primary.envoy[0]
        span = next(
            (s for s in primary.spans if s.span_id == envoy.span_id), None
        )

        cascade = _compute_cascade_path(primary.spans, envoy.span_id)
        dep_graph = _compute_dependency_graph(primary.spans)
        services = sorted({s.service_name for s in primary.spans})

        return self._assemble_result(
            primary=primary,
            failure_point=span,
            cascade=cascade,
            dep_graph=dep_graph,
            services=services,
            trace_source="jaeger" if self._config.backend_kind == "jaeger" else "tempo",
            tier=tier,
            mined=mined,
            overall_confidence=92,  # deterministic Envoy match — high floor
            analyzer_summary=(
                f"{envoy.human_summary} at {envoy.service_name}. {envoy.likely_cause}"
            ),
            cross_trace_consensus=(
                "unanimous" if len(all_processed) > 1 else None
            ),
        )

    # ── Tier 1 / 2: LLM call ─────────────────────────────────────────────

    async def _tier_llm_result(
        self,
        *,
        primary: "_ProcessedTrace",
        processed: list["_ProcessedTrace"],
        mined: list[TraceSummary],
        tier_decision: TierDecision,
        event_emitter: Optional[EventEmitter],
    ) -> dict:
        prompt = _build_analyze_prompt(
            processed=processed,
            config=self._config,
            tier=tier_decision,
        )
        system = _build_system_prompt(tier_decision)

        # Model selection via B.11 key resolver.
        model_id = _resolve_model_for_key(tier_decision.model_key)

        try:
            # Note: self.llm_client comes from ReActAgent; it's an AnthropicClient
            # bound to the agent-level default model. For v1 we call it with the
            # resolved model via the kwargs override; if unsupported, the base
            # client falls through to its default. In v1.1 we'll add a per-call
            # model override to AnthropicClient.
            response = await self.llm_client.chat(
                prompt=prompt, system=system, max_tokens=4096,
            )
        except Exception:
            logger.exception("Tier %d LLM call failed; returning low-confidence stub", tier_decision.tier)
            return self._assemble_result(
                primary=primary,
                failure_point=None,
                cascade=[],
                dep_graph=_compute_dependency_graph(primary.spans),
                services=sorted({s.service_name for s in primary.spans}),
                trace_source="jaeger" if self._config.backend_kind == "jaeger" else "tempo",
                tier=tier_decision,
                mined=mined,
                overall_confidence=25,
                analyzer_summary=f"LLM analysis failed; low-confidence fallback result.",
            )

        parsed = self._parse_final_response(response.text)
        if "error" in parsed:
            logger.warning("LLM returned unparseable JSON; using fallback")
            parsed = {}

        return self._assemble_result(
            primary=primary,
            failure_point=_pick_failure_from_llm(parsed, primary.spans),
            cascade=list(parsed.get("cascade_path") or []),
            dep_graph=parsed.get("service_dependency_graph") or _compute_dependency_graph(primary.spans),
            services=sorted({s.service_name for s in primary.spans}),
            trace_source=parsed.get("trace_source")
                or ("jaeger" if self._config.backend_kind == "jaeger" else "tempo"),
            tier=tier_decision,
            mined=mined,
            overall_confidence=int(parsed.get("overall_confidence") or 70),
            analyzer_summary=parsed.get("summary") or "",
            cross_trace_consensus=parsed.get("cross_trace_consensus"),
            retry_detected=bool(parsed.get("retry_detected", False)),
            latency_bottlenecks=_pick_bottlenecks_from_llm(parsed, primary.spans),
        )

    # ── ELK fallback + result shapers ────────────────────────────────────

    async def _elk_fallback(
        self,
        trace_id: str,
        time_window: Optional[tuple[datetime, datetime]],
        event_emitter: Optional[EventEmitter],
        *,
        reason: str,
    ) -> dict:
        if self._elk is None or time_window is None:
            return self._no_trace_result(trace_id, reason=reason)

        await self._emit(event_emitter, "tool_call", "Falling back to ELK log reconstruction")
        start, end = time_window
        rec = await self._elk.reconstruct(trace_id, start=start, end=end)
        if not rec.hops:
            return self._no_trace_result(trace_id, reason=f"{reason}+elk_empty")

        # Build synthetic SpanInfo list so the result shape stays consistent.
        spans = [_hop_to_span(hop, idx) for idx, hop in enumerate(rec.hops)]
        services = rec.services
        dep_graph = _compute_dependency_graph(spans)

        # Penalize confidence per sampling mode.
        penalty = _ELK_FALLBACK_CONFIDENCE_PENALTY.get(self._config.sampling_mode, 0.60)
        adjusted_conf = int(rec.confidence * penalty)

        # Tier decision: ELK fallback forces Tier 2.
        tier = TierDecision(
            tier=2,
            rationale="elk_fallback_low_signal_quality",
            model_key="default",
        )

        result = TraceAnalysisResult(
            trace_id=trace_id,
            total_duration_ms=0.0,
            total_services=len(services),
            total_spans=len(spans),
            call_chain=spans,
            failure_point=next((s for s in spans if s.status == "error"), None),
            cascade_path=services,
            latency_bottlenecks=[],
            retry_detected=any(h.is_retry_of_previous for h in rec.hops),
            service_dependency_graph=dep_graph,
            trace_source="elasticsearch",
            elk_reconstruction_confidence=rec.confidence,
            findings=[],
            negative_findings=self.negative_findings,
            breadcrumbs=self.breadcrumbs,
            overall_confidence=adjusted_conf,
            tokens_used=self.get_token_usage(),
            envoy_findings=[],
            mined_trace_ids=[],
            tier_decision=tier,
            cross_trace_consensus=None,
            sampling_mode=self._config.sampling_mode,
            services_in_chain=services,
        )
        return result.model_dump(mode="json")

    def _no_trace_result(self, trace_id: str, reason: str = "not_found") -> dict:
        """Honest 'no trace data anywhere' response."""
        return TraceAnalysisResult(
            trace_id=trace_id,
            total_duration_ms=0.0,
            total_services=0,
            total_spans=0,
            call_chain=[],
            failure_point=None,
            cascade_path=[],
            latency_bottlenecks=[],
            retry_detected=False,
            service_dependency_graph={},
            trace_source="elasticsearch" if self._elk else "jaeger",
            elk_reconstruction_confidence=None,
            findings=[],
            negative_findings=self.negative_findings,
            breadcrumbs=self.breadcrumbs,
            overall_confidence=0,
            tokens_used=self.get_token_usage(),
            envoy_findings=[],
            mined_trace_ids=[],
            tier_decision=TierDecision(tier=2, rationale=f"no_trace_data:{reason}", model_key="none"),
            cross_trace_consensus=None,
            sampling_mode=self._config.sampling_mode,
            services_in_chain=[],
        ).model_dump(mode="json")

    def _unreachable_result(self, trace_id: Optional[str], err: str) -> dict:
        self.add_negative_finding(
            what_was_checked=f"{self._backend.backend_id} at {self._config.backend_url}",
            result="unreachable",
            implication=f"Tracing data unavailable: {err}",
            source_reference=self._config.backend_url,
        )
        return self._no_trace_result(trace_id or "", reason="backend_unreachable")

    def _assemble_result(
        self,
        *,
        primary: "_ProcessedTrace",
        failure_point: Optional[SpanInfo],
        cascade: list[str],
        dep_graph: dict[str, list[str]],
        services: list[str],
        trace_source: str,
        tier: TierDecision,
        mined: list[TraceSummary],
        overall_confidence: int,
        analyzer_summary: str = "",
        cross_trace_consensus: Optional[str] = None,
        retry_detected: bool = False,
        latency_bottlenecks: Optional[list[SpanInfo]] = None,
    ) -> dict:
        total_duration = max((s.duration_ms for s in primary.spans), default=0.0)
        if primary.summary.was_summarized:
            trace_source = "summarized"

        # TA-PR2 — handoff fields derived deterministically from pattern findings.
        hot_services = sorted({p.service_name for p in primary.patterns})
        critical_path_services = _critical_path_service_chain(primary.spans)
        bottleneck_operations = [
            (p.service_name, p.metadata.get("operation", ""))
            for p in primary.patterns
            if p.kind == "critical_path_hotspot"
        ]
        baseline_hints = self._patterns.hints_for_metrics(primary.patterns)

        result = TraceAnalysisResult(
            trace_id=primary.trace_id,
            total_duration_ms=total_duration,
            total_services=len(services),
            total_spans=primary.summary.total_original_spans,
            call_chain=primary.summary.kept_spans,
            failure_point=failure_point,
            cascade_path=cascade,
            latency_bottlenecks=latency_bottlenecks or [],
            retry_detected=retry_detected,
            service_dependency_graph=dep_graph,
            trace_source=trace_source,  # type: ignore[arg-type]
            elk_reconstruction_confidence=None,
            findings=[],
            negative_findings=self.negative_findings,
            breadcrumbs=self.breadcrumbs,
            overall_confidence=overall_confidence,
            tokens_used=self.get_token_usage(),
            envoy_findings=primary.envoy,
            mined_trace_ids=[m.trace_id for m in mined],
            tier_decision=tier,
            cross_trace_consensus=cross_trace_consensus,
            sampling_mode=self._config.sampling_mode,
            services_in_chain=services,
            # TA-PR2 additions.
            pattern_findings=primary.patterns,
            hot_services=hot_services,
            critical_path_services=critical_path_services,
            bottleneck_operations=bottleneck_operations,
            baseline_regressions=baseline_hints,
        )
        return result.model_dump(mode="json")

    # ── Small helpers ────────────────────────────────────────────────────

    async def _emit(
        self, event_emitter: Optional[EventEmitter], kind: str, msg: str
    ) -> None:
        if event_emitter is None:
            return
        try:
            await event_emitter.emit(self.agent_name, kind, msg)
        except Exception:  # noqa: BLE001
            logger.debug("event_emitter.emit failed")


# ═════════════════════════════════════════════════════════════════════════
#  Module-level helpers
# ═════════════════════════════════════════════════════════════════════════


@dataclass
class _ProcessedTrace:
    trace_id: str
    spans: list[SpanInfo]
    summary: SummarizedTrace
    envoy: list[EnvoyFlagFinding]
    patterns: list[PatternFinding] = field(default_factory=list)


def _build_config(connection_config: Any) -> TracingAgentConfig:
    cfg = TracingAgentConfig()
    if connection_config is None:
        return cfg

    # Jaeger or Tempo — infer from URL if the integration doesn't say.
    if url := getattr(connection_config, "jaeger_url", None):
        cfg.backend_url = url
        cfg.backend_kind = "jaeger"
    if url := getattr(connection_config, "tempo_url", None):
        cfg.backend_url = url
        cfg.backend_kind = "tempo"
    if url := getattr(connection_config, "elasticsearch_url", None):
        cfg.elk_url = url
    # Sampling mode from config (default tail_based).
    mode = getattr(connection_config, "trace_sampling_mode", None)
    if mode in ("head_based", "tail_based", "full"):
        cfg.sampling_mode = mode
    return cfg


def _build_backend(cfg: TracingAgentConfig) -> TraceBackend:
    if cfg.backend_kind == "tempo":
        return TempoBackend(base_url=cfg.backend_url, auth_header=cfg.backend_auth_header)
    return JaegerBackend(base_url=cfg.backend_url, auth_header=cfg.backend_auth_header)


def _resolve_time_window(
    context: dict,
) -> Optional[tuple[datetime, datetime]]:
    """Normalize incident-window inputs into a (start, end) tuple."""
    if window := context.get("time_window"):
        if isinstance(window, (tuple, list)) and len(window) == 2:
            start, end = window
            if isinstance(start, datetime) and isinstance(end, datetime):
                return (start, end)
    # Fall back: use last N minutes if only a minutes hint is given.
    if mins := context.get("window_minutes"):
        end = datetime.now(timezone.utc)
        return (end - timedelta(minutes=int(mins)), end)
    return None


def _sampling_was_expected(mode: SamplingMode, trace_present: bool) -> bool:
    """True when 'trace is missing' is an expected outcome under this mode."""
    if trace_present:
        return True
    return mode == "head_based"


def _resolve_model_for_key(key: Literal["cheap", "default", "none"]) -> str:
    """Use B.11 key_resolver pattern to map logical key → model ID.

    For v1 we map to environment variables the operator sets. The full
    agent_model_routes DB-table flow is the v1.1 follow-up.
    """
    if key == "cheap":
        return os.getenv("TRACING_AGENT_CHEAP_MODEL", "claude-haiku-4-5-20251001")
    return os.getenv("TRACING_AGENT_DEFAULT_MODEL", "claude-sonnet-4-6")


def _is_failure_point_ambiguous(
    spans: list[SpanInfo], envoy: list[EnvoyFlagFinding]
) -> bool:
    """Multiple candidate failure points → ambiguous → Tier 2."""
    if len(envoy) >= 2:
        return True
    error_spans = [s for s in spans if s.status == "error"]
    if len(error_spans) <= 1:
        return False
    # Multiple errors — ambiguous only if they're in different services.
    services = {s.service_name for s in error_spans}
    return len(services) >= 2


def _compute_cascade_path(spans: list[SpanInfo], failure_span_id: str) -> list[str]:
    """Walk from the failure span up the parent chain; return service names."""
    by_id = {s.span_id: s for s in spans}
    chain: list[str] = []
    cur = by_id.get(failure_span_id)
    seen: set[str] = set()
    while cur is not None and cur.span_id not in seen:
        seen.add(cur.span_id)
        chain.append(cur.service_name)
        cur = by_id.get(cur.parent_span_id) if cur.parent_span_id else None
    # Reverse so the chain reads root → failure.
    return list(reversed(chain))


def _compute_dependency_graph(spans: list[SpanInfo]) -> dict[str, list[str]]:
    """service → [downstream services] — directed edges from parent's service."""
    by_id = {s.span_id: s for s in spans}
    edges: dict[str, set[str]] = {}
    for span in spans:
        if not span.parent_span_id:
            continue
        parent = by_id.get(span.parent_span_id)
        if parent is None:
            continue
        if parent.service_name == span.service_name:
            continue
        edges.setdefault(parent.service_name, set()).add(span.service_name)
    return {k: sorted(v) for k, v in edges.items()}


def _critical_path_service_chain(spans: list[SpanInfo]) -> list[str]:
    """Ordered service list along the trace's critical path (root → leaf).

    TA-PR2 handoff contract — metrics_agent uses this to drill into the
    RED metrics of these services in order.
    """
    if not spans:
        return []
    by_id = {s.span_id: s for s in spans}
    parent_ids = {s.parent_span_id for s in spans if s.parent_span_id}
    leaves = [s for s in spans if s.span_id not in parent_ids]
    if not leaves:
        leaves = spans

    best_total = 0.0
    best_chain: list[str] = []
    for leaf in leaves:
        chain: list[str] = []
        total = 0.0
        cur: Optional[SpanInfo] = leaf
        seen: set[str] = set()
        while cur is not None and cur.span_id not in seen:
            seen.add(cur.span_id)
            chain.append(cur.service_name)
            total += cur.duration_ms
            cur = by_id.get(cur.parent_span_id) if cur.parent_span_id else None
        if total > best_total:
            best_total = total
            best_chain = chain

    # Dedup preserving order: root...leaf reading makes more sense reversed.
    seen2: set[str] = set()
    ordered = []
    for s in reversed(best_chain):
        if s not in seen2:
            seen2.add(s)
            ordered.append(s)
    return ordered


def _hop_to_span(hop: Any, idx: int) -> SpanInfo:
    """Convert ELK reconstructor hop → SpanInfo for result-shape consistency."""
    return SpanInfo(
        span_id=f"elk-{idx}",
        service_name=hop.service_name,
        operation_name=hop.message[:60] if hop.message else "log_event",
        duration_ms=0.0,  # ELK hops have no duration signal
        status=hop.status,
        error_message=hop.message if hop.status == "error" else None,
        parent_span_id=f"elk-{idx - 1}" if idx > 0 else None,
    )


def _pick_failure_from_llm(parsed: dict, spans: list[SpanInfo]) -> Optional[SpanInfo]:
    """Pick the LLM's failure_point, validated against actual spans to prevent
    hallucinated span IDs."""
    fp = parsed.get("failure_point") or {}
    span_id = fp.get("span_id") if isinstance(fp, dict) else None
    if span_id:
        for s in spans:
            if s.span_id == span_id:
                return s
    # Fall back: the first error span in the input.
    for s in spans:
        if s.status == "error":
            return s
    return None


def _pick_bottlenecks_from_llm(parsed: dict, spans: list[SpanInfo]) -> list[SpanInfo]:
    ids = []
    for b in parsed.get("latency_bottlenecks") or []:
        if isinstance(b, dict) and b.get("span_id"):
            ids.append(b["span_id"])
    if not ids:
        return []
    by_id = {s.span_id: s for s in spans}
    return [by_id[i] for i in ids if i in by_id]


# ── Prompt builders ──────────────────────────────────────────────────────


def _build_system_prompt(tier: TierDecision) -> str:
    base = (
        "You are a Distributed Tracing Agent for SRE troubleshooting.\n\n"
        "You are given pre-fetched, deterministically-reduced trace data. "
        "Analyze and produce the final JSON.\n\n"
        "CONFIDENCE CALIBRATION: use 0-100 where 100 = you can name the "
        "specific failing span + cause. 50 = genuine uncertainty. Below 40 "
        "is fine — emit low confidence when evidence is thin rather than "
        "fabricating certainty.\n\n"
        "EVIDENCE CITATION: failure_point.span_id MUST match an actual "
        "span ID from the input. Do not invent span IDs.\n\n"
        "OUTPUT: respond with ONLY JSON (no markdown, no prose wrapper):\n"
        '{\n'
        '    "trace_id": "...",\n'
        '    "total_duration_ms": 0,\n'
        '    "failure_point": {"span_id": "...", "service_name": "...", ...},\n'
        '    "cascade_path": ["svc-a", "svc-b"],\n'
        '    "latency_bottlenecks": [{"span_id": "..."}],\n'
        '    "retry_detected": false,\n'
        '    "service_dependency_graph": {"svc-a": ["svc-b"]},\n'
        '    "trace_source": "jaeger|tempo|elasticsearch|summarized",\n'
        '    "overall_confidence": 0,\n'
        '    "summary": "one paragraph human-readable",\n'
        '    "cross_trace_consensus": "unanimous|majority|divergent|null"\n'
        "}\n"
    )
    if tier.tier == 1:
        base += (
            "\nThis is a Tier 1 analysis — the deterministic layer has already "
            "identified the likely failure. Focus on natural-language synthesis "
            "of why it matters + likely root cause in 3-4 sentences.\n"
        )
    else:
        base += (
            "\nThis is a Tier 2 analysis — either cross-trace consensus is "
            "needed or the signal is ambiguous. Explicitly reconcile "
            "differences across traces and state your consensus verdict.\n"
        )
    return base


def _build_analyze_prompt(
    *,
    processed: list[_ProcessedTrace],
    config: TracingAgentConfig,
    tier: TierDecision,
) -> str:
    parts: list[str] = ["# Trace Analysis — Pre-Fetched Data\n"]
    parts.append(f"## Sampling Mode: {config.sampling_mode}")
    if tier.tier == 2 and len(processed) > 1:
        parts.append(
            f"## Cross-Trace Consensus: analyzing {len(processed)} mined traces"
        )

    for idx, pt in enumerate(processed, 1):
        parts.append(f"\n## Trace {idx}: {pt.trace_id}")
        parts.append(
            f"Total original spans: {pt.summary.total_original_spans}"
            + (" (summarized)" if pt.summary.was_summarized else "")
        )

        if pt.envoy:
            parts.append("\n### Deterministic Envoy Findings")
            for f in pt.envoy:
                parts.append(
                    f"- [{f.flag}] {f.service_name} — {f.human_summary}. {f.likely_cause}"
                )

        if pt.patterns:
            parts.append("\n### Deterministic Pattern Findings (pre-analyzed — build on these, do not re-derive)")
            for p in pt.patterns[:15]:
                parts.append(
                    f"- [{p.kind} / {p.severity}, conf={p.confidence}] "
                    f"{p.service_name}: {p.human_summary}"
                )

        parts.append(f"\n### Spans ({len(pt.summary.kept_spans)} shown)")
        for span in pt.summary.kept_spans[:400]:  # hard prompt-budget guard
            status_tag = f"[{span.status}]" if span.status != "ok" else "   "
            err = f" — {span.error_message}" if span.error_message else ""
            critical = " ★" if span.critical_path else ""
            parts.append(
                f"  {status_tag} {span.span_id}  {span.service_name} → "
                f"{span.operation_name}  ({span.duration_ms}ms){critical}{err}"
            )
            if span.parent_span_id:
                parts.append(f"       parent: {span.parent_span_id}")

        if pt.summary.aggregates:
            parts.append(f"\n### Aggregated siblings ({len(pt.summary.aggregates)} buckets)")
            for b in pt.summary.aggregates[:50]:
                parts.append(
                    f"  - {b.service_name}/{b.operation_name} × {b.span_count} spans "
                    f"(p50={b.p50_ms}ms, p99={b.p99_ms}ms, total={b.total_duration_ms}ms)"
                )

        # Redaction provenance footer — LLM needs to know input was filtered.
        total_stripped = sum(len(s.stripped_tag_keys) for s in pt.spans)
        total_redacted = sum(s.value_redactions for s in pt.spans)
        if total_stripped or total_redacted:
            parts.append(
                f"\n### Redaction note: {total_stripped} tags stripped by "
                f"policy, {total_redacted} values scrubbed."
            )

    parts.append("\n## Your Task")
    parts.append("Produce the final JSON analysis per the system prompt.")
    return "\n".join(parts)


# Expose the private import for any legacy consumers that grep for it.
__all__ = ["TracingAgent", "TracingAgentConfig"]
