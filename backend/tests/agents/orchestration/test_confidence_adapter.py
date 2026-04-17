"""Stage A.3 — state-to-confidence adapter."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional
from unittest.mock import patch

import pytest

from src.agents.orchestration.confidence_adapter import (
    compute_state_confidence,
    confidence_inputs_from_state,
    state_confidence_mode,
)


@dataclass
class StubPin:
    evidence_type: str = "log"
    confidence: Optional[float] = None
    baseline_delta_pct: Optional[float] = None


@dataclass
class StubVerdict:
    verdict: str


@dataclass
class StubState:
    evidence_pins: list[Any] = field(default_factory=list)
    critic_verdicts: list[Any] = field(default_factory=list)
    evidence_graph: Optional[Any] = None
    signature_match: Optional[Any] = None


class TestModeFlag:
    def test_default_is_deterministic(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DIAGNOSTIC_CONFIDENCE_MODE", None)
            assert state_confidence_mode() == "deterministic"

    def test_legacy_env_flag_recognised(self):
        with patch.dict(os.environ, {"DIAGNOSTIC_CONFIDENCE_MODE": "legacy"}):
            assert state_confidence_mode() == "legacy"

    def test_case_insensitive(self):
        with patch.dict(os.environ, {"DIAGNOSTIC_CONFIDENCE_MODE": "LEGACY"}):
            assert state_confidence_mode() == "legacy"

    def test_garbage_falls_back_to_deterministic(self):
        with patch.dict(os.environ, {"DIAGNOSTIC_CONFIDENCE_MODE": "maybe"}):
            assert state_confidence_mode() == "deterministic"


class TestConfidenceInputsFromState:
    def test_counts_pins_and_sources(self):
        s = StubState(
            evidence_pins=[
                StubPin(evidence_type="log"),
                StubPin(evidence_type="metric"),
                StubPin(evidence_type="log"),
                StubPin(evidence_type="k8s_event"),
            ],
        )
        inputs = confidence_inputs_from_state(s)
        assert inputs.evidence_pin_count == 4
        assert inputs.source_diversity == 3  # logs, metrics, k8s

    def test_max_baseline_delta_picks_largest_absolute(self):
        s = StubState(
            evidence_pins=[
                StubPin(baseline_delta_pct=20),
                StubPin(baseline_delta_pct=-85),
                StubPin(baseline_delta_pct=5),
            ],
        )
        inputs = confidence_inputs_from_state(s)
        assert inputs.baseline_delta_pct == 85

    def test_contradictions_count_challenged_verdicts(self):
        s = StubState(
            critic_verdicts=[
                StubVerdict("confirmed"),
                StubVerdict("challenged"),
                StubVerdict("challenged"),
            ],
        )
        inputs = confidence_inputs_from_state(s)
        assert inputs.contradiction_count == 2

    def test_topology_path_from_evidence_graph_roots(self):
        s = StubState(evidence_graph={"root_causes": ["n-1", "n-2", "n-3"]})
        inputs = confidence_inputs_from_state(s)
        assert inputs.topology_path_length == 3

    def test_signature_match_flag_propagates(self):
        s = StubState(signature_match="oom_cascade")
        inputs = confidence_inputs_from_state(s)
        assert inputs.signature_match is True


class TestDeterministicMode:
    def test_deterministic_is_pure_function_of_state(self):
        s = StubState(
            evidence_pins=[
                StubPin(evidence_type="log", baseline_delta_pct=50),
                StubPin(evidence_type="metric", baseline_delta_pct=40),
                StubPin(evidence_type="k8s_event"),
            ],
        )
        with patch.dict(os.environ, {"DIAGNOSTIC_CONFIDENCE_MODE": "deterministic"}):
            a = compute_state_confidence(s)
            b = compute_state_confidence(s)
        assert a == b
        assert 0.0 <= a <= 1.0


class TestLegacyMode:
    def test_legacy_averages_per_evidence_type(self):
        s = StubState(
            evidence_pins=[
                StubPin(evidence_type="log", confidence=0.8),
                StubPin(evidence_type="log", confidence=0.6),
                StubPin(evidence_type="metric", confidence=0.9),
            ],
        )
        # logs avg = 0.7, metrics avg = 0.9, overall = 0.8
        with patch.dict(os.environ, {"DIAGNOSTIC_CONFIDENCE_MODE": "legacy"}):
            result = compute_state_confidence(s)
        assert result == pytest.approx(0.8, abs=1e-9)

    def test_legacy_returns_zero_when_no_pins(self):
        s = StubState()
        with patch.dict(os.environ, {"DIAGNOSTIC_CONFIDENCE_MODE": "legacy"}):
            assert compute_state_confidence(s) == 0.0

    def test_legacy_ignores_pins_without_confidence(self):
        s = StubState(
            evidence_pins=[
                StubPin(evidence_type="log"),  # no confidence
                StubPin(evidence_type="metric", confidence=0.5),
            ],
        )
        with patch.dict(os.environ, {"DIAGNOSTIC_CONFIDENCE_MODE": "legacy"}):
            assert compute_state_confidence(s) == 0.5


class TestBounds:
    def test_result_always_in_0_1(self):
        s = StubState(
            evidence_pins=[
                StubPin(evidence_type="log", baseline_delta_pct=10000)
                for _ in range(50)
            ],
        )
        for mode in ("deterministic", "legacy"):
            with patch.dict(os.environ, {"DIAGNOSTIC_CONFIDENCE_MODE": mode}):
                v = compute_state_confidence(s)
                assert 0.0 <= v <= 1.0
