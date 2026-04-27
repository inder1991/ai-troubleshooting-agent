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

Two modes:
  * --target <path>  per-file mode (collects directory CLAUDE.mds + cross-
                     cutting files matching applies_to).
  * (no flag)        global mode used by the SessionStart hook — emits
                     root + cross-cutting + generated, no per-file walk.

Budget management (point 1 fix): --max-bytes caps total emitted bytes
(default 32 KB ≈ 8k tokens). Emission order is priority-based so the
mandatory tier (root, policy yamls, cross-cutting *.md) always lands;
generated/* JSONs (largest, most volatile) come last, smallest-file
first. Anything dropped/truncated emits a single `[TRUNCATED] <path>`
line so the AI knows the data exists and where to find it.

H-25 (failure-first): if <target> doesn't exist, the loader still returns
root rules (allows early bootstrapping of new files); if a YAML
front-matter is malformed, the loader records the file under
`malformed_files` and continues; if .harness/generated/ is missing,
generated returns {}.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tools._common import parse_front_matter as _strip_front_matter  # noqa: E402

DEFAULT_MAX_BYTES = 32_768  # ~8k tokens at 4 bytes/token avg


_READ_ERRORS: list[Path] = []


def _read_file_safe(path: Path) -> str:
    """Read path; return empty string on OSError. Never raises.

    B20 (v1.2.1): record the failing path in `_READ_ERRORS` so
    `build_context` can surface it in the `malformed_files` channel.
    Pre-v1.2.1 a permission error or stale NFS handle silently became
    an empty file; the AI saw "no rules apply" with no signal.
    """
    try:
        return path.read_text()
    except OSError:
        _READ_ERRORS.append(path)
        return ""


def load_root() -> str:
    """Return the contents of root CLAUDE.md, or empty if missing."""
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
    """Read every .harness/generated/*.json into a dict keyed by filename stem.
    Malformed files are recorded as {"_load_error": True}."""
    out: dict[str, Any] = {}
    gen_dir = REPO_ROOT / ".harness/generated"
    if not gen_dir.is_dir():
        return out
    for path in sorted(gen_dir.glob("*.json")):
        try:
            out[path.stem] = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
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
        # B24 (v1.2.1): fnmatch.fnmatch follows OS case-sensitivity
        # (insensitive on macOS, sensitive on Linux per Python docs).
        # fnmatchcase is always case-sensitive, so consumer/CI matches
        # the same set of files regardless of platform.
        if any(fnmatch.fnmatchcase(target_str, glob) for glob in applies):
            matched.append(path)
    return matched, malformed


def collect_policies() -> list[Path]:
    """Return every .harness/*.yaml policy file (small, always relevant)."""
    harness_dir = REPO_ROOT / ".harness"
    if not harness_dir.is_dir():
        return []
    return sorted(harness_dir.glob("*.yaml"))


def build_context(target: Path | None) -> dict[str, Any]:
    """Assemble the full context block. target=None → global mode (no per-file walk)."""
    _READ_ERRORS.clear()
    root_text = load_root()
    directory_files = collect_directory_rules(target) if target else []
    generated = load_generated()
    if target:
        cross_cutting_files, malformed = collect_cross_cutting(target)
    else:
        # Global mode: include every *.md in .harness/ (excluding README) regardless of applies_to.
        harness_dir = REPO_ROOT / ".harness"
        cross_cutting_files = (
            sorted(p for p in harness_dir.glob("*.md") if p.name != "README.md")
            if harness_dir.is_dir() else []
        )
        malformed = []

    # Read everything BEFORE building the malformed list so OSError reads
    # surface alongside the front-matter parse failures (B20).
    directory_text = [_read_file_safe(p) for p in directory_files]
    cross_cutting_text = [_read_file_safe(p) for p in cross_cutting_files]

    malformed_paths = list(malformed) + list(_READ_ERRORS)

    return {
        "target": str(target) if target else "<global>",
        "root": root_text,
        "directory_rules_files": [str(p.relative_to(REPO_ROOT)) for p in directory_files],
        "directory_rules": directory_text,
        "cross_cutting_files": [str(p.relative_to(REPO_ROOT)) for p in cross_cutting_files],
        "cross_cutting": cross_cutting_text,
        "policy_yaml_files": [str(p.relative_to(REPO_ROOT)) for p in collect_policies()],
        "generated": generated,
        "malformed_files": [
            str(p.relative_to(REPO_ROOT)) if p.is_absolute() else str(p)
            for p in malformed_paths
        ],
        "precedence_order": [
            "root", "policies", "cross_cutting", "generated", "directory_rules",
        ],
    }


def _truncated_line(path: str, byte_count: int, extra: str = "") -> str:
    suffix = f" {extra}" if extra else ""
    return (
        f"[TRUNCATED] {path} ({byte_count} bytes{suffix}) — "
        f"read with: cat {path}\n"
    )


def render_text(ctx: dict[str, Any], max_bytes: int = DEFAULT_MAX_BYTES) -> str:
    """Render ctx into a budget-capped text block.

    Emission order (priority high → low):
      1. Root CLAUDE.md (mandatory; always emitted even if alone exceeds budget)
      2. Policy yamls (mandatory; small + always relevant)
      3. Cross-cutting *.md
      4. Directory rules (closest-first)
      5. Generated JSONs, smallest file first

    When budget would be exceeded by including a file, emit a [TRUNCATED]
    pointer line instead. Mandatory tiers ignore the budget; the rest stop
    at the cap. max_bytes=0 means unlimited (CI agents).
    """
    parts: list[str] = []
    used = 0

    def add(text: str) -> None:
        """Append text to the output buffer and update the running byte count."""
        nonlocal used
        parts.append(text)
        used += len(text.encode("utf-8"))

    def fits(text: str) -> bool:
        """True iff appending text would still leave us under max_bytes (or unlimited)."""
        return max_bytes == 0 or used + len(text.encode("utf-8")) <= max_bytes

    # --- Mandatory tier (always emit, ignore budget) ---
    add("# ROOT (CLAUDE.md)\n")
    add(ctx["root"])

    if ctx["policy_yaml_files"]:
        add("\n# POLICIES\n")
        for path in ctx["policy_yaml_files"]:
            try:
                text = (REPO_ROOT / path).read_text()
            except OSError:
                continue
            add(f"\n## {path}\n```yaml\n{text}\n```\n")

    # --- Should tier (cross-cutting + dir rules — emit if it fits) ---
    if ctx["cross_cutting_files"]:
        header = "\n# CROSS-CUTTING\n"
        if fits(header):
            add(header)
            for path, text in zip(ctx["cross_cutting_files"], ctx["cross_cutting"]):
                section = f"\n## {path}\n{text}"
                if fits(section):
                    add(section)
                else:
                    pointer = _truncated_line(path, len(text.encode("utf-8")))
                    if fits(pointer):
                        add(pointer)
                    break

    if ctx["directory_rules_files"]:
        header = "\n# DIRECTORY RULES (closest-first)\n"
        if fits(header):
            add(header)
            for path, text in zip(ctx["directory_rules_files"], ctx["directory_rules"]):
                section = f"\n## {path}\n{text}"
                if fits(section):
                    add(section)
                else:
                    pointer = _truncated_line(path, len(text.encode("utf-8")))
                    if fits(pointer):
                        add(pointer)
                    break

    # --- Nice tier (generated JSONs, smallest first so we fit as many as possible) ---
    if ctx["generated"]:
        sized: list[tuple[str, str, int]] = []
        for key, value in ctx["generated"].items():
            try:
                serialized = json.dumps(value, indent=2, sort_keys=True)
            except (TypeError, ValueError):
                serialized = json.dumps(value)
            sized.append((key, serialized, len(serialized.encode("utf-8"))))
        sized.sort(key=lambda t: t[2])  # smallest first

        # Always emit at least the section header + per-file pointers, even when
        # mandatory tier already blew the budget. Pointers are tiny (~120 bytes
        # each) and the AI needs them to know the data exists.
        add("\n# GENERATED FACTS\n")
        truncated_any = False
        for key, serialized, size in sized:
            section = f"\n## {key}\n```json\n{serialized}\n```\n"
            if fits(section):
                add(section)
            else:
                truncated_any = True
                add(_truncated_line(
                    f".harness/generated/{key}.json",
                    size,
                    extra=f"~{serialized.count(chr(10))} lines",
                ))
        if truncated_any and max_bytes > 0:
            add(
                f"\n[BUDGET] {used} / {max_bytes} bytes used. Use "
                "`make harness` to refresh; cat any [TRUNCATED] file directly.\n"
            )

    return "".join(parts)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint.

    Two modes:
      --target <path>          per-file mode (directory walk + applies_to filter)
      (no --target)            global mode (cross-cutting + generated only)

    --max-bytes 0  unlimited. Default ~32 KB.
    --json         emit structured JSON instead of rendered text.
    """
    parser = argparse.ArgumentParser(description="Load harness context.")
    parser.add_argument(
        "--target",
        help="Path (relative to repo root) being edited. Omit for global session-start mode.",
    )
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_BYTES,
        help=f"Cap total emitted bytes (default {DEFAULT_MAX_BYTES}; 0 = unlimited).",
    )
    parser.add_argument("--json", action="store_true", help="Emit structured JSON instead of text.")
    args = parser.parse_args(argv)

    target = Path(args.target) if args.target else None
    ctx = build_context(target)

    if args.json:
        print(json.dumps(ctx, indent=2, sort_keys=True))
    else:
        print(render_text(ctx, max_bytes=args.max_bytes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
