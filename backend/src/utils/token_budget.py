"""Token estimation and context truncation for LLM calls."""

def estimate_tokens(text: str) -> int:
    """Approximate token count (4 chars ≈ 1 token for English text)."""
    return len(text) // 4

def enforce_budget(system_prompt: str, conversation: list, context: str,
                   model_max: int = 200_000, target_ratio: float = 0.7) -> tuple[str, list, str]:
    """Truncate context to fit within model context window."""
    target = int(model_max * target_ratio)
    total = estimate_tokens(system_prompt) + estimate_tokens(str(conversation)) + estimate_tokens(context)
    if total <= target:
        return system_prompt, conversation, context

    truncated_conv = conversation[-10:]
    total = estimate_tokens(system_prompt) + estimate_tokens(str(truncated_conv)) + estimate_tokens(context)
    if total <= target:
        return system_prompt, truncated_conv, context

    remaining = target - estimate_tokens(system_prompt) - estimate_tokens(str(truncated_conv))
    max_chars = max(0, remaining * 4)
    truncated_context = context[:max_chars]
    return system_prompt, truncated_conv, truncated_context
