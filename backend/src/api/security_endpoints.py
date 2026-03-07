"""CRUD endpoints for security & infrastructure resources.

Covers: FirewallRule, NATRule, NACL, NACLRule, LoadBalancer,
LBTargetGroup, VLAN, MPLSCircuit, ComplianceZone.
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from src.network.models import (
    FirewallRule, NATRule,
    NACL, NACLRule,
    LoadBalancer, LBTargetGroup,
    VLAN, MPLSCircuit, ComplianceZone,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

security_router = APIRouter(prefix="/api/v4/network/security", tags=["security"])

_topology_store = None


def init_security_endpoints(topology_store):
    global _topology_store
    _topology_store = topology_store


def _store():
    if not _topology_store:
        raise HTTPException(503, "Store not initialized")
    return _topology_store


# ── Firewall Rule CRUD ───────────────────────────────────────────────


@security_router.post("/firewall-rules", status_code=201)
def create_firewall_rule(rule: FirewallRule):
    _store().add_firewall_rule(rule)
    return rule.model_dump()


@security_router.get("/firewall-rules")
def list_firewall_rules(device_id: Optional[str] = None):
    return _store().list_firewall_rules(device_id=device_id)


# ── NAT Rule CRUD ────────────────────────────────────────────────────


@security_router.post("/nat-rules", status_code=201)
def create_nat_rule(rule: NATRule):
    _store().add_nat_rule(rule)
    return rule.model_dump()


@security_router.get("/nat-rules")
def list_nat_rules(device_id: Optional[str] = None):
    return _store().list_nat_rules(device_id=device_id)


# ── NACL CRUD ────────────────────────────────────────────────────────


@security_router.post("/nacls", status_code=201)
def create_nacl(nacl: NACL):
    _store().add_nacl(nacl)
    return nacl.model_dump()


@security_router.get("/nacls")
def list_nacls(vpc_id: Optional[str] = None):
    return _store().list_nacls(vpc_id=vpc_id)


# ── NACL Rule CRUD ───────────────────────────────────────────────────


@security_router.post("/nacl-rules", status_code=201)
def create_nacl_rule(rule: NACLRule):
    _store().add_nacl_rule(rule)
    return rule.model_dump()


@security_router.get("/nacl-rules")
def list_nacl_rules(nacl_id: str = Query(...)):
    return _store().list_nacl_rules(nacl_id=nacl_id)


# ── Load Balancer CRUD ───────────────────────────────────────────────


@security_router.post("/load-balancers", status_code=201)
def create_load_balancer(lb: LoadBalancer):
    _store().add_load_balancer(lb)
    return lb.model_dump()


@security_router.get("/load-balancers")
def list_load_balancers():
    return _store().list_load_balancers()


# ── LB Target Group CRUD ────────────────────────────────────────────


@security_router.post("/lb-target-groups", status_code=201)
def create_lb_target_group(tg: LBTargetGroup):
    _store().add_lb_target_group(tg)
    return tg.model_dump()


@security_router.get("/lb-target-groups")
def list_lb_target_groups(lb_id: Optional[str] = None):
    return _store().list_lb_target_groups(lb_id=lb_id)


# ── VLAN CRUD ────────────────────────────────────────────────────────


@security_router.post("/vlans", status_code=201)
def create_vlan(vlan: VLAN):
    _store().add_vlan(vlan)
    return vlan.model_dump()


@security_router.get("/vlans")
def list_vlans():
    return _store().list_vlans()


# ── MPLS Circuit CRUD ───────────────────────────────────────────────


@security_router.post("/mpls-circuits", status_code=201)
def create_mpls_circuit(mpls: MPLSCircuit):
    _store().add_mpls_circuit(mpls)
    return mpls.model_dump()


@security_router.get("/mpls-circuits")
def list_mpls_circuits():
    return _store().list_mpls_circuits()


# ── Compliance Zone CRUD ─────────────────────────────────────────────


@security_router.post("/compliance-zones", status_code=201)
def create_compliance_zone(cz: ComplianceZone):
    _store().add_compliance_zone(cz)
    return cz.model_dump()


@security_router.get("/compliance-zones")
def list_compliance_zones():
    return _store().list_compliance_zones()
