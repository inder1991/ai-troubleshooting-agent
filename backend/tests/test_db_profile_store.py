"""Tests for database profile CRUD store."""
import pytest
import os
import tempfile


@pytest.fixture
def store():
    from src.database.profile_store import DBProfileStore
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = DBProfileStore(db_path=path)
    yield s
    os.unlink(path)


class TestDBProfileStore:
    def test_create_and_get(self, store):
        profile = store.create(
            name="prod-pg", engine="postgresql",
            host="db.prod.io", port=5432, database="myapp",
            username="admin", password="secret123",
        )
        assert profile["id"]
        assert profile["name"] == "prod-pg"

        fetched = store.get(profile["id"])
        assert fetched["host"] == "db.prod.io"

    def test_list_all(self, store):
        store.create(name="a", engine="postgresql", host="h", port=5432,
                     database="d", username="u", password="p")
        store.create(name="b", engine="mongodb", host="h", port=27017,
                     database="d", username="u", password="p")
        profiles = store.list_all()
        assert len(profiles) == 2

    def test_update(self, store):
        p = store.create(name="old", engine="postgresql", host="h", port=5432,
                         database="d", username="u", password="p")
        store.update(p["id"], name="new-name", host="new-host")
        fetched = store.get(p["id"])
        assert fetched["name"] == "new-name"
        assert fetched["host"] == "new-host"

    def test_delete(self, store):
        p = store.create(name="del", engine="postgresql", host="h", port=5432,
                         database="d", username="u", password="p")
        store.delete(p["id"])
        assert store.get(p["id"]) is None

    def test_get_missing(self, store):
        assert store.get("nonexistent") is None

    def test_password_not_in_list(self, store):
        store.create(name="a", engine="postgresql", host="h", port=5432,
                     database="d", username="u", password="secret")
        profiles = store.list_all()
        assert "password" not in profiles[0]
