"""Sprint H.0b Story 7 — a11y tooling installed and configured (Q14)."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_JSON = REPO_ROOT / "frontend/package.json"
ESLINT_CFG = REPO_ROOT / "frontend/eslint.config.js"


def _deps() -> dict[str, str]:
    pkg = json.loads(PACKAGE_JSON.read_text())
    return {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}


def test_eslint_jsx_a11y_installed() -> None:
    assert "eslint-plugin-jsx-a11y" in _deps()


def test_vitest_axe_installed() -> None:
    assert "vitest-axe" in _deps()


def test_axe_core_playwright_installed() -> None:
    assert "@axe-core/playwright" in _deps()


def test_eslint_config_extends_jsx_a11y() -> None:
    text = ESLINT_CFG.read_text()
    assert "jsx-a11y" in text, "eslint config must reference jsx-a11y"
