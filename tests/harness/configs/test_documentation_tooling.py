"""Sprint H.0b Story 8 — documentation infrastructure (Q15)."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ADR_TEMPLATE = REPO_ROOT / "docs/decisions/_TEMPLATE.md"
API_MD = REPO_ROOT / "docs/api.md"
PYPROJECT = REPO_ROOT / "backend/pyproject.toml"
PACKAGE_JSON = REPO_ROOT / "frontend/package.json"


def test_adr_template_exists() -> None:
    assert ADR_TEMPLATE.is_file()


def test_adr_template_has_required_sections() -> None:
    text = ADR_TEMPLATE.read_text()
    for section in ("Status:", "Date:", "## Context", "## Decision", "## Consequences"):
        assert section in text, f"ADR template missing: {section}"


def test_api_md_stub_exists() -> None:
    assert API_MD.is_file()


def test_ruff_select_includes_D() -> None:
    cfg = tomllib.loads(PYPROJECT.read_text())
    ruff = cfg.get("tool", {}).get("ruff", {})
    select = ruff.get("lint", {}).get("select", []) or ruff.get("select", [])
    assert "D" in select, "ruff lint.select must include D (pydocstyle) for Q15"


def test_eslint_plugin_jsdoc_installed() -> None:
    pkg = json.loads(PACKAGE_JSON.read_text())
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    assert "eslint-plugin-jsdoc" in deps
