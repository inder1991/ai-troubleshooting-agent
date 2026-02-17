import asyncio
import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from anthropic import APIStatusError

from src.models.schemas import Breadcrumb, EvidencePin, NegativeFinding, ReActBudget, TokenUsage
from src.utils.llm_client import AnthropicClient
from src.utils.event_emitter import EventEmitter

MAX_RETRIES = 3
RETRY_DELAYS = [2, 5, 15]  # seconds


class ReActAgent(ABC):
    """Abstract base class implementing the ReAct (Reason + Act + Observe) pattern."""

    def __init__(
        self,
        agent_name: str,
        max_iterations: int = 10,
        model: str = "claude-sonnet-4-5-20250929",
    ):
        self.agent_name = agent_name
        self.max_iterations = max_iterations
        self.llm_client = AnthropicClient(agent_name=agent_name, model=model)
        self.breadcrumbs: list[Breadcrumb] = []
        self.negative_findings: list[NegativeFinding] = []
        self.evidence_pins: list[EvidencePin] = []
        self.budget = ReActBudget()
        self._tools: list[dict] = []
        self._tool_handlers: dict[str, Any] = {}

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

        if event_emitter:
            await event_emitter.emit(self.agent_name, "started", f"{self.agent_name} starting analysis")

        messages = [{"role": "user", "content": initial_prompt}]

        for iteration in range(self.max_iterations):
            if self.budget.is_exhausted():
                if event_emitter:
                    await event_emitter.emit(self.agent_name, "warning", "Budget exhausted")
                return {
                    "error": "budget_exhausted",
                    "partial_results": self.breadcrumbs,
                    "evidence_pins": [p.model_dump(mode="json") for p in self.evidence_pins],
                }

            # Call LLM with tools (retry on transient errors)
            response = None
            for attempt in range(MAX_RETRIES + 1):
                try:
                    response = await self.llm_client._client.messages.create(
                        model=self.llm_client.model,
                        max_tokens=4096,
                        system=system_prompt,
                        messages=messages,
                        tools=self._tools if self._tools else None,
                        temperature=0.0,
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

            # Track tokens
            self.llm_client._total_input_tokens += response.usage.input_tokens
            self.llm_client._total_output_tokens += response.usage.output_tokens
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
                return result

            if tool_use_blocks:
                # Add assistant message with all content blocks
                messages.append({"role": "assistant", "content": response.content})

                # Process each tool call
                tool_results = []
                for tool_block in tool_use_blocks:
                    tool_name = tool_block.name
                    tool_input = tool_block.input

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

                    self.budget.record_tool_call()

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_block.id,
                        "content": result,
                    })

                messages.append({"role": "user", "content": tool_results})
            else:
                # No tool calls and not end_turn — shouldn't happen, but handle gracefully
                final_text = text_blocks[0].text if text_blocks else ""
                result = self._parse_final_response(final_text)
                result["evidence_pins"] = [p.model_dump(mode="json") for p in self.evidence_pins]
                return result

        # Max iterations reached
        if event_emitter:
            await event_emitter.emit(self.agent_name, "warning", f"Max iterations ({self.max_iterations}) reached")

        return {
            "error": "max_iterations_reached",
            "partial_results": self.breadcrumbs,
            "evidence_pins": [p.model_dump(mode="json") for p in self.evidence_pins],
        }
