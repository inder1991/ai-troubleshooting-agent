from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _mock_cicd_audit_hook(monkeypatch):
    """Prevent cicd client tests from writing to the audit SQLite DB."""
    mock = MagicMock()
    monkeypatch.setattr(
        "src.integrations.cicd.jenkins_client.record_cicd_read", mock
    )
    monkeypatch.setattr(
        "src.integrations.cicd.argocd_client.record_cicd_read", mock
    )
    yield mock
