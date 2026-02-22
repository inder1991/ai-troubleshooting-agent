import pytest
from src.agents.change_agent import ChangeAgent
from src.models.schemas import ChangeRiskScore


class TestChangeRiskScore:
    def test_create_score(self):
        score = ChangeRiskScore(
            change_id="abc123",
            change_type="code_deploy",
            risk_score=0.8,
            temporal_correlation=0.9,
            scope_overlap=0.7,
            author="dev@example.com",
            description="Updated Redis config",
        )
        assert score.risk_score == 0.8

    def test_likely_related(self):
        score = ChangeRiskScore(
            change_id="abc",
            change_type="config_change",
            risk_score=0.7,
            temporal_correlation=0.8,
            scope_overlap=0.6,
            author="dev",
            description="test",
        )
        assert score.risk_score > 0.6 and score.temporal_correlation > 0.7


class TestChangeAgent:
    def test_agent_creation(self):
        agent = ChangeAgent()
        assert agent.agent_name == "change_agent"

    @pytest.mark.asyncio
    async def test_define_tools(self):
        agent = ChangeAgent()
        tools = await agent._define_tools()
        assert len(tools) == 4
        names = [t["name"] for t in tools]
        assert "github_recent_commits" in names
        assert "deployment_history" in names
        assert "config_diff" in names
        assert "github_get_commit_diff" in names

    @pytest.mark.asyncio
    async def test_build_initial_prompt(self):
        agent = ChangeAgent()
        prompt = await agent._build_initial_prompt({
            "namespace": "order-svc",
            "repo_url": "https://github.com/test/repo",
        })
        assert "order-svc" in prompt

    def test_parse_final_response_json(self):
        agent = ChangeAgent()
        result = agent._parse_final_response(
            '{"summary": "No changes detected", "change_correlations": []}'
        )
        assert "summary" in result
        assert result["change_correlations"] == []

    def test_parse_final_response_plain_text(self):
        agent = ChangeAgent()
        result = agent._parse_final_response("plain text response")
        assert "summary" in result
