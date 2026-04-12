import logging
import tiktoken

logger = logging.getLogger(__name__)

MODEL_LIMITS = {
    "claude-haiku-4-5-20251001": 128_000,
    "claude-sonnet-4-20250514": 200_000,
    "claude-opus-4-6": 200_000,
}
DEFAULT_LIMIT = 128_000
THRESHOLD = 0.80
MAX_SINGLE_RESULT_TOKENS = 20_000
TAIL_LINES = 500
KEEP_RECENT_TOOL_PAIRS = 3


class ContextWindowGuard:
    def __init__(self, model_name: str = "claude-haiku-4-5-20251001"):
        self._model = model_name
        try:
            self._enc = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self._enc = tiktoken.get_encoding("cl100k_base")

    def estimate_tokens(self, messages: list[dict]) -> int:
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += len(self._enc.encode(content))
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and "text" in block:
                        total += len(self._enc.encode(block["text"]))
        return total

    def model_limit(self, model_name: str | None = None) -> int:
        name = model_name or self._model
        for key, limit in MODEL_LIMITS.items():
            if key in name:
                return limit
        return DEFAULT_LIMIT

    def truncate_if_needed(self, messages: list[dict]) -> list[dict]:
        limit = int(self.model_limit() * THRESHOLD)
        current = self.estimate_tokens(messages)
        if current <= limit:
            return messages

        logger.warning(f"Context at {current} tokens ({current/self.model_limit()*100:.0f}%), truncating (limit={limit})")

        result = list(messages)
        result = self._tail_large_results(result)
        if self.estimate_tokens(result) <= limit:
            return result

        result = self._drop_old_tool_results(result)
        return result

    def _tail_large_results(self, messages: list[dict]) -> list[dict]:
        out = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str) and len(self._enc.encode(content)) > MAX_SINGLE_RESULT_TOKENS:
                lines = content.split("\n")
                if len(lines) > TAIL_LINES:
                    truncated = f"[Truncated {len(lines) - TAIL_LINES} lines]\n" + "\n".join(lines[-TAIL_LINES:])
                    out.append({**msg, "content": truncated})
                    continue
            out.append(msg)
        return out

    def _drop_old_tool_results(self, messages: list[dict]) -> list[dict]:
        if len(messages) <= 2:
            return messages
        head = messages[:1]
        tail_pairs = messages[-KEEP_RECENT_TOOL_PAIRS * 2:]
        middle = messages[1:-KEEP_RECENT_TOOL_PAIRS * 2] if len(messages) > KEEP_RECENT_TOOL_PAIRS * 2 + 1 else []
        if middle:
            summary_text = f"[Prior investigation: {len(middle)} messages summarized. Key actions taken but details truncated to fit context window.]"
            summary = {"role": "user", "content": summary_text}
            return head + [summary] + tail_pairs
        return messages
