from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.integrations.probe import GlobalProbe


@pytest.mark.asyncio
async def test_jenkins_probe_returns_reachable_on_200():
    probe = GlobalProbe()
    fake_resp = MagicMock(status_code=200)
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(return_value=fake_resp)
    with patch("httpx.AsyncClient", return_value=fake_client) as AC:
        ep = await probe.test_connection(
            service_type="jenkins",
            url="https://jenkins.example",
            auth_method="basic_auth",
            credentials="user:token",
        )
    assert ep.reachable is True
    # verify we hit /api/json and sent basic auth
    call = fake_client.get.call_args
    assert call.args[0] == "https://jenkins.example/api/json"
    headers = call.kwargs["headers"]
    assert headers.get("Authorization", "").startswith("Basic ")


@pytest.mark.asyncio
async def test_jenkins_probe_returns_error_on_401():
    probe = GlobalProbe()
    fake_resp = MagicMock(status_code=401)
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(return_value=fake_resp)
    with patch("httpx.AsyncClient", return_value=fake_client):
        ep = await probe.test_connection(
            service_type="jenkins",
            url="https://jenkins.example",
            auth_method="basic_auth",
            credentials="user:badtoken",
        )
    assert ep.reachable is False
    assert "401" in (ep.error or "")


@pytest.mark.asyncio
async def test_argocd_rest_probe_returns_reachable():
    probe = GlobalProbe()
    fake_resp = MagicMock(status_code=200)
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(return_value=fake_resp)
    with patch("httpx.AsyncClient", return_value=fake_client):
        ep = await probe.test_connection(
            service_type="argocd",
            url="https://argo.example",
            auth_method="bearer_token",
            credentials="tok",
        )
    assert ep.reachable is True
    call = fake_client.get.call_args
    assert call.args[0] == "https://argo.example/api/version"
    headers = call.kwargs["headers"]
    assert headers.get("Authorization") == "Bearer tok"


@pytest.mark.asyncio
async def test_argocd_kubeconfig_probe_returns_reachable_without_http():
    """Kubeconfig mode skips HTTP probe; verified on first real use."""
    probe = GlobalProbe()
    with patch("httpx.AsyncClient") as AC:
        ep = await probe.test_connection(
            service_type="argocd",
            url="https://incluster.argo",
            auth_method="kubeconfig",
            credentials="kubeconfig-yaml-blob",
        )
    assert ep.reachable is True
    assert "kubeconfig" in (ep.discovered_url or "").lower()
    AC.assert_not_called()  # no HTTP was made


@pytest.mark.asyncio
async def test_jenkins_probe_handles_connection_error():
    import httpx
    probe = GlobalProbe()
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(side_effect=httpx.ConnectError("dns fail"))
    with patch("httpx.AsyncClient", return_value=fake_client):
        ep = await probe.test_connection(
            service_type="jenkins",
            url="https://jenkins.example",
            auth_method="basic_auth",
            credentials="u:t",
        )
    assert ep.reachable is False
    assert "Connection failed" in (ep.error or "")
