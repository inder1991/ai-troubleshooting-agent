"""Task 3.3 — singleton http clients per backend."""
from __future__ import annotations

import pytest
import pytest_asyncio

from src.integrations import http_clients


@pytest_asyncio.fixture(autouse=True)
async def _reset():
    await http_clients.reset_for_tests()
    yield
    await http_clients.reset_for_tests()


class TestPerBackendSingleton:
    def test_same_backend_returns_same_instance(self):
        c1 = http_clients.get_client("jira")
        c2 = http_clients.get_client("jira")
        assert c1 is c2

    def test_different_backends_return_different_instances(self):
        jira = http_clients.get_client("jira")
        gh = http_clients.get_client("github")
        assert jira is not gh

    def test_unknown_backend_raises(self):
        with pytest.raises(KeyError):
            http_clients.get_client("martian-api")


class TestEnumerate:
    def test_enumerate_includes_expected_backends(self):
        pools = http_clients.enumerate_backend_pools()
        assert "elasticsearch" in pools
        assert "prometheus" in pools
        assert "kubernetes" in pools
        assert "github" in pools
        assert "jira" in pools
        assert "confluence" in pools
        assert "remedy" in pools

    def test_each_backend_has_documented_limits(self):
        pools = http_clients.enumerate_backend_pools()
        for name in pools:
            max_c, keep = http_clients.limits_for(name)
            assert max_c > 0, name
            assert keep > 0, name


class TestShutdown:
    @pytest.mark.asyncio
    async def test_close_all_releases_clients(self):
        c = http_clients.get_client("jira")
        assert c.is_closed is False
        await http_clients.close_all()
        assert c.is_closed is True

    @pytest.mark.asyncio
    async def test_get_client_after_close_rebuilds(self):
        c1 = http_clients.get_client("jira")
        await http_clients.close_all()
        c2 = http_clients.get_client("jira")
        assert c1 is not c2
        assert c2.is_closed is False
