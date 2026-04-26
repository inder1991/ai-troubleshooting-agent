"""Shared test helpers for harness checks.

Re-export common patterns so individual check tests stay short:
  assert_check_fires(check_name, target, expected_rule, ...) — runs the
    check and asserts it emits >= 1 ERROR matching that rule id.
  assert_check_silent(check_name, target, ...) — runs the check and
    asserts it produces zero output and exits 0.

Both helpers accept:
  * check_name: filename stem under .harness/checks/ (without .py)
  * target: path to a fixture file or dir
  * expected_rule: substring required in the rule= field of an emitted
                   line (assert_check_fires only)
  * pretend_path: forwarded as `--pretend-path <virtual-path>` (some
                  checks scope rules by virtual path, distinct from
                  the on-disk fixture location)
  * extra_args: list of extra argv tokens forwarded to the check
                subprocess (e.g., ["--policy", str(policy_path)])

Backward-compat: positional (rule_id, fixture) call shape from H.0a is
still supported by alias.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKS_DIR = REPO_ROOT / ".harness/checks"


def _run_check(
    check_name: str,
    target: Path,
    *,
    pretend_path: str | None = None,
    extra_args: list[str] | None = None,
) -> tuple[int, str]:
    script = CHECKS_DIR / f"{check_name}.py"
    if not script.exists():
        raise FileNotFoundError(f"no check at {script}")
    argv: list[str] = [sys.executable, str(script), "--target", str(target)]
    if pretend_path is not None:
        argv += ["--pretend-path", pretend_path]
    if extra_args:
        argv += list(extra_args)
    result = subprocess.run(argv, cwd=REPO_ROOT, capture_output=True, text=True)
    return result.returncode, result.stdout


def assert_check_fires(
    check_name: str | None = None,
    target: Path | None = None,
    *,
    expected_rule: str | None = None,
    pretend_path: str | None = None,
    extra_args: list[str] | None = None,
    # Positional aliases for H.0a-style calls: assert_check_fires(rule_id, fixture)
    rule_id: str | None = None,
    fixture: Path | None = None,
) -> None:
    """Assert the check exits non-zero and emits >= 1 [ERROR] line.

    If `expected_rule` is given, the rule= field in some [ERROR] line
    must contain that exact rule id substring.
    """
    name = check_name if check_name is not None else rule_id
    tgt = target if target is not None else fixture
    if name is None or tgt is None:
        raise TypeError("assert_check_fires requires check_name + target (or rule_id + fixture)")
    expected = expected_rule if expected_rule is not None else name

    code, out = _run_check(name, tgt, pretend_path=pretend_path, extra_args=extra_args)
    assert code != 0, (
        f"check `{name}` should have failed on {tgt} but exited 0. "
        f"Output: {out}"
    )
    assert "[ERROR]" in out, (
        f"check `{name}` should emit at least one [ERROR] line: {out}"
    )
    assert f"rule={expected}" in out, (
        f"check `{name}` fired but didn't tag any [ERROR] with rule={expected}: {out}"
    )
    assert "suggestion=" in out, (
        f"check `{name}` violations must include `suggestion=` field (H-23). Got: {out}"
    )


def assert_check_silent(
    check_name: str | None = None,
    target: Path | None = None,
    *,
    pretend_path: str | None = None,
    extra_args: list[str] | None = None,
    rule_id: str | None = None,
    fixture: Path | None = None,
) -> None:
    """Assert the check exits 0 and emits no ERROR lines.

    Allows WARN/INFO output (some checks emit informational notes on
    compliant fixtures) but no ERROR.
    """
    name = check_name if check_name is not None else rule_id
    tgt = target if target is not None else fixture
    if name is None or tgt is None:
        raise TypeError("assert_check_silent requires check_name + target (or rule_id + fixture)")
    code, out = _run_check(name, tgt, pretend_path=pretend_path, extra_args=extra_args)
    assert code == 0, (
        f"check `{name}` should pass on {tgt} but exited {code}. Output: {out}"
    )
    assert "[ERROR]" not in out, (
        f"check `{name}` produced [ERROR] output on a compliant fixture: {out}"
    )
