import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from src.agents.cross_repo_tracer import CrossRepoTracer, CrossRepoFinding


@pytest.fixture
def tracer():
    return CrossRepoTracer(
        repo_map={"auth-service": "https://github.com/org/auth-service"},
        github_token="fake-token",
    )


def test_should_trace_low_confidence(tracer):
    assert tracer.should_trace(code_confidence=0.4, internal_deps_with_recent_commits=0) is True


def test_should_trace_recent_internal_deps(tracer):
    assert tracer.should_trace(code_confidence=0.8, internal_deps_with_recent_commits=2) is True


def test_should_not_trace_high_confidence_no_deps(tracer):
    assert tracer.should_trace(code_confidence=0.9, internal_deps_with_recent_commits=0) is False


def test_cross_repo_finding_structure():
    f = CrossRepoFinding(
        source_repo="org/auth-service",
        source_file="client.py",
        source_commit="abc123",
        target_repo="org/api-gateway",
        target_file="handler.py",
        target_import="from auth_service.client import validate",
        correlation_type="api_rename",
        correlation_score=0.94,
    )
    assert f.correlation_score > 0.9
