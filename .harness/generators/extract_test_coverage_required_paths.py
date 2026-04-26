#!/usr/bin/env python3
"""Generator — backend test-coverage required paths.

Reads .harness/typecheck_policy.yaml and emits the list of
mypy_strict_paths as paths that downstream consumers (CI, ADR review)
should expect strict typecheck coverage on. Rationale: Q19.

Output: .harness/generated/test_coverage_required_paths.json
Schema: .harness/schemas/generated/test_coverage_required_paths.schema.json

H-25:
  Missing input    — exit 0 with empty list (policy yaml may be absent).
  Malformed input  — exit 0 with empty list; never crash.
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
    """Return {required_paths, rationale} from typecheck_policy.yaml."""
    policy_path = root / ".harness" / "typecheck_policy.yaml"
    if not policy_path.exists():
        return {"required_paths": [], "rationale": "Q19"}
    try:
        data = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {"required_paths": [], "rationale": "Q19"}
    paths = data.get("mypy_strict_paths") or []
    if not isinstance(paths, list):
        paths = []
    return {"required_paths": sorted(str(p) for p in paths), "rationale": "Q19"}


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
    out_path = write_generated("test_coverage_required_paths", payload)
    print(f"[INFO] wrote {len(payload['required_paths'])} required_paths → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
