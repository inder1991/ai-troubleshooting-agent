"""Sprint H.0b Story 12 — mypy strict per-module + tsc strict + baselines (Q19)."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PYPROJECT = REPO_ROOT / "backend/pyproject.toml"
TSCONFIG = REPO_ROOT / "frontend/tsconfig.json"
MYPY_BASELINE = REPO_ROOT / ".harness/baselines/mypy_baseline.json"
TSC_BASELINE = REPO_ROOT / ".harness/baselines/tsc_baseline.json"
BASELINE_GEN = REPO_ROOT / "tools/generate_typecheck_baseline.py"


def _strip_jsonc(text: str) -> str:
    text = re.sub(r"//.*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return text


def test_mypy_strict_overrides_present_for_locked_paths() -> None:
    cfg = tomllib.loads(PYPROJECT.read_text())
    overrides = cfg.get("tool", {}).get("mypy", {}).get("overrides", [])
    text = json.dumps(overrides)
    for spine in ("src.storage", "src.learning", "src.models", "src.api"):
        assert spine in text, f"mypy strict override missing for {spine}"


def test_tsconfig_strict_and_unchecked_indexed_access() -> None:
    raw = TSCONFIG.read_text()
    data = json.loads(_strip_jsonc(raw))
    co = data.get("compilerOptions", {})
    assert co.get("strict") is True
    assert co.get("noUncheckedIndexedAccess") is True


def test_mypy_baseline_exists() -> None:
    assert MYPY_BASELINE.is_file()


def test_tsc_baseline_exists() -> None:
    assert TSC_BASELINE.is_file()


def test_baseline_files_have_required_schema() -> None:
    for path in (MYPY_BASELINE, TSC_BASELINE):
        data = json.loads(path.read_text())
        for required in ("generated_at", "tool_version", "violations"):
            assert required in data, f"{path.name} missing required field {required}"
        assert isinstance(data["violations"], list)


def test_baseline_generator_exists() -> None:
    assert BASELINE_GEN.is_file()
