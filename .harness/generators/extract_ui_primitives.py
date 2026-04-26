#!/usr/bin/env python3
"""Generator — frontend UI primitives.

Walks frontend/src/components/ui/*.tsx and emits, per file, the set of
top-level `export const|function` names plus a `uses_radix` flag set
when any `from "@radix-ui/..."` import appears.

Output: .harness/generated/ui_primitives.json
Schema: .harness/schemas/generated/ui_primitives.schema.json

H-25:
  Missing input    — exit 0; emit empty list.
  Malformed input  — skip individual file; never block.
  Upstream failed  — none.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / ".harness/generators"))

from _common import write_generated  # noqa: E402

EXPORT_NAME_RE = re.compile(
    r'^\s*export\s+(?:const|function|class)\s+(\w+)', re.MULTILINE,
)
RADIX_IMPORT_RE = re.compile(r'from\s+["\']@radix-ui/')


def _scan(root: Path) -> list[dict]:
    """Walk frontend/src/components/ui/*.tsx under root."""
    ui_dir = root / "frontend" / "src" / "components" / "ui"
    out: list[dict] = []
    if not ui_dir.exists():
        return out
    for path in sorted(ui_dir.glob("*.tsx")):
        if path.name.endswith(".test.tsx"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        names = sorted(set(EXPORT_NAME_RE.findall(text)))
        if not names:
            continue
        out.append({
            "name": path.stem,
            "exports": names,
            "file": str(path.relative_to(root)),
            "uses_radix": bool(RADIX_IMPORT_RE.search(text)),
        })
    out.sort(key=lambda e: e["file"])
    return out


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args(argv)
    payload = {"primitives": _scan(args.root)}
    if args.print:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    out_path = write_generated("ui_primitives", payload)
    print(f"[INFO] wrote {len(payload['primitives'])} primitives → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
