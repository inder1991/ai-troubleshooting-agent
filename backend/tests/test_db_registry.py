"""Tests for DatabaseAdapterRegistry."""
import pytest
from src.database.adapters.mock_adapter import MockDatabaseAdapter


@pytest.fixture
def registry():
    from src.database.adapters.registry import DatabaseAdapterRegistry
    return DatabaseAdapterRegistry()


@pytest.fixture
def adapter():
    return MockDatabaseAdapter(
        engine="postgresql", host="localhost", port=5432, database="testdb"
    )


class TestDatabaseAdapterRegistry:
    def test_register_and_lookup(self, registry, adapter):
        registry.register("inst-1", adapter)
        assert registry.get_by_instance("inst-1") is adapter

    def test_register_with_profile_binding(self, registry, adapter):
        registry.register("inst-1", adapter, profile_id="prof-1")
        assert registry.get_by_profile("prof-1") is adapter

    def test_lookup_missing(self, registry):
        assert registry.get_by_instance("nope") is None
        assert registry.get_by_profile("nope") is None

    def test_remove(self, registry, adapter):
        registry.register("inst-1", adapter, profile_id="prof-1")
        registry.remove("inst-1")
        assert registry.get_by_instance("inst-1") is None
        assert registry.get_by_profile("prof-1") is None

    def test_len(self, registry, adapter):
        assert len(registry) == 0
        registry.register("inst-1", adapter)
        assert len(registry) == 1

    def test_all_instances(self, registry, adapter):
        registry.register("inst-1", adapter)
        all_inst = registry.all_instances()
        assert "inst-1" in all_inst
