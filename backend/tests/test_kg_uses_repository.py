"""Tests: KnowledgeGraph can hold an optional TopologyRepository reference."""

import pytest

from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.topology_store import TopologyStore
from src.network.repository.sqlite_repository import SQLiteRepository
from src.network.models import (
    Device as PydanticDevice,
    DeviceType,
    Interface as PydanticInterface,
    Subnet,
)


@pytest.fixture
def kg_with_repo(tmp_path):
    db_path = str(tmp_path / "test.db")
    store = TopologyStore(db_path)
    repo = SQLiteRepository(store)

    # Seed data using Pydantic models + store
    store.add_device(PydanticDevice(
        id="rtr-01", name="rtr-01", device_type=DeviceType.ROUTER,
        management_ip="10.0.0.1", vendor="cisco",
    ))
    store.add_device(PydanticDevice(
        id="sw-01", name="sw-01", device_type=DeviceType.SWITCH,
        management_ip="10.0.0.2", vendor="cisco",
    ))
    store.add_subnet(Subnet(id="s1", cidr="10.0.0.0/30", gateway_ip="10.0.0.1"))
    store.add_interface(PydanticInterface(
        id="rtr-01:Gi0/0", device_id="rtr-01", name="Gi0/0", ip="10.0.0.1",
    ))
    store.add_interface(PydanticInterface(
        id="sw-01:Gi0/48", device_id="sw-01", name="Gi0/48", ip="10.0.0.2",
    ))

    kg = NetworkKnowledgeGraph(store)
    kg.repo = repo
    kg.load_from_store()
    return kg, repo


def test_kg_has_repo(kg_with_repo):
    kg, repo = kg_with_repo
    assert kg.repo is not None
    assert kg.repo is repo


def test_kg_still_builds_graph(kg_with_repo):
    kg, _ = kg_with_repo
    assert kg.graph.number_of_nodes() > 0


def test_repo_can_read_devices(kg_with_repo):
    _, repo = kg_with_repo
    devices = repo.get_devices()
    assert len(devices) == 2


def test_repo_can_read_interfaces(kg_with_repo):
    _, repo = kg_with_repo
    interfaces = repo.get_interfaces("rtr-01")
    assert len(interfaces) >= 1
