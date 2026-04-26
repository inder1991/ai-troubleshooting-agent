"""H.2.4 + H.2.5 — a11y/docs + logging/errors/conventions generators (combined)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
GEN_DIR = REPO_ROOT / ".harness" / "generators"


def _run(generator: str, root: Path = REPO_ROOT) -> dict:
    result = subprocess.run(
        [sys.executable, str(GEN_DIR / f"{generator}.py"),
         "--root", str(root), "--print"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"{generator} failed: {result.stderr}"
    return json.loads(result.stdout)


def test_extract_accessibility_inventory_runs() -> None:
    payload = _run("extract_accessibility_inventory")
    assert "ui_primitives" in payload
    assert "incident_critical_pages" in payload
    assert "soft_warn_rules" in payload


def test_extract_documentation_inventory_runs() -> None:
    payload = _run("extract_documentation_inventory")
    assert "python_symbols" in payload
    assert "frontend_exports" in payload
    assert "adrs" in payload
    # Sanity: this very project has plenty of ADRs by now
    assert len(payload["adrs"]) > 5


def test_extract_logging_inventory_runs() -> None:
    payload = _run("extract_logging_inventory")
    assert "structlog_processors" in payload
    assert "tracing_initialized" in payload
    assert "log_calls" in payload


def test_extract_error_taxonomy_runs() -> None:
    payload = _run("extract_error_taxonomy")
    assert "exception_classes" in payload
    assert "result_aliases" in payload


def test_extract_outbound_http_inventory_runs() -> None:
    payload = _run("extract_outbound_http_inventory")
    assert "callsites" in payload


def test_extract_conventions_inventory_runs() -> None:
    payload = _run("extract_conventions_inventory")
    assert "ruff" in payload
    assert "eslint" in payload
    assert "commitlint" in payload
