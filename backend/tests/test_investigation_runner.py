import pytest
from src.workflows.runners.investigation_runner import InvestigationAgentRunner


class FakeAgent:
    def __init__(self, connection_config=None):
        self.run_called = False
        self.run_two_pass_called = False
        self._connection_config = connection_config

    async def run(self, context, event_emitter=None):
        self.run_called = True
        return {"evidence_pins": [{"claim": "OOM detected"}], "overall_confidence": 75}

    async def run_two_pass(self, context, event_emitter=None):
        self.run_two_pass_called = True
        return {"evidence_pins": [{"claim": "high latency"}], "overall_confidence": 60}

    def get_token_usage(self):
        return {"prompt": 100, "completion": 50}


@pytest.mark.asyncio
async def test_runner_calls_agent_run():
    runner = InvestigationAgentRunner(
        agent_cls=FakeAgent,
        agent_name="log_agent",
        connection_config={"host": "localhost"},
    )
    result = await runner.run(
        inputs={"service_name": "api"},
        context={},
    )
    assert "evidence_pins" in result
    assert result["evidence_pins"][0]["claim"] == "OOM detected"


@pytest.mark.asyncio
async def test_runner_uses_two_pass_for_supported_agents():
    runner = InvestigationAgentRunner(
        agent_cls=FakeAgent,
        agent_name="metrics_agent",
        connection_config={},
        use_two_pass=True,
    )
    result = await runner.run(
        inputs={"service_name": "api"},
        context={},
    )
    assert result["evidence_pins"][0]["claim"] == "high latency"


@pytest.mark.asyncio
async def test_runner_handles_agent_failure():
    class FailingAgent:
        def __init__(self, connection_config=None):
            pass
        async def run(self, context, event_emitter=None):
            raise RuntimeError("LLM quota exceeded")
        def get_token_usage(self):
            return {}

    runner = InvestigationAgentRunner(
        agent_cls=FailingAgent,
        agent_name="log_agent",
        connection_config={},
    )
    with pytest.raises(RuntimeError, match="LLM quota exceeded"):
        await runner.run(inputs={}, context={})
