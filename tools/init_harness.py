#!/usr/bin/env python3
"""Bootstrap the AI harness into a target repo.

Usage:
  python3 tools/init_harness.py --target /path/to/new/repo \
                                --owner @platform-team \
                                --tech-stack python

Idempotent: re-running on an already-bootstrapped repo updates only files
that don't yet exist (use --force to overwrite without diff).

H-25:
  Missing input    — exit 2 if --target absent (argparse enforces).
  Malformed input  — exit 2 if templates dir or source .harness/ missing.
  Upstream failed  — none (no subprocess invocations).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = REPO_ROOT / "tools" / "init_harness_templates"
TOOL_FILES = (
    "load_harness.py",
    "run_validate.py",
    "run_harness_regen.py",
    "refresh_baselines.py",
    "_session_start_hook.sh",
    "install_pre_commit.sh",
    "generate_typecheck_baseline.py",
    "_common.py",
)


def _render(template: str, owner: str, tech_stack: str) -> str:
    """Substitute {{OWNER}} and {{TECH_STACK}} placeholders."""
    return (
        template
        .replace("{{OWNER}}", owner)
        .replace("{{TECH_STACK}}", tech_stack)
    )


def _copy_skeleton(src: Path, dest: Path, force: bool) -> int:
    """Copy .harness/ skeleton + tools/* + .claude/settings.json into dest.
    Returns number of files written."""
    written = 0

    # .harness/ tree (excluding any baselines that grew on the source repo;
    # downstream consumers should rebaseline against their own code).
    for source in (src / ".harness").rglob("*"):
        if not source.is_file():
            continue
        rel = source.relative_to(src)
        # Skip source-specific baselines and generated truth files.
        if "/baselines/" in str(rel) and source.name.endswith(".json"):
            continue
        if "/generated/" in str(rel) and source.name.endswith(".json"):
            continue
        out_path = dest / rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.exists() and not force:
            continue
        shutil.copy2(source, out_path)
        written += 1

    # tools/ — only the harness-relevant scripts; not project-specific tools.
    for tool in TOOL_FILES:
        source = src / "tools" / tool
        if not source.exists():
            continue
        out_path = dest / "tools" / tool
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.exists() and not force:
            continue
        shutil.copy2(source, out_path)
        written += 1

    # .claude/settings.json — ships the SessionStart hook.
    claude_settings_src = src / ".claude" / "settings.json"
    if claude_settings_src.exists():
        out_path = dest / ".claude" / "settings.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if not out_path.exists() or force:
            shutil.copy2(claude_settings_src, out_path)
            written += 1

    return written


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True,
                        help="Destination repo root.")
    parser.add_argument("--owner", type=str, required=True,
                        help="Top-level CLAUDE.md `owner:` field (e.g. @platform-team).")
    parser.add_argument("--tech-stack", choices=["python", "typescript", "polyglot"],
                        default="polyglot")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing files; default is idempotent (skip if exists).")
    args = parser.parse_args(argv)

    if not TEMPLATES_DIR.exists():
        print(f"[ERROR] templates dir missing: {TEMPLATES_DIR}", file=sys.stderr)
        return 2
    if not (REPO_ROOT / ".harness").exists():
        print(f"[ERROR] source .harness/ missing at {REPO_ROOT}", file=sys.stderr)
        return 2

    args.target.mkdir(parents=True, exist_ok=True)

    # CLAUDE.md (with template substitution)
    claude_template = (TEMPLATES_DIR / "CLAUDE.md.tmpl").read_text(encoding="utf-8")
    claude_out = args.target / "CLAUDE.md"
    if not claude_out.exists() or args.force:
        claude_out.write_text(_render(claude_template, args.owner, args.tech_stack), encoding="utf-8")

    # Makefile (no substitution)
    makefile_template = (TEMPLATES_DIR / "Makefile.tmpl").read_text(encoding="utf-8")
    makefile_out = args.target / "Makefile"
    if not makefile_out.exists() or args.force:
        makefile_out.write_text(makefile_template, encoding="utf-8")

    # AGENTS.md alias (verbatim copy of CLAUDE.md so multi-agent tooling sees the same rules)
    agents_md = args.target / "AGENTS.md"
    if not agents_md.exists() or args.force:
        agents_md.write_text(claude_out.read_text(encoding="utf-8"), encoding="utf-8")

    # .cursorrules pointer
    cursor_rules = args.target / ".cursorrules"
    if not cursor_rules.exists() or args.force:
        cursor_rules.write_text("see CLAUDE.md and CLAUDE.md in subdirectories\n", encoding="utf-8")

    written = _copy_skeleton(REPO_ROOT, args.target, args.force)

    print(f"[INFO] bootstrap complete: {written} skeleton files + 4 root templates")
    print("Next steps:")
    print(f"  1. cd {args.target}")
    print("  2. make harness-install   # install pre-commit hook")
    print("  3. make harness           # regenerate .harness/generated/*.json")
    print("  4. make validate-fast     # smoke-test the harness")
    return 0


if __name__ == "__main__":
    sys.exit(main())
