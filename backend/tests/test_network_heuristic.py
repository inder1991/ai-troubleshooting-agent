"""Tests for network_agent heuristic additions."""

import pytest
from src.agents.cluster.network_agent import _heuristic_analyze


@pytest.mark.asyncio
async def test_endpoint_not_ready_detected():
    data = {
        "services": [],
        "logs": [],
        "network_policies": [],
        "endpoints": [
            {"name": "app-ep", "namespace": "production", "ready_addresses": 2, "not_ready_addresses": 3},
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"] for a in result["anomalies"]]
    assert any("not_ready" in d.lower() or "not ready" in d.lower() for d in descs)


@pytest.mark.asyncio
async def test_route_missing_backend():
    data = {
        "services": [],
        "logs": [],
        "network_policies": [],
        "routes": [
            {"name": "broken-route", "namespace": "production", "host": "app.example.com",
             "backend_service": "missing-svc", "backend_endpoints": 0, "admitted": True},
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"] for a in result["anomalies"]]
    assert any("route" in d.lower() and ("missing" in d.lower() or "0 endpoint" in d.lower()) for d in descs)


@pytest.mark.asyncio
async def test_ingress_missing_backend():
    data = {
        "services": [],
        "logs": [],
        "network_policies": [],
        "ingresses": [
            {"name": "broken-ingress", "namespace": "staging", "hosts": ["api.staging.example.com"],
             "backend_services": ["missing-svc"], "missing_backends": ["missing-svc"],
             "ingress_class": "nginx"},
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"] for a in result["anomalies"]]
    assert any("ingress" in d.lower() and "missing" in d.lower() for d in descs)


@pytest.mark.asyncio
async def test_ingress_no_class():
    data = {
        "services": [],
        "logs": [],
        "network_policies": [],
        "ingresses": [
            {"name": "no-class-ingress", "namespace": "staging", "hosts": ["test.example.com"],
             "backend_services": ["svc"], "missing_backends": [],
             "ingress_class": None},
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"] for a in result["anomalies"]]
    assert any("ingress" in d.lower() and "class" in d.lower() for d in descs)


@pytest.mark.asyncio
async def test_dns_replicas_zero():
    data = {
        "services": [],
        "logs": [],
        "network_policies": [],
        "dns_deployments": [
            {"name": "dns-default", "namespace": "openshift-dns", "replicas_desired": 2, "replicas_ready": 0},
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"] for a in result["anomalies"]]
    severities = {a["description"]: a["severity"] for a in result["anomalies"]}
    dns_anomalies = [d for d in descs if "dns" in d.lower()]
    assert len(dns_anomalies) > 0
    for d in dns_anomalies:
        assert severities[d] == "critical"
