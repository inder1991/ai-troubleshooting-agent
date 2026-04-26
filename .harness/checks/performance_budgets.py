#!/usr/bin/env python3
"""Q12 — performance budgets.

Three primary rules (bundle rules covered by direct stats.json scan
when present; deferred to H.2 generators):
  Q12.agent-cost-hint-required    — agent contract YAML missing cost_hint.* fields.
  Q12.agent-budget-exceeded       — cost_hint value above policy cap.
  Q12.gateway-needs-timed-query   — StorageGateway method without @timed_query.

H-25:
  Missing input    — exit 2.
  Malformed input  — WARN harness.unparseable.
  Upstream failed  — none.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / ".harness/checks"))

from _common import emit, load_baseline  # noqa: E402

DEFAULT_BUDGETS = REPO_ROOT / ".harness" / "performance_budgets.yaml"
COST_HINT_FIELDS = ("tool_calls_max", "tokens_max", "wall_clock_max_ms")
BASELINE = load_baseline("performance_budgets")


def _emit(file: Path, rule: str, msg: str, suggestion: str, line: int = 1) -> bool:
    sig = (str(file), int(line), rule)
    if sig in BASELINE:
        return False
    emit("ERROR", file, rule, msg, suggestion, line=line)
    return True


def _load_budgets(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    # Tolerate the live .harness/performance_budgets.yaml shape
    # (hard.agent_budgets.default + hard.database.single_query_max_ms +
    # hard.frontend_bundle.*) in addition to the fixture-style flat shape.
    if "hard" in data and "agent_budgets" not in data:
        hard = data.get("hard", {})
        agent = (hard.get("agent_budgets") or {}).get("default", {})
        return {
            "agent_budgets": {
                "tool_calls_max": agent.get("tool_calls_max"),
                "tokens_max": agent.get("tokens_max"),
                "wall_clock_max_ms": (agent.get("wall_clock_max_s") or 0) * 1000 or agent.get("wall_clock_max_ms"),
            },
            "db_query_max_ms": hard.get("database", {}).get("single_query_max_ms"),
            "bundle_kb": {
                "initial": hard.get("frontend_bundle", {}).get("initial_js_kb_gzipped"),
                "route": hard.get("frontend_bundle", {}).get("per_route_chunk_kb_gzipped"),
                "css": hard.get("frontend_bundle", {}).get("total_css_kb_gzipped"),
            },
        }
    return data


def _scan_agent_yaml(path: Path, budgets: dict) -> int:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError) as exc:
        emit("WARN", path, "harness.unparseable",
             f"could not parse {path.name}: {exc}", "fix YAML syntax", line=1)
        return 0
    if not isinstance(data, dict):
        return 0
    cost_hint = data.get("cost_hint")
    errors = 0
    if not isinstance(cost_hint, dict):
        if _emit(path, "Q12.agent-cost-hint-required",
                 f"agent contract {path.name} missing cost_hint section",
                 "add `cost_hint: { tool_calls_max, tokens_max, wall_clock_max_ms }`"):
            errors += 1
        return errors
    caps = budgets.get("agent_budgets") or {}
    for field in COST_HINT_FIELDS:
        if field not in cost_hint:
            if _emit(path, "Q12.agent-cost-hint-required",
                     f"cost_hint missing `{field}`",
                     f"add cost_hint.{field}"):
                errors += 1
            continue
        cap = caps.get(field)
        if cap is not None and isinstance(cost_hint[field], (int, float)) and cost_hint[field] > cap:
            if _emit(path, "Q12.agent-budget-exceeded",
                     f"cost_hint.{field}={cost_hint[field]} exceeds cap {cap}",
                     f"reduce {field} to <= {cap} or raise cap with ADR"):
                errors += 1
    return errors


def _scan_gateway_python(path: Path) -> int:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return 0
    errors = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "StorageGateway":
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if sub.name.startswith("_"):
                        continue
                    if not _has_timed_query(sub):
                        if _emit(path, "Q12.gateway-needs-timed-query",
                                 f"StorageGateway.{sub.name} missing @timed_query",
                                 'add @timed_query("<method-name>") to time the call',
                                 sub.lineno):
                            errors += 1
    return errors


def _has_timed_query(fn) -> bool:
    for dec in fn.decorator_list:
        src = ast.dump(dec)
        if "timed_query" in src:
            return True
    return False


def scan(targets: list[Path], budgets_path: Path, pretend_path: str | None) -> int:
    if not budgets_path.exists():
        emit("ERROR", budgets_path, "harness.target-missing",
             f"budgets file does not exist: {budgets_path}",
             "seed .harness/performance_budgets.yaml (Sprint H.0b Story 5)", line=0)
        return 2
    budgets = _load_budgets(budgets_path)
    total_errors = 0
    for target in targets:
        if not target.exists():
            # default targets may legitimately not exist (no contracts dir yet)
            continue
        files: list[Path]
        if target.is_file():
            files = [target]
        else:
            files = []
            for p in target.rglob("*"):
                if not p.is_file():
                    continue
                if any(tok in str(p) for tok in (
                    "__pycache__", ".venv", "/venv/", "node_modules",
                    "site-packages", ".git", "tests/harness/fixtures",
                )):
                    continue
                if p.suffix in {".yaml", ".yml", ".py"}:
                    files.append(p)
        for path in files:
            virtual = pretend_path or (
                str(path.relative_to(REPO_ROOT))
                if path.is_relative_to(REPO_ROOT) else path.name
            )
            is_agent_yaml = path.suffix in {".yaml", ".yml"} and (
                "agent" in path.name or "/contracts/" in virtual
            )
            is_gateway = path.suffix == ".py" and (
                virtual.endswith("storage/gateway.py") or path.name == "gateway.py"
            )
            if is_agent_yaml:
                total_errors += _scan_agent_yaml(path, budgets)
            elif is_gateway:
                total_errors += _scan_gateway_python(path)
    return 1 if total_errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, action="append")
    parser.add_argument("--budgets", type=Path, default=DEFAULT_BUDGETS)
    parser.add_argument("--pretend-path", type=str)
    args = parser.parse_args(argv)
    targets = list(args.target) if args.target else [
        REPO_ROOT / "backend" / "src" / "contracts",
        REPO_ROOT / "backend" / "src" / "storage" / "gateway.py",
    ]
    return scan(targets, args.budgets, args.pretend_path)


if __name__ == "__main__":
    sys.exit(main())
