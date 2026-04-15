"""Feature-flag defaults and env override behavior."""

from importlib import reload


def test_catalog_flag_default_off():
    from backend.src.config import settings
    assert settings.CATALOG_UI_ENABLED is False


def test_catalog_flag_respects_env(monkeypatch):
    monkeypatch.setenv("CATALOG_UI_ENABLED", "true")
    from backend.src import config
    reload(config)
    assert config.settings.CATALOG_UI_ENABLED is True
    # Reset module state so later tests see default
    monkeypatch.delenv("CATALOG_UI_ENABLED", raising=False)
    reload(config)
