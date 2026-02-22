import asyncio
import json
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from anthropic import APIStatusError

from src.models.schemas import Breadcrumb, EvidencePin, NegativeFinding, ReActBudget, TokenUsage
from src.utils.llm_client import AnthropicClient
from src.utils.event_emitter import EventEmitter
from src.utils.logger import get_logger

logger = get_logger(__name__)

MAX_RETRIES = 3
RETRY_DELAYS = [2, 5, 15]  # seconds

DEFAULT_MODEL = "claude-sonnet-4-20250514"


class ReActAgent(ABC):
    """Abstract base class implementing the ReAct (Reason + Act + Observe) pattern."""

    _INFRA_ERROR_PATTERNS = [
        "connection refused", "connection error", "connect timeout",
        "name or service not known", "no route to host", "unreachable",
        "connectionerror", "readtimeouterror", "cannot connect",
        "404 not found", "403 forbidden", "401 unauthorized",
    ]

    def __init__(
        self,
        agent_name: str,
        max_iterations: int = 10,
        model: str = "",
        connection_config=None,
        budget_overrides: dict | None = None,
    ):
        # Model resolution: explicit > per-agent override > global config > env > default
        resolved_model = model
        if not resolved_model and connection_config:
            overrides = dict(getattr(connection_config, 'llm_model_overrides', ()))
            resolved_model = overrides.get(agent_name, "")
            if not resolved_model:
                resolved_model = getattr(connection_config, 'llm_model', "")
        if not resolved_model:
            resolved_model = os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL)

        # Iteration resolution: per-agent override > global config > constructor default
        MIN_ITERATIONS = 3
        resolved_iters = max_iterations
        if connection_config:
            iter_overrides = dict(getattr(connection_config, 'max_iterations_overrides', ()))
            if agent_name in iter_overrides:
                resolved_iters = iter_overrides[agent_name]
            elif getattr(connection_config, 'max_iterations', 0) > 0:
                resolved_iters = connection_config.max_iterations
        resolved_iters = max(resolved_iters, MIN_ITERATIONS)
        logger.info("Iteration config resolved", extra={
            "agent_name": agent_name, "action": "iter_config",
            "extra": {"constructor_arg": max_iterations, "config_val": getattr(connection_config, 'max_iterations', None), "resolved": resolved_iters},
        })

        self.agent_name = agent_name
        self.max_iterations = resolved_iters
        self.llm_client = AnthropicClient(agent_name=agent_name, model=resolved_model)
        self.breadcrumbs: list[Breadcrumb] = []
        self.negative_findings: list[NegativeFinding] = []
        self.evidence_pins: list[EvidencePin] = []
        self.budget = ReActBudget(**(budget_overrides or {}))
        self._tools: list[dict] = []
        self._tool_handlers: dict[str, Any] = {}
        self._consecutive_infra_failures = 0
        self._wrap_up_nudge_sent = False

    @abstractmethod
    async def _define_tools(self) -> list[dict]:
        """Define the tools available to this agent. Return Anthropic tool format."""
        ...

    @abstractmethod
    async def _build_system_prompt(self) -> str:
        """Build the system prompt for this agent."""
        ...

    @abstractmethod
    async def _build_initial_prompt(self, context: dict) -> str:
        """Build the initial user prompt from the given context."""
        ...

    @abstractmethod
    async def _handle_tool_call(self, tool_name: str, tool_input: dict) -> str:
        """Execute a tool call and return the result as a string."""
        ...

    @abstractmethod
    def _parse_final_response(self, text: str) -> dict:
        """Parse the agent's final text response into structured output."""
        ...

    def add_breadcrumb(
        self,
        action: str,
        source_type: str,
        source_reference: str,
        raw_evidence: str,
    ) -> None:
        """Record evidence trail for traceability."""
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
        self,
        what_was_checked: str,
        result: str,
        implication: str,
        source_reference: str,
    ) -> None:
        """Record what was checked and NOT found — builds trust."""
        self.negative_findings.append(
            NegativeFinding(
                agent_name=self.agent_name,
                what_was_checked=what_was_checked,
                result=result,
                implication=implication,
                source_reference=source_reference,
            )
        )

    def add_evidence_pin(
        self,
        claim: str,
        supporting_evidence: list[str],
        source_tool: str,
        confidence: float,
        evidence_type: str,
    ) -> EvidencePin:
        """Pin a piece of evidence with structured metadata."""
        pin = EvidencePin(
            claim=claim,
            supporting_evidence=supporting_evidence,
            source_agent=self.agent_name,
            source_tool=source_tool,
            confidence=confidence,
            timestamp=datetime.now(timezone.utc),
            evidence_type=evidence_type,
        )
        self.evidence_pins.append(pin)
        return pin

    def get_token_usage(self) -> TokenUsage:
        """Get cumulative token usage for this agent."""
        return self.llm_client.get_total_usage()

    def _summarize_tool_call(self, tool_name: str, tool_input: dict) -> str:
        """Generate human-readable summary of a tool call. Subclasses may override."""
        summaries = {
            "search_elasticsearch": lambda i: f"Searching logs in '{i.get('index', 'default')}' for '{i.get('query', '')}' ({i.get('time_range', 'recent')})",
            "analyze_patterns": lambda i: f"Analyzing error patterns in {i.get('log_count', 'collected')} log entries",
            "query_prometheus": lambda i: f"Querying metric: {i.get('query', i.get('metric_name', 'unknown'))}",
            "get_pod_status": lambda i: f"Checking pod health in namespace '{i.get('namespace', 'default')}'",
            "get_recent_events": lambda i: f"Fetching recent K8s events for '{i.get('namespace', 'default')}'",
            "search_traces": lambda i: f"Searching traces for service '{i.get('service_name', 'unknown')}'",
            "analyze_code": lambda i: f"Analyzing code at '{i.get('file_path', 'unknown')}'",
            "list_available_indices": lambda i: "Discovering available log indices",
            "get_pod_logs": lambda i: f"Fetching logs for pod '{i.get('pod_name', 'unknown')}'",
            "get_deployments": lambda i: f"Listing deployments in '{i.get('namespace', 'default')}'",
            "describe_resource": lambda i: f"Describing {i.get('resource_type', 'resource')} '{i.get('name', 'unknown')}'",
            "github_recent_commits": lambda i: f"Fetching recent commits from '{i.get('repo_url', 'repository')}'",
            "deployment_history": lambda i: f"Checking deployment rollout history in '{i.get('namespace', 'default')}'",
            "config_diff": lambda i: f"Checking ConfigMap changes in '{i.get('namespace', 'default')}'",
            "github_get_commit_diff": lambda i: f"Fetching diff for commit '{i.get('commit_sha', 'unknown')[:8]}'",
        }
        fn = summaries.get(tool_name)
        if fn:
            try:
                return fn(tool_input)
            except Exception:
                pass
        return f"Running {tool_name}"

    async def run(self, context: dict, event_emitter: EventEmitter | None = None) -> dict:
        """Execute the ReAct loop.

        1. Build system prompt and initial user message
        2. Send to LLM with tools
        3. If LLM calls a tool: execute it, feed result back, loop
        4. If LLM returns text (no tool call): parse and return
        5. Stop after max_iterations
        """
        self._tools = await self._define_tools()
        system_prompt = await self._build_system_prompt()
        initial_prompt = await self._build_initial_prompt(context)

        logger.info("Agent started", extra={"agent_name": self.agent_name, "action": "start", "extra": {"iteration": 0}})

        if event_emitter:
            await event_emitter.emit(self.agent_name, "started", f"{self.agent_name} starting analysis")

        messages = [{"role": "user", "content": initial_prompt}]

        for iteration in range(self.max_iterations):
            # Check if budget is exhausted — force a final answer instead of returning nothing
            if self.budget.is_exhausted():
                logger.warning("Budget exhausted — forcing final answer", extra={
                    "agent_name": self.agent_name, "action": "budget_exhausted_wrap_up",
                    "extra": {
                        "llm_calls": f"{self.budget.current_llm_calls}/{self.budget.max_llm_calls}",
                        "tool_calls": f"{self.budget.current_tool_calls}/{self.budget.max_tool_calls}",
                        "tokens": f"{self.budget.current_tokens}/{self.budget.max_tokens}",
                        "iteration": iteration,
                    },
                })
                if event_emitter:
                    await event_emitter.emit(self.agent_name, "warning", "Budget low — producing final answer")
                # Force one last LLM call with NO tools to get a final answer
                wrap_up_result = await self._force_final_answer(system_prompt, messages, event_emitter)
                if wrap_up_result is not None:
                    return wrap_up_result
                # If wrap-up also failed, fall through to empty return
                return {
                    "error": "budget_exhausted",
                    "partial_results": self.breadcrumbs,
                    "evidence_pins": [p.model_dump(mode="json") for p in self.evidence_pins],
                }

            # Inject wrap-up nudge when iterations are running low
            remaining_iterations = self.max_iterations - iteration
            remaining_llm_calls = self.budget.max_llm_calls - self.budget.current_llm_calls
            remaining_budget_pct = 1.0 - (self.budget.current_tokens / self.budget.max_tokens) if self.budget.max_tokens > 0 else 1.0

            # Only nudge if we've used at least 60% of iterations (avoids premature nudge on short agents)
            used_pct = iteration / self.max_iterations if self.max_iterations > 0 else 0
            if used_pct >= 0.6 and (remaining_iterations == 2 or remaining_llm_calls == 2 or remaining_budget_pct < 0.15):
                if not getattr(self, '_wrap_up_nudge_sent', False):
                    self._wrap_up_nudge_sent = True
                    messages.append({
                        "role": "user",
                        "content": (
                            "⚠️ SYSTEM: You are running low on budget. "
                            "You have ~2 iterations remaining. "
                            "STOP investigating and produce your FINAL JSON ANSWER NOW "
                            "with everything you have found so far. Do NOT make any more tool calls."
                        ),
                    })
                    logger.info("Wrap-up nudge injected", extra={
                        "agent_name": self.agent_name, "action": "wrap_up_nudge",
                        "extra": {"iteration": iteration, "remaining_iters": remaining_iterations,
                                  "remaining_llm_calls": remaining_llm_calls,
                                  "remaining_budget_pct": f"{remaining_budget_pct:.0%}"},
                    })

            # Call LLM with tools (retry on transient errors)
            response = None
            for attempt in range(MAX_RETRIES + 1):
                try:
                    response = await self.llm_client.chat_with_tools(
                        system=system_prompt,
                        messages=messages,
                        tools=self._tools if self._tools else None,
                    )
                    break
                except APIStatusError as e:
                    if e.status_code in (429, 529) and attempt < MAX_RETRIES:
                        delay = RETRY_DELAYS[attempt]
                        if event_emitter:
                            await event_emitter.emit(
                                self.agent_name, "warning",
                                f"API overloaded, retrying in {delay}s (attempt {attempt + 1}/{MAX_RETRIES})"
                            )
                        await asyncio.sleep(delay)
                    elif e.status_code >= 500 and attempt < MAX_RETRIES:
                        delay = RETRY_DELAYS[attempt]
                        if event_emitter:
                            await event_emitter.emit(
                                self.agent_name, "warning",
                                f"Server error ({e.status_code}), retrying in {delay}s (attempt {attempt + 1}/{MAX_RETRIES})"
                            )
                        await asyncio.sleep(delay)
                    else:
                        raise

            if response is None:
                raise RuntimeError("LLM call failed after all retries")

            # Budget tracking (token accounting is handled by chat_with_tools)
            self.budget.record_llm_call(response.usage.input_tokens + response.usage.output_tokens)

            # Check if the response contains tool use
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
            text_blocks = [b for b in response.content if b.type == "text"]

            if response.stop_reason == "end_turn" and not tool_use_blocks:
                # Agent is done — parse final response
                final_text = text_blocks[0].text if text_blocks else ""
                if event_emitter:
                    await event_emitter.emit(self.agent_name, "success", f"{self.agent_name} completed analysis")
                result = self._parse_final_response(final_text)
                result["evidence_pins"] = [p.model_dump(mode="json") for p in self.evidence_pins]
                logger.info("Agent completed", extra={"agent_name": self.agent_name, "action": "complete", "extra": {"iterations": iteration + 1, "findings": len(self.evidence_pins)}})
                return result

            if tool_use_blocks:
                # Add assistant message with all content blocks
                messages.append({"role": "assistant", "content": response.content})

                # Process each tool call
                tool_results = []
                for tool_block in tool_use_blocks:
                    tool_name = tool_block.name
                    tool_input = tool_block.input

                    # Log tool call with input params (redact tokens/credentials)
                    safe_input = {k: ("***" if "token" in k.lower() or "secret" in k.lower() or "password" in k.lower() else v) for k, v in tool_input.items()}
                    logger.info("Tool called", extra={"agent_name": self.agent_name, "action": "tool_call", "tool": tool_name, "extra": {"iteration": iteration + 1, "input": safe_input}})

                    if event_emitter:
                        summary = self._summarize_tool_call(tool_name, tool_input)
                        await event_emitter.emit(
                            self.agent_name, "tool_call",
                            summary,
                            details={"tool": tool_name, "input_keys": list(tool_input.keys())}
                        )

                    try:
                        result = await self._handle_tool_call(tool_name, tool_input)
                    except Exception as e:
                        result = f"Error executing {tool_name}: {str(e)}"

                    # Log tool result (truncated for readability)
                    result_preview = result[:500] if isinstance(result, str) else str(result)[:500]
                    logger.info("Tool result", extra={
                        "agent_name": self.agent_name, "action": "tool_result",
                        "tool": tool_name,
                        "extra": {"iteration": iteration + 1, "result_length": len(result) if isinstance(result, str) else 0, "preview": result_preview},
                    })

                    self.budget.record_tool_call()

                    # Track consecutive infrastructure failures for early exit.
                    # Only check error results (from the except block above), NOT
                    # successful tool results — source code files naturally contain
                    # strings like "ConnectionError" that would false-positive here.
                    result_str = result if isinstance(result, str) else ""
                    is_tool_error = result_str.startswith("Error executing ")
                    if is_tool_error and any(pat in result_str.lower() for pat in self._INFRA_ERROR_PATTERNS):
                        self._consecutive_infra_failures += 1
                    elif not is_tool_error:
                        self._consecutive_infra_failures = 0

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_block.id,
                        "content": result,
                    })

                # Early exit if infrastructure is consistently unreachable
                if self._consecutive_infra_failures >= 2:
                    logger.warning("Early exit: infrastructure unavailable", extra={
                        "agent_name": self.agent_name, "action": "early_exit_infra",
                    })
                    if event_emitter:
                        await event_emitter.emit(
                            self.agent_name, "warning",
                            f"{self.agent_name}: data source unreachable after {self._consecutive_infra_failures} failures — stopping early"
                        )
                    return {
                        "error": "data_source_unreachable",
                        "partial_results": self.breadcrumbs,
                        "evidence_pins": [p.model_dump(mode="json") for p in self.evidence_pins],
                    }

                messages.append({"role": "user", "content": tool_results})
            else:
                # No tool calls and not end_turn — shouldn't happen, but handle gracefully
                final_text = text_blocks[0].text if text_blocks else ""
                result = self._parse_final_response(final_text)
                result["evidence_pins"] = [p.model_dump(mode="json") for p in self.evidence_pins]
                return result

        # Max iterations reached — force a final answer instead of returning nothing
        logger.warning("Max iterations reached — forcing final answer", extra={"agent_name": self.agent_name, "action": "max_iterations", "extra": {"max": self.max_iterations}})
        if event_emitter:
            await event_emitter.emit(self.agent_name, "warning", f"Max iterations ({self.max_iterations}) reached — producing final answer")

        wrap_up_result = await self._force_final_answer(system_prompt, messages, event_emitter)
        if wrap_up_result is not None:
            return wrap_up_result

        return {
            "error": "max_iterations_reached",
            "partial_results": self.breadcrumbs,
            "evidence_pins": [p.model_dump(mode="json") for p in self.evidence_pins],
        }

    async def _force_final_answer(
        self, system_prompt: str, messages: list, event_emitter: EventEmitter | None
    ) -> dict | None:
        """Make one last LLM call with no tools to force a final text answer."""
        try:
            wrap_up_messages = messages + [{
                "role": "user",
                "content": (
                    "⚠️ SYSTEM: Budget/iterations exhausted. You MUST produce your FINAL JSON ANSWER NOW. "
                    "Summarize ALL findings from the tool calls you already made. "
                    "Do NOT call any tools. Respond ONLY with your final JSON answer."
                ),
            }]
            response = await self.llm_client.chat_with_tools(
                system=system_prompt,
                messages=wrap_up_messages,
                tools=None,  # No tools — force text-only response
            )
            text_blocks = [b for b in response.content if b.type == "text"]
            if text_blocks:
                final_text = text_blocks[0].text
                logger.info("Forced final answer produced", extra={
                    "agent_name": self.agent_name, "action": "forced_final_answer",
                    "extra": {"response_length": len(final_text)},
                })
                if event_emitter:
                    await event_emitter.emit(self.agent_name, "success", f"{self.agent_name} completed analysis")
                result = self._parse_final_response(final_text)
                result["evidence_pins"] = [p.model_dump(mode="json") for p in self.evidence_pins]
                return result
        except Exception as e:
            logger.error("Failed to force final answer", extra={
                "agent_name": self.agent_name, "action": "forced_final_answer_error",
                "extra": {"error": str(e)},
            })
        return None
