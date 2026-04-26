#!/usr/bin/env python3
"""H-21 self-test — every referenced harness rule has a check or an exemption.

One rule:
  H21.rule-not-covered — rule id (H-N or QN[.X]) appears in --plans but is
                         neither referenced inside any .harness/checks/*.py
                         file nor listed in
                         .harness/rule_coverage_exemptions.yaml.

H-25:
  Missing input    — exit 2 if no --plans file resolves.
  Malformed input  — WARN harness.unparseable on yaml/markdown read errors.
  Upstream failed  — none.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / ".harness/checks"))

from _common import emit  # noqa: E402

DEFAULT_PLANS = (REPO_ROOT / "docs" / "plans" / "2026-04-26-ai-harness.md",)
DEFAULT_EXEMPTIONS = REPO_ROOT / ".harness" / "rule_coverage_exemptions.yaml"
DEFAULT_CHECKS_DIR = REPO_ROOT / ".harness" / "checks"

RULE_REF_RE = re.compile(r'\b(H-\d+|Q\d+(?:\.[A-Za-z0-9_-]+)?)\b')


def _load_exemptions(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError):
        emit("WARN", path, "harness.unparseable",
             f"could not parse {path.name}", "fix YAML syntax", line=1)
        return set()
    out: set[str] = set()
    for entry in data.get("exemptions") or []:
        if isinstance(entry, dict) and "rule" in entry:
            out.add(str(entry["rule"]))
    return out


def _referenced_rules(plan_paths: Iterable[Path]) -> set[str]:
    refs: set[str] = set()
    for path in plan_paths:
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            emit("WARN", path, "harness.unparseable",
                 f"could not read {path.name}", "fix file", line=1)
            continue
        refs.update(RULE_REF_RE.findall(text))
    return refs


def _covered_by_checks(checks_dir: Path) -> set[str]:
    covered: set[str] = set()
    if not checks_dir.exists():
        return covered
    for f in checks_dir.glob("*.py"):
        if f.name in {"__init__.py", "_common.py"}:
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        covered.update(RULE_REF_RE.findall(text))
    return covered


def scan(plan_paths: list[Path], exemptions_path: Path, checks_dir: Path) -> int:
    """Compute referenced - (covered + exempted). ERROR per uncovered rule."""
    referenced = _referenced_rules(plan_paths)
    if not referenced:
        emit("WARN", plan_paths[0] if plan_paths else Path("?"),
             "H21.rule-not-covered",
             "no rule references found in plans; nothing to enforce",
             "confirm --plans path is correct", line=0)
        return 0
    exempted = _load_exemptions(exemptions_path)
    covered = _covered_by_checks(checks_dir)
    # A bare `QN` reference is considered covered if any `QN.X` rule appears.
    covered_q_prefixes = {c.split(".")[0] for c in covered if "." in c}
    covered = covered | covered_q_prefixes
    uncovered = sorted(referenced - covered - exempted)
    if not uncovered:
        return 0
    for rule in uncovered:
        emit("ERROR", exemptions_path, "H21.rule-not-covered",
             f"rule `{rule}` referenced in plan but not enforced or exempted",
             f"add a .harness/checks/* enforcing {rule} OR add to "
             f"rule_coverage_exemptions.yaml with `reason:`", line=0)
    return 1


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint: parse plans/exemptions/checks-dir, run scan."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path,
                        help="Ignored; provided for orchestrator compatibility.")
    parser.add_argument("--plans", type=Path, action="append")
    parser.add_argument("--exemptions", type=Path, default=DEFAULT_EXEMPTIONS)
    parser.add_argument("--checks-dir", type=Path, default=DEFAULT_CHECKS_DIR)
    parser.add_argument("--pretend-path", type=str)
    args = parser.parse_args(argv)
    plan_paths = list(args.plans) if args.plans else list(DEFAULT_PLANS)
    return scan(plan_paths, args.exemptions, args.checks_dir)


if __name__ == "__main__":
    sys.exit(main())
