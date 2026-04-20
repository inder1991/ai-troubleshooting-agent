"""FastAPI demo-controller — the single button panel the operator
clicks during the CXO demo. Runs on the operator's laptop at :7777.

Endpoints (storyboard §5):
  GET  /                         → operator HTML page
  GET  /demo/state               → current demo state
  POST /demo/healthcheck         → pings ES / Prom / Jaeger / K8s
  POST /demo/reset               → truncate tables + remove fault + stop k6
  POST /demo/start-traffic?rps=N → patch k6 + rollout
  POST /demo/inject-fault        → kubectl apply fault yaml
  POST /demo/trigger-incident    → deterministic race for 47 customers
  POST /demo/spike?rps=500       → boost k6 for 60s then revert
  POST /demo/historical-seed     → inject the Feb-2026 sibling incident into the workflow backend

  GET  /remediation/{pr_id}      → returns a pre-baked diff bundle so
                                   the workflow's RemediationCampaign
                                   endpoint can display it inline
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response

from . import healthcheck, kube, trigger
from .state import STATE

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format='{"ts":"%(asctime)s","service":"demo-controller","level":"%(levelname)s","msg":"%(message)s"}',
)
log = logging.getLogger("demo-controller")

REPO_ROOT = Path(__file__).resolve().parents[2]
OPERATOR_UI = REPO_ROOT / "operator-ui" / "index.html"
FIXTURES = REPO_ROOT / "fixtures"

app = FastAPI(title="Zepay Demo Controller", version="demo-0.1.0")


# ── HTML ────────────────────────────────────────────────────────────


@app.get("/")
def root() -> FileResponse:
    return FileResponse(OPERATOR_UI)


# ── State + health ─────────────────────────────────────────────────


@app.get("/demo/state")
def state() -> dict:
    return STATE.to_dict()


@app.post("/demo/healthcheck")
def do_healthcheck() -> dict:
    checks = healthcheck.run_checks()
    ok = all(c.get("ok") for c in checks.values())
    return {"ok": ok, "checks": checks}


# ── Scenario controls ──────────────────────────────────────────────


@app.post("/demo/reset")
def reset() -> dict:
    try:
        kube.remove_fault()
    except Exception as e:
        log.warning("remove_fault swallowed: %s", e)
    try:
        kube.pg_reset_ledger()
    except Exception as e:
        log.warning("pg_reset_ledger swallowed: %s", e)
    STATE.traffic_on = False
    STATE.fault_on = False
    STATE.current_incident_id = None
    STATE.last_trigger_ts = None
    STATE.last_verdict_ts = None
    STATE.triggered_txn_ids.clear()
    return {"reset": True, "state": STATE.to_dict()}


@app.post("/demo/start-traffic")
def start_traffic(rps: int = 50) -> dict:
    if rps < 1 or rps > 2000:
        raise HTTPException(400, "rps must be 1..2000")
    kube.scale_k6(rps)
    STATE.traffic_on = True
    return {"traffic_on": True, "rps": rps}


@app.post("/demo/inject-fault")
def inject_fault() -> dict:
    kube.apply_fault()
    STATE.fault_on = True
    return {"fault_active": True, "affects": "20% of /v1/inventory/reserve calls, 15s delay"}


@app.post("/demo/trigger-incident")
def trigger_incident() -> dict:
    if not STATE.fault_on:
        raise HTTPException(409, "fault not active; call /demo/inject-fault first")
    ids = trigger.trigger_race()
    return {
        "incident_id": STATE.current_incident_id,
        "triggered_count": len(ids),
        "expected_verdict_seconds": 90,
    }


@app.post("/demo/spike")
def spike(rps: int = 500, duration_s: int = 60) -> dict:
    """Boost RPS for a fixed duration, then revert to 50."""
    if rps < 50 or rps > 2000:
        raise HTTPException(400, "spike rps must be 50..2000")
    if duration_s < 5 or duration_s > 600:
        raise HTTPException(400, "spike duration_s must be 5..600")

    kube.scale_k6(rps)

    def revert() -> None:
        time.sleep(duration_s)
        try:
            kube.scale_k6(50)
        except Exception as e:
            log.error("spike revert failed: %s", e)

    threading.Thread(target=revert, daemon=True).start()
    return {"spike": True, "rps": rps, "duration_s": duration_s}


@app.post("/demo/historical-seed")
def historical_seed() -> dict:
    """Writes the prior Feb-2026 checkout-cart-sync-drift incident into
    the workflow backend's archive via the existing demo-seed endpoint.

    The workflow backend is expected to be reachable at localhost:8000
    (the normal dev address) with DEMO_MODE=on.
    """
    import httpx

    payload_path = FIXTURES / "historical-incident.json"
    if not payload_path.exists():
        raise HTTPException(500, f"fixture missing: {payload_path}")
    body = json.loads(payload_path.read_text())

    backend = os.environ.get("WORKFLOW_BACKEND_URL", "http://localhost:8000")
    url = f"{backend}/api/v4/demo/seed/zepay-historical"
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(url, json=body)
            if r.status_code >= 400:
                raise HTTPException(
                    502,
                    f"workflow backend returned {r.status_code}: {r.text[:200]}",
                )
    except httpx.HTTPError as e:
        raise HTTPException(502, f"workflow backend unreachable: {e}") from e
    STATE.history_seeded = True
    return {"history_seeded": True}


# ── Remediation fix-diff payloads ──────────────────────────────────


_FIX_FILES = {
    "8427": "pr-8427-payment-service.json",
    "1203": "pr-1203-shared-finance-models.json",
    "294":  "pr-294-reconciliation-job.json",
}


@app.get("/remediation/{pr_id}")
def get_remediation(pr_id: str) -> Response:
    fname = _FIX_FILES.get(pr_id)
    if not fname:
        raise HTTPException(404, f"no remediation bundle for PR #{pr_id}")
    p = FIXTURES / "remediation" / fname
    if not p.exists():
        raise HTTPException(500, f"bundle missing: {p}")
    return Response(p.read_text(), media_type="application/json")


# ── Plain 404 handler so unknown endpoints don't 500 ───────────────


@app.get("/{path:path}")
def catchall(path: str) -> Response:
    return JSONResponse({"error": "not found"}, status_code=404)
