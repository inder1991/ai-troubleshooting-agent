"""Integration tests: TopologyStore → SQLiteRepository → TopologyValidator."""

import pytest


class TestRepositoryAPIWiring:
    def test_sqlite_repository_instantiation(self, tmp_path):
        """Repository can be created from TopologyStore and returns data."""
        from src.network.topology_store import TopologyStore
        from src.network.repository.sqlite_repository import SQLiteRepository

        store = TopologyStore(str(tmp_path / "test.db"))
        repo = SQLiteRepository(store)
        assert repo is not None
        assert isinstance(repo.get_devices(), list)

    def test_repository_validation_endpoint_data(self, tmp_path):
        """Repository + validator produces a clean report."""
        from src.network.topology_store import TopologyStore
        from src.network.repository.sqlite_repository import SQLiteRepository
        from src.network.repository.validation import TopologyValidator

        store = TopologyStore(str(tmp_path / "test.db"))
        repo = SQLiteRepository(store)
        validator = TopologyValidator()

        devices = repo.get_devices()
        report = validator.validate(
            devices=devices,
            interfaces=[],
            ip_addresses=[],
            subnets=[],
            routes=[],
        )
        assert report["issue_count"] == 0
