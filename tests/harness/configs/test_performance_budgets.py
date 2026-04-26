"""Sprint H.0b Story 5 — performance_budgets.yaml seeded with Q12 hard + soft gates."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
PERF_YAML = REPO_ROOT / ".harness/performance_budgets.yaml"


def test_perf_yaml_exists() -> None:
    assert PERF_YAML.is_file()


def test_perf_yaml_has_hard_gates() -> None:
    data = yaml.safe_load(PERF_YAML.read_text())
    assert "hard" in data
    for key in ("agent_budgets", "database", "frontend_bundle"):
        assert key in data["hard"], f"hard gate missing: {key}"


def test_perf_yaml_has_soft_gates() -> None:
    data = yaml.safe_load(PERF_YAML.read_text())
    assert "soft" in data
    for key in ("api_latency", "frontend_rendering"):
        assert key in data["soft"], f"soft gate missing: {key}"


def test_perf_yaml_db_query_budget_is_100ms() -> None:
    data = yaml.safe_load(PERF_YAML.read_text())
    assert data["hard"]["database"]["single_query_max_ms"] == 100


def test_perf_yaml_default_agent_budgets_are_sensible() -> None:
    defaults = yaml.safe_load(PERF_YAML.read_text())["hard"]["agent_budgets"]["default"]
    assert defaults["tool_calls_max"] == 20
    assert defaults["tokens_max"] == 20000
    assert defaults["wall_clock_max_s"] == 30


def test_perf_yaml_bundle_budgets() -> None:
    bundle = yaml.safe_load(PERF_YAML.read_text())["hard"]["frontend_bundle"]
    assert bundle["initial_js_kb_gzipped"] == 220
    assert bundle["per_route_chunk_kb_gzipped"] == 100
    assert bundle["total_css_kb_gzipped"] == 50
