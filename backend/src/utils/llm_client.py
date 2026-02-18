import os
import time
from anthropic import AsyncAnthropic
from src.models.schemas import TokenUsage
from src.utils.logger import get_logger

logger = get_logger(__name__)


class LLMResponse:
    """Wrapper for Anthropic API response."""
    def __init__(self, text: str, input_tokens: int, output_tokens: int):
        self.text = text
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class AnthropicClient:
    """Anthropic API client with cumulative token tracking."""

    def __init__(self, agent_name: str = "unknown", model: str = "claude-3-5-haiku-20241022"):
        self.agent_name = agent_name
        self.model = model  # Caller handles resolution
        self._client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self._total_input_tokens = 0
        self._total_output_tokens = 0

    async def chat(
        self,
        prompt: str,
        system: str | None = None,
        messages: list[dict] | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Send a message to Claude and track token usage."""
        if messages is None:
            messages = [{"role": "user", "content": prompt}]

        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system

        logger.info("LLM call", extra={
            "agent_name": self.agent_name,
            "action": "llm_call",
            "tool": self.model,
            "tokens": {"max_tokens": max_tokens},
            "extra": {
                "system": (system[:500] + "...") if system and len(system) > 500 else system,
                "messages": [
                    {"role": m["role"], "content": m["content"][:1000] + "..." if len(m.get("content", "")) > 1000 else m.get("content", "")}
                    for m in messages
                ],
                "temperature": temperature,
            },
        })

        start = time.monotonic()
        try:
            response = await self._client.messages.create(**kwargs)
        except Exception as e:
            logger.error("LLM call failed", extra={"agent_name": self.agent_name, "action": "llm_error", "extra": str(e)})
            raise

        elapsed_ms = round((time.monotonic() - start) * 1000)
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens

        text = response.content[0].text if response.content else ""

        logger.info("LLM response", extra={
            "agent_name": self.agent_name,
            "action": "llm_response",
            "tokens": {"input": input_tokens, "output": output_tokens},
            "duration_ms": elapsed_ms,
            "extra": {
                "response": text[:2000] + "..." if len(text) > 2000 else text,
                "stop_reason": response.stop_reason,
            },
        })

        return LLMResponse(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    async def chat_with_tools(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ):
        """Send a message with tool definitions. Returns raw Anthropic response object."""
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools

        logger.info("LLM call", extra={
            "agent_name": self.agent_name,
            "action": "llm_call",
            "tool": self.model,
            "extra": {
                "system": (system[:500] + "...") if len(system) > 500 else system,
                "message_count": len(messages),
                "tool_count": len(tools) if tools else 0,
            },
        })

        start = time.monotonic()
        try:
            response = await self._client.messages.create(**kwargs)
        except Exception as e:
            logger.error("LLM call failed", extra={
                "agent_name": self.agent_name, "action": "llm_error", "extra": str(e)
            })
            raise

        elapsed_ms = round((time.monotonic() - start) * 1000)
        self._total_input_tokens += response.usage.input_tokens
        self._total_output_tokens += response.usage.output_tokens

        # Response logging
        tool_names = [b.name for b in response.content if b.type == "tool_use"]
        text_preview = ""
        for b in response.content:
            if b.type == "text" and b.text:
                text_preview = b.text[:1000] + "..." if len(b.text) > 1000 else b.text

        logger.info("LLM response", extra={
            "agent_name": self.agent_name,
            "action": "llm_response",
            "tokens": {"input": response.usage.input_tokens, "output": response.usage.output_tokens},
            "duration_ms": elapsed_ms,
            "extra": {
                "stop_reason": response.stop_reason,
                "tool_calls": tool_names if tool_names else None,
                "response_text": text_preview if text_preview else None,
            },
        })

        return response

    def get_total_usage(self) -> TokenUsage:
        """Get cumulative token usage for this client instance."""
        return TokenUsage(
            agent_name=self.agent_name,
            input_tokens=self._total_input_tokens,
            output_tokens=self._total_output_tokens,
            total_tokens=self._total_input_tokens + self._total_output_tokens,
        )

    def reset_usage(self) -> None:
        """Reset token counters."""
        self._total_input_tokens = 0
        self._total_output_tokens = 0
