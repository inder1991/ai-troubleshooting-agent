from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.integrations.cicd.base import InstanceError, ResolveResult
from src.integrations.cicd.resolver import resolve_cicd_clients


def _gi(
    name: str,
    service_type: str,
    *,
    cluster_ids: list[str] | None = None,
    handle: str | None = "handle-1",
    url: str = "https://x.example",
):
    """Fake GlobalIntegration-shaped object (duck-typed)."""
    m = MagicMock()
    m.id = f"gi-{name}"
    # NOTE: `name` is a reserved MagicMock ctor kwarg, so assign post-hoc.
    m.name = name
    m.service_type = service_type
    m.url = url
    m.auth_method = "api_token" if service_type == "jenkins" else "bearer_token"
    m.auth_credential_handle = handle
    m.config = {"cluster_ids": cluster_ids} if cluster_ids is not None else {}
    return m


@pytest.mark.asyncio
async def test_resolver_returns_empty_when_nothing_configured():
    with patch("src.integrations.cicd.resolver.GlobalIntegrationStore") as Store:
        Store.return_value.list_by_service_type.return_value = []
        result = await resolve_cicd_clients(active_cluster_id=None)
    assert isinstance(result, ResolveResult)
    assert result.jenkins == []
    assert result.argocd == []
    assert result.errors == []


@pytest.mark.asyncio
async def test_resolver_includes_jenkins_linked_to_active_cluster():
    jenkins_gi = _gi("prod-jenkins", "jenkins", cluster_ids=["cluster-a"])
    with patch("src.integrations.cicd.resolver.GlobalIntegrationStore") as Store, \
         patch("src.integrations.cicd.resolver.get_credential_resolver") as gcr, \
         patch("src.integrations.cicd.resolver.JenkinsClient") as JC:
        Store.return_value.list_by_service_type.side_effect = (
            lambda t: [jenkins_gi] if t == "jenkins" else []
        )
        gcr.return_value.resolve.return_value = "u:tok"
        stub = MagicMock(source="jenkins")
        stub.name = "prod-jenkins"
        JC.return_value = stub
        result = await resolve_cicd_clients(active_cluster_id="cluster-a")
    assert len(result.jenkins) == 1
    assert result.jenkins[0].name == "prod-jenkins"
    assert result.argocd == []
    assert result.errors == []


@pytest.mark.asyncio
async def test_resolver_skips_jenkins_not_linked_to_active_cluster():
    jenkins_gi = _gi("staging-jenkins", "jenkins", cluster_ids=["cluster-b"])
    with patch("src.integrations.cicd.resolver.GlobalIntegrationStore") as Store, \
         patch("src.integrations.cicd.resolver.get_credential_resolver") as gcr, \
         patch("src.integrations.cicd.resolver.JenkinsClient") as JC:
        Store.return_value.list_by_service_type.side_effect = (
            lambda t: [jenkins_gi] if t == "jenkins" else []
        )
        gcr.return_value.resolve.return_value = "u:tok"
        JC.return_value = MagicMock(source="jenkins", name="staging-jenkins")
        result = await resolve_cicd_clients(active_cluster_id="cluster-a")
    assert result.jenkins == []
    assert result.errors == []


@pytest.mark.asyncio
async def test_resolver_includes_global_jenkins_with_empty_cluster_ids():
    # No cluster_ids in config => global, included for any active cluster
    jenkins_gi = _gi("global-jenkins", "jenkins", cluster_ids=None)
    with patch("src.integrations.cicd.resolver.GlobalIntegrationStore") as Store, \
         patch("src.integrations.cicd.resolver.get_credential_resolver") as gcr, \
         patch("src.integrations.cicd.resolver.JenkinsClient") as JC:
        Store.return_value.list_by_service_type.side_effect = (
            lambda t: [jenkins_gi] if t == "jenkins" else []
        )
        gcr.return_value.resolve.return_value = "u:tok"
        JC.return_value = MagicMock(source="jenkins", name="global-jenkins")
        result = await resolve_cicd_clients(active_cluster_id="cluster-a")
    assert len(result.jenkins) == 1


@pytest.mark.asyncio
async def test_resolver_isolates_failing_instance_records_error():
    good = _gi("good-jenkins", "jenkins", cluster_ids=None)
    bad = _gi("bad-jenkins", "jenkins", cluster_ids=None, handle=None)
    with patch("src.integrations.cicd.resolver.GlobalIntegrationStore") as Store, \
         patch("src.integrations.cicd.resolver.get_credential_resolver") as gcr, \
         patch("src.integrations.cicd.resolver.JenkinsClient") as JC:
        Store.return_value.list_by_service_type.side_effect = (
            lambda t: [good, bad] if t == "jenkins" else []
        )
        gcr.return_value.resolve.return_value = "u:tok"
        stub = MagicMock(source="jenkins")
        stub.name = "good-jenkins"
        JC.return_value = stub
        result = await resolve_cicd_clients(active_cluster_id=None)
    assert len(result.jenkins) == 1
    assert result.jenkins[0].name == "good-jenkins"
    assert len(result.errors) == 1
    assert result.errors[0].name == "bad-jenkins"
    assert result.errors[0].source == "jenkins"
    assert "credential" in result.errors[0].message.lower()


@pytest.mark.asyncio
async def test_resolver_includes_argocd_rest_instance():
    argo_gi = _gi("prod-argo", "argocd", cluster_ids=None)
    with patch("src.integrations.cicd.resolver.GlobalIntegrationStore") as Store, \
         patch("src.integrations.cicd.resolver.get_credential_resolver") as gcr, \
         patch("src.integrations.cicd.resolver.ArgoCDClient") as AC:
        Store.return_value.list_by_service_type.side_effect = (
            lambda t: [argo_gi] if t == "argocd" else []
        )
        gcr.return_value.resolve.return_value = "bearer-token"
        stub = MagicMock(source="argocd")
        stub.name = "prod-argo"
        AC.from_rest.return_value = stub
        result = await resolve_cicd_clients(active_cluster_id=None)
    assert len(result.argocd) == 1
    assert result.argocd[0].name == "prod-argo"


@pytest.mark.asyncio
async def test_resolver_isolates_jenkins_and_still_returns_argocd():
    bad_jenkins = _gi("bad-j", "jenkins", cluster_ids=None, handle=None)
    good_argo = _gi("good-a", "argocd", cluster_ids=None)
    with patch("src.integrations.cicd.resolver.GlobalIntegrationStore") as Store, \
         patch("src.integrations.cicd.resolver.get_credential_resolver") as gcr, \
         patch("src.integrations.cicd.resolver.ArgoCDClient") as AC:
        Store.return_value.list_by_service_type.side_effect = (
            lambda t: [bad_jenkins] if t == "jenkins" else [good_argo]
        )
        gcr.return_value.resolve.return_value = "bearer-token"
        AC.from_rest.return_value = MagicMock(source="argocd", name="good-a")
        result = await resolve_cicd_clients(active_cluster_id=None)
    assert result.jenkins == []
    assert len(result.argocd) == 1
    assert len(result.errors) == 1
    assert result.errors[0].source == "jenkins"
