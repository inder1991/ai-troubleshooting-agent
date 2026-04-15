"""Tests for new cluster_client methods: list_webhooks, list_routes, list_ingresses."""

import pytest
from src.agents.cluster_client.mock_client import MockClusterClient


@pytest.mark.asyncio
async def test_list_webhooks_returns_query_result():
    client = MockClusterClient(platform="openshift")
    result = await client.list_webhooks()
    assert hasattr(result, "data")
    assert isinstance(result.data, list)
    assert len(result.data) > 0
    webhook = result.data[0]
    assert "name" in webhook
    assert "failure_policy" in webhook
    assert "timeout_seconds" in webhook
    assert "client_config" in webhook


@pytest.mark.asyncio
async def test_list_routes_returns_query_result():
    client = MockClusterClient(platform="openshift")
    result = await client.list_routes()
    assert hasattr(result, "data")
    assert isinstance(result.data, list)
    assert len(result.data) > 0
    route = result.data[0]
    assert "name" in route
    assert "host" in route
    assert "backend_service" in route
    assert "admitted" in route


@pytest.mark.asyncio
async def test_list_ingresses_returns_query_result():
    client = MockClusterClient(platform="openshift")
    result = await client.list_ingresses()
    assert hasattr(result, "data")
    assert isinstance(result.data, list)
    assert len(result.data) > 0
    ingress = result.data[0]
    assert "name" in ingress
    assert "hosts" in ingress
    assert "backend_services" in ingress
    assert "ingress_class" in ingress
