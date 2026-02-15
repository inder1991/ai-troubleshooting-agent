import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.utils.llm_client import AnthropicClient, LLMResponse
from src.models.schemas import TokenUsage


@pytest.mark.asyncio
async def test_client_tracks_tokens():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="test response")]
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)

    with patch("src.utils.llm_client.AsyncAnthropic") as mock_cls:
        mock_instance = AsyncMock()
        mock_instance.messages.create = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_instance

        client = AnthropicClient(agent_name="test_agent")
        result = await client.chat("Analyze this log")
        assert result.text == "test response"
        usage = client.get_total_usage()
        assert usage.total_tokens == 150
        assert usage.agent_name == "test_agent"


@pytest.mark.asyncio
async def test_client_accumulates_tokens():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="response")]
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)

    with patch("src.utils.llm_client.AsyncAnthropic") as mock_cls:
        mock_instance = AsyncMock()
        mock_instance.messages.create = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_instance

        client = AnthropicClient(agent_name="log_agent")
        await client.chat("Query 1")
        await client.chat("Query 2")
        usage = client.get_total_usage()
        assert usage.input_tokens == 200
        assert usage.output_tokens == 100
        assert usage.total_tokens == 300
        assert usage.agent_name == "log_agent"


@pytest.mark.asyncio
async def test_client_reset_usage():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="response")]
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)

    with patch("src.utils.llm_client.AsyncAnthropic") as mock_cls:
        mock_instance = AsyncMock()
        mock_instance.messages.create = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_instance

        client = AnthropicClient()
        await client.chat("Query")
        client.reset_usage()
        usage = client.get_total_usage()
        assert usage.total_tokens == 0


@pytest.mark.asyncio
async def test_client_passes_system_prompt():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="response")]
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)

    with patch("src.utils.llm_client.AsyncAnthropic") as mock_cls:
        mock_instance = AsyncMock()
        mock_instance.messages.create = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_instance

        client = AnthropicClient()
        await client.chat("Query", system="You are a log analyzer.")
        call_kwargs = mock_instance.messages.create.call_args[1]
        assert call_kwargs["system"] == "You are a log analyzer."


@pytest.mark.asyncio
async def test_client_uses_custom_messages():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="response")]
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)

    with patch("src.utils.llm_client.AsyncAnthropic") as mock_cls:
        mock_instance = AsyncMock()
        mock_instance.messages.create = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_instance

        client = AnthropicClient()
        custom_msgs = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
            {"role": "user", "content": "Analyze"}
        ]
        await client.chat("ignored", messages=custom_msgs)
        call_kwargs = mock_instance.messages.create.call_args[1]
        assert call_kwargs["messages"] == custom_msgs


def test_llm_response_attributes():
    r = LLMResponse(text="hello", input_tokens=10, output_tokens=5)
    assert r.text == "hello"
    assert r.input_tokens == 10
    assert r.output_tokens == 5
