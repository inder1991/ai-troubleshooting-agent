"""Sprint H.0b Story 1 — vitest.config.ts must declare per-path coverage
thresholds matching Q5 of the harness plan."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
VITEST_CONFIG = REPO_ROOT / "frontend/vitest.config.ts"
PLAYWRIGHT_CONFIG = REPO_ROOT / "frontend/playwright.config.ts"


def test_vitest_config_exists() -> None:
    assert VITEST_CONFIG.is_file()


def test_vitest_config_declares_coverage() -> None:
    text = VITEST_CONFIG.read_text()
    assert "coverage" in text, "vitest config must enable coverage"
    # Thresholds keyed by glob; per Q5 services/api ≥ 90%, hooks ≥ 85%
    assert re.search(r"frontend/src/services/api", text), (
        "coverage thresholds must target services/api"
    )
    assert re.search(r"frontend/src/hooks", text), (
        "coverage thresholds must target hooks"
    )


def test_vitest_config_threshold_for_services_api_is_90() -> None:
    text = VITEST_CONFIG.read_text()
    # Loose check: a `0.9` or `90` near the services/api path
    section = text[text.index("services/api"):text.index("services/api") + 400]
    assert "0.9" in section or "90" in section


def test_vitest_config_threshold_for_hooks_is_85() -> None:
    text = VITEST_CONFIG.read_text()
    section = text[text.index("hooks"):text.index("hooks") + 400]
    assert "0.85" in section or "85" in section


def test_playwright_config_exists() -> None:
    assert PLAYWRIGHT_CONFIG.is_file()


def test_playwright_quarantines_e2e_dir() -> None:
    text = PLAYWRIGHT_CONFIG.read_text()
    assert "frontend/e2e" in text or "./e2e" in text or "'e2e'" in text, (
        "playwright config must point at the frontend/e2e directory"
    )
