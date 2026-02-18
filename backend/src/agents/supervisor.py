import json
import asyncio
import time
from typing import Optional
from datetime import datetime, timezone

from src.models.schemas import (
    DiagnosticState, DiagnosticStateV5, DiagnosticPhase, Finding, CriticVerdict,
    TokenUsage, TimeWindow, ConfidenceLedger, EvidencePin, ReasoningManifest, ReasoningStep,
    MetricAnomaly, MetricsAnalysisResult, CorrelatedSignalGroup, EventMarker,
    LogAnalysisResult, ErrorPattern, LogEvidence,
)
from src.agents.log_agent import LogAnalysisAgent
from src.agents.metrics_agent import MetricsAgent
from src.agents.k8s_agent import K8sAgent
from src.agents.tracing_agent import TracingAgent
from src.agents.code_agent import CodeNavigatorAgent
from src.agents.change_agent import ChangeAgent
from src.agents.critic_agent import CriticAgent
from src.agents.causal_engine import EvidenceGraphBuilder
from src.agents.impact_analyzer import ImpactAnalyzer
from src.utils.llm_client import AnthropicClient
from src.utils.event_emitter import EventEmitter
from src.utils.logger import get_logger

logger = get_logger(__name__)


def update_confidence_ledger(ledger: ConfidenceLedger, pins: list[EvidencePin]) -> None:
    """Update ledger from evidence pins. Average confidence per type, then compute weighted final."""
    type_map: dict[str, list[float]] = {
        "log": [], "metric": [], "trace": [], "k8s_event": [], "code": [], "change": [],
    }
    for pin in pins:
        if pin.evidence_type in type_map:
            type_map[pin.evidence_type].append(pin.confidence)

    if type_map["log"]:
        ledger.log_confidence = sum(type_map["log"]) / len(type_map["log"])
    if type_map["metric"]:
        ledger.metrics_confidence = sum(type_map["metric"]) / len(type_map["metric"])
    if type_map["trace"]:
        ledger.tracing_confidence = sum(type_map["trace"]) / len(type_map["trace"])
    if type_map["k8s_event"]:
        ledger.k8s_confidence = sum(type_map["k8s_event"]) / len(type_map["k8s_event"])
    if type_map["code"]:
        ledger.code_confidence = sum(type_map["code"]) / len(type_map["code"])
    if type_map["change"]:
        ledger.change_confidence = sum(type_map["change"]) / len(type_map["change"])

    ledger.compute_weighted_final()


def add_reasoning_step(
    manifest: ReasoningManifest,
    decision: str,
    reasoning: str,
    evidence_considered: list[str],
    confidence: float,
    alternatives_rejected: list[str],
) -> None:
    """Append a new reasoning step to the manifest."""
    step = ReasoningStep(
        step_number=len(manifest.steps) + 1,
        timestamp=datetime.now(timezone.utc),
        decision=decision,
        reasoning=reasoning,
        evidence_considered=evidence_considered,
        confidence_at_step=confidence,
        alternatives_rejected=alternatives_rejected,
    )
    manifest.steps.append(step)


