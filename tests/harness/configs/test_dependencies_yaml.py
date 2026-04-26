"""Sprint H.0b Story 4 — .harness/dependencies.yaml seeded + valid (Q11)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
DEPS_YAML = REPO_ROOT / ".harness/dependencies.yaml"
VALIDATOR = REPO_ROOT / "tools/validate_dependencies_yaml.py"


def test_dependencies_yaml_exists() -> None:
    assert DEPS_YAML.is_file()


def test_dependencies_yaml_loads() -> None:
    yaml.safe_load(DEPS_YAML.read_text())


def test_dependencies_yaml_has_required_top_level() -> None:
    data = yaml.safe_load(DEPS_YAML.read_text())
    for key in ("version", "spine_paths", "whitelist", "blacklist", "audit"):
        assert key in data, f"dependencies.yaml missing top-level `{key}`"


def test_dependencies_yaml_blacklist_includes_known_banned() -> None:
    data = yaml.safe_load(DEPS_YAML.read_text())
    banned = data["blacklist"]["global"]
    for must in ("requests", "axios", "redux", "jest", "moment"):
        assert must in banned, f"global blacklist should include `{must}` (Q1/Q2/Q5/Q7)"


def test_validator_exists() -> None:
    assert VALIDATOR.is_file()


def test_validator_passes_on_seeded_yaml() -> None:
    result = subprocess.run(
        [sys.executable, str(VALIDATOR)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"validator should pass on seeded yaml: {result.stderr}"
    )
