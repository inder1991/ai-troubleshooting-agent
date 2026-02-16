"""Tests for V5 Governance API endpoints."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from src.api.main import app
    return TestClient(app)


class TestGovernanceAPI:
    def test_evidence_graph_404(self, client):
        resp = client.get("/api/v5/session/nonexistent/evidence-graph")
        assert resp.status_code == 404

    def test_confidence_404(self, client):
        resp = client.get("/api/v5/session/nonexistent/confidence")
        assert resp.status_code == 404

    def test_reasoning_404(self, client):
        resp = client.get("/api/v5/session/nonexistent/reasoning")
        assert resp.status_code == 404

    def test_attestation_404(self, client):
        resp = client.post("/api/v5/session/nonexistent/attestation", json={
            "gate_type": "discovery_complete", "decision": "approve", "decided_by": "sre"
        })
        assert resp.status_code == 404

    def test_timeline_404(self, client):
        resp = client.get("/api/v5/session/nonexistent/timeline")
        assert resp.status_code == 404
