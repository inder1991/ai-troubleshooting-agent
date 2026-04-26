#!/usr/bin/env python3
"""Schema-validate .harness/dependencies.yaml.

Runs in `make validate-fast` (wired by Sprint H.1a). Catches malformed
YAML or missing required keys at PR time, not at the moment a check
tries to read it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEPS_YAML = REPO_ROOT / ".harness/dependencies.yaml"

REQUIRED_TOP_LEVEL = ["version", "spine_paths", "whitelist", "blacklist", "audit"]
REQUIRED_SPINE_PATHS = ["backend", "frontend"]
REQUIRED_WHITELIST_SECTIONS = ["backend_spine", "frontend_spine"]
REQUIRED_BLACKLIST_SECTIONS = ["global"]
REQUIRED_AUDIT_KEYS = [
    "trigger_paths", "backend_command", "frontend_command", "block_on", "warn_on",
]


def _err(msg: str) -> None:
    print(f"[ERROR] file={DEPS_YAML.relative_to(REPO_ROOT)} "
          f'rule=dependencies_yaml_schema message="{msg}" '
          f'suggestion="See docs/plans/2026-04-26-ai-harness.md section 2 Q11 for the canonical shape."',
          file=sys.stderr)


def main() -> int:
    if not DEPS_YAML.exists():
        _err("dependencies.yaml missing")
        return 1
    try:
        data = yaml.safe_load(DEPS_YAML.read_text())
    except yaml.YAMLError as e:
        _err(f"invalid YAML: {e}")
        return 1

    if not isinstance(data, dict):
        _err("top-level YAML must be a mapping")
        return 1

    for key in REQUIRED_TOP_LEVEL:
        if key not in data:
            _err(f"missing top-level key: {key}")
            return 1

    if not isinstance(data["spine_paths"], dict):
        _err("spine_paths must be a mapping")
        return 1
    for key in REQUIRED_SPINE_PATHS:
        if key not in data["spine_paths"]:
            _err(f"spine_paths missing key: {key}")
            return 1

    for key in REQUIRED_WHITELIST_SECTIONS:
        if key not in data["whitelist"]:
            _err(f"whitelist missing section: {key}")
            return 1

    for key in REQUIRED_BLACKLIST_SECTIONS:
        if key not in data["blacklist"]:
            _err(f"blacklist missing section: {key}")
            return 1

    for key in REQUIRED_AUDIT_KEYS:
        if key not in data["audit"]:
            _err(f"audit missing key: {key}")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
