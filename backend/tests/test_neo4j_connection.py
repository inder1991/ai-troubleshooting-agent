"""Tests for Neo4j connection manager.

All tests are skip-gated on NEO4J_URI env var.
Run with: NEO4J_URI=bolt://localhost:7687 python3 -m pytest tests/test_neo4j_connection.py -v
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


def test_connect_and_verify(neo4j_manager):
    """Connect and run a trivial read query."""
    result = neo4j_manager.execute_read("RETURN 1 AS n")
    assert len(result) == 1
    assert result[0]["n"] == 1


def test_connection_context_manager():
    """Use the connection manager via `with` statement."""
    from src.network.repository.neo4j_connection import Neo4jConnectionManager

    uri = os.environ["NEO4J_URI"]
    with Neo4jConnectionManager(uri=uri, username="neo4j", password="debugduck") as mgr:
        result = mgr.execute_read("RETURN 42 AS answer")
        assert result[0]["answer"] == 42


def test_execute_write(neo4j_manager):
    """CREATE a _TestNode, read it back, then DELETE for cleanup."""
    # Write
    neo4j_manager.execute_write(
        "CREATE (n:_TestNode {name: $name}) RETURN n.name AS name",
        {"name": "test_neo4j_conn"},
    )

    # Read back
    result = neo4j_manager.execute_read(
        "MATCH (n:_TestNode {name: $name}) RETURN n.name AS name",
        {"name": "test_neo4j_conn"},
    )
    assert len(result) == 1
    assert result[0]["name"] == "test_neo4j_conn"

    # Cleanup
    neo4j_manager.execute_write(
        "MATCH (n:_TestNode {name: $name}) DELETE n",
        {"name": "test_neo4j_conn"},
    )

    # Verify cleanup
    result = neo4j_manager.execute_read(
        "MATCH (n:_TestNode {name: $name}) RETURN n.name AS name",
        {"name": "test_neo4j_conn"},
    )
    assert len(result) == 0
