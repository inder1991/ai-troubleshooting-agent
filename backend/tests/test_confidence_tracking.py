"""Tests for confidence tracking helper functions in supervisor.py."""

import pytest
from datetime import datetime, timezone

from src.models.schemas import ConfidenceLedger, EvidencePin, ReasoningManifest
from src.agents.supervisor import update_confidence_ledger, add_reasoning_step


def _make_pin(evidence_type: str, confidence: float) -> EvidencePin:
    return EvidencePin(
        claim="test claim",
        supporting_evidence=["ev1"],
        source_agent="test_agent",
        source_tool="test_tool",
        confidence=confidence,
        timestamp=datetime.now(timezone.utc),
        evidence_type=evidence_type,
    )


class TestUpdateConfidenceLedger:
    def test_update_ledger_from_log_evidence(self):
        ledger = ConfidenceLedger()
        pins = [_make_pin("log", 0.8)]
        update_confidence_ledger(ledger, pins)
        assert ledger.log_confidence == 0.8
        assert ledger.weighted_final > 0

    def test_update_ledger_from_multiple_sources(self):
        ledger = ConfidenceLedger()
        pins = [_make_pin("log", 0.8), _make_pin("metric", 0.9)]
        update_confidence_ledger(ledger, pins)
        assert ledger.log_confidence == 0.8
        assert ledger.metrics_confidence == 0.9

    def test_ledger_averages_multiple_pins_same_type(self):
        ledger = ConfidenceLedger()
        pins = [_make_pin("log", 0.6), _make_pin("log", 0.8)]
        update_confidence_ledger(ledger, pins)
        assert ledger.log_confidence == pytest.approx(0.7)


class TestAddReasoningStep:
    def test_add_reasoning_step(self):
        manifest = ReasoningManifest(session_id="s1")
        add_reasoning_step(
            manifest,
            decision="investigate logs",
            reasoning="logs are primary source",
            evidence_considered=["ev1"],
            confidence=0.5,
            alternatives_rejected=["skip logs"],
        )
        assert len(manifest.steps) == 1
        assert manifest.steps[0].step_number == 1

    def test_add_multiple_reasoning_steps(self):
        manifest = ReasoningManifest(session_id="s1")
        add_reasoning_step(manifest, "step1", "reason1", ["ev1"], 0.5, ["alt1"])
        add_reasoning_step(manifest, "step2", "reason2", ["ev2"], 0.7, ["alt2"])
        assert len(manifest.steps) == 2
        assert manifest.steps[0].step_number == 1
        assert manifest.steps[1].step_number == 2
