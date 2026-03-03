import pytest
from src.agents.network.path_synthesizer import path_synthesizer
from src.agents.network.report_generator import report_generator


def test_nacl_deny_blocks_path():
    """NACL deny should set any_deny and reduce confidence."""
    state = {
        "candidate_paths": [{"index": 0, "hops": ["d1", "d2"], "hop_count": 2}],
        "firewall_verdicts": [],
        "nacl_verdicts": [{"nacl_id": "nacl-1", "nacl_name": "prod-nacl", "action": "deny",
                          "inbound": {"action": "deny", "rule_number": 50}, "outbound": {"action": "allow", "rule_number": 100}}],
        "trace_hops": [],
        "nat_translations": [],
        "routing_loop_detected": False,
    }
    result = path_synthesizer(state)
    assert result["final_path"]["blocked"] is True
    assert result["confidence"] <= 0.5


def test_vpn_segments_in_final_path():
    """VPN segments should appear in final_path."""
    state = {
        "candidate_paths": [{"index": 0, "hops": ["d1", "d2"], "hop_count": 2}],
        "firewall_verdicts": [],
        "nacl_verdicts": [],
        "trace_hops": [],
        "nat_translations": [],
        "routing_loop_detected": False,
        "vpn_segments": [{"device_id": "vpn-1", "name": "site-vpn", "tunnel_type": "ipsec", "encryption": "AES-256"}],
    }
    result = path_synthesizer(state)
    assert len(result["final_path"]["vpn_segments"]) == 1
    assert result["final_path"]["vpn_segments"][0]["name"] == "site-vpn"


def test_vpc_crossings_in_final_path():
    """VPC crossings should appear in final_path."""
    state = {
        "candidate_paths": [{"index": 0, "hops": ["d1", "d2"], "hop_count": 2}],
        "firewall_verdicts": [],
        "nacl_verdicts": [],
        "trace_hops": [],
        "nat_translations": [],
        "routing_loop_detected": False,
        "vpc_boundary_crossings": [{"from_vpc": "vpc-1", "to_vpc": "vpc-2"}],
    }
    result = path_synthesizer(state)
    assert len(result["final_path"]["vpc_crossings"]) == 1


def test_lb_in_final_path():
    """Load balancers should appear in final_path."""
    state = {
        "candidate_paths": [{"index": 0, "hops": ["d1", "d2"], "hop_count": 2}],
        "firewall_verdicts": [],
        "nacl_verdicts": [],
        "trace_hops": [],
        "nat_translations": [],
        "routing_loop_detected": False,
        "load_balancers_in_path": [{"device_id": "lb-1", "device_name": "api-lb", "device_type": "load_balancer"}],
    }
    result = path_synthesizer(state)
    assert len(result["final_path"]["load_balancers"]) == 1


def test_report_nacl_next_steps():
    """Report should include NACL-specific next steps when NACL denies."""
    state = {
        "final_path": {"blocked": True},
        "firewall_verdicts": [],
        "nacl_verdicts": [{"nacl_id": "nacl-1", "nacl_name": "prod-nacl", "action": "deny"}],
        "nat_translations": [],
        "identity_chain": [],
        "trace_hops": [],
        "contradictions": [],
        "confidence": 0.5,
        "diagnosis_status": "complete",
        "evidence": [],
        "vpn_segments": [],
        "vpc_boundary_crossings": [],
        "load_balancers_in_path": [],
    }
    result = report_generator(state)
    assert any("NACL" in step for step in result["next_steps"])


def test_report_vpn_in_summary():
    """Report summary should mention VPN tunnels."""
    state = {
        "final_path": {"blocked": False},
        "firewall_verdicts": [],
        "nacl_verdicts": [],
        "nat_translations": [],
        "identity_chain": [],
        "trace_hops": [],
        "contradictions": [],
        "confidence": 0.8,
        "diagnosis_status": "complete",
        "evidence": [],
        "vpn_segments": [{"device_id": "vpn-1", "name": "site-vpn"}],
        "vpc_boundary_crossings": [{"from_vpc": "vpc-1", "to_vpc": "vpc-2"}],
        "load_balancers_in_path": [{"device_id": "lb-1", "device_name": "api-lb"}],
    }
    result = report_generator(state)
    assert "VPN" in result["executive_summary"]
    assert "VPC" in result["executive_summary"]
    assert "Load balancer" in result["executive_summary"]
