"""Application configuration — controlled by environment variables."""

import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Application mode: "demo" or "production"
APP_MODE = os.environ.get("DEBUGDUCK_MODE", "demo")


def is_demo_mode() -> bool:
    return APP_MODE == "demo"


def is_production_mode() -> bool:
    return APP_MODE == "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=True)

    CATALOG_UI_ENABLED: bool = Field(
        default=False,
        description="Phase 1: expose /v4/catalog/* endpoints and /catalog UI",
    )


settings = Settings()
