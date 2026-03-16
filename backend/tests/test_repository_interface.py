"""Tests for the abstract TopologyRepository interface."""

import inspect
import pytest

from src.network.repository.interface import TopologyRepository


class TestTopologyRepositoryAbstract:
    """Verify the ABC cannot be instantiated and declares all required methods."""

    def test_cannot_instantiate_abstract(self):
        """TopologyRepository is abstract — direct instantiation must raise TypeError."""
        with pytest.raises(TypeError):
            TopologyRepository()

    def test_defines_read_methods(self):
        """All 10 read methods must be declared on the class."""
        read_methods = [
            "get_device",
            "get_devices",
            "get_interfaces",
            "get_ip_addresses",
            "get_routes",
            "get_neighbors",
            "get_security_policies",
            "find_device_by_ip",
            "find_device_by_serial",
            "find_device_by_hostname",
        ]
        for name in read_methods:
            assert hasattr(TopologyRepository, name), f"Missing read method: {name}"
            member = getattr(TopologyRepository, name)
            assert callable(member), f"{name} is not callable"

    def test_defines_write_methods(self):
        """All 7 write methods must be declared on the class."""
        write_methods = [
            "upsert_device",
            "upsert_interface",
            "upsert_ip_address",
            "upsert_neighbor_link",
            "upsert_route",
            "upsert_security_policy",
            "mark_stale",
        ]
        for name in write_methods:
            assert hasattr(TopologyRepository, name), f"Missing write method: {name}"
            member = getattr(TopologyRepository, name)
            assert callable(member), f"{name} is not callable"

    def test_defines_graph_query_methods(self):
        """All 3 graph-query methods must be declared on the class."""
        graph_methods = [
            "find_paths",
            "blast_radius",
            "get_topology_export",
        ]
        for name in graph_methods:
            assert hasattr(TopologyRepository, name), f"Missing graph method: {name}"
            member = getattr(TopologyRepository, name)
            assert callable(member), f"{name} is not callable"
