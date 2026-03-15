import asyncio
import json
import logging
import uuid
from src.utils.llm_client import AnthropicClient
from src.database.models import DBFindingV2, EvidenceSource
from .tool_policy import ToolPolicyEnforcer, ToolCallExecutor, ToolCallRecord
from .tool_definitions import (
    QUERY_ANALYST_TOOLS, HEALTH_ANALYST_TOOLS, SCHEMA_ANALYST_TOOLS, FINDING_OUTPUT_TOOL,
)
from .prompts import get_query_analyst_prompt, get_health_analyst_prompt, get_schema_analyst_prompt

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 4096
DEFAULT_MAX_ITERATIONS = 5
DEFAULT_AGENT_TIMEOUT = 60.0

AGENT_CONFIG = {
    "query_analyst": {
        "tools": QUERY_ANALYST_TOOLS,
        "prompt_fn": get_query_analyst_prompt,
        "model": "claude-haiku-4-5-20251001",
    },
    "health_analyst": {
        "tools": HEALTH_ANALYST_TOOLS,
        "prompt_fn": get_health_analyst_prompt,
        "model": "claude-haiku-4-5-20251001",
    },
    "schema_analyst": {
        "tools": SCHEMA_ANALYST_TOOLS,
        "prompt_fn": get_schema_analyst_prompt,
        "model": "claude-haiku-4-5-20251001",
    },
}


async def run_llm_agent(
    agent_name: str,
    adapter,
    emitter,
    engine: str = "postgresql",
    context: dict | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    timeout: float = DEFAULT_AGENT_TIMEOUT,
) -> tuple[list[DBFindingV2], list[ToolCallRecord]]:
    """Run a single LLM tool-calling agent. Returns (findings, call_log)."""

    config = AGENT_CONFIG.get(agent_name)
    if not config:
        raise ValueError(f"Unknown agent: {agent_name}")

    # Build tools list (agent-specific tools + report_findings output tool)
    tools = config["tools"] + [FINDING_OUTPUT_TOOL]

    # Get system prompt
    system_prompt = config["prompt_fn"](engine)

    # Build initial user message with context
    context_str = json.dumps(context or {}, indent=2, default=str)
    user_message = (
        f"Diagnose this {engine} database. Context:\n{context_str}\n\n"
        "Begin your investigation by calling diagnostic tools."
    )

    # Initialize policy enforcer and executor
    policy = ToolPolicyEnforcer(agent_name)
    executor = ToolCallExecutor(agent_name, adapter, emitter, policy)

    # LLM client
    llm = AnthropicClient(agent_name=agent_name, model=config["model"])

    # Message history
    messages = [{"role": "user", "content": user_message}]

    findings: list[DBFindingV2] = []

    try:
        for iteration in range(max_iterations):
            # Call LLM with tools
            response = await asyncio.wait_for(
                llm.chat_with_tools(
                    system=system_prompt,
                    messages=messages,
                    tools=tools,
                    max_tokens=DEFAULT_MAX_TOKENS,
                    temperature=0.0,
                ),
                timeout=timeout / max_iterations,  # Budget per iteration
            )

            # Process response content
            assistant_content = []
            tool_results = []
            found_report = False

            for block in getattr(response, 'content', []):
                assistant_content.append(block)
                block_type = getattr(block, 'type', None)

                if block_type == "text" and getattr(block, 'text', ''):
                    # Emit reasoning in real-time
                    await emitter.emit(agent_name, "reasoning", block.text)

                    # Check for free-text tool attempts
                    if executor._looks_like_tool_call(block.text):
                        logger.warning("Free-text tool attempt", extra={
                            "agent": agent_name, "text": block.text[:200],
                        })

                elif block_type == "tool_use":
                    block_name = getattr(block, 'name', None)
                    if not block_name:
                        continue

                    if block_name == "report_findings":
                        # Validate input is a dict
                        if not isinstance(getattr(block, 'input', None), dict):
                            logger.warning("Malformed report_findings: input is not a dict")
                            continue

                        # Parse findings from the output tool
                        found_report = True
                        raw_findings = block.input.get("findings", [])
                        for rf in raw_findings:
                            evidence_sources = [
                                EvidenceSource(
                                    tool_call_id=es.get("tool_call_id", ""),
                                    tool_name=es.get("tool_name", ""),
                                    data_snippet=es.get("data_snippet", ""),
                                )
                                for es in rf.get("evidence_sources", [])
                            ]
                            findings.append(DBFindingV2(
                                finding_id=f"f-{agent_name}-{uuid.uuid4().hex[:8]}",
                                agent=agent_name,
                                category=rf.get("category", "configuration"),
                                title=rf.get("title", ""),
                                severity=rf.get("severity", "medium"),
                                confidence_raw=rf.get("confidence", 0.7),
                                confidence_calibrated=rf.get("confidence", 0.7),
                                detail=rf.get("detail", ""),
                                evidence_sources=evidence_sources,
                                recommendation=rf.get("recommendation", ""),
                                remediation_sql=rf.get("remediation_sql", ""),
                                remediation_warning=rf.get("remediation_warning", ""),
                                related_findings=rf.get("related_findings", []),
                                remediation_available=bool(rf.get("remediation_sql")),
                                rule_check="llm_assessed",
                            ))

                        # Add tool result to continue conversation
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": f"Recorded {len(raw_findings)} findings.",
                        })
                    else:
                        # Execute diagnostic tool via executor
                        await emitter.emit(agent_name, "progress",
                            f"Calling {block_name}({json.dumps(getattr(block, 'input', {}) or {})[:80]})")

                        result = await executor.execute_tool_call(
                            block_name, getattr(block, 'input', None) or {}, block.id
                        )
                        tool_results.append(result)

            # Add assistant message + tool results to history
            messages.append({"role": "assistant", "content": assistant_content})
            if tool_results:
                messages.append({"role": "user", "content": tool_results})

            # Cap message history to prevent unbounded growth
            MAX_MESSAGES = 20
            if len(messages) > MAX_MESSAGES:
                messages = [messages[0]] + messages[-(MAX_MESSAGES - 1):]

            # If report_findings was called or stop_reason is end_turn, we're done
            if found_report or response.stop_reason == "end_turn":
                break

        # Emit finding count
        if emitter:
            await emitter.emit(agent_name, "finding",
                f"LLM analysis complete — {len(findings)} findings",
                details={"finding_count": len(findings)})

    except asyncio.TimeoutError:
        logger.warning("LLM agent timed out", extra={"agent": agent_name})
        if emitter:
            await emitter.emit(agent_name, "warning", f"LLM analysis timed out after {timeout}s")
    except Exception as e:
        logger.error("LLM agent failed: %s", e, extra={"agent": agent_name})
        if emitter:
            await emitter.emit(agent_name, "warning", f"LLM analysis failed: {e}")

    return findings, executor.call_log