class SupervisorAgent:
    """State machine orchestrator that routes work to specialized agents."""

    def __init__(self, connection_config=None):
        self.agent_name = "supervisor"
        self.llm_client = AnthropicClient(agent_name="supervisor")
        self._connection_config = connection_config
        self._agents = {
            "log_agent": LogAnalysisAgent,
            "metrics_agent": MetricsAgent,
            "k8s_agent": K8sAgent,
            "tracing_agent": TracingAgent,
            "code_agent": CodeNavigatorAgent,
            "change_agent": ChangeAgent,
        }
        self._critic = CriticAgent()

    async def run(
        self,
        initial_input: dict,
        event_emitter: EventEmitter,
        websocket_manager=None,
    ) -> DiagnosticState:
        """Run the full diagnostic workflow."""
        state = DiagnosticState(
            session_id=initial_input.get("session_id", "unknown"),
            phase=DiagnosticPhase.INITIAL,
            service_name=initial_input.get("service_name", "unknown"),
            trace_id=initial_input.get("trace_id"),
            time_window=TimeWindow(
                start=initial_input.get("time_start", "now-1h"),
                end=initial_input.get("time_end", "now"),
            ),
            cluster_url=initial_input.get("cluster_url"),
            namespace=initial_input.get("namespace"),
            repo_url=initial_input.get("repo_url"),
            elk_index=initial_input.get("elk_index"),
        )

        logger.info("Session started", extra={"session_id": state.session_id, "agent_name": "supervisor", "action": "session_start", "extra": state.service_name})
        await event_emitter.emit("supervisor", "started", f"Starting diagnosis for {state.service_name}")

        max_rounds = 10
        for round_num in range(max_rounds):
            next_agents = self._decide_next_agents(state)

            if not next_agents:
                # Run impact analysis before marking complete
                await self._run_impact_analysis(state, event_emitter)

                # Query memory store for similar past incidents
                await self._query_past_incidents(state, event_emitter)

                state.phase = DiagnosticPhase.DIAGNOSIS_COMPLETE
                logger.info("Diagnosis complete", extra={"session_id": state.session_id, "agent_name": "supervisor", "action": "diagnosis_complete", "extra": {"overall_confidence": state.overall_confidence, "total_findings": len(state.all_findings)}})
                await event_emitter.emit("supervisor", "success", "Diagnosis complete")

                # Emit attestation gate event
                await event_emitter.emit(
                    "supervisor", "attestation_required",
                    "Human attestation required before proceeding to remediation",
                    details={
                        "gate_type": "discovery_complete",
                        "findings_count": len(state.all_findings),
                        "confidence": state.overall_confidence,
                        "proposed_action": "Proceed to remediation phase",
                    }
                )
                break

            state.agents_pending = next_agents

            # Dispatch agents (parallel if multiple)
            for agent_name in next_agents:
                logger.info("Agent dispatched", extra={"session_id": state.session_id, "agent_name": agent_name, "action": "dispatch", "extra": {"phase": state.phase.value}})
                await event_emitter.emit("supervisor", "progress", f"Dispatching {agent_name}")
                agent_result = await self._dispatch_agent(agent_name, state, event_emitter)

                if agent_result:
                    await self._update_state_with_result(state, agent_name, agent_result, event_emitter)
                    state.agents_completed.append(agent_name)

                    # Emit agent summary
                    summary = self._build_agent_summary(agent_name, agent_result, state)
                    await event_emitter.emit(
                        agent_name, "summary",
                        summary,
                        details={"confidence": state.overall_confidence, "findings_count": len(state.all_findings)}
                    )

                    # Run Critic validation on major findings
                    for finding in state.all_findings:
                        if finding.critic_verdict is None:
                            verdict = self._critic._evaluate_finding(finding)
                            finding.critic_verdict = verdict
                            state.critic_verdicts.append(verdict)
                            logger.info("Critic validation", extra={"session_id": state.session_id, "agent_name": "critic", "action": "verdict", "extra": {"finding": finding.summary[:80], "verdict": verdict.verdict, "confidence": verdict.confidence_in_verdict}})

                            if verdict.verdict == "challenged" and verdict.confidence_in_verdict > 80:
                                await event_emitter.emit(
                                    "critic", "warning",
                                    f"Challenged: {finding.summary} — {verdict.reasoning}"
                                )
                                state.phase = DiagnosticPhase.RE_INVESTIGATING

            self._update_phase(state, event_emitter)

        # Compile token usage
        state.token_usage.append(self.llm_client.get_total_usage())
        state.token_usage.append(self._critic.get_token_usage())

        return state

    async def run_v5(
        self,
        state: DiagnosticStateV5,
        event_emitter: Optional[EventEmitter] = None,
    ) -> DiagnosticStateV5:
        """V5 pipeline with governance, causal intelligence, and confidence tracking."""
        builder = EvidenceGraphBuilder()

        # Reordered dispatch: Metrics -> Tracing -> K8s -> Log -> Code
        agent_order = ["metrics_agent", "tracing_agent", "k8s_agent", "log_agent", "code_agent"]

        for agent_name in agent_order:
            if agent_name not in self._agents:
                continue

            # Record reasoning step
            add_reasoning_step(
                state.reasoning_manifest,
                decision=f"dispatch_{agent_name}",
                reasoning=f"Dispatching {agent_name} per v5 telemetry pivot priority",
                evidence_considered=[p.claim for p in state.evidence_pins[-3:]],
                confidence=state.confidence_ledger.weighted_final,
                alternatives_rejected=[],
            )

            # Dispatch agent
            result = await self._dispatch_agent(agent_name, state, event_emitter)

            if result:
                # Extract evidence pins from result
                pins_data = result.get("evidence_pins", [])
                for pin_data in pins_data:
                    try:
                        pin = EvidencePin(**pin_data) if isinstance(pin_data, dict) else pin_data
                        state.evidence_pins.append(pin)
                        builder.add_evidence(pin, node_type="symptom")
                    except Exception:
                        pass

                # Update confidence ledger
                update_confidence_ledger(state.confidence_ledger, state.evidence_pins)

            state.agents_completed.append(agent_name)

        # Build causal graph
        builder.identify_root_causes()
        state.evidence_graph = builder.graph
        state.incident_timeline = builder.build_timeline()

        return state

    def _decide_next_agents(self, state: DiagnosticState) -> list[str]:
        """Decide which agents to dispatch based on current state."""
        if state.phase == DiagnosticPhase.INITIAL:
            return ["log_agent"]

        if state.phase == DiagnosticPhase.LOGS_ANALYZED:
            agents = ["metrics_agent"]
            # If we have cluster info, dispatch K8s agent in parallel
            if state.cluster_url or state.namespace:
                agents.append("k8s_agent")
            # Dispatch change agent if repo_url is available
            if state.repo_url and "change_agent" not in state.agents_completed:
                agents.append("change_agent")
            return agents

        if state.phase == DiagnosticPhase.METRICS_ANALYZED:
            agents = []
            if state.trace_id and "tracing_agent" not in state.agents_completed:
                agents.append("tracing_agent")
            if "k8s_agent" not in state.agents_completed and (state.cluster_url or state.namespace):
                agents.append("k8s_agent")
            if not agents and state.repo_url and "code_agent" not in state.agents_completed:
                agents.append("code_agent")
            return agents

        if state.phase == DiagnosticPhase.K8S_ANALYZED:
            agents = []
            if state.trace_id and "tracing_agent" not in state.agents_completed:
                agents.append("tracing_agent")
            if state.repo_url and "code_agent" not in state.agents_completed:
                agents.append("code_agent")
            return agents

        if state.phase == DiagnosticPhase.TRACING_ANALYZED:
            if state.repo_url and "code_agent" not in state.agents_completed:
                return ["code_agent"]
            return []

        if state.phase == DiagnosticPhase.CODE_ANALYZED:
            return []

        if state.phase == DiagnosticPhase.DIAGNOSIS_COMPLETE:
            return []

        return []

    def _decide_action_for_confidence(self, state: DiagnosticState) -> str:
        """Decide action based on overall confidence score."""
        if state.overall_confidence >= 70:
            return "proceed"
        elif state.overall_confidence >= 50:
            return "ask_user"
        else:
            return "ask_user"

    async def _dispatch_agent(
        self, agent_name: str, state: DiagnosticState, event_emitter: Optional[EventEmitter] = None
    ) -> Optional[dict]:
        """Dispatch a specialized agent and return its result."""
        agent_cls = self._agents.get(agent_name)
        if not agent_cls:
            return None

        # Inject connection config into agents whose constructors accept it
        import inspect
        if self._connection_config and "connection_config" in inspect.signature(agent_cls.__init__).parameters:
            agent = agent_cls(connection_config=self._connection_config)
        else:
            agent = agent_cls()
        context = self._build_agent_context(agent_name, state)

        start = time.monotonic()
        try:
            result = await agent.run(context, event_emitter)
            elapsed_ms = round((time.monotonic() - start) * 1000)
            # Collect token usage
            state.token_usage.append(agent.get_token_usage())
            logger.info("Agent completed", extra={"session_id": getattr(state, 'session_id', ''), "agent_name": agent_name, "action": "agent_complete", "extra": {"confidence": result.get("overall_confidence", 0), "findings": len(result.get("evidence_pins", []))}, "duration_ms": elapsed_ms})
            return result
        except Exception as e:
            logger.error("Agent failed", extra={"session_id": getattr(state, 'session_id', ''), "agent_name": agent_name, "action": "agent_error", "extra": str(e)})
            if event_emitter:
                await event_emitter.emit(agent_name, "error", f"Agent failed: {str(e)}")
            return None

    def _build_agent_context(self, agent_name: str, state: DiagnosticState) -> dict:
        """Build context dict for a specific agent."""
        base = {
            "service_name": state.service_name,
            "time_window": {"start": state.time_window.start, "end": state.time_window.end},
        }

        if agent_name == "log_agent":
            base["elk_index"] = state.elk_index or "*"
            base["timeframe"] = state.time_window.start
            base["trace_id"] = state.trace_id

        elif agent_name == "metrics_agent":
            base["namespace"] = state.namespace or "default"
            if state.log_analysis:
                base["error_patterns"] = state.log_analysis.primary_pattern.model_dump() if state.log_analysis.primary_pattern else None
                # Extract error hints for USE-method saturation queries
                error_hints = []
                if state.log_analysis.primary_pattern:
                    exc = (state.log_analysis.primary_pattern.exception_type or "").lower()
                    msg = (state.log_analysis.primary_pattern.error_message or "").lower()
                    combined = f"{exc} {msg}"
                    if "oom" in combined or "memory" in combined:
                        error_hints.append("oom")
                    if "pool" in combined or "connection" in combined:
                        error_hints.append("connectionpool")
                    if "timeout" in combined:
                        error_hints.append("timeout")
                    if "disk" in combined or "storage" in combined:
                        error_hints.append("disk")
                base["error_hints"] = error_hints

        elif agent_name == "k8s_agent":
            base["namespace"] = state.namespace or "default"
            base["cluster_url"] = state.cluster_url

        elif agent_name == "tracing_agent":
            base["trace_id"] = state.trace_id

        elif agent_name == "code_agent":
            base["repo_path"] = state.repo_url
            if state.log_analysis and state.log_analysis.primary_pattern:
                base["exception_type"] = state.log_analysis.primary_pattern.exception_type
                # Extract stack trace from sample logs if available
                stack_trace = ""
                for sample in state.log_analysis.primary_pattern.sample_logs:
                    if sample.raw_line and len(sample.raw_line) > len(stack_trace):
                        stack_trace = sample.raw_line
                base["stack_trace"] = stack_trace

        elif agent_name == "change_agent":
            base["repo_url"] = state.repo_url
            base["namespace"] = state.namespace or "default"
            base["incident_start"] = state.time_window.start
            if self._connection_config:
                cluster_type = getattr(self._connection_config, "cluster_type", "kubernetes")
                base["cli_tool"] = "oc" if cluster_type == "openshift" else "kubectl"

        return base

    async def _update_state_with_result(
        self, state: DiagnosticState, agent_name: str, result: dict,
        event_emitter: Optional[EventEmitter] = None,
    ) -> None:
        """Update DiagnosticState with agent results."""
        # Store breadcrumbs and negative findings
        for b_dict in result.get("breadcrumbs", []):
            try:
                from src.models.schemas import Breadcrumb
                b = Breadcrumb(**b_dict) if isinstance(b_dict, dict) else b_dict
                state.all_breadcrumbs.append(b)
            except Exception:
                pass

        for nf_dict in result.get("negative_findings", []):
            try:
                from src.models.schemas import NegativeFinding
                nf = NegativeFinding(**nf_dict) if isinstance(nf_dict, dict) else nf_dict
                state.all_negative_findings.append(nf)
            except Exception:
                pass

        # Update confidence
        confidence = result.get("overall_confidence", 50)
        # Running weighted average
        if state.overall_confidence == 0:
            state.overall_confidence = min(confidence, 100)
        else:
            state.overall_confidence = min((state.overall_confidence + confidence) // 2, 100)

        # Add findings
        if agent_name == "log_agent" and result.get("primary_pattern"):
            pattern = result["primary_pattern"]
            if isinstance(pattern, dict) and pattern.get("exception_type"):
                state.all_findings.append(Finding(
                    finding_id=f"log_{pattern.get('pattern_id', '1')}",
                    agent_name="log_agent",
                    category=pattern.get("exception_type", "unknown"),
                    summary=pattern.get("error_message", ""),
                    confidence_score=min(pattern.get("confidence_score", 50), 100),
                    severity=pattern.get("severity", "medium"),
                    breadcrumbs=[],
                    negative_findings=[],
                ))

                # Emit finding discovery event
                if event_emitter:
                    await event_emitter.emit(
                        agent_name, "finding",
                        f"Found: {pattern.get('exception_type', 'Error')} — {pattern.get('error_message', '')[:120]}",
                        details={
                            "severity": pattern.get("severity", "medium"),
                            "confidence": min(pattern.get("confidence_score", 50), 100),
                            "category": pattern.get("exception_type", "unknown"),
                        }
                    )

        # Store service flow from log agent
        if agent_name == "log_agent":
            service_flow = result.get("service_flow", [])
            if service_flow:
                state.service_flow = service_flow
                state.flow_source = result.get("flow_source", "elasticsearch")
                state.flow_confidence = result.get("flow_confidence", 0)
                if event_emitter:
                    services_in_flow = list(dict.fromkeys(s["service"] for s in service_flow))
                    await event_emitter.emit(
                        "log_agent", "finding",
                        f"Flow reconstructed: {' → '.join(services_in_flow)} ({len(service_flow)} steps)",
                        details={"type": "service_flow", "services": services_in_flow}
                    )

        # Populate state.log_analysis from log_agent result
        if agent_name == "log_agent":
            primary_raw = result.get("primary_pattern", {})
            if isinstance(primary_raw, dict) and primary_raw.get("exception_type"):
                try:
                    # Ensure sample_logs is a list of LogEvidence (LLM may omit it)
                    sample_logs_raw = primary_raw.get("sample_logs", [])
                    sample_logs = []
                    for sl in sample_logs_raw:
                        try:
                            sample_logs.append(LogEvidence(**sl) if isinstance(sl, dict) else sl)
                        except Exception:
                            pass

                    primary = ErrorPattern(
                        pattern_id=primary_raw.get("pattern_id", "p1"),
                        exception_type=primary_raw.get("exception_type", "UnknownError"),
                        error_message=primary_raw.get("error_message", ""),
                        frequency=primary_raw.get("frequency", 1),
                        severity=primary_raw.get("severity", "medium"),
                        affected_components=primary_raw.get("affected_components", []),
                        sample_logs=sample_logs,
                        confidence_score=min(primary_raw.get("confidence_score", 50), 100),
                        priority_rank=primary_raw.get("priority_rank", 1),
                        priority_reasoning=primary_raw.get("priority_reasoning", ""),
                    )

                    secondary = []
                    for sp_raw in result.get("secondary_patterns", []):
                        try:
                            sp_samples = []
                            for sl in sp_raw.get("sample_logs", []):
                                try:
                                    sp_samples.append(LogEvidence(**sl) if isinstance(sl, dict) else sl)
                                except Exception:
                                    pass
                            secondary.append(ErrorPattern(
                                pattern_id=sp_raw.get("pattern_id", f"s{len(secondary)+1}"),
                                exception_type=sp_raw.get("exception_type", "UnknownError"),
                                error_message=sp_raw.get("error_message", ""),
                                frequency=sp_raw.get("frequency", 1),
                                severity=sp_raw.get("severity", "medium"),
                                affected_components=sp_raw.get("affected_components", []),
                                sample_logs=sp_samples,
                                confidence_score=min(sp_raw.get("confidence_score", 50), 100),
                                priority_rank=sp_raw.get("priority_rank", len(secondary) + 2),
                                priority_reasoning=sp_raw.get("priority_reasoning", ""),
                            ))
                        except Exception:
                            pass

                    # Parse tokens_used from result
                    tu_raw = result.get("tokens_used", {})
                    tokens = TokenUsage(
                        agent_name="log_agent",
                        input_tokens=tu_raw.get("input_tokens", 0),
                        output_tokens=tu_raw.get("output_tokens", 0),
                        total_tokens=tu_raw.get("total_tokens", 0),
                    )

                    state.log_analysis = LogAnalysisResult(
                        primary_pattern=primary,
                        secondary_patterns=secondary,
                        negative_findings=[nf for nf in state.all_negative_findings if nf.agent_name == "log_agent"],
                        breadcrumbs=[b for b in state.all_breadcrumbs if b.agent_name == "log_agent"],
                        overall_confidence=min(result.get("overall_confidence", 50), 100),
                        tokens_used=tokens,
                    )
                except Exception as e:
                    logger.warning("Failed to build LogAnalysisResult: %s", e)

        # Handle change_agent results
        if agent_name == "change_agent":
            state.change_analysis = result
            correlations = result.get("change_correlations", [])
            if correlations and event_emitter:
                for corr in correlations[:3]:
                    desc = corr.get("description", corr.get("sha", "unknown"))
                    score = corr.get("correlation_score", corr.get("risk_score", "N/A"))
                    await event_emitter.emit(
                        agent_name, "finding",
                        f"Change detected: {desc} — correlation: {score}",
                        details={"type": "change_correlation", **corr}
                    )

        # Handle metrics_agent results
        if agent_name == "metrics_agent":
            anomalies_raw = result.get("anomalies", [])
            anomalies = []
            for a in anomalies_raw:
                try:
                    anomalies.append(MetricAnomaly(**a) if isinstance(a, dict) else a)
                except Exception:
                    pass

            correlated_raw = result.get("correlated_signals", [])
            correlated = []
            for cs in correlated_raw:
                try:
                    correlated.append(CorrelatedSignalGroup(**cs) if isinstance(cs, dict) else cs)
                except Exception:
                    pass

            # Parse time_series_data from agent result
            ts_data_raw = result.get("time_series_data", {})
            ts_data: dict = {}
            from src.models.schemas import DataPoint
            for key, points in ts_data_raw.items():
                parsed_points = []
                for pt in points:
                    try:
                        parsed_points.append(DataPoint(**pt) if isinstance(pt, dict) else pt)
                    except Exception:
                        pass
                if parsed_points:
                    ts_data[key] = parsed_points

            # Parse tokens_used from result
            tu_raw = result.get("tokens_used", {})
            if isinstance(tu_raw, dict) and tu_raw.get("total_tokens", 0) > 0:
                metrics_tokens = TokenUsage(
                    agent_name="metrics_agent",
                    input_tokens=tu_raw.get("input_tokens", 0),
                    output_tokens=tu_raw.get("output_tokens", 0),
                    total_tokens=tu_raw.get("total_tokens", 0),
                )
            else:
                metrics_tokens = TokenUsage(agent_name="metrics_agent", input_tokens=0, output_tokens=0, total_tokens=0)

            state.metrics_analysis = MetricsAnalysisResult(
                anomalies=anomalies,
                correlated_signals=correlated,
                time_series_data=ts_data,
                chart_highlights=[],
                negative_findings=[nf for nf in state.all_negative_findings if nf.agent_name == "metrics_agent"],
                breadcrumbs=[b for b in state.all_breadcrumbs if b.agent_name == "metrics_agent"],
                overall_confidence=min(result.get("overall_confidence", 50), 100),
                tokens_used=metrics_tokens,
            )

            # Build event markers from log analysis
            event_markers = []
            if state.log_analysis and state.log_analysis.primary_pattern:
                pattern = state.log_analysis.primary_pattern
                if pattern.sample_logs:
                    first_log = pattern.sample_logs[0]
                    event_markers.append(EventMarker(
                        timestamp=first_log.timestamp,
                        label=f"First: {pattern.exception_type or 'error'}",
                        source="log_agent",
                        severity=pattern.severity or "medium",
                    ))
            for b in state.all_breadcrumbs:
                if b.agent_name == "log_agent" and b.timestamp:
                    if any(kw in b.action.lower() for kw in ("error", "exception", "failure", "timeout")):
                        event_markers.append(EventMarker(
                            timestamp=b.timestamp,
                            label=b.action[:60],
                            source=b.agent_name,
                        ))
            state.metrics_analysis.event_markers = event_markers[:10]

            # Promote critical/high anomalies to Findings
            for a in anomalies:
                if a.severity in ("critical", "high"):
                    state.all_findings.append(Finding(
                        finding_id=f"metric_{a.metric_name}",
                        agent_name="metrics_agent",
                        category="metric_anomaly",
                        summary=f"{a.metric_name}: peak {a.peak_value} vs baseline {a.baseline_value} — {a.correlation_to_incident}",
                        confidence_score=min(a.confidence_score, 100),
                        severity=a.severity,
                        breadcrumbs=[],
                        negative_findings=[],
                    ))

            if event_emitter and anomalies:
                severity_counts: dict[str, int] = {}
                for a in anomalies:
                    severity_counts[a.severity] = severity_counts.get(a.severity, 0) + 1
                await event_emitter.emit(
                    "metrics_agent", "finding",
                    f"Found {len(anomalies)} metric anomalies",
                    details={"anomaly_count": len(anomalies), "severity_breakdown": severity_counts}
                )

        # Store reasoning
        state.supervisor_reasoning.append(
            f"Round: {agent_name} completed with confidence {confidence}"
        )

    def _update_phase(self, state: DiagnosticState, event_emitter: Optional[EventEmitter] = None) -> None:
        """Update diagnostic phase based on completed agents."""
        old_phase = state.phase
        completed = set(state.agents_completed)

        if "code_agent" in completed:
            state.phase = DiagnosticPhase.CODE_ANALYZED
        elif "tracing_agent" in completed:
            state.phase = DiagnosticPhase.TRACING_ANALYZED
        elif "k8s_agent" in completed and "metrics_agent" in completed:
            state.phase = DiagnosticPhase.K8S_ANALYZED
        elif "metrics_agent" in completed:
            state.phase = DiagnosticPhase.METRICS_ANALYZED
        elif "log_agent" in completed:
            state.phase = DiagnosticPhase.LOGS_ANALYZED
        # change_agent runs in parallel and doesn't gate phase transitions

        if state.phase != old_phase:
            logger.info("Phase transition", extra={"session_id": state.session_id, "agent_name": "supervisor", "action": "phase_transition", "extra": {"from": old_phase.value, "to": state.phase.value}})
        if state.phase != old_phase and event_emitter:
            asyncio.ensure_future(event_emitter.emit(
                "supervisor", "phase_change",
                f"Phase: {state.phase.value.replace('_', ' ').title()}",
                details={"phase": state.phase.value, "previous_phase": old_phase.value}
            ))

    def _build_agent_summary(self, agent_name: str, result: dict, state: DiagnosticState) -> str:
        """Build a human-readable summary of agent completion."""
        confidence = result.get("overall_confidence", 0)
        if agent_name == "log_agent":
            primary = result.get("primary_pattern", {})
            pattern_msg = primary.get("error_message", "No pattern found") if isinstance(primary, dict) else "No pattern found"
            flow = result.get("service_flow", [])
            flow_part = f", flow: {len(flow)} steps across {len(set(s['service'] for s in flow))} services" if flow else ""
            return f"Log analysis complete — Primary: {pattern_msg[:100]}{flow_part} (confidence: {confidence}%)"
        elif agent_name == "metrics_agent":
            anomalies = result.get("anomalies", [])
            return f"Metrics analysis complete — {len(anomalies)} anomalies detected (confidence: {confidence}%)"
        elif agent_name == "k8s_agent":
            pods = result.get("pod_statuses", [])
            events = result.get("events", [])
            return f"K8s analysis complete — {len(pods)} pods checked, {len(events)} events (confidence: {confidence}%)"
        elif agent_name == "tracing_agent":
            spans = result.get("spans", [])
            return f"Trace analysis complete — {len(spans)} spans analyzed (confidence: {confidence}%)"
        elif agent_name == "code_agent":
            files = result.get("impacted_files", [])
            return f"Code analysis complete — {len(files)} files impacted (confidence: {confidence}%)"
        elif agent_name == "change_agent":
            correlations = result.get("change_correlations", [])
            return f"Change analysis complete — {len(correlations)} correlated changes found (confidence: {confidence}%)"
        return f"{agent_name} completed (confidence: {confidence}%)"

    async def _run_impact_analysis(
        self, state: DiagnosticState, event_emitter: EventEmitter
    ) -> None:
        """Run blast radius and severity analysis after all agents complete."""
        try:
            analyzer = ImpactAnalyzer()

            upstream, downstream, shared = [], [], []
            if state.trace_analysis and state.trace_analysis.service_dependency_graph:
                graph = state.trace_analysis.service_dependency_graph
                for svc, deps in graph.items():
                    if state.service_name in deps:
                        upstream.append(svc)
                    elif svc == state.service_name:
                        downstream.extend(deps)
                shared = list(set(upstream) & set(downstream))

            blast_radius = analyzer.estimate_blast_radius(
                primary_service=state.service_name,
                upstream=upstream,
                downstream=downstream,
                shared=shared,
            )
            severity = analyzer.recommend_severity(state.service_name, blast_radius)

            state.blast_radius_result = blast_radius
            state.severity_result = severity

            total_affected = len(blast_radius.upstream_affected) + len(blast_radius.downstream_affected)
            await event_emitter.emit(
                "supervisor", "finding",
                f"Impact: {severity.recommended_severity} — {blast_radius.scope} blast radius, {total_affected} services affected",
                details={
                    "type": "blast_radius",
                    "severity": severity.recommended_severity,
                    "scope": blast_radius.scope,
                    "affected_count": total_affected,
                }
            )
        except Exception as e:
            logger.warning("Impact analysis failed: %s", e)

    async def _query_past_incidents(
        self, state: DiagnosticState, event_emitter: EventEmitter
    ) -> None:
        """Query memory store for similar past incidents."""
        try:
            from src.memory.store import MemoryStore
            from src.memory.models import IncidentFingerprint

            memory = MemoryStore()

            current_fp = IncidentFingerprint(
                session_id=state.session_id,
                error_patterns=[f.category for f in state.all_findings],
                affected_services=[state.service_name],
                affected_namespaces=[state.namespace] if state.namespace else [],
                symptom_categories=[f.summary[:50] for f in state.all_findings],
            )

            similar_incidents = memory.find_similar(current_fp, threshold=0.4)

            if similar_incidents:
                state.past_incidents = [
                    {
                        "fingerprint_id": si.fingerprint.fingerprint_id,
                        "session_id": si.fingerprint.session_id,
                        "similarity_score": si.similarity_score,
                        "root_cause": si.fingerprint.root_cause,
                        "resolution_steps": si.fingerprint.resolution_steps,
                        "error_patterns": si.fingerprint.error_patterns,
                        "affected_services": si.fingerprint.affected_services,
                        "time_to_resolve": si.fingerprint.time_to_resolve,
                    }
                    for si in similar_incidents
                ]
                top = similar_incidents[0]
                await event_emitter.emit(
                    "supervisor", "finding",
                    f"Found {len(similar_incidents)} similar past incidents — top match: {top.fingerprint.root_cause or 'unknown'} ({top.similarity_score:.0%})",
                    details={"type": "past_incidents", "count": len(similar_incidents)}
                )
        except Exception as e:
            logger.warning("Past incident query failed: %s", e)

    async def handle_user_message(self, message: str, state: DiagnosticState) -> str:
        """Handle a user message during analysis."""
        response = await self.llm_client.chat(
            prompt=f"""Current diagnostic state:
- Phase: {state.phase.value}
- Service: {state.service_name}
- Agents completed: {state.agents_completed}
- Overall confidence: {state.overall_confidence}%
- Findings so far: {len(state.all_findings)}

User message: {message}

Respond helpfully. If they're asking for status, give a brief update. If they're providing additional context, acknowledge it.""",
            system="You are an AI SRE assistant. Respond concisely to user messages during an active diagnosis."
        )
        return response.text
