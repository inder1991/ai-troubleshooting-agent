from __future__ import annotations

import pytest

from pydantic import ValidationError

from src.integrations.profile_models import GlobalIntegration


def test_jenkins_service_type_accepted():
    gi = GlobalIntegration(service_type="jenkins", name="prod-jenkins")
    assert gi.service_type == "jenkins"


def test_argocd_service_type_accepted():
    gi = GlobalIntegration(service_type="argocd", name="prod-argo")
    assert gi.service_type == "argocd"


def test_invalid_service_type_rejected():
    with pytest.raises(ValidationError):
        GlobalIntegration(service_type="bogus", name="x")


def test_kubeconfig_auth_method_accepted():
    gi = GlobalIntegration(
        service_type="argocd",
        name="incluster-argo",
        auth_method="kubeconfig",
    )
    assert gi.auth_method == "kubeconfig"
