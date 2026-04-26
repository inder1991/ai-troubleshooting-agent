#!/usr/bin/env python3
"""Deterministic harness rule loader.

Consumed by:
  * Claude Code session-start hook (Sprint H.2)
  * autonomous CI agents (Consumer 2)
  * tools/run_validate.py for cross-checks

Per H-11, the loading algorithm is:

  1. Load root CLAUDE.md.
  2. Walk up <target>'s directory tree, collect every CLAUDE.md.
  3. Load all .harness/generated/*.json.
  4. Match .harness/*.md whose `applies_to` glob matches <target>.
  5. Concatenate in precedence order and return.

H-25 (failure-first): if <target> doesn't exist, the loader still
returns root rules (allows early bootstrapping of new files); if a YAML
front-matter is malformed, the loader records the file under
`malformed_files` and continues; if .harness/generated/ is missing,
generated returns {}.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read_file_safe(path: Path) -> str:
    try:
        return path.read_text()
    except OSError:
        return ""


def _strip_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """Return (parsed_front_matter, body). Empty dict on absence/malformed."""
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not match:
        return {}, text
    fm_text, body = match.group(1), match.group(2)
    # Light, dependency-free YAML parsing for the limited subset we use:
    # `key: value` lines, list values via `applies_to:` followed by `- ...`.
    fm: dict[str, Any] = {}
    current_list_key: str | None = None
    for raw in fm_text.splitlines():
        line = raw.rstrip()
        if not line or line.startswith("#"):
            continue
        list_item = re.match(r"^\s+-\s+(.+)$", line)
        if list_item and current_list_key is not None:
            fm.setdefault(current_list_key, []).append(list_item.group(1).strip())
            continue
        kv = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if not kv:
            current_list_key = None
            continue
        key, value = kv.group(1), kv.group(2).strip()
        if value == "":
            current_list_key = key
            fm[key] = []
        else:
            current_list_key = None
            fm[key] = value.strip('"').strip("'")
    return fm, body


def load_root() -> str:
    return _read_file_safe(REPO_ROOT / "CLAUDE.md")


def collect_directory_rules(target: Path) -> list[Path]:
    """Walk up from target's parent directory to repo root, collecting CLAUDE.md."""
    found: list[Path] = []
    current = (REPO_ROOT / target).resolve().parent
    repo_resolved = REPO_ROOT.resolve()
    while True:
        candidate = current / "CLAUDE.md"
        if candidate.is_file() and candidate.resolve() != (REPO_ROOT / "CLAUDE.md").resolve():
            found.append(candidate)
        if current == repo_resolved:
            break
        if repo_resolved not in current.parents:
            break
        current = current.parent
    # Order: closest-to-target first → root-adjacent last
    return found


def load_generated() -> dict[str, Any]:
    out: dict[str, Any] = {}
    gen_dir = REPO_ROOT / ".harness/generated"
    if not gen_dir.is_dir():
        return out
    for path in sorted(gen_dir.glob("*.json")):
        try:
            out[path.stem] = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            # H-25: malformed generated files don't crash the loader.
            out[path.stem] = {"_load_error": True}
    return out


def collect_cross_cutting(target: Path) -> tuple[list[Path], list[Path]]:
    """Match .harness/*.md whose `applies_to` glob covers `target`.

    Returns (matched_files, malformed_files).
    """
    matched: list[Path] = []
    malformed: list[Path] = []
    harness_dir = REPO_ROOT / ".harness"
    if not harness_dir.is_dir():
        return matched, malformed
    for path in sorted(harness_dir.glob("*.md")):
        # Skip our own README.
        if path.name == "README.md":
            continue
        text = _read_file_safe(path)
        fm, _ = _strip_front_matter(text)
        if not fm:
            malformed.append(path)
            continue
        applies = fm.get("applies_to", [])
        if isinstance(applies, str):
            applies = [applies]
        target_str = str(target).replace("\\", "/")
        if any(fnmatch.fnmatch(target_str, glob) for glob in applies):
            matched.append(path)
    return matched, malformed


def build_context(target: Path) -> dict[str, Any]:
    root_text = load_root()
    directory_files = collect_directory_rules(target)
    generated = load_generated()
    cross_cutting_files, malformed = collect_cross_cutting(target)

    return {
        "target": str(target),
        "root": root_text,
        "directory_rules_files": [str(p.relative_to(REPO_ROOT)) for p in directory_files],
        "directory_rules": [_read_file_safe(p) for p in directory_files],
        "cross_cutting_files": [str(p.relative_to(REPO_ROOT)) for p in cross_cutting_files],
        "cross_cutting": [_read_file_safe(p) for p in cross_cutting_files],
        "generated": generated,
        "malformed_files": [str(p.relative_to(REPO_ROOT)) for p in malformed],
        "precedence_order": [
            "root", "cross_cutting", "generated", "directory_rules",
        ],
    }


def render_text(ctx: dict[str, Any]) -> str:
    """Human-readable concatenated context block."""
    parts: list[str] = []
    parts.append("# ROOT (CLAUDE.md)\n")
    parts.append(ctx["root"])

    if ctx["cross_cutting_files"]:
        parts.append("\n# CROSS-CUTTING\n")
        for path, text in zip(ctx["cross_cutting_files"], ctx["cross_cutting"]):
            parts.append(f"\n## {path}\n")
            parts.append(text)

    if ctx["generated"]:
        parts.append("\n# GENERATED FACTS\n")
        for key, value in sorted(ctx["generated"].items()):
            parts.append(f"\n## {key}\n```json\n{json.dumps(value, indent=2, sort_keys=True)}\n```\n")

    if ctx["directory_rules_files"]:
        parts.append("\n# DIRECTORY RULES (closest-first)\n")
        for path, text in zip(ctx["directory_rules_files"], ctx["directory_rules"]):
            parts.append(f"\n## {path}\n")
            parts.append(text)

    return "".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load harness context for a target file.")
    parser.add_argument("--target", required=True, help="Path (relative to repo root) being edited.")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON instead of text.")
    args = parser.parse_args(argv)

    target = Path(args.target)
    ctx = build_context(target)

    if args.json:
        print(json.dumps(ctx, indent=2, sort_keys=True))
    else:
        print(render_text(ctx))
    return 0


if __name__ == "__main__":
    sys.exit(main())
