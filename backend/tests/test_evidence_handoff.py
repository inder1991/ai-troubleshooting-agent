import pytest
from datetime import datetime
from src.agents.evidence_handoff import (
    EvidenceHandoff, format_handoff_for_agent, serialize_handoffs,
)


@pytest.fixture
def sample_handoffs():
    return [
        EvidenceHandoff(
            claim="OOM killed pod-xyz", domain="k8s",
            timestamp=datetime(2026, 4, 12, 14, 32),
            confidence=0.82, source_agent="k8s_agent", finding_id="f1",
            open_questions=["Sidecar or main container?"],
        ),
        EvidenceHandoff(
            claim="Memory spike at 14:30", domain="metrics",
            timestamp=datetime(2026, 4, 12, 14, 30),
            confidence=0.75, source_agent="metrics_agent", finding_id="f2",
            corroborating_domains=["k8s"],
        ),
    ]


def test_serialize_returns_dict(sample_handoffs):
    result = serialize_handoffs(sample_handoffs)
    assert isinstance(result, dict)
    assert "handoffs" in result
    assert len(result["handoffs"]) == 2


def test_serialize_preserves_all_fields(sample_handoffs):
    result = serialize_handoffs(sample_handoffs)
    h = result["handoffs"][0]
    assert h["claim"] == "OOM killed pod-xyz"
    assert h["domain"] == "k8s"
    assert h["confidence"] == 0.82
    assert h["source_agent"] == "k8s_agent"
    assert h["finding_id"] == "f1"
    assert h["timestamp"] == "2026-04-12T14:32:00"
    assert h["open_questions"] == ["Sidecar or main container?"]


def test_serialize_handles_null_timestamp():
    handoffs = [EvidenceHandoff(claim="test", domain="logs")]
    result = serialize_handoffs(handoffs)
    assert result["handoffs"][0]["timestamp"] is None


def test_serialize_is_json_safe(sample_handoffs):
    import json
    result = serialize_handoffs(sample_handoffs)
    serialized = json.dumps(result)
    deserialized = json.loads(serialized)
    assert deserialized["handoffs"][0]["claim"] == "OOM killed pod-xyz"


def test_serialize_includes_corroborating(sample_handoffs):
    result = serialize_handoffs(sample_handoffs)
    h2 = result["handoffs"][1]
    assert h2["corroborating_domains"] == ["k8s"]


def test_format_handoff_text(sample_handoffs):
    text = format_handoff_for_agent(sample_handoffs, "code")
    assert "OOM killed pod-xyz" in text
    assert "Sidecar or main container?" in text
    assert "code" in text
    assert "Corroborated by: k8s" in text


def test_format_empty_handoff():
    text = format_handoff_for_agent([], "metrics")
    assert text == ""


def test_structured_and_text_cover_same_claims(sample_handoffs):
    structured = serialize_handoffs(sample_handoffs)
    text = format_handoff_for_agent(sample_handoffs, "code")
    for h in structured["handoffs"]:
        assert h["claim"] in text
