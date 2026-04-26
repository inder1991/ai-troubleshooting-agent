"""Sprint H.0b Story 10 — frontend ErrorBoundary primitive + tenacity installed."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ERROR_BOUNDARY = REPO_ROOT / "frontend/src/components/ui/error-boundary.tsx"


def test_error_boundary_primitive_exists() -> None:
    assert ERROR_BOUNDARY.is_file()


def test_error_boundary_exports_named() -> None:
    text = ERROR_BOUNDARY.read_text()
    assert "export class ErrorBoundary" in text or "export function ErrorBoundary" in text


def test_tenacity_installed() -> None:
    r = subprocess.run(
        [sys.executable, "-c", "import tenacity"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
