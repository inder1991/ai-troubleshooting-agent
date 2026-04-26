"""Sprint H.0b Story 11 — Q18 conventions infrastructure."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PYPROJECT = REPO_ROOT / "backend/pyproject.toml"
TSCONFIG = REPO_ROOT / "frontend/tsconfig.json"
VITE_CFG = REPO_ROOT / "frontend/vite.config.ts"
ESLINT_CFG = REPO_ROOT / "frontend/eslint.config.js"
PACKAGE_JSON = REPO_ROOT / "frontend/package.json"
COMMITLINT_CFG_CJS = REPO_ROOT / "frontend/commitlint.config.cjs"
COMMITLINT_CFG_JSON = REPO_ROOT / "frontend/.commitlintrc.json"


def _strip_jsonc(text: str) -> str:
    """Strip line + block comments so we can json-parse tsconfig.json."""
    text = re.sub(r"//.*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return text


def test_ruff_isort_force_sort_within_sections() -> None:
    cfg = tomllib.loads(PYPROJECT.read_text())
    isort = cfg.get("tool", {}).get("ruff", {}).get("lint", {}).get("isort", {}) \
            or cfg.get("tool", {}).get("ruff", {}).get("isort", {})
    assert isort.get("force-sort-within-sections") is True
    known_first = isort.get("known-first-party", [])
    assert "src" in known_first


def test_tsconfig_has_path_alias() -> None:
    raw = TSCONFIG.read_text()
    data = json.loads(_strip_jsonc(raw))
    paths = data.get("compilerOptions", {}).get("paths", {})
    assert "@/*" in paths


def test_vite_alias_present() -> None:
    text = VITE_CFG.read_text()
    assert "@" in text and "src" in text and "alias" in text


def test_eslint_import_plugin_configured() -> None:
    text = ESLINT_CFG.read_text()
    for rule in ("import/order", "import/no-default-export", "import/no-relative-parent-imports"):
        assert rule in text, f"eslint rule `{rule}` not configured"


def test_commitlint_config_present() -> None:
    assert COMMITLINT_CFG_CJS.exists() or COMMITLINT_CFG_JSON.exists()


def test_commitlint_dep_installed() -> None:
    pkg = json.loads(PACKAGE_JSON.read_text())
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    assert "@commitlint/cli" in deps
    assert "@commitlint/config-conventional" in deps
