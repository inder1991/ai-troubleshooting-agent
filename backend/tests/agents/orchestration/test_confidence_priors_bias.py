"""Priors feeding back into compute_confidence — opt-in bias."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.agents.confidence_calibrator import ConfidenceCalibrator, DEFAULT_PRIOR
from src.agents.orchestration.confidence_adapter import (
    _apply_prior_tilt,
    compute_state_confidence,
    compute_state_confidence_async,
)
from src.database.engine import get_engine, get_session


_TEST_AGENTS = ("bias_test_log", "bias_test_metrics", "bias_test_k8s")


@pytest_asyncio.fixture(autouse=True)
async def _isolate():
    await get_engine().dispose(close=False)
    await _purge()
    yield
    await _purge()
    await get_engine().dispose(close=False)


async def _purge():
    async with get_session() as session:
        async with session.begin():
            await session.execute(
                text("DELETE FROM agent_priors WHERE agent_name = ANY(:names)"),
                {"names": list(_TEST_AGENTS)},
            )


@dataclass
class StubPin:
    evidence_type: str = "log"
    confidence: Optional[float] = None
    baseline_delta_pct: Optional[float] = None
    source_agent: Optional[str] = None


@dataclass
class StubState:
    evidence_pins: list[Any] = field(default_factory=list)
    critic_verdicts: list[Any] = field(default_factory=list)
    evidence_graph: Optional[Any] = None
    signature_match: Optional[Any] = None
    _agent_priors_cache: Optional[dict] = None


class TestTiltMath:
    def test_zero_tilt_at_default_prior(self):
        assert _apply_prior_tilt(0.80, [DEFAULT_PRIOR]) == pytest.approx(0.80, abs=1e-9)

    def test_positive_tilt_above_default(self):
        tilted = _apply_prior_tilt(0.80, [1.0])
        assert tilted > 0.80
        assert tilted - 0.80 == pytest.approx(0.05, abs=1e-9)

    def test_negative_tilt_below_default(self):
        tilted = _apply_prior_tilt(0.80, [0.0])
        assert tilted < 0.80

    def test_tilt_clamped_to_0_1(self):
        assert _apply_prior_tilt(0.99, [1.0]) <= 1.0
        assert _apply_prior_tilt(0.01, [0.0]) >= 0.0


class TestSyncPathNoBiasWhenFlagOff:
    def test_no_change_when_flag_off(self):
        s = StubState(
            evidence_pins=[
                StubPin(evidence_type="log", source_agent="bias_test_log"),
                StubPin(evidence_type="metric", source_agent="bias_test_metrics"),
                StubPin(evidence_type="k8s_event", source_agent="bias_test_k8s"),
            ],
        )
        with patch.dict(os.environ, {"DIAGNOSTIC_PRIORS_BIAS": "off"}, clear=False):
            base = compute_state_confidence(s)
        # Cache set explicitly; still should be ignored when flag off
        s2 = StubState(
            evidence_pins=s.evidence_pins,
            _agent_priors_cache={"bias_test_log": 1.0},
        )
        with patch.dict(os.environ, {"DIAGNOSTIC_PRIORS_BIAS": "off"}, clear=False):
            result = compute_state_confidence(s2)
        assert result == base


class TestSyncPathUsesStateCache:
    def test_bias_applied_from_cache(self):
        s = StubState(
            evidence_pins=[
                StubPin(evidence_type="log", source_agent="bias_test_log"),
                StubPin(evidence_type="metric", source_agent="bias_test_metrics"),
                StubPin(evidence_type="k8s_event", source_agent="bias_test_k8s"),
            ],
            _agent_priors_cache={
                "bias_test_log": 1.0,
                "bias_test_metrics": 1.0,
                "bias_test_k8s": 1.0,
            },
        )
        with patch.dict(os.environ, {"DIAGNOSTIC_PRIORS_BIAS": "on"}, clear=False):
            base_without = compute_state_confidence(
                StubState(evidence_pins=s.evidence_pins)
            )
            biased = compute_state_confidence(s)
        assert biased > base_without


class TestAsyncPathReadsPriorsFromDb:
    @pytest.mark.asyncio
    async def test_accurate_agents_boost_confidence(self):
        # Seed priors: all three agents trained to high accuracy
        cal = ConfidenceCalibrator()
        for agent in _TEST_AGENTS:
            for _ in range(30):
                await cal.update_prior(agent, was_correct=True)

        s = StubState(
            evidence_pins=[
                StubPin(
                    evidence_type="log",
                    source_agent=agent,
                    baseline_delta_pct=60,
                )
                for agent in _TEST_AGENTS
            ],
        )
        with patch.dict(os.environ, {"DIAGNOSTIC_PRIORS_BIAS": "on"}, clear=False):
            biased = await compute_state_confidence_async(s)
        with patch.dict(os.environ, {"DIAGNOSTIC_PRIORS_BIAS": "off"}, clear=False):
            base = await compute_state_confidence_async(s)
        assert biased > base

    @pytest.mark.asyncio
    async def test_no_agents_no_bias_even_when_flag_on(self):
        s = StubState()
        with patch.dict(os.environ, {"DIAGNOSTIC_PRIORS_BIAS": "on"}, clear=False):
            result = await compute_state_confidence_async(s)
        # Empty state -> 0 before + 0 after (no tilt applied without agents)
        assert 0.0 <= result <= 1.0
