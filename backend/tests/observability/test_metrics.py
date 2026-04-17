"""Task 4.28 — step-latency metrics + alert rules."""
from __future__ import annotations

import pytest

from src.observability.metrics import (
    alert_rules_yaml,
    get_registry,
    record_investigation_outcome,
    record_step_completion,
    set_in_flight,
)


@pytest.fixture(autouse=True)
def _reset():
    get_registry().reset_for_tests()
    yield
    get_registry().reset_for_tests()


class TestStepDuration:
    def test_emits_sample_with_agent_label(self):
        record_step_completion(agent="metrics_agent", duration_ms=250, status="success")
        samples = get_registry().get("investigation_step_duration_ms").samples
        assert any(s.labels["agent"] == "metrics_agent" for s in samples)

    def test_distinguishes_statuses(self):
        record_step_completion(agent="log_agent", duration_ms=100, status="success")
        record_step_completion(agent="log_agent", duration_ms=500, status="timeout")
        record_step_completion(agent="log_agent", duration_ms=50, status="error")
        samples = get_registry().get("investigation_step_duration_ms").samples
        statuses = {s.labels["status"] for s in samples}
        assert statuses == {"success", "timeout", "error"}

    def test_rejects_unknown_status(self):
        with pytest.raises(ValueError):
            record_step_completion(agent="x", duration_ms=1, status="weird")


class TestInvestigationTotal:
    def test_increments_by_outcome(self):
        record_investigation_outcome(outcome="completed")
        record_investigation_outcome(outcome="completed")
        record_investigation_outcome(outcome="failed")
        samples = get_registry().get("investigation_total").samples
        # Collect latest value per label set
        values = {}
        for s in samples:
            values[tuple(sorted(s.labels.items()))] = s.value
        assert values[(("outcome", "completed"),)] == 2
        assert values[(("outcome", "failed"),)] == 1

    def test_rejects_unknown_outcome(self):
        with pytest.raises(ValueError):
            record_investigation_outcome(outcome="weird")


class TestInFlight:
    def test_set_replaces_value(self):
        set_in_flight(3)
        set_in_flight(7)
        samples = get_registry().get("investigation_in_flight").samples
        # Last sample is 7.
        assert samples[-1].value == 7


class TestAlertRulesYAML:
    def test_contains_three_rules(self):
        y = alert_rules_yaml()
        assert "DiagnosticStepSlowP95" in y
        assert "DiagnosticInFlightNearCap" in y
        assert "DiagnosticFailureRateHigh" in y

    def test_parses_as_yaml(self):
        import yaml
        parsed = yaml.safe_load(alert_rules_yaml())
        assert parsed["groups"][0]["name"] == "diagnostic-investigation-slos"
        rules = parsed["groups"][0]["rules"]
        assert len(rules) == 3

    def test_thresholds_present(self):
        y = alert_rules_yaml()
        # Thresholds come from the plan's Task 4.28 Step 3.
        assert "30000" in y  # p95 > 30s = 30000ms
        assert "0.80" in y   # in-flight 80% of cap
        assert "0.05" in y   # failure rate 5%
