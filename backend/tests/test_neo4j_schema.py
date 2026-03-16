"""Tests for Neo4j schema manager.

All tests are skip-gated on NEO4J_URI env var.
Run with: NEO4J_URI=bolt://localhost:7687 python3 -m pytest tests/test_neo4j_schema.py -v
"""

import os
import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("NEO4J_URI"),
    reason="NEO4J_URI not set — Neo4j not available",
)


@pytest.fixture
def neo4j_manager():
    """Create a Neo4jConnectionManager for testing."""
    from src.network.repository.neo4j_connection import Neo4jConnectionManager

    uri = os.environ["NEO4J_URI"]
    mgr = Neo4jConnectionManager(
        uri=uri,
        username="neo4j",
        password="debugduck",
    )
    yield mgr
    mgr.close()


@pytest.fixture
def schema_manager(neo4j_manager):
    """Create a Neo4jSchemaManager backed by the test connection."""
    from src.network.repository.neo4j_schema import Neo4jSchemaManager

    return Neo4jSchemaManager(neo4j_manager)


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


def test_apply_schema(schema_manager):
    """apply() should complete without raising."""
    schema_manager.apply()

    info = schema_manager.get_schema_info()
    assert info["schema_version"] == 1
    assert info["constraint_count"] >= 13
    assert info["index_count"] >= 10


def test_constraints_created(schema_manager, neo4j_manager):
    """Key label constraints should be present after apply."""
    schema_manager.apply()

    constraints = neo4j_manager.execute_read("SHOW CONSTRAINTS")
    constraint_labels = set()
    for c in constraints:
        for label in c.get("labelsOrTypes", []):
            constraint_labels.add(label)

    for expected in ("Device", "Interface", "IPAddress", "Subnet"):
        assert expected in constraint_labels, f"Missing constraint for {expected}"


def test_indexes_created(schema_manager, neo4j_manager):
    """Key indexes should be present after apply."""
    schema_manager.apply()

    indexes = neo4j_manager.execute_read("SHOW INDEXES")
    index_labels = set()
    for idx in indexes:
        for label in (idx.get("labelsOrTypes") or []):
            index_labels.add(label)

    for expected in ("Device", "Interface"):
        assert expected in index_labels, f"Missing index for {expected}"


def test_schema_idempotent(schema_manager):
    """Calling apply() twice should not raise."""
    schema_manager.apply()
    schema_manager.apply()

    info = schema_manager.get_schema_info()
    assert info["constraint_count"] >= 13
