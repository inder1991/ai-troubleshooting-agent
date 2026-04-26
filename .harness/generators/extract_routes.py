#!/usr/bin/env python3
"""Generator — frontend route table.

Reads frontend/src/router.tsx and emits, per route entry in
`createBrowserRouter([...])`, the path + element module + lazy flag.

Output: .harness/generated/routes.json
Schema: .harness/schemas/generated/routes.schema.json

H-25:
  Missing input    — exit 0 with empty list (router.tsx may not exist).
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

ROUTE_ENTRY_RE = re.compile(
    r'\{\s*path\s*:\s*["\'](?P<path>[^"\']+)["\']\s*,'
    r'\s*element\s*:\s*<\s*(?P<element>\w+)\s*/?>\s*[,}]',
)
LAZY_RE = re.compile(
    r'(?:const|let|var)\s+(?P<name>\w+)\s*=\s*lazy\s*\(\s*\(\s*\)\s*=>\s*'
    r'import\s*\(\s*["\'](?P<module>[^"\']+)["\']\s*\)',
)
SYNC_IMPORT_RE = re.compile(
    r'import\s+(?P<name>\w+)\s+from\s+["\'](?P<module>[^"\']+)["\']',
)


def _scan(root: Path) -> list[dict]:
    """Read frontend/src/router.tsx; cross-reference route entries to imports."""
    router = root / "frontend" / "src" / "router.tsx"
    if not router.exists():
        return []
    try:
        text = router.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    lazy_modules = {m.group("name"): m.group("module") for m in LAZY_RE.finditer(text)}
    sync_modules = {m.group("name"): m.group("module") for m in SYNC_IMPORT_RE.finditer(text)}
    out: list[dict] = []
    for m in ROUTE_ENTRY_RE.finditer(text):
        elem = m.group("element")
        if elem in lazy_modules:
            module = lazy_modules[elem]
            lazy_flag = True
        elif elem in sync_modules:
            module = sync_modules[elem]
            lazy_flag = False
        else:
            module = elem
            lazy_flag = False
        out.append({
            "path": m.group("path"),
            "page_module": module,
            "lazy_imported": lazy_flag,
        })
    out.sort(key=lambda e: e["path"])
    return out


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args(argv)
    payload = {"routes": _scan(args.root)}
    if args.print:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    out_path = write_generated("routes", payload)
    print(f"[INFO] wrote {len(payload['routes'])} routes → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
