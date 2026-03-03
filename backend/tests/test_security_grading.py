"""Tests for security grading heuristic."""
from src.agents.network.report_generator import _compute_security_grade


def test_any_any_is_critical():
    verdict = {
        "action": "allow",
        "matched_source": "0.0.0.0/0",
        "matched_destination": "0.0.0.0/0",
        "matched_ports": "any",
    }
    assert _compute_security_grade(verdict) == "CRITICAL"


def test_internet_to_specific_is_high():
    verdict = {
        "action": "allow",
        "matched_source": "0.0.0.0/0",
        "matched_destination": "10.0.1.0/24",
        "matched_ports": "443",
    }
    assert _compute_security_grade(verdict) == "HIGH"


def test_tight_rule_is_low():
    verdict = {
        "action": "allow",
        "matched_source": "10.0.1.0/24",
        "matched_destination": "10.0.2.50/32",
        "matched_ports": "443",
    }
    assert _compute_security_grade(verdict) == "LOW"


def test_deny_has_no_grade():
    verdict = {"action": "deny"}
    assert _compute_security_grade(verdict) is None
