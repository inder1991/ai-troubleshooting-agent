"""Sprint H.0b Story 9 — observability dependencies installed; frontend
errorReporter wrapper exists."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ERROR_REPORTER = REPO_ROOT / "frontend/src/lib/errorReporter.ts"


def test_structlog_installed() -> None:
    r = subprocess.run(
        [sys.executable, "-c", "import structlog"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0


def test_opentelemetry_api_installed() -> None:
    r = subprocess.run(
        [sys.executable, "-c", "from opentelemetry import trace"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0


def test_frontend_error_reporter_exists() -> None:
    assert ERROR_REPORTER.is_file()
    text = ERROR_REPORTER.read_text()
    assert "captureMessage" in text or "captureException" in text
