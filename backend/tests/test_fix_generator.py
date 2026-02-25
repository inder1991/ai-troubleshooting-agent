"""
Tests for Agent 3: Fix Generator & PR Orchestrator

Verifies:
- Initialization with AnthropicClient
- Verification phase accepts DiagnosticState
- Self-correction uses Anthropic API format
- Token tracking via get_total_usage()
- ImpactAssessor uses AnthropicClient
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from pathlib import Path

from src.utils.llm_client import AnthropicClient, LLMResponse
from src.utils.event_emitter import EventEmitter
from src.models.schemas import (
    DiagnosticState,
    DiagnosticPhase,
    TimeWindow,
    TokenUsage,
    CodeAnalysisResult,
    ImpactedFile,
    LineRange,
    FixArea,
    LogAnalysisResult,
    ErrorPattern,
    LogEvidence,
    Breadcrumb,
    NegativeFinding,
    Finding,
)
from src.agents.agent3.fix_generator import Agent3FixGenerator
from src.agents.agent3.assessors import ImpactAssessor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_llm_client():
    """Create a mock AnthropicClient."""
    client = MagicMock(spec=AnthropicClient)
    client.agent_name = "fix_generator"

    # Default chat response
    mock_response = LLMResponse(text="corrected code", input_tokens=100, output_tokens=50)
    client.chat = AsyncMock(return_value=mock_response)

    # Token usage
    client.get_total_usage.return_value = TokenUsage(
        agent_name="fix_generator",
        input_tokens=200,
        output_tokens=100,
        total_tokens=300,
    )

    return client


@pytest.fixture
def mock_event_emitter():
    """Create a mock EventEmitter."""
    emitter = MagicMock(spec=EventEmitter)
    emitter.emit = AsyncMock()
    return emitter


@pytest.fixture
def sample_state():
    """Create a minimal DiagnosticState for testing."""
    return DiagnosticState(
        session_id="test-session-123",
        phase=DiagnosticPhase.FIX_IN_PROGRESS,
        service_name="payment-service",
        time_window=TimeWindow(start="2026-02-15T00:00:00Z", end="2026-02-15T01:00:00Z"),
        overall_confidence=75,
    )


@pytest.fixture
def state_with_code_analysis(sample_state):
    """DiagnosticState with code_analysis populated."""
    from datetime import datetime, timezone

    sample_state.code_analysis = CodeAnalysisResult(
        root_cause_location=ImpactedFile(
            file_path="src/services/payment.py",
            impact_type="direct_error",
            relevant_lines=[LineRange(start=42, end=50)],
            code_snippet="def process_payment():",
            relationship="process_payment",
            fix_relevance="must_fix",
        ),
        impacted_files=[],
        call_chain=["process_payment", "validate_card", "charge"],
        dependency_graph={},
        shared_resource_conflicts=[],
        suggested_fix_areas=[
            FixArea(
                file_path="src/services/payment.py",
                description="Add retry logic to process_payment",
                suggested_change="Wrap call in tenacity retry",
            )
        ],
        mermaid_diagram="graph LR; A-->B",
        negative_findings=[],
        breadcrumbs=[],
        overall_confidence=80,
        tokens_used=TokenUsage(
            agent_name="code_navigator",
            input_tokens=500,
            output_tokens=200,
            total_tokens=700,
        ),
    )
    return sample_state


@pytest.fixture
def fix_generator(mock_llm_client, mock_event_emitter, tmp_path):
    """Create an Agent3FixGenerator with mocked dependencies."""
    # Create a dummy file so _read_original_file works
    src_dir = tmp_path / "src" / "services"
    src_dir.mkdir(parents=True)
    (src_dir / "payment.py").write_text("def process_payment():\n    pass\n")

    return Agent3FixGenerator(
        repo_path=str(tmp_path),
        llm_client=mock_llm_client,
        agent2_module=None,
        event_emitter=mock_event_emitter,
    )


# ---------------------------------------------------------------------------
# Initialization Tests
# ---------------------------------------------------------------------------


class TestFixGeneratorInit:

    def test_initializes_with_anthropic_client(self, mock_llm_client, tmp_path):
        """Fix generator accepts AnthropicClient instead of LangChain LLM."""
        gen = Agent3FixGenerator(
            repo_path=str(tmp_path),
            llm_client=mock_llm_client,
        )
        assert gen.llm_client is mock_llm_client

    def test_initializes_with_event_emitter(self, mock_llm_client, mock_event_emitter, tmp_path):
        """Fix generator accepts optional EventEmitter."""
        gen = Agent3FixGenerator(
            repo_path=str(tmp_path),
            llm_client=mock_llm_client,
            event_emitter=mock_event_emitter,
        )
        assert gen.event_emitter is mock_event_emitter

    def test_initializes_without_optional_params(self, mock_llm_client, tmp_path):
        """Fix generator works without optional params."""
        gen = Agent3FixGenerator(
            repo_path=str(tmp_path),
            llm_client=mock_llm_client,
        )
        assert gen.event_emitter is None
        assert gen.agent2_module is None

    def test_components_initialized(self, fix_generator, mock_llm_client):
        """Validator, reviewer, assessor, stager are initialized."""
        assert fix_generator.validator is not None
        assert fix_generator.reviewer is not None
        assert fix_generator.assessor is not None
        assert fix_generator.stager is not None

    def test_assessor_receives_anthropic_client(self, fix_generator, mock_llm_client):
        """ImpactAssessor receives the AnthropicClient."""
        assert fix_generator.assessor.llm_client is mock_llm_client


# ---------------------------------------------------------------------------
# State Context Extraction Tests
# ---------------------------------------------------------------------------


class TestStateContextExtraction:

    def test_build_agent1_context_minimal(self, fix_generator, sample_state):
        """Agent1 context from minimal state has defaults."""
        ctx = fix_generator._build_agent1_context(sample_state)
        assert ctx["incident_id"] == "test-session-123"
        assert ctx["severity"] == "medium"
        assert ctx["filePath"] == ""

    def test_build_agent1_context_with_code_analysis(self, fix_generator, state_with_code_analysis):
        """Agent1 context extracts file path from code analysis."""
        ctx = fix_generator._build_agent1_context(state_with_code_analysis)
        assert ctx["filePath"] == "src/services/payment.py"
        assert ctx["lineNumber"] == "42"
        assert ctx["functionName"] == "process_payment"

    def test_build_agent2_context_with_code_analysis(self, fix_generator, state_with_code_analysis):
        """Agent2 context extracts call chain and fix recommendations."""
        ctx = fix_generator._build_agent2_context(state_with_code_analysis)
        assert ctx["call_chain"] == ["process_payment", "validate_card", "charge"]
        assert "Add retry logic" in ctx["recommended_fix"]
        assert ctx["confidence_score"] == 0.75


# ---------------------------------------------------------------------------
# Self-Correction Tests
# ---------------------------------------------------------------------------


class TestSelfCorrection:

    @pytest.mark.asyncio
    async def test_self_correct_calls_anthropic_chat(self, fix_generator, mock_llm_client):
        """Self-correction uses AnthropicClient.chat() with system prompt."""
        validation = {
            "syntax": {"valid": False, "error": "unexpected indent"},
            "linting": {"passed": True, "issues": {}},
        }

        result = await fix_generator._self_correct("bad code", validation)

        mock_llm_client.chat.assert_called_once()
        call_kwargs = mock_llm_client.chat.call_args
        assert "system" in call_kwargs.kwargs
        assert "syntax/linting errors" in call_kwargs.kwargs["system"]
        assert "prompt" in call_kwargs.kwargs
        assert result == "corrected code"

    @pytest.mark.asyncio
    async def test_self_correct_extracts_code_from_markdown(self, fix_generator, mock_llm_client):
        """Self-correction strips markdown code blocks from response."""
        mock_llm_client.chat.return_value = LLMResponse(
            text="Here is the fix:\n```python\nfixed_code_here\n```\n",
            input_tokens=50,
            output_tokens=20,
        )

        validation = {
            "syntax": {"valid": False, "error": "bad indent"},
            "linting": {"passed": True, "issues": {}},
        }

        result = await fix_generator._self_correct("bad code", validation)
        assert result == "fixed_code_here"

    @pytest.mark.asyncio
    async def test_self_correct_includes_linting_errors(self, fix_generator, mock_llm_client):
        """Self-correction includes linting errors in the prompt."""
        validation = {
            "syntax": {"valid": True, "error": None},
            "linting": {
                "passed": False,
                "issues": {"errors": ["E501 line too long", "F401 unused import"]},
            },
        }

        await fix_generator._self_correct("some code", validation)

        prompt_text = mock_llm_client.chat.call_args.kwargs["prompt"]
        assert "E501" in prompt_text
        assert "F401" in prompt_text


# ---------------------------------------------------------------------------
# Token Tracking Tests
# ---------------------------------------------------------------------------


class TestTokenTracking:

    def test_get_total_usage_returns_token_usage(self, mock_llm_client):
        """get_total_usage returns a TokenUsage model."""
        usage = mock_llm_client.get_total_usage()
        assert isinstance(usage, TokenUsage)
        assert usage.agent_name == "fix_generator"
        assert usage.total_tokens == 300

    @pytest.mark.asyncio
    async def test_verification_phase_includes_token_usage(
        self, fix_generator, mock_llm_client, state_with_code_analysis
    ):
        """PR data from verification phase includes token_usage."""
        # Mock all downstream dependencies
        fix_generator.validator.validate_all = MagicMock(
            return_value={
                "passed": True,
                "syntax": {"valid": True, "error": None},
                "linting": {"passed": True, "issues": {}},
                "imports": {"valid": True, "missing": []},
            }
        )
        fix_generator.reviewer.request_review = MagicMock(
            return_value={
                "approved": True,
                "confidence": 0.9,
                "concerns": [],
                "recommendations": [],
            }
        )

        # Mock assessor (now async)
        fix_generator.assessor.assess_impact = AsyncMock(
            return_value={
                "side_effects": [],
                "security_review": "No concerns",
                "regression_risk": "Low",
                "affected_functions": ["process_payment"],
                "diff_lines": 5,
            }
        )

        fix_generator.stager.create_branch = MagicMock(return_value="fix/test-branch")
        fix_generator.stager.stage_changes = MagicMock()
        fix_generator.stager.create_commit = MagicMock(return_value="abc1234567890")
        fix_generator.stager.generate_pr_template = MagicMock(return_value="PR body")

        pr_data = await fix_generator.run_verification_phase(
            state=state_with_code_analysis,
            generated_fixes="def process_payment():\n    return True\n",
        )

        assert "token_usage" in pr_data
        assert pr_data["token_usage"]["total_tokens"] == 300
        mock_llm_client.get_total_usage.assert_called()


# ---------------------------------------------------------------------------
# Event Emitter Tests
# ---------------------------------------------------------------------------


class TestEventEmitter:

    @pytest.mark.asyncio
    async def test_emit_progress_calls_event_emitter(self, fix_generator, mock_event_emitter):
        """Progress events go through EventEmitter."""
        await fix_generator._emit_progress("validation", "Running checks...")

        mock_event_emitter.emit.assert_called_once_with(
            agent_name="fix_generator",
            event_type="progress",
            message="Running checks...",
            details={"stage": "validation"},
        )

    @pytest.mark.asyncio
    async def test_emit_progress_noop_without_emitter(self, mock_llm_client, tmp_path):
        """No error when event_emitter is None."""
        gen = Agent3FixGenerator(
            repo_path=str(tmp_path),
            llm_client=mock_llm_client,
        )
        # Should not raise
        await gen._emit_progress("test", "test message")


# ---------------------------------------------------------------------------
# ImpactAssessor Tests
# ---------------------------------------------------------------------------


class TestImpactAssessor:

    def test_assessor_accepts_anthropic_client(self, mock_llm_client):
        """ImpactAssessor initializes with AnthropicClient."""
        assessor = ImpactAssessor(mock_llm_client)
        assert assessor.llm_client is mock_llm_client

    @pytest.mark.asyncio
    async def test_assess_impact_calls_anthropic(self, mock_llm_client):
        """assess_impact uses AnthropicClient.chat for LLM analysis."""
        mock_llm_client.chat.return_value = LLMResponse(
            text='{"side_effects": ["may affect latency"], "security_review": "ok", "breaking_changes": []}',
            input_tokens=100,
            output_tokens=50,
        )

        assessor = ImpactAssessor(mock_llm_client)
        result = await assessor.assess_impact(
            file_path="test.py",
            original_code="def foo():\n    pass",
            fixed_code="def foo():\n    return 1",
            call_chain=["foo"],
        )

        mock_llm_client.chat.assert_called_once()
        assert result["regression_risk"] in ("Low", "Medium", "High")
        assert isinstance(result["affected_functions"], list)

    @pytest.mark.asyncio
    async def test_assess_impact_fallback_on_llm_failure(self, mock_llm_client):
        """Falls back to heuristic analysis when LLM fails."""
        mock_llm_client.chat.side_effect = Exception("API error")

        assessor = ImpactAssessor(mock_llm_client)
        result = await assessor.assess_impact(
            file_path="test.py",
            original_code="import os\ndef foo():\n    pass",
            fixed_code="import os\nimport retry\ndef foo():\n    retry(pass)",
            call_chain=["foo"],
        )

        # Should still return a valid result via heuristics
        assert "side_effects" in result
        assert "regression_risk" in result


# ---------------------------------------------------------------------------
# Verification Phase Integration Test
# ---------------------------------------------------------------------------


class TestVerificationPhase:

    @pytest.mark.asyncio
    async def test_accepts_diagnostic_state(
        self, fix_generator, state_with_code_analysis, mock_llm_client
    ):
        """run_verification_phase accepts DiagnosticState as input."""
        # Mock all downstream
        fix_generator.validator.validate_all = MagicMock(
            return_value={
                "passed": True,
                "syntax": {"valid": True, "error": None},
                "linting": {"passed": True, "issues": {}},
                "imports": {"valid": True, "missing": []},
            }
        )
        fix_generator.reviewer.request_review = MagicMock(
            return_value={
                "approved": True,
                "confidence": 0.85,
                "concerns": [],
                "recommendations": [],
            }
        )
        fix_generator.assessor.assess_impact = AsyncMock(
            return_value={
                "side_effects": [],
                "security_review": "No concerns",
                "regression_risk": "Low",
                "affected_functions": [],
                "diff_lines": 3,
            }
        )
        fix_generator.stager.create_branch = MagicMock(return_value="fix/test")
        fix_generator.stager.stage_changes = MagicMock()
        fix_generator.stager.create_commit = MagicMock(return_value="deadbeef1234")
        fix_generator.stager.generate_pr_template = MagicMock(return_value="body")

        pr_data = await fix_generator.run_verification_phase(
            state=state_with_code_analysis,
            generated_fixes="def process_payment():\n    return True\n",
        )

        assert pr_data["status"] == "awaiting_approval"
        assert pr_data["branch_name"] == "fix/test"
        assert "token_usage" in pr_data

    @pytest.mark.asyncio
    async def test_self_correction_triggered_on_failure(
        self, fix_generator, state_with_code_analysis, mock_llm_client
    ):
        """When validation fails, self-correction is triggered."""
        call_count = 0

        def validate_side_effect(file_path, code):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "passed": False,
                    "syntax": {"valid": False, "error": "bad indent"},
                    "linting": {"passed": True, "issues": {}},
                    "imports": {"valid": True, "missing": []},
                }
            return {
                "passed": True,
                "syntax": {"valid": True, "error": None},
                "linting": {"passed": True, "issues": {}},
                "imports": {"valid": True, "missing": []},
            }

        fix_generator.validator.validate_all = MagicMock(side_effect=validate_side_effect)
        fix_generator.reviewer.request_review = MagicMock(
            return_value={
                "approved": True,
                "confidence": 0.9,
                "concerns": [],
                "recommendations": [],
            }
        )
        fix_generator.assessor.assess_impact = AsyncMock(
            return_value={
                "side_effects": [],
                "security_review": "ok",
                "regression_risk": "Low",
                "affected_functions": [],
                "diff_lines": 2,
            }
        )
        fix_generator.stager.create_branch = MagicMock(return_value="fix/test")
        fix_generator.stager.stage_changes = MagicMock()
        fix_generator.stager.create_commit = MagicMock(return_value="abcd1234abcd")
        fix_generator.stager.generate_pr_template = MagicMock(return_value="body")

        await fix_generator.run_verification_phase(
            state=state_with_code_analysis,
            generated_fixes="bad code",
        )

        # Self-correct should have been called (AnthropicClient.chat)
        mock_llm_client.chat.assert_called_once()
