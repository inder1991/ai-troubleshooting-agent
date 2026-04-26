#!/usr/bin/env python3
"""Generator — conventions inventory (ruff + eslint + commitlint).

Reads backend/pyproject.toml [tool.ruff] (line_length, select, ignore lists),
frontend/eslint.config.js (regex-find plugins + active rule count), and
commitlint.config.{js,cjs} (extends preset). Emits a consolidated view.

Output: .harness/generated/conventions_inventory.json
Schema: .harness/schemas/generated/conventions_inventory.schema.json

H-25:
  Missing input    — emit empty defaults.
  Malformed input  — exit 0 with empty defaults.
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

RUFF_LINE_LEN_RE = re.compile(r'line-length\s*=\s*(\d+)')
RUFF_SELECT_RE = re.compile(r'select\s*=\s*\[([^\]]*)\]', re.DOTALL)
RUFF_IGNORE_RE = re.compile(r'ignore\s*=\s*\[([^\]]*)\]', re.DOTALL)
RUFF_TOKEN_RE = re.compile(r'"([^"]+)"')
ESLINT_PLUGIN_RE = re.compile(r'["\']([^"\']*plugin[^"\']*)["\']')
ESLINT_RULE_RE = re.compile(r'"[\w@/-]+"\s*:\s*\[?\s*"(?:error|warn|off)"')
COMMITLINT_EXTENDS_RE = re.compile(r'extends\s*:\s*\[([^\]]*)\]')
COMMITLINT_TOKEN_RE = re.compile(r'["\']([^"\']+)["\']')


def _scan_ruff(root: Path) -> dict:
    pyproject = root / "backend" / "pyproject.toml"
    if not pyproject.exists():
        return {"select": [], "ignore": [], "line_length": None}
    try:
        text = pyproject.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {"select": [], "ignore": [], "line_length": None}
    line_len_match = RUFF_LINE_LEN_RE.search(text)
    line_length = int(line_len_match.group(1)) if line_len_match else None
    select_match = RUFF_SELECT_RE.search(text)
    select = sorted(set(RUFF_TOKEN_RE.findall(select_match.group(1)))) if select_match else []
    ignore_match = RUFF_IGNORE_RE.search(text)
    ignore = sorted(set(RUFF_TOKEN_RE.findall(ignore_match.group(1)))) if ignore_match else []
    return {"select": select, "ignore": ignore, "line_length": line_length}


def _scan_eslint(root: Path) -> dict:
    cfg = root / "frontend" / "eslint.config.js"
    if not cfg.exists():
        return {"plugins": [], "rule_count": 0}
    try:
        text = cfg.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {"plugins": [], "rule_count": 0}
    plugins = sorted(set(ESLINT_PLUGIN_RE.findall(text)))
    rule_count = len(ESLINT_RULE_RE.findall(text))
    return {"plugins": plugins, "rule_count": rule_count}


def _scan_commitlint(root: Path) -> dict:
    for name in ("commitlint.config.js", "commitlint.config.cjs", "commitlint.config.mjs", ".commitlintrc.js"):
        cfg = root / name
        if cfg.exists():
            try:
                text = cfg.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            m = COMMITLINT_EXTENDS_RE.search(text)
            if m:
                extends = sorted(set(COMMITLINT_TOKEN_RE.findall(m.group(1))))
                return {"extends": extends, "config_file": name}
            return {"extends": [], "config_file": name}
    return {"extends": [], "config_file": None}


def _scan(root: Path) -> dict:
    return {
        "ruff": _scan_ruff(root),
        "eslint": _scan_eslint(root),
        "commitlint": _scan_commitlint(root),
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
    out_path = write_generated("conventions_inventory", payload)
    print(f"[INFO] wrote conventions_inventory → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
