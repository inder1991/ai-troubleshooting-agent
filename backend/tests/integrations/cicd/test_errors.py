from __future__ import annotations

import pytest

from src.integrations.cicd.base import CICDClientError


def test_cicd_client_error_carries_structured_fields():
    err = CICDClientError(
        source="jenkins",
        instance="prod-jenkins",
        kind="auth",
        message="401 Unauthorized",
        retriable=False,
    )
    assert err.source == "jenkins"
    assert err.instance == "prod-jenkins"
    assert err.kind == "auth"
    assert err.retriable is False
    assert "401" in str(err)


def test_cicd_client_error_defaults_retriable_for_network_kind():
    err = CICDClientError(
        source="argocd", instance="prod", kind="network", message="conn reset",
    )
    assert err.retriable is True


def test_cicd_client_error_is_raisable():
    with pytest.raises(CICDClientError) as exc_info:
        raise CICDClientError(
            source="jenkins", instance="x", kind="timeout", message="t/o",
        )
    assert exc_info.value.kind == "timeout"
