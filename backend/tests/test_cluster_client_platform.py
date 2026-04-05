"""Tests for platform-layer cluster_client methods."""

import pytest
from src.agents.cluster_client.mock_client import MockClusterClient


@pytest.fixture
def client():
    return MockClusterClient(platform="openshift")


@pytest.fixture
def k8s_client():
    return MockClusterClient(platform="kubernetes")


@pytest.mark.asyncio
async def test_get_cluster_version_returns_data(client):
    result = await client.get_cluster_version()
    assert result.data
    cv = result.data[0]
    assert "version" in cv
    assert "desired" in cv
    assert "conditions" in cv
    assert "history" in cv


@pytest.mark.asyncio
async def test_get_cluster_version_empty_on_k8s(k8s_client):
    result = await k8s_client.get_cluster_version()
    assert result.data == []


@pytest.mark.asyncio
async def test_list_machines_returns_data(client):
    result = await client.list_machines()
    assert len(result.data) >= 2
    machine = result.data[0]
    assert "name" in machine
    assert "phase" in machine
    assert "node_ref" in machine


@pytest.mark.asyncio
async def test_list_machines_empty_on_k8s(k8s_client):
    result = await k8s_client.list_machines()
    assert result.data == []


@pytest.mark.asyncio
async def test_list_subscriptions_returns_data(client):
    result = await client.list_subscriptions()
    assert len(result.data) >= 2
    sub = result.data[0]
    assert "name" in sub
    assert "package" in sub
    assert "state" in sub
    assert "currentCSV" in sub
    assert "installedCSV" in sub


@pytest.mark.asyncio
async def test_list_csvs_returns_data(client):
    result = await client.list_csvs()
    assert len(result.data) >= 2
    csv = result.data[0]
    assert "name" in csv
    assert "phase" in csv


@pytest.mark.asyncio
async def test_list_install_plans_returns_data(client):
    result = await client.list_install_plans()
    assert len(result.data) >= 1
    ip = result.data[0]
    assert "name" in ip
    assert "approval" in ip
    assert "phase" in ip
    assert "csv_names" in ip


@pytest.mark.asyncio
async def test_olm_methods_empty_on_k8s(k8s_client):
    for method_name in ("list_subscriptions", "list_csvs", "list_install_plans"):
        result = await getattr(k8s_client, method_name)()
        assert result.data == [], f"{method_name} should be empty on k8s"
