"""SNMP configuration endpoints."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from src.utils.logger import get_logger

logger = get_logger(__name__)

snmp_router = APIRouter(prefix="/api/v4/network/snmp", tags=["snmp"])

_knowledge_graph = None


def init_snmp_endpoints(knowledge_graph):
    global _knowledge_graph
    _knowledge_graph = knowledge_graph


@snmp_router.get("/{device_id}")
def get_snmp_config(device_id: str):
    kg = _knowledge_graph
    if not kg or device_id not in kg.graph:
        raise HTTPException(status_code=404, detail="Device not found")
    node = dict(kg.graph.nodes[device_id])
    return {
        "device_id": device_id,
        "snmp_enabled": node.get("snmp_enabled", False),
        "snmp_version": node.get("snmp_version", "v2c"),
        "snmp_community": node.get("snmp_community", "public"),
        "snmp_port": node.get("snmp_port", 161),
    }


@snmp_router.put("/{device_id}")
def update_snmp_config(device_id: str, config: dict):
    kg = _knowledge_graph
    if not kg or device_id not in kg.graph:
        raise HTTPException(status_code=404, detail="Device not found")
    allowed = {"snmp_enabled", "snmp_version", "snmp_community", "snmp_port"}
    for key in allowed:
        if key in config:
            kg.graph.nodes[device_id][key] = config[key]
    return {"status": "updated", "device_id": device_id}
