"""Bridge — build IncidentGraph from EvidencePins; find_root_causes wiring."""
from datetime import datetime, timedelta

from src.agents.causal_engine import (
    build_incident_graph_from_pins,
    find_root_causes,
)
from src.models.schemas import EvidencePin


def _pin(claim: str, agent: str, ts: datetime, etype: str = "log") -> EvidencePin:
    return EvidencePin(
        claim=claim,
        supporting_evidence=["ev"],
        source_agent=agent,
        source_tool="stub",
        confidence=0.8,
        timestamp=ts,
        evidence_type=etype,
    )


def test_empty_pins_yield_empty_graph():
    g = build_incident_graph_from_pins([])
    assert list(g.nodes) == []


def test_same_agent_temporal_chain_creates_precedes_edges():
    t0 = datetime(2026, 4, 17, 12, 0, 0)
    pins = [
        _pin("A", "log_agent", t0),
        _pin("B", "log_agent", t0 + timedelta(seconds=60)),
        _pin("C", "log_agent", t0 + timedelta(seconds=120)),
    ]
    g = build_incident_graph_from_pins(pins)
    # 3 pins → each pair within 5min window → 3 edges (0→1, 0→2, 1→2)
    edge_types = [d["edge_type"] for _, _, d in g.G.edges(data=True)]
    assert edge_types == ["precedes", "precedes", "precedes"]


def test_cross_agent_pins_get_no_edge():
    t0 = datetime(2026, 4, 17, 12, 0, 0)
    pins = [
        _pin("A", "log_agent", t0),
        _pin("B", "metrics_agent", t0 + timedelta(seconds=30)),
    ]
    g = build_incident_graph_from_pins(pins)
    assert len(list(g.G.edges)) == 0


def test_pins_further_than_5min_apart_drop_out():
    t0 = datetime(2026, 4, 17, 12, 0, 0)
    pins = [
        _pin("A", "log_agent", t0),
        _pin("B", "log_agent", t0 + timedelta(minutes=10)),
    ]
    g = build_incident_graph_from_pins(pins)
    assert len(list(g.G.edges)) == 0


def test_find_root_causes_returns_empty_without_causes_edges():
    # Bridge contract: without certified 'causes' edges, no roots.
    t0 = datetime(2026, 4, 17, 12, 0, 0)
    pins = [_pin("A", "log_agent", t0), _pin("B", "log_agent", t0 + timedelta(seconds=60))]
    g = build_incident_graph_from_pins(pins)
    assert find_root_causes(g) == []
