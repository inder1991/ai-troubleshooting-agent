from __future__ import annotations

import pytest

from src.integrations.profile_store import GlobalIntegrationStore
from src.integrations.profile_models import GlobalIntegration


@pytest.fixture
def store(tmp_path):
    db = tmp_path / "t.db"
    s = GlobalIntegrationStore(db_path=str(db))
    s._ensure_tables()
    return s


def test_list_by_service_type_returns_multiple_entries_in_order(store):
    a = GlobalIntegration(id="gi-a", service_type="github", name="first")
    b = GlobalIntegration(id="gi-b", service_type="github", name="second")
    other = GlobalIntegration(id="gi-c", service_type="jira", name="unrelated")
    store.add(a)
    store.add(b)
    store.add(other)
    result = store.list_by_service_type("github")
    names = [gi.name for gi in result]
    assert "first" in names and "second" in names
    assert "unrelated" not in names


def test_list_by_service_type_returns_empty_when_none_match(store):
    assert store.list_by_service_type("github") == []
