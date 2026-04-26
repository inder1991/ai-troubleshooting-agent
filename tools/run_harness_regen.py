#!/usr/bin/env python3
"""Orchestrate `make harness` — run every .harness/generators/*.py in
topological order, then validate every output against its schema.

Topological order: most generators are independent and run in parallel.
DEPENDENCIES dict declares cross-generator prereqs. Currently:
  extract_security_inventory → extract_backend_routes (consumes
                                .harness/generated/backend_routes.json).

H-4: generated files are auto-derived; never hand-edited.
H-25:
  Missing input    — exit 2 if .harness/generators/ missing.
  Malformed input  — emit ERROR per generator that fails (does not block others).
  Upstream failed  — surfaces the failing generator's name + its stderr.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATORS_DIR = REPO_ROOT / ".harness" / "generators"
SCHEMA_CHECK = REPO_ROOT / ".harness" / "checks" / "harness_policy_schema.py"

# Each key is a generator stem; value is the list of stems that must run first.
DEPENDENCIES: dict[str, list[str]] = {
    "extract_security_inventory": ["extract_backend_routes"],
}


def _all_generators() -> list[str]:
    """Return sorted list of generator stems (no _common, no __init__)."""
    return sorted(
        p.stem for p in GENERATORS_DIR.glob("*.py")
        if p.name not in {"__init__.py", "_common.py"}
    )


def _topological_order(generators: list[str]) -> list[str]:
    """DFS topological sort using DEPENDENCIES; preserves input ordering otherwise."""
    visited: set[str] = set()
    order: list[str] = []

    def visit(name: str) -> None:
        """Recursive DFS helper: ensure every dep is appended before `name`."""
        if name in visited:
            return
        visited.add(name)
        for dep in DEPENDENCIES.get(name, []):
            visit(dep)
        order.append(name)

    for g in generators:
        visit(g)
    return order


def _run_one(name: str) -> tuple[str, int, str]:
    """Spawn one generator; return (name, returncode, combined_output)."""
    script = GENERATORS_DIR / f"{name}.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )
    return name, result.returncode, (result.stdout or "") + (result.stderr or "")


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint: discover generators, run in topological order,
    validate outputs, return aggregate exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", action="append",
                        help="Run only the named generator(s). Repeatable.")
    parser.add_argument("--parallel", type=int, default=4,
                        help="Number of parallel workers for independents (default 4).")
    args = parser.parse_args(argv)

    if not GENERATORS_DIR.exists():
        print(f"[ERROR] {GENERATORS_DIR} missing", file=sys.stderr)
        return 2

    targets = args.only if args.only else _all_generators()
    ordered = _topological_order(targets)

    overall = 0
    # Phase 1 — independents (no declared deps) run in parallel.
    # Phase 2 — dependents run sequentially in topological order, AFTER
    # phase 1 so each dependent's prereqs have already produced fresh output.
    dependents = [n for n in ordered if DEPENDENCIES.get(n)]
    independents = [n for n in ordered if not DEPENDENCIES.get(n)]

    with concurrent.futures.ProcessPoolExecutor(max_workers=args.parallel) as pool:
        for n, rc, output in pool.map(_run_one, independents):
            print(f"[GEN] {n} → exit {rc}")
            if rc != 0:
                print(output)
                overall = rc

    for name in dependents:
        n, rc, output = _run_one(name)
        print(f"[GEN] {n} → exit {rc}")
        if rc != 0:
            print(output)
            overall = rc

    # Schema-validate every emitted JSON.
    if SCHEMA_CHECK.exists():
        rc = subprocess.run(
            [sys.executable, str(SCHEMA_CHECK)],
            cwd=REPO_ROOT,
        ).returncode
        if rc != 0:
            overall = rc

    print(f"\nHARNESS_REGEN_SUMMARY status={'PASS' if overall == 0 else 'FAIL'}")
    return overall


if __name__ == "__main__":
    sys.exit(main())
