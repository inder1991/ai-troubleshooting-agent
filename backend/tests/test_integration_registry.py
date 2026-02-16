import pytest
import os
from backend.src.integrations.models import IntegrationConfig
from backend.src.integrations.store import IntegrationStore


def _make_openshift_config(**kwargs):
    defaults = dict(
        name="prod-openshift",
        cluster_type="openshift",
        cluster_url="https://api.ocp.example.com:6443",
        auth_method="token",
        auth_data="sha256~fake-token",
    )
    defaults.update(kwargs)
    return IntegrationConfig(**defaults)


def _make_kubernetes_config(**kwargs):
    defaults = dict(
        name="staging-k8s",
        cluster_type="kubernetes",
        cluster_url="https://k8s.example.com:6443",
        auth_method="kubeconfig",
        auth_data="apiVersion: v1\nkind: Config...",
    )
    defaults.update(kwargs)
    return IntegrationConfig(**defaults)


# ---- Model tests ----

def test_create_openshift_config():
    cfg = _make_openshift_config()
    assert cfg.cluster_type == "openshift"
    assert cfg.auth_method == "token"
    assert cfg.status == "active"
    assert cfg.id  # UUID generated


def test_create_kubernetes_config():
    cfg = _make_kubernetes_config()
    assert cfg.cluster_type == "kubernetes"
    assert cfg.auth_method == "kubeconfig"
    assert cfg.prometheus_url is None


# ---- Store tests ----

@pytest.fixture
def store(tmp_path):
    db_path = str(tmp_path / "test_integrations.db")
    return IntegrationStore(db_path=db_path)


def test_add_integration(store):
    cfg = _make_openshift_config()
    result = store.add(cfg)
    assert result.id == cfg.id
    assert result.name == "prod-openshift"


def test_list_integrations(store):
    store.add(_make_openshift_config())
    store.add(_make_kubernetes_config())
    items = store.list_all()
    assert len(items) == 2


def test_get_integration(store):
    cfg = _make_openshift_config()
    store.add(cfg)
    fetched = store.get(cfg.id)
    assert fetched is not None
    assert fetched.name == cfg.name
    assert fetched.cluster_url == cfg.cluster_url


def test_get_integration_not_found(store):
    assert store.get("nonexistent-id") is None


def test_delete_integration(store):
    cfg = _make_openshift_config()
    store.add(cfg)
    store.delete(cfg.id)
    assert store.get(cfg.id) is None


def test_update_integration(store):
    cfg = _make_openshift_config()
    store.add(cfg)
    cfg.status = "unreachable"
    cfg.prometheus_url = "https://prometheus.example.com"
    store.update(cfg)
    updated = store.get(cfg.id)
    assert updated is not None
    assert updated.status == "unreachable"
    assert updated.prometheus_url == "https://prometheus.example.com"
