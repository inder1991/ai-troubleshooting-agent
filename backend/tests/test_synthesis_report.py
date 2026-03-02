"""Tests for path synthesizer and report generator."""
import pytest
from src.agents.network.path_synthesizer import path_synthesizer
from src.agents.network.report_generator import report_generator


class TestPathSynthesizer:
    def test_traced_path_preferred(self):
        state = {
            "candidate_paths": [{"hops": ["r1", "fw1", "sw1"], "index": 0, "hop_count": 3}],
            "traced_path": {"hops": ["10.0.0.1", "10.0.0.2", "10.0.1.1"], "method": "icmp", "hop_count": 3},
            "firewall_verdicts": [{"action": "allow", "confidence": 0.95}],
            "trace_hops": [],
            "nat_translations": [],
        }
        result = path_synthesizer(state)
        assert result["final_path"]["source"] == "traced"
        assert result["diagnosis_status"] == "complete"
        assert result["confidence"] > 0

    def test_graph_path_fallback(self):
        state = {
            "candidate_paths": [{"hops": ["r1", "fw1", "sw1"], "index": 0, "hop_count": 3}],
            "traced_path": None,
            "firewall_verdicts": [],
            "trace_hops": [],
            "nat_translations": [],
        }
        result = path_synthesizer(state)
        assert result["final_path"]["source"] == "graph"

    def test_no_path(self):
        state = {
            "candidate_paths": [],
            "traced_path": None,
            "firewall_verdicts": [],
            "trace_hops": [],
            "nat_translations": [],
        }
        result = path_synthesizer(state)
        assert result["diagnosis_status"] == "no_path_known"
        assert result["confidence"] == 0.0

    def test_contradiction_detection(self):
        state = {
            "candidate_paths": [{"hops": ["a", "b", "c"]}],
            "traced_path": {"hops": ["x", "y", "z"], "method": "icmp"},
            "firewall_verdicts": [],
            "trace_hops": [],
            "nat_translations": [],
        }
        result = path_synthesizer(state)
        assert len(result["contradictions"]) > 0
        assert result["contradictions"][0]["type"] == "path_mismatch"

    def test_routing_loop_reduces_confidence(self):
        state = {
            "candidate_paths": [{"hops": ["r1", "fw1"], "index": 0, "hop_count": 2}],
            "traced_path": {"hops": ["10.0.0.1", "10.0.0.2", "10.0.0.1"], "method": "icmp"},
            "firewall_verdicts": [{"action": "allow", "confidence": 0.95}],
            "trace_hops": [],
            "nat_translations": [],
            "routing_loop_detected": True,
        }
        result = path_synthesizer(state)
        assert result["confidence"] < 0.5
        assert any(c["type"] == "routing_loop" for c in result["contradictions"])

    def test_deny_caps_confidence(self):
        state = {
            "candidate_paths": [{"hops": ["r1", "fw1", "sw1"]}],
            "traced_path": {"hops": ["10.0.0.1", "10.0.0.2", "10.0.1.1"], "method": "icmp"},
            "firewall_verdicts": [{"action": "deny", "confidence": 0.95}],
            "trace_hops": [],
            "nat_translations": [],
        }
        result = path_synthesizer(state)
        assert result["confidence"] <= 0.5
        assert result["final_path"]["blocked"] is True

    def test_nat_flag(self):
        state = {
            "candidate_paths": [{"hops": ["r1", "fw1"]}],
            "traced_path": None,
            "firewall_verdicts": [],
            "trace_hops": [],
            "nat_translations": [{"direction": "snat", "translated_src": "203.0.113.1"}],
        }
        result = path_synthesizer(state)
        assert result["final_path"]["has_nat"] is True


class TestReportGenerator:
    def test_blocked_report(self):
        state = {
            "final_path": {"blocked": True, "hops": ["r1", "fw1"]},
            "firewall_verdicts": [
                {"action": "deny", "device_name": "Firewall1", "confidence": 0.95},
            ],
            "nat_translations": [],
            "identity_chain": [],
            "trace_hops": [],
            "contradictions": [],
            "confidence": 0.45,
            "diagnosis_status": "complete",
            "evidence": [],
        }
        result = report_generator(state)
        assert "BLOCKED" in result["executive_summary"]
        assert "Firewall1" in result["executive_summary"]
        assert any("Review firewall" in s for s in result["next_steps"])

    def test_allowed_report(self):
        state = {
            "final_path": {"blocked": False, "hops": ["r1", "sw1"]},
            "firewall_verdicts": [{"action": "allow", "confidence": 0.95}],
            "nat_translations": [],
            "identity_chain": [],
            "trace_hops": [],
            "contradictions": [],
            "confidence": 0.85,
            "diagnosis_status": "complete",
            "evidence": [],
        }
        result = report_generator(state)
        assert "ALLOWED" in result["executive_summary"]

    def test_no_path_report(self):
        state = {
            "final_path": {},
            "firewall_verdicts": [],
            "nat_translations": [],
            "identity_chain": [],
            "trace_hops": [],
            "contradictions": [],
            "confidence": 0.0,
            "diagnosis_status": "no_path_known",
            "evidence": [],
        }
        result = report_generator(state)
        assert "Unable to determine" in result["executive_summary"]
        assert any("topology" in s.lower() for s in result["next_steps"])

    def test_loop_report(self):
        state = {
            "final_path": {"blocked": False, "hops": ["r1"]},
            "firewall_verdicts": [],
            "nat_translations": [],
            "identity_chain": [],
            "trace_hops": [],
            "contradictions": [{"type": "routing_loop"}],
            "confidence": 0.1,
            "diagnosis_status": "error",
            "routing_loop_detected": True,
            "evidence": [],
        }
        result = report_generator(state)
        assert "loop" in result["executive_summary"].lower()

    def test_low_confidence_report(self):
        state = {
            "final_path": {"blocked": False, "hops": ["r1"]},
            "firewall_verdicts": [],
            "nat_translations": [],
            "identity_chain": [],
            "trace_hops": [],
            "contradictions": [],
            "confidence": 0.2,
            "diagnosis_status": "complete",
            "evidence": [],
        }
        result = report_generator(state)
        assert "inconclusive" in result["executive_summary"].lower()
