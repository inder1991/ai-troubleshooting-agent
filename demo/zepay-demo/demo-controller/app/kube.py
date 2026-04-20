"""Thin kubectl / API-client wrapper.

The demo-controller runs on the operator's laptop and talks to the
cluster via the user's kubeconfig (the same one they used to open the
port-forwards). For simplicity we shell out to `kubectl` rather than
pulling the full python k8s client — the controller does maybe 10
commands across the whole demo, so subprocess is fine and avoids an
auth/kubeconfig reimplementation.
"""
import logging
import shlex
import subprocess
from pathlib import Path

log = logging.getLogger("demo-controller.kube")

REPO_ROOT = Path(__file__).resolve().parents[3]
FAULT_YAML = REPO_ROOT / "istio" / "inventory-timeout-fault.yaml"


def run_kubectl(*args: str, check: bool = True, timeout: int = 30) -> subprocess.CompletedProcess:
    cmd = ["kubectl", *args]
    log.info("kubectl %s", " ".join(shlex.quote(a) for a in args))
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"kubectl {' '.join(args)} failed (code {proc.returncode}):\n"
            f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
        )
    return proc


def apply_fault() -> None:
    run_kubectl("apply", "-f", str(FAULT_YAML))


def remove_fault() -> None:
    run_kubectl("delete", "-f", str(FAULT_YAML), "--ignore-not-found=true")


def scale_k6(rps: int) -> None:
    """Bump k6's RPS env var and restart the pod. The Deployment
    has only one replica so `kubectl rollout restart` is a clean swap.
    """
    run_kubectl(
        "set", "env",
        "deploy/k6-traffic",
        "-n", "demo-ctrl",
        f"RPS={rps}",
    )
    run_kubectl("rollout", "restart", "deploy/k6-traffic", "-n", "demo-ctrl")


def pg_reset_ledger() -> None:
    """Truncate ledger.txns + wallet.balances + inventory.items + notif.outbox
    between demo runs. Leaves the schemas/tables intact.
    """
    # Exec into the postgres pod; assumes the secret's DB is set.
    # Using `kubectl exec` keeps us from needing psycopg here.
    sql = (
        "TRUNCATE ledger.txns, wallet.balances, inventory.items, notif.outbox;"
    )
    run_kubectl(
        "exec", "-n", "payments-prod",
        "deploy/postgres", "--",
        "psql", "-U", "zepay", "-d", "zepay", "-c", sql,
    )
