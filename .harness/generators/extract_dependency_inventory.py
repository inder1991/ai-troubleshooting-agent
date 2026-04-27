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
    """Parse pyproject.toml [project.dependencies] using tomllib (3.11+ stdlib).

    Handles multi-line specs, comments, and PEP 631 syntax correctly — the
    previous regex-based parser failed silently on any of those.
    """
    if not path.exists():
        return []
    try:
        import tomllib  # Python 3.11+
    except ImportError:  # pragma: no cover - older Python
        return []
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return []
    deps = (data.get("project") or {}).get("dependencies") or []
    out: list[tuple[str, str]] = []
    for spec in deps:
        if not isinstance(spec, str):
            continue
        spec = spec.strip()
        if not spec:
            continue
        # Split "<name>[extras]<op><version>" — find the first version
        # operator or whitespace after the (optional) extras suffix.
        parts = re.split(r"(?=[<>=~!\s;])", spec, maxsplit=1)
        name_with_extras = parts[0].strip()
        # Strip extras: "fastapi[all]" → "fastapi".
        name = name_with_extras.split("[", 1)[0].strip()
        version = (parts[1].strip() if len(parts) > 1 else "") or "*"
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
