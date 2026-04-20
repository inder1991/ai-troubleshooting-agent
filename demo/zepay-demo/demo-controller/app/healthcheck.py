"""Pre-demo health check — fails loudly if any port-forward is missing.

Exactly matches what the operator runs from scripts/port-forwards.sh.
"""
import httpx

CHECKS = [
    ("elasticsearch", "http://localhost:9200/_cluster/health"),
    ("prometheus",    "http://localhost:9090/-/healthy"),
    ("jaeger",        "http://localhost:16686/"),
]


def run_checks() -> dict[str, dict]:
    results: dict[str, dict] = {}
    with httpx.Client(timeout=2.0) as client:
        for name, url in CHECKS:
            try:
                r = client.get(url)
                results[name] = {
                    "ok": r.status_code < 400,
                    "status_code": r.status_code,
                }
            except Exception as e:
                results[name] = {"ok": False, "error": f"{type(e).__name__}: {e}"}

    # k8s is reached via kubectl which the rest of the controller uses.
    # Running `kubectl version --client=false` as a liveness proxy.
    try:
        import subprocess
        proc = subprocess.run(
            ["kubectl", "version", "--request-timeout=2s", "-o", "json"],
            capture_output=True, text=True, timeout=3,
        )
        results["k8s"] = {"ok": proc.returncode == 0}
    except Exception as e:
        results["k8s"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}

    return results
