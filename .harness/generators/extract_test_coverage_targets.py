#!/usr/bin/env python3
"""Generator — vitest coverage thresholds.

Reads frontend/vitest.config.ts (when present) and emits, per glob in
the `coverage.thresholds` block, the four numeric thresholds.

Output: .harness/generated/test_coverage_targets.json
Schema: .harness/schemas/generated/test_coverage_targets.schema.json

H-25:
  Missing input    — exit 0 with empty list (vitest config may be absent).
  Malformed input  — skip; never block.
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

THRESHOLDS_ANCHOR_RE = re.compile(r'thresholds\s*:\s*\{', re.DOTALL)
PER_GLOB_RE = re.compile(
    r'["\'](?P<glob>[^"\']+)["\']\s*:\s*\{\s*'
    r'lines\s*:\s*(?P<lines>[\d.]+)\s*,\s*'
    r'functions\s*:\s*(?P<functions>[\d.]+)\s*,\s*'
    r'branches\s*:\s*(?P<branches>[\d.]+)\s*,\s*'
    r'statements\s*:\s*(?P<statements>[\d.]+)\s*\}',
)


def _scan(root: Path) -> list[dict]:
    """Read frontend/vitest.config.ts; emit per-glob thresholds list."""
    cfg = root / "frontend" / "vitest.config.ts"
    if not cfg.exists():
        return []
    try:
        text = cfg.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    anchor = THRESHOLDS_ANCHOR_RE.search(text)
    if not anchor:
        return []
    body = text[anchor.end():]
    out: list[dict] = []
    for m in PER_GLOB_RE.finditer(body):
        out.append({
            "glob": m.group("glob"),
            "lines": float(m.group("lines")),
            "functions": float(m.group("functions")),
            "branches": float(m.group("branches")),
            "statements": float(m.group("statements")),
        })
    out.sort(key=lambda e: e["glob"])
    return out


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args(argv)
    payload = {"thresholds": _scan(args.root)}
    if args.print:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    out_path = write_generated("test_coverage_targets", payload)
    print(f"[INFO] wrote {len(payload['thresholds'])} thresholds → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
