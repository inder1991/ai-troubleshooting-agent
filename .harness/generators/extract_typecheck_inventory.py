#!/usr/bin/env python3
"""Generator — typecheck inventory.

Reads .harness/typecheck_policy.yaml (mypy_strict_paths, tsc_root) plus
.harness/baselines/{mypy,tsc}_baseline.json (sizes only). Reads
frontend/tsconfig.json to detect strict + noUncheckedIndexedAccess flags.
Does NOT actually run mypy/tsc — that's the typecheck_policy.py check's job.

Output: .harness/generated/typecheck_inventory.json
Schema: .harness/schemas/generated/typecheck_inventory.schema.json

H-25:
  Missing input    — exit 0 with empty defaults.
  Malformed input  — exit 0 with empty defaults.
  Upstream failed  — none (no subprocess).
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


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}


def _baseline_size(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict) and isinstance(data.get("violations"), list):
        return len(data["violations"])
    return 0


def _tsconfig_flags(root: Path) -> tuple[bool, bool]:
    """Returns (strict, noUncheckedIndexedAccess) from frontend/tsconfig.json."""
    tsconfig = root / "frontend" / "tsconfig.json"
    if not tsconfig.exists():
        return False, False
    try:
        text = tsconfig.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False, False
    # Heuristic: tsconfig may have JSON-with-comments; search literal flags.
    return ("\"strict\": true" in text), ("\"noUncheckedIndexedAccess\": true" in text)


def _scan(root: Path) -> dict:
    """Build the consolidated typecheck view."""
    policy = _load_yaml(root / ".harness" / "typecheck_policy.yaml")
    strict_paths = sorted(policy.get("mypy_strict_paths") or [])
    tsc_strict, no_unchecked = _tsconfig_flags(root)
    return {
        "strict_paths_python": strict_paths,
        "tsc_strict": tsc_strict,
        "tsc_no_unchecked_indexed_access": no_unchecked,
        "mypy_baseline_size": _baseline_size(root / ".harness" / "baselines" / "mypy_baseline.json"),
        "tsc_baseline_size": _baseline_size(root / ".harness" / "baselines" / "tsc_baseline.json"),
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
    out_path = write_generated("typecheck_inventory", payload)
    print(f"[INFO] wrote typecheck_inventory → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
