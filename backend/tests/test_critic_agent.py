import pytest
from src.agents.critic_agent import CriticAgent
from src.models.schemas import Finding, CriticVerdict


def test_critic_agent_init():
    critic = CriticAgent()
    assert critic.agent_name == "critic"


def test_critic_detects_contradiction():
    finding = Finding(
        finding_id="f1", agent_name="log_agent",
        category="database_down", summary="Database is down",
        confidence_score=80, severity="critical",
        breadcrumbs=[], negative_findings=[]
    )
    metrics_context = {"db_cpu": {"value": 5.0, "status": "healthy"}, "db_connections": {"value": 10, "status": "normal"}}
    verdict = CriticAgent._evaluate_finding(finding, metrics_context=metrics_context)
    assert verdict.verdict == "challenged"
    assert "healthy" in verdict.reasoning.lower() or "contradicts" in verdict.reasoning.lower()


def test_critic_validates_consistent_finding():
    finding = Finding(
        finding_id="f2", agent_name="log_agent",
        category="oom_killed", summary="Pod OOM killed",
        confidence_score=90, severity="critical",
        breadcrumbs=[], negative_findings=[]
    )
    k8s_context = {"oom_kills": 3, "memory_percent": 95}
    verdict = CriticAgent._evaluate_finding(finding, k8s_context=k8s_context)
    assert verdict.verdict == "validated"


def test_critic_challenges_no_oom():
    finding = Finding(
        finding_id="f3", agent_name="log_agent",
        category="oom_killed", summary="Pod OOM killed",
        confidence_score=70, severity="high",
        breadcrumbs=[], negative_findings=[]
    )
    k8s_context = {"oom_kills": 0, "memory_percent": 30}
    verdict = CriticAgent._evaluate_finding(finding, k8s_context=k8s_context)
    assert verdict.verdict == "challenged"


def test_critic_no_contradiction():
    finding = Finding(
        finding_id="f4", agent_name="log_agent",
        category="network_error", summary="Network timeout",
        confidence_score=75, severity="high",
        breadcrumbs=[], negative_findings=[]
    )
    verdict = CriticAgent._evaluate_finding(finding)
    assert verdict.verdict == "validated"
    assert verdict.confidence_in_verdict == 80


def test_critic_verdict_is_pydantic():
    finding = Finding(
        finding_id="f5", agent_name="test",
        category="test", summary="test",
        confidence_score=50, severity="low",
        breadcrumbs=[], negative_findings=[]
    )
    verdict = CriticAgent._evaluate_finding(finding)
    assert isinstance(verdict, CriticVerdict)
    assert verdict.finding_id == "f5"
