#!/usr/bin/env python3
"""Generator — Python + npm dependency inventory.

Reads backend/pyproject.toml [project.dependencies] and frontend/
package.json (dependencies + devDependencies). Cross-references each
with .harness/dependencies.yaml allow/deny lists.

Output: .harness/generated/dependency_inventory.json
Schema: .harness/schemas/generated/dependency_inventory.schema.json

H-25:
  Missing input    — exit 0 with empty lists.
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

DEP_LINE_RE = re.compile(r'^\s*"(?P<spec>[^"]+)"\s*,?\s*$')


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}


def _parse_pyproject(path: Path) -> list[tuple[str, str]]:
    """Crude: find [project] dependencies array, return (name, version) pairs."""
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    in_block = False
    out: list[tuple[str, str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("dependencies") and "[" in stripped:
            in_block = True
            continue
        if in_block:
            if "]" in stripped:
                in_block = False
                continue
            m = DEP_LINE_RE.match(line)
            if m:
                spec = m.group("spec")
                parts = re.split(r"[<>=~!\s]", spec, maxsplit=1)
                name = parts[0].strip()
                version = spec[len(name):].strip() or "*"
                out.append((name, version))
    return out


def _parse_package_json(path: Path) -> list[tuple[str, str, str]]:
    """Return (name, version, scope=runtime|dev) tuples."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    out: list[tuple[str, str, str]] = []
    for name, version in (data.get("dependencies") or {}).items():
        out.append((name, str(version), "runtime"))
    for name, version in (data.get("devDependencies") or {}).items():
        out.append((name, str(version), "dev"))
    return out


def _scan(root: Path) -> dict:
    """Build {python: [...], npm: [...]} with allow/spine/blacklist flags."""
    policy = _load_yaml(root / ".harness" / "dependencies.yaml")
    py_spine = set(policy.get("whitelist", {}).get("backend_spine") or [])
    npm_spine = set(policy.get("whitelist", {}).get("frontend_spine") or [])
    blacklist = set(policy.get("blacklist", {}).get("global") or [])

    python_out: list[dict] = []
    for name, version in _parse_pyproject(root / "backend" / "pyproject.toml"):
        python_out.append({
            "name": name,
            "version": version,
            "allowed": name not in blacklist,
            "on_spine": name in py_spine,
        })
    python_out.sort(key=lambda e: e["name"])

    npm_out: list[dict] = []
    for name, version, scope in _parse_package_json(root / "frontend" / "package.json"):
        npm_out.append({
            "name": name,
            "version": version,
            "scope": scope,
            "allowed": name not in blacklist,
            "on_spine": name in npm_spine,
        })
    npm_out.sort(key=lambda e: (e["name"], e["scope"]))

    return {"python": python_out, "npm": npm_out}


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
    out_path = write_generated("dependency_inventory", payload)
    print(f"[INFO] wrote {len(payload['python'])} python + {len(payload['npm'])} npm → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
