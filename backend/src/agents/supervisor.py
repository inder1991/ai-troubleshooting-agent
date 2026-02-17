import json
import asyncio
import logging
from typing import Optional
from datetime import datetime, timezone

from src.models.schemas import (
    DiagnosticState, DiagnosticStateV5, DiagnosticPhase, Finding, CriticVerdict,
    TokenUsage, TimeWindow, ConfidenceLedger, EvidencePin, ReasoningManifest, ReasoningStep,
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

logger = logging.getLogger(__name__)


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
        )

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

        # Inject connection config into agents that support it
        if agent_name in ("log_agent", "metrics_agent", "k8s_agent", "tracing_agent") and self._connection_config:
            agent = agent_cls(connection_config=self._connection_config)
        else:
            agent = agent_cls()
        context = self._build_agent_context(agent_name, state)

        try:
            result = await agent.run(context, event_emitter)
            # Collect token usage
            state.token_usage.append(agent.get_token_usage())
            return result
        except Exception as e:
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
            base["elk_index"] = "app-logs-*"
            base["timeframe"] = state.time_window.start
            base["trace_id"] = state.trace_id

        elif agent_name == "metrics_agent":
            base["namespace"] = state.namespace or "default"
            if state.log_analysis:
                base["error_patterns"] = state.log_analysis.primary_pattern.model_dump() if state.log_analysis else None

        elif agent_name == "k8s_agent":
            base["namespace"] = state.namespace or "default"
            base["cluster_url"] = state.cluster_url

        elif agent_name == "tracing_agent":
            base["trace_id"] = state.trace_id

        elif agent_name == "code_agent":
            base["repo_path"] = state.repo_url
            if state.log_analysis:
                base["exception_type"] = state.log_analysis.primary_pattern.exception_type
                base["stack_trace"] = ""  # Would come from log analysis

        elif agent_name == "change_agent":
            base["repo_url"] = state.repo_url
            base["namespace"] = state.namespace or "default"
            base["incident_start"] = state.time_window.start
            if self._connection_config:
                base["cli_tool"] = self._connection_config.get("cli_tool", "kubectl")

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
            return f"Log analysis complete — Primary: {pattern_msg[:100]} (confidence: {confidence}%)"
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
