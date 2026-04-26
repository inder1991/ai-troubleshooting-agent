#!/usr/bin/env python3
"""Generator — frontend accessibility inventory.

Walks frontend/src/components/ui/*.tsx, pairs each primitive with its
*.test.tsx, checks for `axe(` or `runAxe(` presence. Reads
.harness/accessibility_policy.yaml for incident_critical pages and
soft_warn rule list.

Output: .harness/generated/accessibility_inventory.json
Schema: .harness/schemas/generated/accessibility_inventory.schema.json

H-25:
  Missing input    — exit 0 with empty inventory.
  Malformed input  — skip silently.
  Upstream failed  — none.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / ".harness/generators"))

from _common import write_generated  # noqa: E402

AXE_CALL_RE = re.compile(r'\b(axe|runAxe)\s*\(')


def _scan(root: Path) -> dict:
    """Walk ui primitives and incident-critical pages."""
    ui_primitives: list[dict] = []
    ui_dir = root / "frontend" / "src" / "components" / "ui"
    if ui_dir.exists():
        for tsx in sorted(ui_dir.glob("*.tsx")):
            if tsx.name.endswith(".test.tsx"):
                continue
            test_file = tsx.with_name(tsx.stem + ".test.tsx")
            present = False
            test_path_rel = None
            if test_file.exists():
                test_path_rel = str(test_file.relative_to(root))
                try:
                    text = test_file.read_text(encoding="utf-8")
                    present = bool(AXE_CALL_RE.search(text))
                except (OSError, UnicodeDecodeError):
                    pass
            ui_primitives.append({
                "name": tsx.stem,
                "axe_test_present": present,
                "test_file": test_path_rel,
            })
    ui_primitives.sort(key=lambda e: e["name"])

    policy = root / ".harness" / "accessibility_policy.yaml"
    incident_critical: list[dict] = []
    soft_warn: list[str] = []
    if policy.exists():
        try:
            data = yaml.safe_load(policy.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            data = {}
        e2e_dir = root / "frontend" / "e2e" / "a11y"
        for page in (data.get("incident_critical") or []):
            spec = e2e_dir / f"{page.lower()}.spec.ts"
            incident_critical.append({
                "name": page,
                "e2e_spec_present": spec.exists(),
                "spec_file": str(spec.relative_to(root)) if spec.exists() else None,
            })
        soft_warn = sorted(data.get("soft_warn") or [])
    incident_critical.sort(key=lambda e: e["name"])

    return {
        "ui_primitives": ui_primitives,
        "incident_critical_pages": incident_critical,
        "soft_warn_rules": soft_warn,
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
    out_path = write_generated("accessibility_inventory", payload)
    print(f"[INFO] wrote a11y inventory ({len(payload['ui_primitives'])} primitives) → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
