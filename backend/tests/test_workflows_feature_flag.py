from importlib import reload


def test_workflows_flag_default_off():
    from src.config import settings
    assert settings.WORKFLOWS_ENABLED is False


def test_workflows_flag_respects_env(monkeypatch):
    monkeypatch.setenv("WORKFLOWS_ENABLED", "true")
    from src import config
    reload(config)
    assert config.settings.WORKFLOWS_ENABLED is True
    monkeypatch.delenv("WORKFLOWS_ENABLED", raising=False)
    reload(config)
