"""Pre-demo health check — fails loudly if any port-forward is missing.

Exactly matches what the operator runs from scripts/port-forwards.sh.

ES note:
    ECK ships Elasticsearch with TLS + basic auth by default. The
    password is written to ~/.zepay-demo/es-password by the operator
    (see docs/OPERATOR-RUNBOOK.md §0). We read it here lazily so the
    healthcheck works against a stock ECK install without extra wiring.
    HTTPS + -k equivalent (verify=False) because the self-signed cert
    has no reason to live in the demo-controller's trust store.
"""
from pathlib import Path

import httpx


ES_PASSWORD_FILE = Path.home() / ".zepay-demo" / "es-password"


def _es_auth():
    try:
        pw = ES_PASSWORD_FILE.read_text().strip()
    except FileNotFoundError:
        return None
    return ("elastic", pw)


def run_checks() -> dict[str, dict]:
    results: dict[str, dict] = {}

    # ES — TLS + basic auth. Using curl (subprocess) because httpx on
    # macOS Python 3.14 has a TLS-handshake timeout interacting with
    # kubectl port-forward that curl doesn't. The demo-controller's
    # other probes use httpx happily; only ES needs this workaround.
    import subprocess
    try:
        pw_file = ES_PASSWORD_FILE
        if not pw_file.exists():
            results["elasticsearch"] = {
                "ok": False,
                "error": f"password file missing: {pw_file}",
            }
        else:
            pw = pw_file.read_text().strip()
            proc = subprocess.run(
                [
                    "curl", "-sk", "--max-time", "5",
                    "-u", f"elastic:{pw}",
                    "-o", "/dev/null",
                    "-w", "%{http_code}",
                    "https://localhost:9200/_cluster/health",
                ],
                capture_output=True, text=True, timeout=8,
            )
            code = int(proc.stdout.strip() or "0")
            results["elasticsearch"] = {
                "ok": 200 <= code < 400,
                "status_code": code,
            }
    except Exception as e:
        results["elasticsearch"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}

    # Prometheus + Jaeger — plain HTTP
    for name, url in [
        ("prometheus", "http://localhost:9090/-/healthy"),
        ("jaeger",     "http://localhost:16686/"),
    ]:
        try:
            with httpx.Client(timeout=3.0) as client:
                r = client.get(url)
                results[name] = {
                    "ok": r.status_code < 400,
                    "status_code": r.status_code,
                }
        except Exception as e:
            results[name] = {"ok": False, "error": f"{type(e).__name__}: {e}"}

    # k8s — kubectl version as a liveness proxy.
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
