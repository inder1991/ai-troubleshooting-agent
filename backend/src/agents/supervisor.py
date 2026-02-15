import json
import asyncio
from typing import Optional

from src.models.schemas import (
    DiagnosticState, DiagnosticPhase, Finding, CriticVerdict, TokenUsage, TimeWindow
)
from src.agents.log_agent import LogAnalysisAgent
from src.agents.metrics_agent import MetricsAgent
from src.agents.k8s_agent import K8sAgent
from src.agents.tracing_agent import TracingAgent
from src.agents.code_agent import CodeNavigatorAgent
from src.agents.critic_agent import CriticAgent
from src.utils.llm_client import AnthropicClient
from src.utils.event_emitter import EventEmitter


class SupervisorAgent:
    """State machine orchestrator that routes work to specialized agents."""

    def __init__(self):
        self.agent_name = "supervisor"
        self.llm_client = AnthropicClient(agent_name="supervisor")
        self._agents = {
            "log_agent": LogAnalysisAgent,
            "metrics_agent": MetricsAgent,
            "k8s_agent": K8sAgent,
            "tracing_agent": TracingAgent,
            "code_agent": CodeNavigatorAgent,
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
                state.phase = DiagnosticPhase.DIAGNOSIS_COMPLETE
                await event_emitter.emit("supervisor", "success", "Diagnosis complete")
                break

            state.agents_pending = next_agents

            # Dispatch agents (parallel if multiple)
            for agent_name in next_agents:
                await event_emitter.emit("supervisor", "progress", f"Dispatching {agent_name}")
                agent_result = await self._dispatch_agent(agent_name, state, event_emitter)

                if agent_result:
                    self._update_state_with_result(state, agent_name, agent_result)
                    state.agents_completed.append(agent_name)

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

            self._update_phase(state)

        # Compile token usage
        state.token_usage.append(self.llm_client.get_total_usage())
        state.token_usage.append(self._critic.get_token_usage())

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
        self, agent_name: str, state: DiagnosticState, event_emitter: EventEmitter
    ) -> Optional[dict]:
        """Dispatch a specialized agent and return its result."""
        agent_cls = self._agents.get(agent_name)
        if not agent_cls:
            return None

        agent = agent_cls()
        context = self._build_agent_context(agent_name, state)

        try:
            result = await agent.run(context, event_emitter)
            # Collect token usage
            state.token_usage.append(agent.get_token_usage())
            return result
        except Exception as e:
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

        return base

    def _update_state_with_result(self, state: DiagnosticState, agent_name: str, result: dict) -> None:
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

        # Store reasoning
        state.supervisor_reasoning.append(
            f"Round: {agent_name} completed with confidence {confidence}"
        )

    def _update_phase(self, state: DiagnosticState) -> None:
        """Update diagnostic phase based on completed agents."""
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
