"""Bulk export endpoints for devices, subnets, interfaces, alert rules."""
from __future__ import annotations
import csv
import io
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse, JSONResponse
from src.utils.logger import get_logger

logger = get_logger(__name__)

export_router = APIRouter(prefix="/api/v4/network/export", tags=["export"])

_topology_store = None
_alert_engine = None


def init_export_endpoints(topology_store, alert_engine=None):
    global _topology_store, _alert_engine
    _topology_store = topology_store
    _alert_engine = alert_engine


def _to_csv_response(rows: list[dict], filename: str) -> StreamingResponse:
    if not rows:
        return StreamingResponse(
            iter(["No data"]), media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@export_router.get("/devices")
def export_devices(format: str = Query("json", pattern="^(json|csv)$")):
    store = _topology_store
    if not store:
        return []
    devices = store.list_devices()
    rows = [_serialize(d) for d in devices]
    if format == "csv":
        return _to_csv_response(rows, "devices.csv")
    return JSONResponse(content=rows)


@export_router.get("/subnets")
def export_subnets(format: str = Query("json", pattern="^(json|csv)$")):
    store = _topology_store
    if not store:
        return []
    subnets = store.list_subnets()
    rows = [_serialize(s) for s in subnets]
    if format == "csv":
        return _to_csv_response(rows, "subnets.csv")
    return JSONResponse(content=rows)


@export_router.get("/interfaces")
def export_interfaces(format: str = Query("json", pattern="^(json|csv)$")):
    store = _topology_store
    if not store:
        return []
    interfaces = store.list_interfaces()
    rows = [_serialize(i) for i in interfaces]
    if format == "csv":
        return _to_csv_response(rows, "interfaces.csv")
    return JSONResponse(content=rows)


@export_router.get("/alert-rules")
def export_alert_rules(format: str = Query("json", pattern="^(json|csv)$")):
    engine = _alert_engine
    if not engine:
        return JSONResponse(content=[])
    rules = engine.list_rules()
    if format == "csv":
        return _to_csv_response(rules, "alert-rules.csv")
    return JSONResponse(content=rules)


def _serialize(obj) -> dict:
    """Serialize a Pydantic model or dataclass to a JSON-safe dict."""
    if hasattr(obj, "model_dump"):
        d = obj.model_dump()
    elif hasattr(obj, "dict"):
        d = obj.dict()
    elif hasattr(obj, "__dict__"):
        d = obj.__dict__.copy()
    else:
        d = dict(obj)
    # Convert enums and non-serializable values to strings
    for k, v in d.items():
        if hasattr(v, "value"):
            d[k] = v.value
        elif v is not None and not isinstance(v, (str, int, float, bool, list, dict)):
            d[k] = str(v)
    return d
