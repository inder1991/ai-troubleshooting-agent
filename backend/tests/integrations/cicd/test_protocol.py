from __future__ import annotations

from src.integrations.cicd.base import (
    CICDClient, InstanceError, ResolveResult,
)


class _FakeClient:
    source = "jenkins"
    name = "fake"

    async def list_deploy_events(self, since, until, target_filter=None):
        return []

    async def get_build_artifacts(self, event):
        return None

    async def health_check(self):
        return True


def test_fake_client_satisfies_protocol():
    # runtime_checkable Protocol — isinstance check should pass
    client: CICDClient = _FakeClient()
    assert isinstance(client, CICDClient)


def test_resolve_result_groups_clients_by_source_and_holds_errors():
    result = ResolveResult(
        jenkins=[_FakeClient()],
        argocd=[],
        errors=[InstanceError(name="broken", source="jenkins", message="401")],
    )
    assert len(result.jenkins) == 1
    assert len(result.argocd) == 0
    assert result.errors[0].name == "broken"
    assert result.errors[0].source == "jenkins"
