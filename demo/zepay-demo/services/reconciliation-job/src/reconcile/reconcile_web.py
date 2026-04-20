"""Lightweight HTTP wrapper around NightlyReconcile.

The CronJob itself is a pod that runs once and exits. But the demo
operator needs to be able to trigger a reconcile mid-demo without
waiting for 3am — so we ALSO ship the same image as a tiny
long-running Deployment that exposes:

    POST /demo/run-now            → run reconcile for today
    POST /demo/run-now?day=YYYY-MM-DD
    GET  /metrics                 → Prometheus snapshot
    GET  /livez                   → liveness
    GET  /readyz                  → readiness (pg.ping)

The CronJob and the Deployment both ship from the same image; the
entrypoint diverges based on RECONCILE_MODE (cronjob | web).
"""
import logging
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import psycopg

from .NightlyReconcile import metrics_bytes, run_once

log = logging.getLogger("reconciliation-job-web")


def _pg_ping() -> None:
    dsn = (
        f"host={os.environ.get('PG_HOST', 'postgres')} "
        f"port={os.environ.get('PG_PORT', '5432')} "
        f"user={os.environ.get('PG_USER', 'zepay')} "
        f"password={os.environ.get('PG_PASSWORD', 'zepay-demo-password')} "
        f"dbname={os.environ.get('PG_DB', 'zepay')}"
    )
    with psycopg.connect(dsn, autocommit=True, connect_timeout=2) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        # Route HTTP access logs through our JSON logger.
        log.info("http %s", fmt % args)

    def _ok(self, body: bytes, content_type: str = "application/json") -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _err(self, code: int, msg: str) -> None:
        body = msg.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        p = urlparse(self.path)
        if p.path == "/metrics":
            self._ok(metrics_bytes(), content_type="text/plain; version=0.0.4")
        elif p.path == "/livez":
            self._ok(b"ok", "text/plain")
        elif p.path == "/readyz":
            try:
                _pg_ping()
                self._ok(b"ok", "text/plain")
            except Exception as e:
                self._err(503, f"not-ready: {e}")
        else:
            self._err(404, "not found")

    def do_POST(self) -> None:
        p = urlparse(self.path)
        if p.path != "/demo/run-now":
            self._err(404, "not found")
            return
        qs = parse_qs(p.query or "")
        day = qs.get("day", [datetime.now(timezone.utc).strftime("%Y-%m-%d")])[0]
        try:
            results = run_once(day)
        except Exception as e:
            log.exception("run_once failed")
            self._err(500, f"error: {e}")
            return
        import json as _json
        self._ok(_json.dumps({"day": day, "results": results}).encode())


def serve() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format='{"ts":"%(asctime)s","service":"reconciliation-job","level":"%(levelname)s","msg":"%(message)s"}',
    )
    port = int(os.environ.get("PORT", "8090"))
    srv = HTTPServer(("", port), Handler)
    log.info("reconciliation-job web mode listening on :%d", port)
    srv.serve_forever()


if __name__ == "__main__":
    serve()
