#!/usr/bin/env python3
"""Generator — consolidated security inventory.

Reads .harness/security_policy.yaml AND .harness/generated/backend_routes.json
(produced by extract_backend_routes). Emits a consolidated view: declared
auth dependency names + rate_limit/csrf exempt lists, plus a routes_summary
counting how many live routes have auth/rate_limit/csrf protection.

Output: .harness/generated/security_inventory.json
Schema: .harness/schemas/generated/security_inventory.schema.json

H-25:
  Missing input    — exit 0 with empty inventory if security_policy.yaml absent.
  Malformed input  — exit 0 with empty inventory.
  Upstream failed  — backend_routes.json missing → routes_summary all zero.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / ".harness/generators"))

from _common import write_generated  # noqa: E402


def _scan(root: Path) -> dict:
    """Build {auth_dependency_names, rate_limit_exempt, csrf_exempt, routes_summary}."""
    policy_path = root / ".harness" / "security_policy.yaml"
    inventory: dict = {
        "auth_dependency_names": [],
        "rate_limit_exempt": [],
        "csrf_exempt": [],
        "routes_summary": {"total": 0, "with_auth": 0, "with_rate_limit": 0, "with_csrf": 0},
    }
    if policy_path.exists():
        try:
            policy = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            policy = {}
        inventory["auth_dependency_names"] = sorted(policy.get("auth_dependency_names") or [])
        inventory["rate_limit_exempt"] = sorted(policy.get("rate_limit_exempt") or [])
        inventory["csrf_exempt"] = sorted(policy.get("csrf_exempt") or [])

    routes_path = root / ".harness" / "generated" / "backend_routes.json"
    if routes_path.exists():
        try:
            routes_data = json.loads(routes_path.read_text(encoding="utf-8"))
            routes = routes_data.get("routes", [])
        except (OSError, json.JSONDecodeError):
            routes = []
    else:
        routes = []
    inventory["routes_summary"] = {
        "total": len(routes),
        "with_auth": sum(1 for r in routes if r.get("auth_dep")),
        "with_rate_limit": sum(1 for r in routes if r.get("rate_limit")),
        "with_csrf": sum(1 for r in routes if r.get("csrf_dep")),
    }
    return inventory


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args(argv)
    payload = _scan(args.root)
    if args.print:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    out_path = write_generated("security_inventory", payload)
    summary = payload["routes_summary"]
    print(f"[INFO] wrote security_inventory ({summary['total']} routes) → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
