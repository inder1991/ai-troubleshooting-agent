import pytest
from src.agents.cluster.causal_invariants import (
    check_hard_block, CAUSAL_INVARIANTS, get_soft_rule, SOFT_RULES,
)


def test_pod_to_node_blocked():
    inv = check_hard_block("pod", "node")
    assert inv is not None
    assert inv.id == "INV-CP-006"
    assert "Pod failure cannot cause node failure" in inv.description


def test_node_to_pod_not_blocked():
    """Node failure CAN cause pod failure — this is valid."""
    inv = check_hard_block("node", "pod")
    assert inv is None


def test_pod_to_etcd_blocked():
    inv = check_hard_block("pod", "etcd")
    assert inv is not None
    assert inv.id == "INV-CP-001"


def test_service_to_node_blocked():
    inv = check_hard_block("service", "node")
    assert inv is not None


def test_deployment_to_pod_not_blocked():
    inv = check_hard_block("deployment", "pod")
    assert inv is None


def test_all_invariants_have_unique_ids():
    ids = [inv.id for inv in CAUSAL_INVARIANTS]
    assert len(ids) == len(set(ids))


def test_all_invariants_have_descriptions():
    for inv in CAUSAL_INVARIANTS:
        assert len(inv.description) > 10


def test_soft_rule_lookup():
    rule = get_soft_rule("SOFT-001")
    assert rule is not None
    assert rule.confidence_hint == 0.2


def test_soft_rule_unknown():
    assert get_soft_rule("SOFT-999") is None


def test_all_soft_rules_have_unique_ids():
    ids = [r.rule_id for r in SOFT_RULES]
    assert len(ids) == len(set(ids))


def test_soft_rule_confidence_hints_bounded():
    for rule in SOFT_RULES:
        assert 0.0 <= rule.confidence_hint <= 1.0
