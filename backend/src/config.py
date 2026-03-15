"""Application configuration — controlled by environment variables."""

import os

# Application mode: "demo" or "production"
APP_MODE = os.environ.get("DEBUGDUCK_MODE", "demo")


def is_demo_mode() -> bool:
    return APP_MODE == "demo"


def is_production_mode() -> bool:
    return APP_MODE == "production"
