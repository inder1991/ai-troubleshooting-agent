#!/usr/bin/env python3
"""Generator — frontend API endpoints.

Walks frontend/src/services/api/*.ts (skipping client.ts + index.ts +
*.test.ts) and emits, for each `apiClient<T>(...)` call, an entry with
url template, method, response type, and source file.

Output: .harness/generated/api_endpoints.json
Schema: .harness/schemas/generated/api_endpoints.schema.json

H-25:
  Missing input    — exit 0 with empty list (frontend may be absent).
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

EXPORT_RE = re.compile(
    r"export\s+const\s+(?P<name>\w+)\s*=\s*[^;]*?"
    r"apiClient<(?P<resp>[^>]+?)>\s*\(\s*"
    r"[`\"']?(?P<url>[^`\"'),]+)[`\"']?"
    r"(?:\s*,\s*\{[^}]*method\s*:\s*[`\"'](?P<method>[A-Z]+)[`\"'])?",
    re.DOTALL,
)


def _scan(root: Path) -> list[dict]:
    """Walk frontend/src/services/api/*.ts under root; return endpoint entries."""
    api_dir = root / "frontend" / "src" / "services" / "api"
    out: list[dict] = []
    if not api_dir.exists():
        return out
    for path in sorted(api_dir.glob("*.ts")):
        if path.name in {"client.ts", "index.ts"} or path.name.endswith(".test.ts"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for m in EXPORT_RE.finditer(text):
            out.append({
                "name": m.group("name"),
                "url_template": m.group("url"),
                "method": (m.group("method") or "GET").upper(),
                "response_type": m.group("resp").strip(),
                "file": str(path.relative_to(root)),
            })
    out.sort(key=lambda e: (e["file"], e["name"]))
    return out


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint: scan --root and write or print the JSON payload."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--print", action="store_true", help="Print JSON instead of writing.")
    args = parser.parse_args(argv)
    payload = {"endpoints": _scan(args.root)}
    if args.print:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    out_path = write_generated("api_endpoints", payload)
    print(f"[INFO] wrote {len(payload['endpoints'])} endpoints → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
