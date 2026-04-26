#!/usr/bin/env python3
"""Generator — performance budgets shaped projection for AI consumption.

Reads .harness/performance_budgets.yaml and projects it into a flat,
AI-readable shape: agent_caps, db_query_max_ms, bundle_kb, soft_track.

Output: .harness/generated/performance_budgets.json
Schema: .harness/schemas/generated/performance_budgets.schema.json

H-25:
  Missing input    — exit 0 with empty defaults.
  Malformed input  — exit 0 with empty defaults.
  Upstream failed  — none.
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
    """Project performance_budgets.yaml into flat shape."""
    policy_path = root / ".harness" / "performance_budgets.yaml"
    if not policy_path.exists():
        return {"agent_caps": {}, "db_query_max_ms": None, "bundle_kb": {}, "soft_track": []}
    try:
        data = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {"agent_caps": {}, "db_query_max_ms": None, "bundle_kb": {}, "soft_track": []}
    hard = data.get("hard") or {}
    soft = data.get("soft") or {}
    agent = hard.get("agent_budgets", {}).get("default") or {}
    db = hard.get("database") or {}
    bundle = hard.get("frontend_bundle") or {}
    return {
        "agent_caps": {
            "tool_calls_max": agent.get("tool_calls_max"),
            "tokens_max": agent.get("tokens_max"),
            "wall_clock_max_s": agent.get("wall_clock_max_s"),
        },
        "db_query_max_ms": db.get("single_query_max_ms"),
        "bundle_kb": {
            k: v for k, v in bundle.items() if isinstance(v, (int, float))
        },
        "soft_track": sorted(soft.keys()) if isinstance(soft, dict) else [],
    }


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
    out_path = write_generated("performance_budgets", payload)
    print(f"[INFO] wrote performance_budgets projection → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
