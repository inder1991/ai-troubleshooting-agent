import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.utils.redis_store import RedisSessionStore
from src.utils.circuit_breaker import RedisCircuitBreaker
from src.utils.redis_semaphore import RedisLLMSemaphore
from src.utils.context_guard import ContextWindowGuard
from src.utils.tool_cache import ToolResultCache
from src.utils.attestation_log import AttestationLogger
from src.tools.dependency_parser import DependencyParser
from src.agents.cross_repo_tracer import CrossRepoTracer
from src.agents.evidence_handoff import EvidenceHandoff, format_handoff_for_agent
from src.models.attestation import AttestationGate, AttestationDecision


def test_all_new_modules_import():
    assert RedisSessionStore is not None
    assert RedisCircuitBreaker is not None
    assert RedisLLMSemaphore is not None
    assert ContextWindowGuard is not None
    assert ToolResultCache is not None
    assert AttestationLogger is not None
    assert DependencyParser is not None
    assert CrossRepoTracer is not None
    assert EvidenceHandoff is not None
    assert AttestationGate is not None


def test_context_guard_model_limits():
    guard = ContextWindowGuard()
    assert guard.model_limit("claude-haiku-4-5-20251001") == 128000
    assert guard.model_limit("claude-sonnet-4-20250514") == 200000


def test_dependency_parser_empty_dir(tmp_path):
    parser = DependencyParser()
    deps = parser.parse(str(tmp_path))
    assert deps == []
