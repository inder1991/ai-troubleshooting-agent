import json
import asyncio
import time
import secrets
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

from src.models.schemas import (
    DiagnosticState, DiagnosticStateV5, DiagnosticPhase, Finding, CriticVerdict,
    TokenUsage, TimeWindow, ConfidenceLedger, EvidencePin, ReasoningManifest, ReasoningStep,
    MetricAnomaly, MetricsAnalysisResult, CorrelatedSignalGroup, EventMarker,
    LogAnalysisResult, ErrorPattern, LogEvidence,
    K8sAnalysisResult, PodHealthStatus, K8sEvent,
    TraceAnalysisResult, SpanInfo,
    CodeAnalysisResult, ImpactedFile, LineRange, FixArea, DiffAnalysisItem,
    Breadcrumb, NegativeFinding, DataPoint,
    FixStatus, FixResult,
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


def generate_incident_id() -> str:
    """Generate a human-friendly incident ID like INC-20250219-A3F7."""
    date_part = datetime.now(timezone.utc).strftime("%Y%m%d")
    rand_part = secrets.token_hex(2).upper()
    return f"INC-{date_part}-{rand_part}"


class SupervisorAgent:
    """State machine orchestrator that routes work to specialized agents."""

    @staticmethod
    def _extract_file_paths_from_traces(traces: list[str]) -> list[str]:
        """Extract file paths from stack trace strings."""
        import re
        paths = set()
        for trace in traces:
            # Python: File "path/to/file.py", line 42
            for m in re.finditer(r'File\s+"([^"]+\.py)"', trace):
                paths.add(m.group(1))
            # Java: at com.example.Foo (Foo.java:42)
            for m in re.finditer(r'\((\w+\.java):\d+\)', trace):
                paths.add(m.group(1))
            # Node/TS: at fn (/path/to/file.ts:42:10)
            for m in re.finditer(r'at\s+.*?\((.+?\.[tj]sx?):\d+', trace):
                paths.add(m.group(1))
            # Generic: src/service/handler.py
            for m in re.finditer(r'([\w/.-]+\.(?:py|java|ts|js|go|rs|rb))', trace):
                paths.add(m.group(1))
        return sorted(paths)

    def __init__(self, connection_config=None):
        self.agent_name = "supervisor"
        # Resolve model from config/env for supervisor's own LLM usage
        supervisor_model = ""
        if connection_config:
            overrides = dict(getattr(connection_config, 'llm_model_overrides', ()))
            supervisor_model = overrides.get("supervisor", "")
            if not supervisor_model:
                supervisor_model = getattr(connection_config, 'llm_model', "")
        if not supervisor_model:
            import os
            supervisor_model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        self.llm_client = AnthropicClient(agent_name="supervisor", model=supervisor_model)
        self._connection_config = connection_config
        self._agents = {
            "log_agent": LogAnalysisAgent,
            "metrics_agent": MetricsAgent,
            "k8s_agent": K8sAgent,
            "change_agent": ChangeAgent,
            # "tracing_agent": TracingAgent,
            "code_agent": CodeNavigatorAgent,
        }
        self._critic = CriticAgent()

        # Human-in-the-loop: repo URL confirmation for change_agent
        self._repo_confirmation_event = asyncio.Event()
        self._pending_repo_confirmation = False
        self._candidate_repos: dict[str, str] = {}
        self._confirmed_repo_map: dict[str, str] = {}

        # Human-in-the-loop: repo mismatch detection for code_agent
        self._repo_mismatch_event = asyncio.Event()
        self._pending_repo_mismatch = False
        self._mismatch_confirmed_repo: str | None = None

        # Human-in-the-loop: fix approval
        self._fix_event = asyncio.Event()
        self._pending_fix_approval = False
        self._fix_human_decision: str | None = None
        self._event_emitter: Optional[EventEmitter] = None

        # Human-in-the-loop: discovery attestation
        self._attestation_acknowledged = False

        # Human-in-the-loop channel for code_agent questions
        self._code_agent_question: str = ""
        self._code_agent_answer: str = ""
        self._code_agent_event = asyncio.Event()
        self._pending_code_agent_question = False

    async def run(
        self,
        initial_input: dict,
        event_emitter: EventEmitter,
        websocket_manager=None,
        on_state_created=None,
    ) -> DiagnosticState:
        """Run the full diagnostic workflow."""
        self._event_emitter = event_emitter
        state = DiagnosticState(
            session_id=initial_input.get("session_id", "unknown"),
            incident_id=initial_input.get("incident_id") or generate_incident_id(),
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

        # Expose state immediately so API endpoints can read partial results
        if on_state_created:
            on_state_created(state)

        logger.info("Session started", extra={"session_id": state.session_id, "incident_id": state.incident_id, "agent_name": "supervisor", "action": "session_start", "extra": state.service_name})
        await event_emitter.emit("supervisor", "started", f"Starting diagnosis for {state.service_name} [{state.incident_id}]")

        max_rounds = 10
        re_investigation_count = 0
        max_re_investigations = 1  # Allow at most 1 re-investigation cycle
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

            # Dispatch agents in parallel
            for agent_name in next_agents:
                logger.info("Agent dispatched", extra={"session_id": state.session_id, "agent_name": agent_name, "action": "dispatch", "extra": {"phase": state.phase.value}})
                await event_emitter.emit("supervisor", "progress", f"Dispatching {agent_name}")

            if len(next_agents) > 1:
                results = await asyncio.gather(
                    *(self._dispatch_agent(name, state, event_emitter) for name in next_agents),
                    return_exceptions=True,
                )
                agent_results = list(zip(next_agents, results))
            else:
                r = await self._dispatch_agent(next_agents[0], state, event_emitter)
                agent_results = [(next_agents[0], r)]

            for agent_name, agent_result in agent_results:
                if isinstance(agent_result, Exception):
                    logger.error("Agent raised exception", extra={"agent_name": agent_name, "extra": str(agent_result)})
                    # C2: Mark failed agent as completed to prevent infinite re-dispatch
                    state.agents_completed.append(agent_name)
                    if event_emitter:
                        await event_emitter.emit(agent_name, "error", f"Agent failed: {str(agent_result)}")
                    continue
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
                            # Build agent contexts for cross-validation
                            metrics_ctx = {}
                            if state.metrics_analysis:
                                for a in state.metrics_analysis.anomalies:
                                    metrics_ctx[a.metric_name] = {"value": a.peak_value, "status": a.severity}
                            k8s_ctx = {}
                            if state.k8s_analysis:
                                k8s_ctx["oom_kills"] = sum(1 for p in state.k8s_analysis.pod_statuses if p.oom_killed)
                                k8s_ctx["memory_percent"] = 0
                                k8s_ctx["crashloop"] = state.k8s_analysis.is_crashloop
                            verdict = self._critic._evaluate_finding(
                                finding, metrics_context=metrics_ctx, k8s_context=k8s_ctx,
                            )
                            finding.critic_verdict = verdict
                            state.critic_verdicts.append(verdict)
                            logger.info("Critic validation", extra={"session_id": state.session_id, "agent_name": "critic", "action": "verdict", "extra": {"finding": finding.summary[:80], "verdict": verdict.verdict, "confidence": verdict.confidence_in_verdict}})

                            if verdict.verdict == "challenged" and verdict.confidence_in_verdict > 80:
                                await event_emitter.emit(
                                    "critic", "warning",
                                    f"Challenged: {finding.summary} — {verdict.reasoning}"
                                )
                                if re_investigation_count < max_re_investigations:
                                    state.phase = DiagnosticPhase.RE_INVESTIGATING
                                    re_investigation_count += 1
                                else:
                                    logger.warning("Max re-investigations reached, proceeding to diagnosis", extra={
                                        "session_id": state.session_id, "agent_name": "supervisor",
                                        "action": "re_investigation_capped",
                                        "extra": {"re_investigation_count": re_investigation_count}
                                    })

            self._update_phase(state, event_emitter)

            # Enrich reasoning chain after metrics analysis completes (skip if mocked — no point reasoning over fixture data)
            import os as _os
            _mock_agents = [a.strip() for a in _os.getenv("MOCK_AGENTS", "").split(",") if a.strip()]
            if "metrics_agent" in [n for n, _ in agent_results if not isinstance(_, Exception)] and "metrics_agent" not in _mock_agents:
                await self._enrich_reasoning_chain(state, event_emitter)

            # Human-in-the-loop: ask user to confirm repos before dispatching change_agent
            if (
                "change_agent" in self._agents
                and "change_agent" not in state.agents_completed
                and "metrics_agent" in state.agents_completed
            ):
                await self._request_repo_confirmation(state, event_emitter)
                # Ensure change_agent is marked complete regardless of outcome
                # (timeout, skip, no affected services) to prevent re-dispatch
                if "change_agent" not in state.agents_completed:
                    state.agents_completed.append("change_agent")

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

        # Reordered dispatch: Metrics -> Tracing -> K8s -> Log -> Code -> Change
        agent_order = ["metrics_agent", "tracing_agent", "k8s_agent", "log_agent", "code_agent", "change_agent"]

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

                # Populate typed agent analysis on state
                await self._update_state_with_result(state, agent_name, result, event_emitter)

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
            # change_agent is dispatched separately via human-in-the-loop repo confirmation
            return agents

        if state.phase == DiagnosticPhase.METRICS_ANALYZED:
            agents = []
            # Only dispatch agents that are actually registered in self._agents
            if state.trace_id and "tracing_agent" not in state.agents_completed and "tracing_agent" in self._agents:
                agents.append("tracing_agent")
            if "k8s_agent" not in state.agents_completed and (state.cluster_url or state.namespace):
                agents.append("k8s_agent")
            if not agents and state.repo_url and "code_agent" not in state.agents_completed:
                agents.append("code_agent")
            return agents

        if state.phase == DiagnosticPhase.K8S_ANALYZED:
            agents = []
            if state.trace_id and "tracing_agent" not in state.agents_completed and "tracing_agent" in self._agents:
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

        if state.phase == DiagnosticPhase.RE_INVESTIGATING:
            # Re-dispatch the challenged agent's domain, then advance phase
            agents = []
            for cv in state.critic_verdicts:
                if cv.verdict == "challenged" and cv.confidence_in_verdict > 80:
                    challenged_agent = cv.agent_source
                    if challenged_agent in self._agents and challenged_agent not in agents:
                        agents.append(challenged_agent)
            # After re-dispatch, reset phase so _update_phase can advance normally
            # This prevents staying locked in RE_INVESTIGATING forever
            if not agents:
                state.phase = DiagnosticPhase.DIAGNOSIS_COMPLETE
            return agents

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

    def _check_prerequisites(self, agent_name: str, state: DiagnosticState) -> str | None:
        """Return skip reason if agent's data sources are unavailable, else None."""
        cfg = self._connection_config

        if agent_name == "code_agent":
            repo = getattr(state, "repo_url", None)
            if not repo or not repo.strip():
                return "No repository URL configured — skipping code analysis"
            if not repo.startswith(("http://", "https://", "git@", "ssh://")) and not Path(repo).is_dir():
                return f"Repository path does not exist: {repo} — skipping code analysis"
            if repo.startswith(("http://", "https://", "git@")):
                import os
                cfg_token = bool(cfg and cfg.github_token) if cfg else False
                env_token = bool(os.getenv("GITHUB_TOKEN"))
                logger.info("code_agent token check", extra={
                    "agent_name": agent_name, "action": "prereq_check",
                    "extra": {"cfg_token": cfg_token, "env_token": env_token, "has_cfg": cfg is not None},
                })
                if not cfg_token and not env_token:
                    return "No GitHub token configured (add via Integrations or GITHUB_TOKEN env var) — skipping code analysis"

        if agent_name == "change_agent":
            has_repo = getattr(state, "repo_url", None) and state.repo_url.strip()
            has_cluster = cfg and cfg.cluster_url
            if not has_repo and not has_cluster:
                return "No repo URL or cluster configured — skipping change correlation"

        if agent_name == "k8s_agent":
            import os
            has_cluster_config = (cfg and cfg.cluster_url) or os.getenv("OPENSHIFT_API_URL") or os.getenv("KUBECONFIG") or Path.home().joinpath(".kube/config").exists()
            if not has_cluster_config:
                return "No cluster URL or kubeconfig found — skipping K8s analysis"

        if agent_name == "metrics_agent":
            if not cfg or not cfg.prometheus_url:
                return "No Prometheus URL configured — skipping metrics analysis"

        if agent_name == "tracing_agent":
            has_jaeger = cfg and cfg.jaeger_url
            has_elk = cfg and cfg.elasticsearch_url
            has_trace_id = getattr(state, "trace_id", None)
            if not has_trace_id and not has_jaeger and not has_elk:
                return "No trace_id or tracing endpoints configured — skipping"

        return None

    _MOCK_FIXTURES_DIR = Path(__file__).parent / "fixtures"

    async def _dispatch_agent(
        self, agent_name: str, state: DiagnosticState, event_emitter: Optional[EventEmitter] = None
    ) -> Optional[dict]:
        """Dispatch a specialized agent and return its result."""
        # Mock mode: return fixture data instead of running the real agent
        import os
        mock_agents = [a.strip() for a in os.getenv("MOCK_AGENTS", "").split(",") if a.strip()]
        if agent_name in mock_agents:
            fixture_path = self._MOCK_FIXTURES_DIR / f"{agent_name}_mock.json"
            if fixture_path.exists():
                logger.info("Agent mocked", extra={
                    "agent_name": agent_name, "action": "mocked",
                    "extra": str(fixture_path),
                })
                if event_emitter:
                    await event_emitter.emit(agent_name, "started", f"{agent_name} (MOCKED)")
                    await event_emitter.emit(agent_name, "success", f"{agent_name} completed (mocked fixture)")
                return json.loads(fixture_path.read_text())

        # Repo mismatch check for code_agent
        if agent_name == "code_agent" and state.patient_zero:
            await self._check_repo_mismatch(state, event_emitter)

        # Check prerequisites before dispatching
        skip_reason = self._check_prerequisites(agent_name, state)
        if skip_reason:
            logger.warning("Agent skipped due to missing prerequisites", extra={
                "session_id": getattr(state, 'session_id', ''),
                "agent_name": agent_name, "action": "skipped",
                "extra": skip_reason,
            })
            if event_emitter:
                await event_emitter.emit(agent_name, "warning", f"Skipped: {skip_reason}")
            # Mark as completed to prevent infinite re-dispatch
            if hasattr(state, 'agents_completed') and agent_name not in state.agents_completed:
                state.agents_completed.append(agent_name)
            return None

        agent_cls = self._agents.get(agent_name)
        if not agent_cls:
            return None

        agent = agent_cls(connection_config=self._connection_config)
        context = await self._build_agent_context(agent_name, state, event_emitter)

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

    async def _build_agent_context(self, agent_name: str, state: DiagnosticState,
                                    event_emitter: Optional[EventEmitter] = None) -> dict:
        """Build context dict for a specific agent."""
        base = {
            "service_name": state.service_name,
            "time_window": {"start": state.time_window.start, "end": state.time_window.end},
        }

        if agent_name == "log_agent":
            base["elk_index"] = state.elk_index or "*"
            base["timeframe"] = state.time_window.start
            base["trace_id"] = state.trace_id
            base["namespace"] = state.namespace or "default"

            # Inject known dependencies from config + prior agent results
            known_deps = []
            if self._connection_config:
                cfg_deps = getattr(self._connection_config, "known_dependencies", ())
                known_deps.extend(
                    {"source": src, "target": tgt, "relationship": rel}
                    for src, tgt, rel in cfg_deps
                )
            if state.inferred_dependencies:
                known_deps.extend(state.inferred_dependencies)
            if known_deps:
                base["known_dependencies"] = known_deps

        elif agent_name == "metrics_agent":
            base["namespace"] = state.namespace or "default"
            if state.log_analysis:
                base["error_patterns"] = state.log_analysis.primary_pattern.model_dump() if state.log_analysis.primary_pattern else None
                # Pass affected components so agent queries metrics for all involved services
                if state.log_analysis.primary_pattern and state.log_analysis.primary_pattern.affected_components:
                    base["affected_services"] = state.log_analysis.primary_pattern.affected_components
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
            if state.suggested_promql_queries:
                base["suggested_promql_queries"] = state.suggested_promql_queries

        elif agent_name == "k8s_agent":
            base["namespace"] = state.namespace or "default"
            base["cluster_url"] = state.cluster_url
            base["suggested_label_selector"] = f"app={state.service_name}"
            # Pass error patterns from log analysis for context
            if state.log_analysis and state.log_analysis.primary_pattern:
                pattern = state.log_analysis.primary_pattern
                base["error_patterns"] = [
                    {
                        "exception_type": pattern.exception_type,
                        "error_message": pattern.error_message,
                        "severity": pattern.severity,
                        "affected_components": pattern.affected_components,
                    }
                ]

        elif agent_name == "tracing_agent":
            base["trace_id"] = state.trace_id

        elif agent_name == "code_agent":
            base["repo_url"] = state.repo_url
            # Pass GitHub token from integration config
            if self._connection_config and self._connection_config.github_token:
                base["github_token"] = self._connection_config.github_token
            # Backward compat: local path
            if state.repo_url and not state.repo_url.startswith(("http://", "https://", "git@")):
                base["repo_path"] = state.repo_url
            if state.log_analysis and state.log_analysis.primary_pattern:
                base["exception_type"] = state.log_analysis.primary_pattern.exception_type
                base["stack_traces"] = list(state.log_analysis.primary_pattern.stack_traces or [])
                stack_trace = ""
                for sample in state.log_analysis.primary_pattern.sample_logs:
                    if sample.raw_line and len(sample.raw_line) > len(stack_trace):
                        stack_trace = sample.raw_line
                base["stack_trace"] = stack_trace
            # Cross-service context from prior agents
            if state.log_analysis and state.log_analysis.primary_pattern:
                base["error_message"] = state.log_analysis.primary_pattern.error_message or ""

            if state.service_flow:
                base["service_flow"] = state.service_flow

            if state.patient_zero:
                base["patient_zero"] = state.patient_zero

            if state.inferred_dependencies:
                base["inferred_dependencies"] = state.inferred_dependencies

            # Trace failure point with HTTP endpoint tags
            if state.trace_analysis:
                if state.trace_analysis.failure_point:
                    fp = state.trace_analysis.failure_point
                    base["trace_failure_point"] = {
                        "service": fp.service_name,
                        "operation": fp.operation_name,
                        "error_message": fp.error_message,
                        "tags": fp.tags,
                    }
                if state.trace_analysis.call_chain:
                    base["trace_call_chain"] = [
                        {"service": s.service_name, "operation": s.operation_name,
                         "status": s.status, "error": s.error_message or ""}
                        for s in state.trace_analysis.call_chain
                    ]

            # Metrics anomaly summary (compact)
            if state.metrics_analysis and state.metrics_analysis.anomalies:
                base["metrics_anomalies"] = [
                    {"metric": a.metric_name, "severity": a.severity,
                     "correlation": a.correlation_to_incident}
                    for a in state.metrics_analysis.anomalies[:5]
                ]

            # K8s crash/OOM summary (compact)
            if state.k8s_analysis:
                k8s_summary = []
                if state.k8s_analysis.is_crashloop:
                    k8s_summary.append("CrashLoopBackOff detected")
                for pod in state.k8s_analysis.pod_statuses:
                    if pod.oom_killed:
                        k8s_summary.append(f"OOMKilled: {pod.pod_name}")
                for evt in state.k8s_analysis.events[:3]:
                    if evt.type == "Warning":
                        k8s_summary.append(f"{evt.reason}: {evt.message[:80]}")
                if k8s_summary:
                    base["k8s_warnings"] = k8s_summary

            # Wire files_changed from change_agent
            if state.change_analysis:
                all_files = []
                for corr in state.change_analysis.get("change_correlations", []):
                    all_files.extend(corr.get("files_changed", []))
                base["files_changed"] = list(dict.fromkeys(all_files))
            # Hand-off: top 3 high-risk files
            high_priority = self._extract_high_priority_files(state)
            if high_priority:
                base["high_priority_files"] = high_priority
            # Auto-infer repo_map for cross-service analysis
            await self._auto_infer_repo_map(state)
            # Multi-repo context
            if hasattr(state, "repo_map") and state.repo_map:
                base["repo_map"] = state.repo_map
            # Human-in-the-loop relay for code_agent
            base["_ask_human_callback"] = self._relay_code_agent_question
            base["_event_emitter"] = event_emitter
            base["_state"] = state

        elif agent_name == "change_agent":
            base["repo_url"] = state.repo_url
            # Pass GitHub token from integration config
            if self._connection_config and self._connection_config.github_token:
                base["github_token"] = self._connection_config.github_token
            base["namespace"] = state.namespace or "default"
            base["incident_start"] = state.time_window.start
            if self._connection_config:
                cluster_type = getattr(self._connection_config, "cluster_type", "kubernetes")
                base["cli_tool"] = "oc" if cluster_type == "openshift" else "kubectl"
            # Pass stack trace file paths for cross-referencing
            if state.log_analysis and state.log_analysis.primary_pattern:
                stack_traces = list(state.log_analysis.primary_pattern.stack_traces or [])
                stack_file_paths = self._extract_file_paths_from_traces(stack_traces)
                if stack_file_paths:
                    base["stack_trace_files"] = stack_file_paths
                base["exception_type"] = state.log_analysis.primary_pattern.exception_type

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

        # Update confidence — proper running average (order-independent)
        confidence = result.get("overall_confidence", 50)
        n = len(state.agents_completed) + 1  # agents already completed + this one
        if n <= 1:
            state.overall_confidence = min(confidence, 100)
        else:
            state.overall_confidence = min(
                round((state.overall_confidence * (n - 1) + confidence) / n), 100
            )

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
            logger.info("Log agent primary_pattern", extra={
                "session_id": getattr(state, 'session_id', ''),
                "agent_name": "supervisor",
                "action": "log_result_inspect",
                "extra": {
                    "has_primary": bool(primary_raw),
                    "exception_type": primary_raw.get("exception_type") if isinstance(primary_raw, dict) else None,
                    "keys": list(primary_raw.keys()) if isinstance(primary_raw, dict) else str(type(primary_raw)),
                },
            })
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
                        stack_traces=primary_raw.get("stack_traces", []),
                        correlation_ids=primary_raw.get("correlation_ids", []),
                        sample_log_ids=primary_raw.get("sample_log_ids", []),
                        causal_role=primary_raw.get("causal_role"),
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
                                stack_traces=sp_raw.get("stack_traces", []),
                                correlation_ids=sp_raw.get("correlation_ids", []),
                                sample_log_ids=sp_raw.get("sample_log_ids", []),
                                causal_role=sp_raw.get("causal_role"),
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

            # Store new enrichment fields from log agent
            state.patient_zero = result.get("patient_zero")
            state.inferred_dependencies = result.get("inferred_dependencies", [])
            state.reasoning_chain = result.get("reasoning_chain", [])
            state.suggested_promql_queries = result.get("suggested_promql_queries", [])

            # Auto-detect namespace from logs when user didn't provide one
            detected_ns = result.get("detected_namespace")
            if detected_ns and (not state.namespace or state.namespace == "default"):
                logger.info("Namespace auto-detected from logs", extra={
                    "session_id": getattr(state, 'session_id', ''),
                    "agent_name": "supervisor",
                    "action": "namespace_detected",
                    "extra": {"namespace": detected_ns},
                })
                state.namespace = detected_ns

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

            # Promote all metric observations to Findings (anomalies + baselines)
            for a in anomalies:
                category = "metric_anomaly" if a.severity in ("critical", "high", "medium") else "metric_baseline"
                state.all_findings.append(Finding(
                    finding_id=f"metric_{a.metric_name}",
                    agent_name="metrics_agent",
                    category=category,
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

        # Handle k8s_agent results
        if agent_name == "k8s_agent":
            pods_raw = result.get("pod_statuses", [])
            pod_statuses = []
            for p in pods_raw:
                try:
                    pod_statuses.append(PodHealthStatus(**p) if isinstance(p, dict) else p)
                except Exception:
                    pass

            events_raw = result.get("events", [])
            events = []
            for e in events_raw:
                try:
                    events.append(K8sEvent(**e) if isinstance(e, dict) else e)
                except Exception:
                    pass

            tu_raw = result.get("tokens_used", {})
            k8s_tokens = TokenUsage(
                agent_name="k8s_agent",
                input_tokens=tu_raw.get("input_tokens", 0),
                output_tokens=tu_raw.get("output_tokens", 0),
                total_tokens=tu_raw.get("total_tokens", 0),
            )

            # Promote k8s findings
            k8s_findings = []
            if result.get("is_crashloop"):
                k8s_findings.append(Finding(
                    finding_id="k8s_crashloop",
                    agent_name="k8s_agent",
                    category="crashloop",
                    summary=f"CrashLoopBackOff detected — {result.get('total_restarts_last_hour', 0)} restarts in last hour",
                    confidence_score=min(result.get("overall_confidence", 70), 100),
                    severity="critical",
                    breadcrumbs=[],
                    negative_findings=[],
                ))
            for p in pod_statuses:
                if p.oom_killed:
                    k8s_findings.append(Finding(
                        finding_id=f"k8s_oom_{p.pod_name}",
                        agent_name="k8s_agent",
                        category="oom_killed",
                        summary=f"Pod {p.pod_name} OOMKilled",
                        confidence_score=90,
                        severity="critical",
                        breadcrumbs=[],
                        negative_findings=[],
                    ))
            state.all_findings.extend(k8s_findings)

            state.k8s_analysis = K8sAnalysisResult(
                cluster_name=state.cluster_url or "unknown",
                namespace=state.namespace or "default",
                service_name=state.service_name,
                pod_statuses=pod_statuses,
                events=events,
                is_crashloop=result.get("is_crashloop", False),
                total_restarts_last_hour=result.get("total_restarts_last_hour", 0),
                resource_mismatch=result.get("resource_mismatch"),
                findings=k8s_findings,
                negative_findings=[nf for nf in state.all_negative_findings if nf.agent_name == "k8s_agent"],
                breadcrumbs=[b for b in state.all_breadcrumbs if b.agent_name == "k8s_agent"],
                overall_confidence=min(result.get("overall_confidence", 50), 100),
                tokens_used=k8s_tokens,
            )

            if event_emitter and (result.get("is_crashloop") or any(p.oom_killed for p in pod_statuses)):
                await event_emitter.emit(
                    "k8s_agent", "finding",
                    f"K8s issues: crashloop={result.get('is_crashloop')}, OOM pods={sum(1 for p in pod_statuses if p.oom_killed)}",
                    details={"pods": len(pod_statuses), "events": len(events)}
                )

        # Handle tracing_agent results
        if agent_name == "tracing_agent":
            chain_raw = result.get("call_chain", [])
            call_chain = []
            for s in chain_raw:
                try:
                    call_chain.append(SpanInfo(**s) if isinstance(s, dict) else s)
                except Exception:
                    pass

            failure_point = None
            fp_raw = result.get("failure_point")
            if fp_raw and isinstance(fp_raw, dict):
                try:
                    failure_point = SpanInfo(**fp_raw)
                except Exception:
                    pass

            bottlenecks_raw = result.get("latency_bottlenecks", [])
            bottlenecks = []
            for b in bottlenecks_raw:
                try:
                    bottlenecks.append(SpanInfo(**b) if isinstance(b, dict) else b)
                except Exception:
                    pass

            tu_raw = result.get("tokens_used", {})
            trace_tokens = TokenUsage(
                agent_name="tracing_agent",
                input_tokens=tu_raw.get("input_tokens", 0),
                output_tokens=tu_raw.get("output_tokens", 0),
                total_tokens=tu_raw.get("total_tokens", 0),
            )

            # Promote trace findings
            trace_findings = []
            if failure_point:
                trace_findings.append(Finding(
                    finding_id=f"trace_failure_{failure_point.span_id}",
                    agent_name="tracing_agent",
                    category="trace_failure",
                    summary=f"Failure at {failure_point.service_name}:{failure_point.operation_name} — {failure_point.error_message or failure_point.status}",
                    confidence_score=min(result.get("overall_confidence", 70), 100),
                    severity="high",
                    breadcrumbs=[],
                    negative_findings=[],
                ))
            state.all_findings.extend(trace_findings)

            trace_source = result.get("trace_source", "jaeger")
            valid_sources = ("jaeger", "tempo", "elasticsearch", "combined")
            if trace_source not in valid_sources:
                trace_source = "jaeger"

            state.trace_analysis = TraceAnalysisResult(
                trace_id=result.get("trace_id", state.trace_id or "unknown"),
                total_duration_ms=result.get("total_duration_ms", 0),
                total_services=result.get("total_services", 0),
                total_spans=result.get("total_spans", 0),
                call_chain=call_chain,
                failure_point=failure_point,
                cascade_path=result.get("cascade_path", []),
                latency_bottlenecks=bottlenecks,
                retry_detected=result.get("retry_detected", False),
                service_dependency_graph=result.get("service_dependency_graph", {}),
                trace_source=trace_source,
                elk_reconstruction_confidence=result.get("elk_reconstruction_confidence"),
                findings=trace_findings,
                negative_findings=[nf for nf in state.all_negative_findings if nf.agent_name == "tracing_agent"],
                breadcrumbs=[b for b in state.all_breadcrumbs if b.agent_name == "tracing_agent"],
                overall_confidence=min(result.get("overall_confidence", 50), 100),
                tokens_used=trace_tokens,
            )

            if event_emitter and failure_point:
                await event_emitter.emit(
                    "tracing_agent", "finding",
                    f"Trace failure: {failure_point.service_name}:{failure_point.operation_name}",
                    details={"total_spans": result.get("total_spans", 0), "cascade_path": result.get("cascade_path", [])}
                )

        # Handle code_agent results
        if agent_name == "code_agent":
            root_loc_raw = result.get("root_cause_location", {})
            impacted_raw = result.get("impacted_files", [])
            fix_areas_raw = result.get("suggested_fix_areas", [])

            def _parse_impacted(raw: dict) -> ImpactedFile:
                lines = []
                for lr in raw.get("relevant_lines", []):
                    try:
                        lines.append(LineRange(**lr) if isinstance(lr, dict) else lr)
                    except Exception:
                        pass
                return ImpactedFile(
                    file_path=raw.get("file_path", "unknown"),
                    impact_type=raw.get("impact_type", "shared_resource"),
                    relevant_lines=lines,
                    code_snippet=raw.get("code_snippet", ""),
                    relationship=raw.get("relationship", ""),
                    fix_relevance=raw.get("fix_relevance", "informational"),
                )

            try:
                root_loc = _parse_impacted(root_loc_raw) if isinstance(root_loc_raw, dict) and root_loc_raw else ImpactedFile(
                    file_path="unknown", impact_type="direct_error", relevant_lines=[], code_snippet="", relationship="error origin", fix_relevance="must_fix"
                )
            except Exception:
                root_loc = ImpactedFile(
                    file_path="unknown", impact_type="direct_error", relevant_lines=[], code_snippet="", relationship="error origin", fix_relevance="must_fix"
                )

            impacted = []
            for f in impacted_raw:
                try:
                    impacted.append(_parse_impacted(f) if isinstance(f, dict) else f)
                except Exception:
                    pass

            fix_areas = []
            for fa in fix_areas_raw:
                try:
                    fix_areas.append(FixArea(**fa) if isinstance(fa, dict) else fa)
                except Exception:
                    pass

            # Parse diff_analysis
            diff_analysis = []
            for da in result.get("diff_analysis", []):
                try:
                    diff_analysis.append(DiffAnalysisItem(**da) if isinstance(da, dict) else da)
                except Exception:
                    pass
            cross_repo_findings = result.get("cross_repo_findings", [])

            tu_raw = result.get("tokens_used", {})
            code_tokens = TokenUsage(
                agent_name="code_agent",
                input_tokens=tu_raw.get("input_tokens", 0),
                output_tokens=tu_raw.get("output_tokens", 0),
                total_tokens=tu_raw.get("total_tokens", 0),
            )

            state.code_analysis = CodeAnalysisResult(
                root_cause_location=root_loc,
                impacted_files=impacted,
                call_chain=result.get("call_chain", []),
                dependency_graph=result.get("dependency_graph", {}),
                shared_resource_conflicts=[
                    s if isinstance(s, str) else s.get("resource", "") or str(s)
                    for s in result.get("shared_resource_conflicts", [])
                ],
                suggested_fix_areas=fix_areas,
                diff_analysis=diff_analysis,
                cross_repo_findings=cross_repo_findings,
                mermaid_diagram=result.get("mermaid_diagram", ""),
                negative_findings=[nf for nf in state.all_negative_findings if nf.agent_name == "code_agent"],
                breadcrumbs=[b for b in state.all_breadcrumbs if b.agent_name == "code_agent"],
                overall_confidence=min(result.get("overall_confidence", 50), 100),
                tokens_used=code_tokens,
            )

            if event_emitter and impacted:
                await event_emitter.emit(
                    "code_agent", "finding",
                    f"Code impact: {len(impacted)} files, root cause in {root_loc.file_path}",
                    details={"impacted_count": len(impacted), "fix_areas": len(fix_areas)}
                )

        # Store reasoning
        state.supervisor_reasoning.append(
            f"Round: {agent_name} completed with confidence {confidence}"
        )

    def _update_phase(self, state: DiagnosticState, event_emitter: Optional[EventEmitter] = None) -> None:
        """Update diagnostic phase based on completed agents."""
        old_phase = state.phase

        # RE_INVESTIGATING is handled by _decide_next_agents; after re-dispatch
        # completes, allow normal phase advancement
        if state.phase == DiagnosticPhase.RE_INVESTIGATING:
            # Allow _decide_next_agents to reset it; don't overwrite here
            return

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
            try:
                asyncio.ensure_future(event_emitter.emit(
                    "supervisor", "phase_change",
                    f"Phase: {state.phase.value.replace('_', ' ').title()}",
                    details={"phase": state.phase.value, "previous_phase": old_phase.value}
                ))
            except Exception:
                logger.debug("Could not emit phase_change event")

    def _build_agent_summary(self, agent_name: str, result: dict, state: DiagnosticState) -> str:
        """Build a human-readable summary of agent completion."""
        confidence = result.get("overall_confidence", 0)
        if agent_name == "log_agent":
            primary = result.get("primary_pattern", {})
            pattern_msg = primary.get("error_message", "No pattern found") if isinstance(primary, dict) else "No pattern found"
            flow = result.get("service_flow", [])
            flow_part = f", flow: {len(flow)} steps across {len(set(s.get('service', 'unknown') for s in flow))} services" if flow else ""
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

    # ── Hand-off helpers ─────────────────────────────────────────────────────

    def _extract_high_priority_files(self, state: DiagnosticState) -> list[dict]:
        """Extract top 3 high-risk changed files from change_agent for code_agent hand-off.

        Prefers the pre-filtered high_priority_files from change_agent (which
        already strips noise like .gitignore, Dockerfile, CI configs, etc.).
        Falls back to re-extracting from change_correlations with noise filter.
        """
        if not state.change_analysis:
            return []

        # Prefer the pre-filtered list from change_agent
        pre_filtered = state.change_analysis.get("high_priority_files", [])
        if pre_filtered:
            return pre_filtered[:3]

        # Fallback: build from correlations with noise filtering
        import re
        noise_re = re.compile(
            r'(^docs?/|README|__pycache__|\.pyc$|'
            r'\.eslintrc|\.prettierrc|\.editorconfig|\.babelrc|'
            r'test_\w+\.py$|_test\.go$|\.test\.[tj]sx?$|'
            r'\.gitignore$|\.dockerignore$|\.lock$|'
            r'LICENSE|CHANGELOG|CONTRIBUTING|'
            r'\.flake8$|\.isort\.cfg$|\.pre-commit|\.coveragerc|\.pylintrc|mypy\.ini$|'
            r'tsconfig.*\.json$|jest\.config|webpack\.config|vite\.config)',
            re.IGNORECASE,
        )
        correlations = state.change_analysis.get("change_correlations", [])
        file_scores: list[dict] = []
        for corr in correlations:
            risk = corr.get("risk_score", corr.get("correlation_score", 0))
            sha = corr.get("sha", corr.get("change_id", ""))
            for f in corr.get("files_changed", []):
                if noise_re.search(f):
                    continue
                file_scores.append({
                    "file_path": f,
                    "risk_score": risk,
                    "sha": sha,
                    "description": corr.get("description", "")[:100],
                })
        file_scores.sort(key=lambda x: x["risk_score"], reverse=True)
        return file_scores[:3]

    async def _auto_infer_repo_map(self, state: DiagnosticState) -> None:
        """Auto-populate repo_map for services not already mapped.

        Strategy: If state.repo_url is github.com/org/X, infer that
        service Y lives at github.com/org/Y. Validates each candidate
        with a HEAD request — only verified repos are added to repo_map.
        Unverified candidates are logged but omitted to prevent the LLM
        from burning iterations on 404s.
        """
        if not state.repo_url:
            return

        import re
        m = re.match(r'https?://github\.com/([^/]+)/', state.repo_url)
        if not m:
            return
        org = m.group(1)

        # Collect all service names from prior agents
        services: set[str] = set()
        if state.patient_zero:
            pz_svc = state.patient_zero.get("service", "")
            if pz_svc:
                services.add(pz_svc)
        for step in (state.service_flow or []):
            svc = step.get("service", "")
            if svc:
                services.add(svc)
        for dep in (state.inferred_dependencies or []):
            services.add(dep.get("source", ""))
            services.add(dep.get("target", ""))
        if state.trace_analysis and state.trace_analysis.call_chain:
            for span in state.trace_analysis.call_chain:
                services.add(span.service_name)
        services.discard("")
        services.discard(state.service_name)  # Already have this repo

        # Build auth headers if token is available
        headers = {"Accept": "application/vnd.github+json"}
        token = ""
        if self._connection_config and self._connection_config.github_token:
            token = self._connection_config.github_token
            headers["Authorization"] = f"Bearer {token}"

        # Validate each candidate repo with a HEAD request
        import httpx
        candidates = {
            svc: f"https://github.com/{org}/{svc}"
            for svc in services
            if svc not in state.repo_map
        }
        if not candidates:
            return

        try:
            async with httpx.AsyncClient(timeout=5) as client:
                for svc, url in candidates.items():
                    owner_repo = f"{org}/{svc}"
                    api_url = f"https://api.github.com/repos/{owner_repo}"
                    try:
                        resp = await client.head(api_url, headers=headers)
                        if resp.status_code == 200:
                            state.repo_map[svc] = url
                            logger.info("Auto-inferred repo verified",
                                        extra={"agent_name": "supervisor",
                                               "action": "repo_map_inferred",
                                               "extra": {"service": svc, "repo": url}})
                        else:
                            logger.info("Auto-inferred repo not found, skipping",
                                        extra={"agent_name": "supervisor",
                                               "action": "repo_map_skipped",
                                               "extra": {"service": svc, "repo": url,
                                                          "status": resp.status_code}})
                    except httpx.HTTPError:
                        # Network error — skip this candidate silently
                        logger.debug("Repo validation request failed for %s", owner_repo)
        except Exception as e:
            logger.warning("Auto-infer repo_map validation failed: %s", e)

    async def _relay_code_agent_question(
        self, question: str, state: DiagnosticState,
        event_emitter: Optional[EventEmitter] = None,
    ) -> str:
        """Relay a question from code_agent to the human via WebSocket chat."""
        self._pending_code_agent_question = True
        self._code_agent_answer = ""
        self._code_agent_event.clear()

        if event_emitter:
            await event_emitter.emit(
                "supervisor", "waiting_for_input",
                "Code agent needs your input",
                details={"input_type": "code_agent_question"},
            )

        # Send question to frontend via WebSocket
        if event_emitter and event_emitter._websocket_manager:
            await event_emitter._websocket_manager.send_message(
                state.session_id,
                {
                    "type": "chat_response",
                    "data": {
                        "role": "assistant",
                        "content": question,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "metadata": {"type": "code_agent_question"},
                    },
                },
            )

        # Wait for human response (3 minute timeout)
        try:
            await asyncio.wait_for(self._code_agent_event.wait(), timeout=180)
        except asyncio.TimeoutError:
            self._pending_code_agent_question = False
            return "No response from user (timed out). Proceed with your best judgment."

        self._pending_code_agent_question = False
        return self._code_agent_answer

    async def _check_repo_mismatch(
        self, state: DiagnosticState, event_emitter: Optional[EventEmitter] = None,
    ) -> None:
        """Check if patient_zero service differs from target service and ask user to confirm."""
        if not state.patient_zero or not event_emitter:
            return
        pz_svc = state.patient_zero.get("service", "") if isinstance(state.patient_zero, dict) else ""
        if not pz_svc or pz_svc.lower() == state.service_name.lower():
            return

        # Derive a candidate repo for the PZ service
        candidate_repo = ""
        if state.repo_url:
            candidates = self._derive_candidate_repos(state.repo_url, [pz_svc], state.service_name)
            candidate_repo = candidates.get(pz_svc, "")

        msg_lines = [
            f"**Repo mismatch detected:** Root cause appears to be in **{pz_svc}**, but the repo provided is for **{state.service_name}**.\n",
        ]
        if candidate_repo:
            msg_lines.append(f"Derived repo for {pz_svc}: `{candidate_repo}`\n")
        msg_lines.append("Please reply with one of:")
        msg_lines.append(f"  \u2022 **confirm** \u2014 switch to `{candidate_repo or pz_svc}` repo")
        msg_lines.append("  \u2022 **keep** \u2014 continue with current repo")
        msg_lines.append("  \u2022 Or provide the correct URL, e.g.: `https://github.com/org/repo`")

        if event_emitter._websocket_manager:
            await event_emitter._websocket_manager.send_message(
                state.session_id,
                {
                    "type": "chat_response",
                    "data": {
                        "role": "assistant",
                        "content": "\n".join(msg_lines),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "metadata": {
                            "type": "repo_mismatch",
                            "patient_zero_service": pz_svc,
                        },
                    },
                },
            )

        await event_emitter.emit(
            "supervisor", "warning",
            f"Repo mismatch: patient_zero is {pz_svc}, repo is for {state.service_name}",
        )

        # Wait for user response (up to 3 minutes)
        self._pending_repo_mismatch = True
        self._mismatch_confirmed_repo = None
        self._repo_mismatch_event.clear()
        await event_emitter.emit(
            "supervisor", "waiting_for_input",
            f"Repo mismatch: confirm switch to {pz_svc} repo or keep current",
            details={"input_type": "repo_mismatch", "patient_zero_service": pz_svc},
        )
        try:
            await asyncio.wait_for(self._repo_mismatch_event.wait(), timeout=180)
        except asyncio.TimeoutError:
            self._pending_repo_mismatch = False
            logger.warning("Repo mismatch confirmation timed out", extra={
                "session_id": state.session_id, "agent_name": "supervisor",
                "action": "repo_mismatch_timeout",
            })
            return

        self._pending_repo_mismatch = False

        # Apply the confirmed repo
        if self._mismatch_confirmed_repo:
            original_repo = state.repo_url
            state.repo_url = self._mismatch_confirmed_repo
            # Populate repo_map with both repos
            state.repo_map[state.service_name] = original_repo or ""
            state.repo_map[pz_svc] = self._mismatch_confirmed_repo

    # ── Human-in-the-loop: repo URL confirmation for change_agent ────────────

    def _get_affected_services(self, state: DiagnosticState) -> list[str]:
        """Extract all affected services from log analysis, patient_zero, and dependencies."""
        services: dict[str, None] = {}  # ordered set
        services[state.service_name] = None
        if state.log_analysis and state.log_analysis.primary_pattern:
            for comp in state.log_analysis.primary_pattern.affected_components:
                services[comp] = None
        if state.patient_zero:
            pz = state.patient_zero
            pz_svc = pz.get("service") if isinstance(pz, dict) else getattr(pz, "service", None)
            if pz_svc:
                services[pz_svc] = None
        if state.inferred_dependencies:
            for dep in state.inferred_dependencies:
                src = dep.get("source") if isinstance(dep, dict) else getattr(dep, "source", None)
                tgt = dep.get("target") if isinstance(dep, dict) else getattr(dep, "target", None)
                if src:
                    services[src] = None
                if tgt:
                    services[tgt] = None
        return list(services.keys())

    @staticmethod
    def _parse_owner_repo(url: str) -> str | None:
        """Extract 'owner/repo' from a GitHub URL."""
        import re
        for pattern in [
            r'github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$',
            r'^([^/]+/[^/]+)$',
        ]:
            m = re.search(pattern, url)
            if m:
                return m.group(1)
        return None

    async def _validate_github_repos(self, repos: dict[str, str]) -> dict[str, str]:
        """Validate which GitHub repos actually exist. Returns only valid repos."""
        import httpx
        token = ""
        if self._connection_config and self._connection_config.github_token:
            token = self._connection_config.github_token
        if not token:
            import os
            token = os.getenv("GITHUB_TOKEN", "")

        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        valid: dict[str, str] = {}
        async with httpx.AsyncClient(timeout=10.0) as client:
            for svc, repo_url in repos.items():
                if not repo_url:
                    continue
                owner_repo = self._parse_owner_repo(repo_url)
                if not owner_repo:
                    # Not a GitHub URL (could be local path) — keep it
                    valid[svc] = repo_url
                    continue
                try:
                    resp = await client.get(
                        f"https://api.github.com/repos/{owner_repo}",
                        headers=headers,
                    )
                    if resp.status_code == 200:
                        valid[svc] = repo_url
                    else:
                        logger.info("Repo validation failed", extra={
                            "agent_name": "supervisor", "action": "repo_validation",
                            "extra": {"service": svc, "repo": owner_repo, "status": resp.status_code},
                        })
                except Exception as e:
                    logger.warning("Repo validation error for %s: %s", owner_repo, e)
        return valid

    def _derive_candidate_repos(
        self, base_repo_url: str | None, affected_services: list[str], target_service: str,
    ) -> dict[str, str]:
        """Derive candidate repo URLs for each affected service from the base repo URL pattern."""
        import re
        repos: dict[str, str] = {}
        if not base_repo_url:
            for svc in affected_services:
                repos[svc] = ""
            return repos

        for svc in affected_services:
            if svc == target_service:
                repos[svc] = base_repo_url
            else:
                # Try to derive: replace the repo name portion with the service name
                # Handles: https://github.com/org/checkout-service → https://github.com/org/inventory-service
                # Also: git@github.com:org/checkout-service.git → git@github.com:org/inventory-service.git
                derived = re.sub(
                    r'(/|:)([^/]+?)(?:\.git)?$',
                    lambda m: f'{m.group(1)}{svc}',
                    base_repo_url,
                )
                repos[svc] = derived if derived != base_repo_url else ""
        return repos

    async def _request_repo_confirmation(
        self, state: DiagnosticState, event_emitter: EventEmitter,
    ) -> None:
        """Ask user to confirm repo URLs for affected services, wait for response, then dispatch change_agent."""
        affected = self._get_affected_services(state)
        if not affected:
            return

        logger.info("Change analysis: affected services detected", extra={
            "session_id": state.session_id, "agent_name": "supervisor",
            "action": "change_affected_services",
            "extra": {"services": affected, "base_repo": state.repo_url},
        })

        candidates = self._derive_candidate_repos(state.repo_url, affected, state.service_name)
        logger.info("Change analysis: candidate repos derived", extra={
            "session_id": state.session_id, "agent_name": "supervisor",
            "action": "change_candidate_repos",
            "extra": {svc: repo or "(none)" for svc, repo in candidates.items()},
        })

        # Validate derived repos exist on GitHub before showing to user
        validated = await self._validate_github_repos(candidates)
        invalid_repos = {s: r for s, r in candidates.items() if r and s not in validated}
        if invalid_repos:
            logger.info("Skipping invalid repos", extra={
                "agent_name": "supervisor", "action": "repo_validation_skip",
                "extra": {"invalid": list(invalid_repos.keys())},
            })
        # Keep services with valid repos + services with no repo (user may provide)
        candidates = {s: (validated.get(s, "") if candidates[s] else "") for s in candidates}
        self._candidate_repos = candidates

        # If no services have valid repos and none need user input, skip entirely
        if not any(candidates.values()) and not any(r == "" for r in candidates.values()):
            await event_emitter.emit("supervisor", "progress", "No valid repos found — skipping change analysis")
            return

        # Build the chat message
        lines = [
            "I've identified these services for **change analysis** (recent commits, deployments, config changes):\n",
        ]
        for svc, repo in candidates.items():
            if repo:
                lines.append(f"  \u2022 **{svc}** \u2192 `{repo}`")
            elif svc in invalid_repos:
                lines.append(f"  \u2022 **{svc}** \u2192 ~~`{invalid_repos[svc]}`~~ *(repo not found)*")
            else:
                lines.append(f"  \u2022 **{svc}** \u2192 *(no repo URL \u2014 please provide)*")
        lines.append("")
        lines.append("Please reply with one of:")
        lines.append("  \u2022 **confirm** \u2014 proceed with these repos")
        lines.append("  \u2022 **skip** \u2014 skip change analysis")
        lines.append("  \u2022 Or provide corrections, e.g.: `inventory-service: https://github.com/org/inv-svc`")

        msg = "\n".join(lines)

        # Send as chat_response via WebSocket so it appears in the Investigator chat
        if event_emitter._websocket_manager:
            await event_emitter._websocket_manager.send_message(
                state.session_id,
                {
                    "type": "chat_response",
                    "data": {
                        "role": "assistant",
                        "content": msg,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                },
            )

        await event_emitter.emit(
            "supervisor", "progress",
            "Waiting for user to confirm repository URLs for change analysis",
        )

        # Wait for user response (up to 5 minutes)
        self._pending_repo_confirmation = True
        self._repo_confirmation_event.clear()
        await event_emitter.emit(
            "supervisor", "waiting_for_input",
            "Waiting for user to confirm repository URLs",
            details={"input_type": "repo_confirmation"},
        )
        try:
            await asyncio.wait_for(self._repo_confirmation_event.wait(), timeout=300)
        except asyncio.TimeoutError:
            self._pending_repo_confirmation = False
            logger.warning("Repo confirmation timed out", extra={
                "session_id": state.session_id, "agent_name": "supervisor",
                "action": "repo_confirmation_timeout",
            })
            await event_emitter.emit(
                "supervisor", "warning",
                "Repo confirmation timed out \u2014 skipping change analysis",
            )
            return

        self._pending_repo_confirmation = False

        # Check if user chose to skip
        if not self._confirmed_repo_map:
            await event_emitter.emit("supervisor", "progress", "Change analysis skipped by user")
            return

        # Validate user-confirmed repos (user may have provided corrections with bad URLs)
        validated_repos = await self._validate_github_repos(self._confirmed_repo_map)
        skipped = [s for s in self._confirmed_repo_map if s not in validated_repos and self._confirmed_repo_map[s]]
        if skipped:
            logger.info("Skipping unvalidated user repos", extra={
                "agent_name": "supervisor", "action": "repo_dispatch_skip",
                "extra": {"skipped_services": skipped},
            })
            if event_emitter:
                await event_emitter.emit(
                    "supervisor", "warning",
                    f"Skipped repos not found on GitHub: {', '.join(skipped)}",
                )

        if not validated_repos:
            await event_emitter.emit("supervisor", "progress", "No valid repos — skipping change analysis")
            return

        # Populate repo_map from validated repos
        state.repo_map = dict(validated_repos)

        logger.info("Change analysis: dispatching for validated repos", extra={
            "session_id": state.session_id, "agent_name": "supervisor",
            "action": "change_dispatch_plan",
            "extra": {"repos": {s: r for s, r in validated_repos.items() if r}, "count": sum(1 for r in validated_repos.values() if r)},
        })

        # Dispatch change_agent for each validated repo
        for svc, repo in validated_repos.items():
            if not repo:
                continue
            logger.info("Change analysis: dispatching for service", extra={
                "session_id": state.session_id, "agent_name": "change_agent",
                "action": "dispatch_for_service",
                "extra": {"service": svc, "repo_url": repo},
            })
            # Temporarily set repo_url and service context for change_agent
            original_repo = state.repo_url
            state.repo_url = repo

            result = await self._dispatch_agent("change_agent", state, event_emitter)

            state.repo_url = original_repo  # restore

            if result and not isinstance(result, Exception):
                # Tag change_correlations with service_name
                for corr in result.get("change_correlations", []):
                    corr["service_name"] = svc

                await self._update_state_with_result(state, "change_agent", result, event_emitter)

                summary = self._build_agent_summary("change_agent", result, state)
                await event_emitter.emit(
                    "change_agent", "summary", summary,
                    details={"confidence": state.overall_confidence, "findings_count": len(state.all_findings)},
                )

        if "change_agent" not in state.agents_completed:
            state.agents_completed.append("change_agent")

    async def _enrich_reasoning_chain(
        self, state: DiagnosticState, event_emitter: EventEmitter
    ) -> None:
        """Send combined log + metrics evidence to LLM to produce comprehensive reasoning chain."""
        try:
            await event_emitter.emit("supervisor", "progress", "Synthesizing AI reasoning from all evidence")

            # Build evidence summary for the LLM
            evidence_parts = []

            # Log evidence
            if state.log_analysis:
                evidence_parts.append("## Log Analysis Evidence")
                if state.log_analysis.primary_pattern:
                    p = state.log_analysis.primary_pattern
                    evidence_parts.append(f"- Primary pattern: {p.exception_type} — \"{p.error_message}\" (freq={p.frequency}, severity={p.severity}, causal_role={p.causal_role})")
                    if p.affected_components:
                        evidence_parts.append(f"  Affected: {', '.join(p.affected_components)}")
                for sp in (state.log_analysis.secondary_patterns or []):
                    evidence_parts.append(f"- Secondary: {sp.exception_type} — \"{sp.error_message}\" (freq={sp.frequency}, causal_role={sp.causal_role})")
            if state.patient_zero:
                pz = state.patient_zero
                evidence_parts.append(f"- Patient Zero: {pz.get('service', 'unknown')} at {pz.get('first_error_time', '?')}")
                evidence_parts.append(f"  Evidence: {pz.get('evidence', '')}")
            if state.inferred_dependencies:
                evidence_parts.append("- Inferred dependencies:")
                for dep in state.inferred_dependencies:
                    evidence_parts.append(f"  {dep.get('source', '?')} → {dep.get('target', '?')} ({dep.get('evidence', '')})")

            # Metrics evidence
            if state.metrics_analysis and state.metrics_analysis.anomalies:
                evidence_parts.append("\n## Metrics Analysis Evidence")
                for a in state.metrics_analysis.anomalies:
                    evidence_parts.append(f"- [{a.severity.upper()}] {a.metric_name}: peak={a.peak_value}, baseline={a.baseline_value} (confidence={a.confidence_score})")
                    evidence_parts.append(f"  Correlation: {a.correlation_to_incident}")
                if state.metrics_analysis.correlated_signals:
                    evidence_parts.append("- Correlated signal groups:")
                    for cs in state.metrics_analysis.correlated_signals:
                        evidence_parts.append(f"  {cs.group_name} [{cs.signal_type}]: {cs.narrative}")

            # Negative findings (what was ruled out)
            ruled_out = [nf for nf in state.all_negative_findings]
            if ruled_out:
                evidence_parts.append("\n## Ruled Out")
                for nf in ruled_out[:5]:
                    evidence_parts.append(f"- {nf.what_was_checked}: {nf.result} → {nf.implication}")

            # Existing reasoning chain from log agent (if any)
            existing_chain = ""
            if state.reasoning_chain:
                existing_chain = "\n## Previous Reasoning (from log analysis)\n"
                for step in state.reasoning_chain:
                    existing_chain += f"- Step {step.get('step', '?')}: {step.get('observation', '')} → {step.get('inference', '')}\n"

            evidence_text = "\n".join(evidence_parts)

            prompt = f"""You are the Lead SRE synthesizing evidence from multiple investigation agents into a coherent diagnostic reasoning chain.

{evidence_text}
{existing_chain}
Your task: Produce a complete reasoning chain that weaves together ALL evidence (logs, metrics, dependencies, negative findings) into a step-by-step causal narrative. Each step should build on the previous one, showing how the incident unfolded.

Rules:
- 5-8 steps maximum
- Each step needs a clear observation (what the data shows) and inference (what it means)
- Start with the earliest signal and work forward chronologically
- Include metrics evidence that validates or refutes the log-based hypothesis
- Include negative findings (what was ruled out) as steps — they build trust
- End with the root cause conclusion and confidence level

Respond ONLY with a JSON array:
[
  {{"step": 1, "observation": "...", "inference": "..."}},
  {{"step": 2, "observation": "...", "inference": "..."}}
]"""

            response = await self.llm_client.chat(
                prompt=prompt,
                system="You are an expert SRE diagnostician. Respond with ONLY a valid JSON array, no markdown fencing.",
                max_tokens=2048,
            )

            # Parse the JSON response
            text = response.text.strip()
            # Strip markdown code fences if present
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()

            chain = json.loads(text)
            if isinstance(chain, list) and len(chain) > 0:
                state.reasoning_chain = chain
                logger.info("Reasoning chain enriched", extra={
                    "session_id": state.session_id, "agent_name": "supervisor",
                    "action": "reasoning_enriched",
                    "extra": {"steps": len(chain)},
                })
                await event_emitter.emit(
                    "supervisor", "summary",
                    f"AI reasoning chain synthesized — {len(chain)} steps from combined log + metrics evidence",
                )
        except Exception as e:
            logger.warning("Failed to enrich reasoning chain: %s", e, extra={
                "session_id": state.session_id, "agent_name": "supervisor",
                "action": "reasoning_enrichment_failed",
            })

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

            # Infer business impact from all affected services
            all_affected_services = (
                [blast_radius.primary_service]
                + blast_radius.upstream_affected
                + blast_radius.downstream_affected
            )
            business_impact = analyzer.infer_business_impact(all_affected_services)
            blast_radius.business_impact = business_impact

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

        # Handle pending fix approval (highest priority gate)
        if self._pending_fix_approval:
            return self._process_fix_decision(message)

        # Handle pending repo mismatch confirmation for code_agent
        if self._pending_repo_mismatch:
            return self._process_repo_mismatch(message, state)

        # Code agent question response
        if self._pending_code_agent_question:
            self._code_agent_answer = message
            self._code_agent_event.set()
            return "Got it, passing your answer to the code analysis agent."

        # Handle pending repo URL confirmation for change_agent
        if self._pending_repo_confirmation:
            return await self._process_repo_confirmation(message)

        # Check if user wants to trigger fix generation after diagnosis
        if state.phase in (DiagnosticPhase.DIAGNOSIS_COMPLETE, DiagnosticPhase.FIX_IN_PROGRESS):
            trigger_words = ["fix", "generate fix", "create fix", "patch", "create pr", "remediate"]
            if any(tw in message.lower() for tw in trigger_words):
                # GATE: require attestation acknowledgment before fix generation
                if not self._attestation_acknowledged:
                    return (
                        "Fix generation requires attestation of the diagnosis findings first. "
                        "Please review and approve the findings before requesting a fix."
                    )
                # Apply same guards as /fix/generate endpoint
                if state.fix_result and state.fix_result.fix_status in (
                    FixStatus.GENERATING, FixStatus.VERIFICATION_IN_PROGRESS, FixStatus.AWAITING_REVIEW,
                ):
                    return f"Fix generation is already in progress (status: {state.fix_result.fix_status.value}). Please wait."
                if self._event_emitter:
                    asyncio.create_task(
                        self.start_fix_generation(state, self._event_emitter, human_guidance=message)
                    )
                    return "Starting fix generation using findings from all diagnostic agents. I'll present the proposed fix for your review shortly."
                return "Fix generation is not available — event emitter not initialized."

        # Stream LLM response — emit chat_chunk messages via WebSocket for live typing
        prompt_text = f"""Current diagnostic state:
- Phase: {state.phase.value}
- Service: {state.service_name}
- Agents completed: {state.agents_completed}
- Overall confidence: {state.overall_confidence}%
- Findings so far: {len(state.all_findings)}

User message: {message}

Respond helpfully. If they're asking for status, give a brief update. If they're providing additional context, acknowledge it."""
        system_text = "You are an AI SRE assistant. Respond concisely to user messages during an active diagnosis."

        ws_mgr = self._event_emitter._websocket_manager if self._event_emitter else None
        full_response = ""
        async for chunk in self.llm_client.chat_stream(prompt=prompt_text, system=system_text):
            full_response += chunk
            if ws_mgr:
                await ws_mgr.send_message(
                    state.session_id,
                    {"type": "chat_chunk", "data": {"content": chunk, "done": False}},
                )

        # Send final chat_chunk with done=True and full_response
        if ws_mgr:
            await ws_mgr.send_message(
                state.session_id,
                {
                    "type": "chat_chunk",
                    "data": {
                        "content": "",
                        "done": True,
                        "full_response": full_response,
                        "phase": state.phase.value,
                        "confidence": state.overall_confidence,
                    },
                },
            )

        return full_response

    async def _process_repo_confirmation(self, message: str) -> str:
        """Parse user's repo confirmation response and signal the waiting coroutine."""
        import re
        text = message.strip().lower()

        logger.info("Repo confirmation response received", extra={
            "agent_name": "supervisor", "action": "repo_confirmation_response",
            "extra": {"response": text[:100]},
        })

        if text in ("skip", "no", "cancel"):
            self._confirmed_repo_map = {}
            self._repo_confirmation_event.set()
            return "Got it — skipping change analysis."

        if text in ("confirm", "yes", "ok", "y", "proceed", "looks good", "lgtm"):
            # Accept candidate repos as-is
            self._confirmed_repo_map = {
                svc: repo for svc, repo in self._candidate_repos.items() if repo
            }
            logger.info("Repos confirmed by user", extra={
                "agent_name": "supervisor", "action": "repo_confirmed",
                "extra": {svc: repo for svc, repo in self._confirmed_repo_map.items()},
            })
            self._repo_confirmation_event.set()
            confirmed_count = len(self._confirmed_repo_map)
            return f"Confirmed {confirmed_count} repo(s) — starting change analysis now."

        # Try to parse corrections: "service-name: https://github.com/org/repo"
        corrections = re.findall(
            r'(\S+)\s*:\s*(https?://\S+|git@\S+)',
            message,
        )
        if corrections:
            return self._apply_repo_corrections(corrections)

        # Fallback: use LLM to parse natural language corrections
        parsed = await self._llm_parse_repo_corrections(message)
        if parsed is not None:
            return parsed

        # Didn't understand — ask again
        return (
            "I didn't understand that. Please reply:\n"
            "  \u2022 **confirm** to proceed with the listed repos\n"
            "  \u2022 **skip** to skip change analysis\n"
            "  \u2022 Or provide corrections, e.g.:\n"
            "    `use https://github.com/org/repo for inventory-service`\n"
            "    `skip redis`"
        )

    def _apply_repo_corrections(self, corrections: list[tuple[str, str]]) -> str:
        """Apply parsed service→repo corrections and signal the waiting coroutine."""
        updated = dict(self._candidate_repos)
        for svc_name, repo_url in corrections:
            matched = None
            for candidate_svc in updated:
                if candidate_svc.lower() == svc_name.lower():
                    matched = candidate_svc
                    break
            if matched:
                updated[matched] = repo_url
            else:
                updated[svc_name] = repo_url

        self._confirmed_repo_map = {s: r for s, r in updated.items() if r}
        logger.info("Repos updated by user corrections", extra={
            "agent_name": "supervisor", "action": "repo_corrected",
            "extra": {svc: repo for svc, repo in self._confirmed_repo_map.items()},
        })
        self._repo_confirmation_event.set()

        lines = ["Updated repos — starting change analysis:"]
        for svc, repo in self._confirmed_repo_map.items():
            lines.append(f"  \u2022 {svc} \u2192 {repo}")
        return "\n".join(lines)

    async def _llm_parse_repo_corrections(self, message: str) -> str | None:
        """Use LLM to parse natural language repo corrections from user."""
        candidates_str = json.dumps(
            {s: r or "(no repo)" for s, r in self._candidate_repos.items()},
            indent=2,
        )
        try:
            response = await self.llm_client.chat(
                prompt=f"""Current candidate repos for change analysis:
{candidates_str}

User message: "{message}"

Parse the user's intent. Respond with ONLY a JSON object:
{{
  "action": "update" | "skip" | "confirm" | "unknown",
  "corrections": {{
    "service-name": "new-repo-url-or-empty-to-remove"
  }},
  "services_to_skip": ["service-name"]
}}

Examples:
- "there is no redis repo, use https://github.com/org/inv for inventory-service"
  → {{"action": "update", "corrections": {{"inventory-service": "https://github.com/org/inv"}}, "services_to_skip": ["redis"]}}
- "skip all" → {{"action": "skip", "corrections": {{}}, "services_to_skip": []}}
- "confirm" → {{"action": "confirm", "corrections": {{}}, "services_to_skip": []}}
- "I don't know" → {{"action": "unknown", "corrections": {{}}, "services_to_skip": []}}""",
                system="Parse user intent about repository URLs. Respond with ONLY valid JSON, no markdown.",
                max_tokens=300,
            )

            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()

            parsed = json.loads(text)
            action = parsed.get("action", "unknown")

            logger.info("LLM parsed repo correction", extra={
                "agent_name": "supervisor", "action": "repo_llm_parsed",
                "extra": {"parsed_action": action, "corrections": parsed.get("corrections", {}), "skips": parsed.get("services_to_skip", [])},
            })

            if action == "skip":
                self._confirmed_repo_map = {}
                self._repo_confirmation_event.set()
                return "Got it — skipping change analysis."

            if action == "confirm":
                self._confirmed_repo_map = {
                    svc: repo for svc, repo in self._candidate_repos.items() if repo
                }
                self._repo_confirmation_event.set()
                return f"Confirmed {len(self._confirmed_repo_map)} repo(s) — starting change analysis now."

            if action == "update":
                updated = dict(self._candidate_repos)

                # Remove skipped services
                for skip_svc in parsed.get("services_to_skip", []):
                    for candidate_svc in list(updated.keys()):
                        if skip_svc.lower() in candidate_svc.lower() or candidate_svc.lower() in skip_svc.lower():
                            updated[candidate_svc] = ""
                            break

                # Apply corrections
                for svc_name, repo_url in parsed.get("corrections", {}).items():
                    if not repo_url:
                        continue
                    matched = None
                    for candidate_svc in updated:
                        if svc_name.lower() in candidate_svc.lower() or candidate_svc.lower() in svc_name.lower():
                            matched = candidate_svc
                            break
                    if matched:
                        updated[matched] = repo_url
                    else:
                        updated[svc_name] = repo_url

                self._confirmed_repo_map = {s: r for s, r in updated.items() if r}
                logger.info("Repos updated via LLM parsing", extra={
                    "agent_name": "supervisor", "action": "repo_llm_corrected",
                    "extra": {svc: repo for svc, repo in self._confirmed_repo_map.items()},
                })
                self._repo_confirmation_event.set()

                lines = ["Updated repos — starting change analysis:"]
                for svc, repo in self._confirmed_repo_map.items():
                    lines.append(f"  \u2022 {svc} \u2192 {repo}")
                skipped = parsed.get("services_to_skip", [])
                if skipped:
                    lines.append(f"  Skipped: {', '.join(skipped)}")
                return "\n".join(lines)

            # action == "unknown"
            return None

        except Exception as e:
            logger.warning("LLM repo correction parsing failed: %s", e)
            return None

    # ── Fix Generation Pipeline ──────────────────────────────────────────────

    async def start_fix_generation(
        self,
        state: DiagnosticState,
        event_emitter: EventEmitter,
        human_guidance: str = "",
    ) -> None:
        """Orchestrate fix generation with human-in-the-loop approval."""
        import tempfile
        import os

        # Guard against parallel fix generation
        if state.fix_result and state.fix_result.fix_status in (
            FixStatus.GENERATING, FixStatus.VERIFICATION_IN_PROGRESS, FixStatus.AWAITING_REVIEW,
        ):
            await event_emitter.emit("fix_generator", "warning", "Fix generation already in progress")
            return

        tmp_path = ""
        try:
            state.phase = DiagnosticPhase.FIX_IN_PROGRESS
            state.fix_result = FixResult(fix_status=FixStatus.GENERATING)
            await event_emitter.emit("fix_generator", "started", "Fix generation started")

            # Resolve github token
            token = ""
            if self._connection_config and self._connection_config.github_token:
                token = self._connection_config.github_token
            if not token:
                token = os.getenv("GITHUB_TOKEN", "")

            # M2: Validate repo_url format before parsing
            repo_url = state.repo_url or ""
            if repo_url and not (repo_url.startswith("https://") or repo_url.startswith("http://") or repo_url.startswith("git@")):
                state.fix_result.fix_status = FixStatus.FAILED
                await event_emitter.emit("fix_generator", "error", f"Invalid repository URL format: {repo_url}")
                return

            # Parse owner/repo
            owner_repo = self._parse_owner_repo(repo_url) if repo_url else None
            if not owner_repo:
                state.fix_result.fix_status = FixStatus.FAILED
                await event_emitter.emit("fix_generator", "error", "Cannot generate fix — no valid repository URL")
                return

            # Clone repo (full clone for branching)
            from src.utils.repo_manager import RepoManager
            tmp_path = tempfile.mkdtemp(prefix="fix_")
            clone_result = RepoManager.clone_repo(owner_repo, tmp_path, shallow=False, token=token)
            if not clone_result["success"]:
                state.fix_result.fix_status = FixStatus.FAILED
                await event_emitter.emit("fix_generator", "error", f"Clone failed: {clone_result.get('error', 'unknown')}")
                return

            # Create Agent 3 instance
            from src.agents.agent3.fix_generator import Agent3FixGenerator
            agent3 = Agent3FixGenerator(
                repo_path=tmp_path,
                llm_client=self.llm_client,
                event_emitter=event_emitter,
            )

            # Loop for feedback-driven regeneration (replaces recursive call)
            current_guidance = human_guidance
            while True:
                # Generate fix
                state.fix_result.fix_status = FixStatus.GENERATING
                generated_fix = await agent3.generate_fix(state, current_guidance, event_emitter)

                # Store results in state
                target_file = ""
                if state.code_analysis and state.code_analysis.root_cause_location:
                    target_file = state.code_analysis.root_cause_location.file_path
                original_code = agent3._read_original_file(target_file)
                diff = agent3._generate_diff(original_code, generated_fix)

                state.fix_result.target_file = target_file
                state.fix_result.original_code = original_code
                state.fix_result.generated_fix = generated_fix
                state.fix_result.diff = diff
                state.fix_result.fix_explanation = self._build_fix_explanation(state, target_file, diff)

                # Verify with code_agent
                state.fix_result.fix_status = FixStatus.VERIFICATION_IN_PROGRESS
                await event_emitter.emit("fix_generator", "progress", "Verifying fix with code agent...")
                await self._verify_fix_with_code_agent(state, event_emitter)

                verification_failed = (state.fix_result.fix_status == FixStatus.VERIFICATION_FAILED)

                # Run Agent 3 Phase 1 (validation, review, impact, staging)
                pr_data = await agent3.run_verification_phase(state, generated_fix)
                state.fix_result.pr_data = pr_data

                state.fix_result.fix_status = FixStatus.AWAITING_REVIEW
                state.fix_result.attempt_count += 1

                # Arm the approval gate BEFORE sending WebSocket message to close timing gap.
                # This ensures _pending_fix_approval is True by the time the user can respond.
                self._pending_fix_approval = True
                self._fix_human_decision = None
                self._fix_event.clear()
                await event_emitter.emit(
                    "fix_generator", "waiting_for_input",
                    "Fix proposed — awaiting human review",
                    details={"input_type": "fix_approval"},
                )

                # Present fix to human via WebSocket
                summary_lines = [
                    f"**Fix generated for** `{target_file}`\n",
                    f"**Diff:**\n```\n{diff[:2000]}\n```\n",
                ]
                if state.fix_result.fix_explanation:
                    summary_lines.append(f"**Explanation:** {state.fix_result.fix_explanation}\n")
                if verification_failed:
                    summary_lines.append("**WARNING: Code agent flagged issues with this fix.**")
                if state.fix_result.verification_result:
                    vr = state.fix_result.verification_result
                    # H5: Use getattr() — vr may be a Pydantic model or a dict
                    vr_verdict = getattr(vr, 'verdict', None) or (vr.get('verdict', 'unknown') if isinstance(vr, dict) else 'unknown')
                    vr_confidence = getattr(vr, 'confidence', None) or (vr.get('confidence', 0) if isinstance(vr, dict) else 0)
                    vr_issues = getattr(vr, 'issues_found', None) or (vr.get('issues_found', []) if isinstance(vr, dict) else [])
                    vr_risks = getattr(vr, 'regression_risks', None) or (vr.get('regression_risks', []) if isinstance(vr, dict) else [])
                    summary_lines.append(f"**Code agent verdict:** {vr_verdict} (confidence: {vr_confidence}%)")
                    if vr_issues:
                        summary_lines.append(f"**Issues:** {', '.join(vr_issues[:3])}")
                    if vr_risks:
                        summary_lines.append(f"**Regression risks:** {', '.join(vr_risks[:3])}")

                summary_lines.append("\nPlease reply with:")
                summary_lines.append("  - **approve** — create a pull request")
                summary_lines.append("  - **reject** — discard this fix")
                summary_lines.append("  - Or provide feedback to regenerate the fix")

                msg = "\n".join(summary_lines)

                if event_emitter._websocket_manager:
                    await event_emitter._websocket_manager.send_message(
                        state.session_id,
                        {
                            "type": "chat_response",
                            "data": {
                                "role": "assistant",
                                "content": msg,
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "metadata": {"type": "fix_proposal"},
                            },
                        },
                    )

                await event_emitter.emit(
                    "fix_generator", "fix_proposal",
                    f"Fix proposed for {target_file} — awaiting human review",
                    details={"target_file": target_file, "diff_lines": len(diff.splitlines()), "verification_failed": verification_failed},
                )
                try:
                    await asyncio.wait_for(self._fix_event.wait(), timeout=600)
                except asyncio.TimeoutError:
                    self._pending_fix_approval = False
                    state.fix_result.fix_status = FixStatus.FAILED
                    await event_emitter.emit("fix_generator", "warning", "Fix approval timed out")
                    # H4: Don't return early — break to reach the finally block for cleanup
                    break

                self._pending_fix_approval = False
                decision = self._fix_human_decision or "reject"

                if decision == "approve":
                    # Create PR
                    state.fix_result.fix_status = FixStatus.PR_CREATING
                    await event_emitter.emit("fix_generator", "progress", "Creating pull request...")
                    pr_result = await agent3.execute_pr_creation(
                        state.session_id, pr_data, token,
                    )
                    state.fix_result.pr_url = pr_result.get("html_url")
                    state.fix_result.pr_number = pr_result.get("number")
                    state.fix_result.fix_status = FixStatus.PR_CREATED

                    await event_emitter.emit(
                        "fix_generator", "fix_approved",
                        f"PR #{state.fix_result.pr_number} created: {state.fix_result.pr_url}",
                    )
                    return  # Done

                elif decision == "reject":
                    state.fix_result.fix_status = FixStatus.REJECTED
                    await event_emitter.emit("fix_generator", "warning", "Fix rejected by user")
                    return  # Done

                else:
                    # Feedback — loop to regenerate
                    state.fix_result.human_feedback.append(decision)
                    if state.fix_result.attempt_count >= state.fix_result.max_attempts:
                        state.fix_result.fix_status = FixStatus.FAILED
                        await event_emitter.emit("fix_generator", "warning", "Max fix attempts reached")
                        return  # Done

                    state.fix_result.fix_status = FixStatus.HUMAN_FEEDBACK
                    await event_emitter.emit(
                        "fix_generator", "progress",
                        f"Regenerating fix with feedback (attempt {state.fix_result.attempt_count + 1}/{state.fix_result.max_attempts})",
                    )
                    current_guidance = decision
                    # Continue loop

        except Exception as e:
            logger.error("Fix generation failed: %s", e, exc_info=True)
            if state.fix_result:
                state.fix_result.fix_status = FixStatus.FAILED
            await event_emitter.emit("fix_generator", "error", f"Fix generation failed: {str(e)}")
        finally:
            # Cleanup cloned repo
            if tmp_path:
                from src.utils.repo_manager import RepoManager
                RepoManager.cleanup_repo(tmp_path)

    def _build_fix_explanation(self, state: DiagnosticState, target_file: str, diff: str) -> str:
        """Build a human-readable explanation of what the fix does."""
        parts = []
        if state.log_analysis and state.log_analysis.primary_pattern:
            p = state.log_analysis.primary_pattern
            parts.append(f"Addresses {p.exception_type}: {p.error_message[:100]}")
        if state.code_analysis and state.code_analysis.suggested_fix_areas:
            fa = state.code_analysis.suggested_fix_areas[0]
            parts.append(f"Applies fix to {fa.file_path}: {fa.suggested_change[:100]}")
        diff_lines = [l for l in diff.splitlines() if l.startswith('+') and not l.startswith('+++')]
        parts.append(f"Changes {len(diff_lines)} line(s) in {target_file}")
        return ". ".join(parts) if parts else f"Fix applied to {target_file}"

    async def _verify_fix_with_code_agent(
        self, state: DiagnosticState, event_emitter: EventEmitter,
    ) -> dict:
        """Run code_agent in verification mode to review the proposed fix."""
        try:
            agent = CodeNavigatorAgent(connection_config=self._connection_config)

            target_file = state.fix_result.target_file if state.fix_result else ""
            diff = state.fix_result.diff if state.fix_result else ""
            call_chain = state.code_analysis.call_chain if state.code_analysis else []
            findings_summaries = [f.summary[:100] for f in state.all_findings[:5]]

            context = {
                "verification_mode": True,
                "fix_diff": diff,
                "fix_file": target_file,
                "call_chain": call_chain,
                "original_findings": findings_summaries,
                "repo_url": state.repo_url or "",
                "service_name": state.service_name,
            }
            if self._connection_config and self._connection_config.github_token:
                context["github_token"] = self._connection_config.github_token

            result = await agent.run(context, event_emitter)

            # Extract only verification-relevant fields (not the full agent result)
            verification_data = {
                "verdict": result.get("verdict", "approve"),
                "confidence": result.get("confidence", 50),
                "issues_found": result.get("issues_found", []),
                "regression_risks": result.get("regression_risks", []),
                "suggestions": result.get("suggestions", []),
                "reasoning": result.get("reasoning", ""),
            }
            if state.fix_result:
                state.fix_result.verification_result = verification_data

            verdict = verification_data.get("verdict", "approve")
            if verdict == "reject":
                state.fix_result.fix_status = FixStatus.VERIFICATION_FAILED
                await event_emitter.emit(
                    "code_agent", "warning",
                    f"Code agent flagged issues with the fix: {result.get('reasoning', '')[:200]}",
                )
            else:
                state.fix_result.fix_status = FixStatus.VERIFIED

            return result
        except Exception as e:
            logger.warning("Fix verification failed: %s", e)
            if state.fix_result:
                state.fix_result.verification_result = {
                    "verdict": "needs_changes",
                    "confidence": 0,
                    "issues_found": [],
                    "regression_risks": [],
                    "suggestions": [],
                    "reasoning": f"Verification could not run: {e}",
                }
                # Don't block on verification crash, but don't pretend it passed
                state.fix_result.fix_status = FixStatus.VERIFICATION_IN_PROGRESS
            return {"verdict": "needs_changes", "confidence": 0, "reasoning": f"Verification skipped: {e}"}

    def _process_fix_decision(self, message: str) -> str:
        """Parse user's fix approval/rejection/feedback and signal the waiting coroutine."""
        text = message.strip().lower()

        if text in ("approve", "yes", "create pr", "lgtm", "ok", "y"):
            self._fix_human_decision = "approve"
            self._fix_event.set()
            return "Approved — creating pull request now."

        if text in ("reject", "no", "cancel", "discard"):
            self._fix_human_decision = "reject"
            self._fix_event.set()
            return "Fix rejected. Diagnosis remains available."

        # Anything else is treated as feedback for regeneration
        self._fix_human_decision = message.strip()
        self._fix_event.set()
        return "Got it — regenerating fix with your feedback."

    def acknowledge_attestation(self, decision: str) -> str:
        """Record that the user has acknowledged the discovery attestation gate."""
        if decision == "approve":
            self._attestation_acknowledged = True
            return "Attestation acknowledged — fix generation is now available."
        elif decision == "reject":
            self._attestation_acknowledged = False
            return "Attestation rejected — investigation findings need revision."
        return "Unknown attestation decision."

    def _process_repo_mismatch(self, message: str, state: DiagnosticState) -> str:
        """Parse user's repo mismatch response and signal the waiting coroutine."""
        import re
        text = message.strip().lower()

        if text in ("keep", "no", "skip"):
            self._mismatch_confirmed_repo = None
            self._repo_mismatch_event.set()
            return "Keeping current repo — continuing code analysis."

        if text in ("confirm", "yes", "ok", "y", "switch"):
            # Derive the PZ repo and switch to it
            pz_svc = ""
            if state.patient_zero:
                pz_svc = state.patient_zero.get("service", "") if isinstance(state.patient_zero, dict) else ""
            if pz_svc and state.repo_url:
                candidates = self._derive_candidate_repos(state.repo_url, [pz_svc], state.service_name)
                derived = candidates.get(pz_svc, "")
                if derived:
                    self._mismatch_confirmed_repo = derived
                    self._repo_mismatch_event.set()
                    return f"Switching to `{derived}` for code analysis."
            self._mismatch_confirmed_repo = None
            self._repo_mismatch_event.set()
            return "Could not derive repo URL — continuing with current repo."

        # Try to parse a raw URL
        url_match = re.search(r'(https?://\S+|git@\S+)', message)
        if url_match:
            self._mismatch_confirmed_repo = url_match.group(1)
            self._repo_mismatch_event.set()
            return f"Switching to `{self._mismatch_confirmed_repo}` for code analysis."

        return (
            "I didn't understand that. Please reply:\n"
            "  \u2022 **confirm** to switch to the derived repo\n"
            "  \u2022 **keep** to continue with the current repo\n"
            "  \u2022 Or provide a URL like: `https://github.com/org/repo`"
        )
