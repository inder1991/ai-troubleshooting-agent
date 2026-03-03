import pytest
from src.agents.network.nacl_evaluator import nacl_evaluator, _evaluate_rules
from src.network.models import NACLRule, NACLDirection, PolicyAction


def test_evaluate_rules_allow():
    rules = [
        NACLRule(id="r1", nacl_id="n1", direction=NACLDirection.INBOUND,
                 rule_number=100, action=PolicyAction.ALLOW, cidr="10.0.0.0/8",
                 port_range_from=443, port_range_to=443),
    ]
    result = _evaluate_rules(rules, "10.0.1.5", "10.0.2.10", 443, "tcp")
    assert result["action"] == "allow"
    assert result["rule_number"] == 100


def test_evaluate_rules_deny():
    rules = [
        NACLRule(id="r1", nacl_id="n1", direction=NACLDirection.INBOUND,
                 rule_number=50, action=PolicyAction.DENY, cidr="10.0.1.0/24",
                 port_range_from=0, port_range_to=65535),
        NACLRule(id="r2", nacl_id="n1", direction=NACLDirection.INBOUND,
                 rule_number=100, action=PolicyAction.ALLOW, cidr="10.0.0.0/8",
                 port_range_from=443, port_range_to=443),
    ]
    result = _evaluate_rules(rules, "10.0.1.5", "10.0.2.10", 443, "tcp")
    assert result["action"] == "deny"  # Rule 50 matches first


def test_evaluate_rules_implicit_deny():
    rules = [
        NACLRule(id="r1", nacl_id="n1", direction=NACLDirection.INBOUND,
                 rule_number=100, action=PolicyAction.ALLOW, cidr="192.168.0.0/16",
                 port_range_from=80, port_range_to=80),
    ]
    result = _evaluate_rules(rules, "10.0.1.5", "10.0.2.10", 443, "tcp")
    assert result["action"] == "deny"
    assert result["rule_number"] == -1


def test_evaluate_rules_all_traffic():
    rules = [
        NACLRule(id="r1", nacl_id="n1", direction=NACLDirection.INBOUND,
                 rule_number=100, action=PolicyAction.ALLOW, cidr="0.0.0.0/0",
                 protocol="-1", port_range_from=0, port_range_to=65535),
    ]
    result = _evaluate_rules(rules, "10.0.1.5", "10.0.2.10", 443, "tcp")
    assert result["action"] == "allow"


def test_nacl_evaluator_no_nacls():
    state = {"nacls_in_path": [], "src_ip": "10.0.0.1", "dst_ip": "10.0.0.2", "port": 443, "protocol": "tcp"}
    result = nacl_evaluator(state, store=None)
    assert result["nacl_verdicts"] == []
