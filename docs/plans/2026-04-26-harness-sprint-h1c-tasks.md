# Harness Sprint H.1c — Per-Task Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship the five cross-stack policy checks for security (Q13, split into part A — secrets/outbound/dangerous patterns — and part B — auth/rate-limit/CSRF), documentation (Q15), logging (Q16), and error handling (Q17), so every cross-cutting backend rule from those four locked decisions becomes deterministically enforceable through `make validate-fast`.

**Architecture:** Same template as Sprints H.1a/H.1b — each check is a standalone Python script under `.harness/checks/<rule_id>.py` that walks the repo (or a `--target`-supplied path), emits structured findings on stdout per H-16/H-23, and exits non-zero on any `ERROR`. Scanning strategies vary by domain: `security_policy_a` blends gitleaks-CLI invocation, regex pattern banlists, and AST scans for outbound-HTTP construction; `security_policy_b` AST-scans FastAPI route decorators for auth/rate-limit/CSRF dependencies; `documentation_policy` parses Python AST to enforce contract-surface docstrings + grep-checks ADR presence; `logging_policy` AST-scans for `print`/`logger.*` correctness + structlog binding; `error_handling_policy` AST-scans for typed `Result` returns + outbound-call retry decorators + RFC 7807 problem+json shape on FastAPI handlers.

**Tech Stack:** Python 3.14, ast (stdlib), pathlib (stdlib), re (stdlib), shutil/subprocess (stdlib for gitleaks invocation), PyYAML (already a dep), pytest (already configured).

**Reference docs:**
- [Consolidated harness plan](./2026-04-26-ai-harness.md) — locked decisions Q13, Q15, Q16, Q17, plus H-16/H-23/H-24/H-25.
- [Sprint H.0a per-task plan](./2026-04-26-harness-sprint-h0a-tasks.md) — substrate (`Makefile`, loader, `run_validate.py` orchestrator, `_helpers.py`).
- [Sprint H.0b per-task plan](./2026-04-26-harness-sprint-h0b-tasks.md) — config files (`security_policy.yaml`, `documentation_policy.yaml`, `logging_policy.yaml`, `error_handling_policy.yaml`, `.gitleaks.toml`); helper modules (`backend/src/observability/{logging,tracing}.py`, `backend/src/errors/Result.py`, `backend/src/utils/http.py with_retry`, `backend/src/api/problem.py`, frontend `<ErrorBoundary>` + `errorReporter`).
- [Sprint H.1a per-task plan](./2026-04-26-harness-sprint-h1a-tasks.md) — canonical TDD red→green template + paired-fixture pattern.
- [Sprint H.1b per-task plan](./2026-04-26-harness-sprint-h1b-tasks.md) — frontend equivalents of the cross-stack rules.

**Prerequisites:** Sprints H.0a, H.0b, H.1a, H.1b complete and committed.

---

## Story map for Sprint H.1c

| Story | Title | Tasks | Pts |
|---|---|---|---|
| H.1c.1 | `security_policy_a.py` (Q13.A) — secrets + outbound HTTP + dangerous patterns | 1.1 – 1.10 | 5 |
| H.1c.2 | `security_policy_b.py` (Q13.B) — API auth + rate-limit + CSRF detection | 2.1 – 2.10 | 5 |
| H.1c.3 | `documentation_policy.py` (Q15) — contract-surface docstrings + ADR triggers + JSDoc | 3.1 – 3.10 | 5 |
| H.1c.4 | `logging_policy.py` (Q16) — structlog discipline + OTel spans + secret redaction | 4.1 – 4.12 | 8 |
| H.1c.5 | `error_handling_policy.py` (Q17) — Result returns + retry + RFC 7807 + ErrorBoundary | 5.1 – 5.12 | 8 |

**Total: 5 stories, ~31 points, 2 weeks** (capacity 26 ± buffer; tight as in H.1a/H.1b but tractable because the two heavy stories — H.1c.4, H.1c.5 — share the AST helpers introduced in H.1c.1 and H.1c.2).

---

## Story-template recap

Identical to Sprints H.1a/H.1b §"Story-template recap":

- **AC-1:** Check exists at `.harness/checks/<rule_id>.py`.
- **AC-2:** Output conforms to H-16 + H-23.
- **AC-3:** Violation fixture causes the check to emit ≥ 1 `[ERROR]` line and exit non-zero.
- **AC-4:** Compliant fixture is silent.
- **AC-5:** Wired into `make validate-fast`.
- **AC-6:** Completes on the full repo in < 2s (security_policy_a allowed up to 4s because of the gitleaks subprocess).
- **AC-7:** H-25 docstring present.

Per-story flow: fixtures → red test → red commit → implement check → green test → live-repo triage (fix or baseline) → validate-fast → green commit.

---

# Story H.1c.1 — `security_policy_a.py` (Q13.A — secrets + outbound + dangerous patterns)

**Rule families enforced (5):**
1. `gitleaks` subprocess on staged + working tree MUST exit 0. Findings re-emitted in our format with `rule=Q13.secret-detected`. (Skipped with WARN if gitleaks binary missing — H-25 upstream.)
2. Banned dangerous patterns anywhere on backend/frontend spine (text scan, line-aware): `eval(`, `exec(`, `os.system(`, `shell=True`, `pickle.loads(`, `yaml.load(` (without `Loader=`), `__import__(` (with non-literal arg), JS-side `dangerouslySetInnerHTML=`, `new Function(`, `document.write(`.
3. Outbound HTTP constructions outside `backend/src/utils/http.py` flagged: `httpx.AsyncClient(verify=False)`, `requests.get(verify=False)`, `ssl._create_unverified_context()`, `urllib3.disable_warnings(`, `httpx.AsyncClient(timeout=None)` — TLS-must-verify + timeout-required policy.
4. Logger calls passing what looks like a secret (string token containing `password=`, `api_key=`, `token=`, `secret=`, `Authorization: Bearer `) without `redact_` helper → ERROR. (Complements Q16's redaction processor — but caught at write time.)
5. Hardcoded secret-shaped string literals anywhere outside `tests/`: matches `[A-Za-z0-9+/]{32,}={0,2}` or `sk-[A-Za-z0-9]{20,}` or `xox[baprs]-[A-Za-z0-9-]{10,}` → WARN (not ERROR; many false positives — gitleaks in rule 1 is the hard gate). Heuristic only.

**Files:**
- Create: `.harness/checks/security_policy_a.py`
- Create: `tests/harness/fixtures/security_policy_a/violation/has_eval.py`
- Create: `tests/harness/fixtures/security_policy_a/violation/has_shell_true.py`
- Create: `tests/harness/fixtures/security_policy_a/violation/yaml_load_unsafe.py`
- Create: `tests/harness/fixtures/security_policy_a/violation/dangerously_set_inner_html.tsx`
- Create: `tests/harness/fixtures/security_policy_a/violation/verify_false_httpx.py`
- Create: `tests/harness/fixtures/security_policy_a/violation/timeout_none_httpx.py`
- Create: `tests/harness/fixtures/security_policy_a/violation/logger_leaks_secret.py`
- Create: `tests/harness/fixtures/security_policy_a/compliant/safe_shell.py`
- Create: `tests/harness/fixtures/security_policy_a/compliant/yaml_safe_load.py`
- Create: `tests/harness/fixtures/security_policy_a/compliant/inner_text.tsx`
- Create: `tests/harness/fixtures/security_policy_a/compliant/redacted_logger.py`
- Create: `tests/harness/checks/test_security_policy_a.py`

### Task 1.1: Create violation fixtures

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
mkdir -p tests/harness/fixtures/security_policy_a/{violation,compliant}
```

`violation/has_eval.py`:

```python
"""Q13 violation — eval() banned."""
def run(expr: str) -> object:
    return eval(expr)
```

`violation/has_shell_true.py`:

```python
"""Q13 violation — subprocess.run with shell=True banned."""
import subprocess

def run(cmd: str) -> int:
    return subprocess.run(cmd, shell=True).returncode
```

`violation/yaml_load_unsafe.py`:

```python
"""Q13 violation — yaml.load without Loader= permits arbitrary code execution."""
import yaml

def parse(text: str) -> object:
    return yaml.load(text)
```

`violation/dangerously_set_inner_html.tsx`:

```tsx
/* Q13 violation — dangerouslySetInnerHTML banned (XSS vector). */
export const Foo = ({ html }: { html: string }) => (
  <div dangerouslySetInnerHTML={{ __html: html }} />
);
```

`violation/verify_false_httpx.py`:

```python
"""Q13 violation — httpx.AsyncClient(verify=False) disables TLS validation."""
import httpx

async def fetch() -> None:
    async with httpx.AsyncClient(verify=False) as client:
        await client.get("https://example.com")
```

`violation/timeout_none_httpx.py`:

```python
"""Q13 violation — timeout=None on outbound httpx call (unbounded wait)."""
import httpx

async def fetch() -> None:
    async with httpx.AsyncClient(timeout=None) as client:
        await client.get("https://example.com")
```

`violation/logger_leaks_secret.py`:

```python
"""Q13 violation — logger sees a Bearer token without redaction.

Pretend-path: backend/src/services/auth.py
"""
import structlog

log = structlog.get_logger()

def authorize(header: str) -> None:
    log.info("incoming_request", auth=f"Authorization: Bearer {header}")
```

### Task 1.2: Create compliant fixtures

`compliant/safe_shell.py`:

```python
"""Q13 compliant — subprocess.run with list args, no shell=True."""
import subprocess

def run(cmd: list[str]) -> int:
    return subprocess.run(cmd).returncode
```

`compliant/yaml_safe_load.py`:

```python
"""Q13 compliant — yaml.safe_load (or yaml.load with explicit safe Loader)."""
import yaml

def parse(text: str) -> object:
    return yaml.safe_load(text)
```

`compliant/inner_text.tsx`:

```tsx
/* Q13 compliant — render text content, never raw HTML. */
export const Foo = ({ text }: { text: string }) => <div>{text}</div>;
```

`compliant/redacted_logger.py`:

```python
"""Q13 compliant — sensitive value passed through redact_ helper.

Pretend-path: backend/src/services/auth.py
"""
import structlog

log = structlog.get_logger()


def redact_token(value: str) -> str:
    return value[:4] + "..."  # implementation lives in observability/logging.py


def authorize(header: str) -> None:
    log.info("incoming_request", auth=redact_token(header))
```

### Task 1.3: Write the failing test

Create `tests/harness/checks/test_security_policy_a.py`:

```python
"""H.1c.1 — security_policy_a check tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness._helpers import assert_check_fires, assert_check_silent

CHECK = "security_policy_a"
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / CHECK


@pytest.mark.parametrize(
    "fixture_name,expected_rule,pretend_path",
    [
        ("has_eval.py", "Q13.dangerous-pattern", "backend/src/services/x.py"),
        ("has_shell_true.py", "Q13.dangerous-pattern", "backend/src/services/x.py"),
        ("yaml_load_unsafe.py", "Q13.dangerous-pattern", "backend/src/services/x.py"),
        ("dangerously_set_inner_html.tsx", "Q13.dangerous-pattern", "frontend/src/components/Foo.tsx"),
        ("verify_false_httpx.py", "Q13.tls-verify-required", "backend/src/services/fetch.py"),
        ("timeout_none_httpx.py", "Q13.outbound-timeout-required", "backend/src/services/fetch.py"),
        ("logger_leaks_secret.py", "Q13.log-secret-leak", "backend/src/services/auth.py"),
    ],
)
def test_violation_fires(fixture_name: str, expected_rule: str, pretend_path: str) -> None:
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / fixture_name,
        expected_rule=expected_rule,
        pretend_path=pretend_path,
    )


@pytest.mark.parametrize(
    "fixture_name,pretend_path",
    [
        ("safe_shell.py", "backend/src/services/x.py"),
        ("yaml_safe_load.py", "backend/src/services/x.py"),
        ("inner_text.tsx", "frontend/src/components/Foo.tsx"),
        ("redacted_logger.py", "backend/src/services/auth.py"),
    ],
)
def test_compliant_silent(fixture_name: str, pretend_path: str) -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / fixture_name,
        pretend_path=pretend_path,
    )
```

### Task 1.4: Run failing test + commit red

```bash
python -m pytest tests/harness/checks/test_security_policy_a.py -v
git add tests/harness/fixtures/security_policy_a tests/harness/checks/test_security_policy_a.py
git commit -m "$(cat <<'EOF'
test(red): H.1c.1 — security_policy_a fixtures + assertions

Seven violation fixtures (eval/shell=True/yaml.load/dangerouslySetInnerHTML
/verify=False httpx/timeout=None httpx/logger leaking Bearer token) plus
four compliant counterparts.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 1.5: Implement the check

Create `.harness/checks/security_policy_a.py`:

```python
#!/usr/bin/env python3
"""Q13.A — security policy: secrets + outbound HTTP + dangerous patterns.

Five rules:
  Q13.secret-detected           — gitleaks CLI fired on staged/working tree
                                   (re-emitted as our finding shape).
  Q13.dangerous-pattern         — eval/exec/os.system/shell=True/pickle.loads/
                                   yaml.load (no Loader)/__import__ + JS-side
                                   dangerouslySetInnerHTML/new Function/document.write.
  Q13.tls-verify-required       — verify=False on httpx/requests OR
                                   ssl._create_unverified_context OR urllib3.disable_warnings.
  Q13.outbound-timeout-required — httpx.AsyncClient(timeout=None) outside
                                   backend/src/utils/http.py.
  Q13.log-secret-leak           — logger call sees a value containing
                                   `Authorization: Bearer …` / `password=` etc.
                                   without going through a redact_* helper.
  Q13.secret-shaped-literal     — base64/secret-shaped string literal outside tests/ (WARN).

H-25:
  Missing input    — exit 2; rule=harness.target-missing.
  Malformed input  — WARN rule=harness.unparseable; skip file.
  Upstream failed  — gitleaks binary missing → WARN
                     rule=Q13.secret-detected (degraded mode).
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from .harness.checks._common import Finding, Severity, emit, walk_python_files  # noqa: E402

DEFAULT_ROOTS = (REPO_ROOT / "backend" / "src", REPO_ROOT / "frontend" / "src")
EXCLUDE_VIRTUAL_PREFIXES = (
    "tests/harness/fixtures/",
    "frontend/dist/",
    "frontend/node_modules/",
    "backend/.venv/",
)
SCANNED_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx"}

DANGEROUS_PYTHON_RE = re.compile(
    r'\b('
    r'eval\s*\(|exec\s*\(|os\.system\s*\(|pickle\.loads\s*\(|'
    r'__import__\s*\('
    r')'
)
SHELL_TRUE_RE = re.compile(r'\bshell\s*=\s*True\b')
YAML_LOAD_UNSAFE_RE = re.compile(r'\byaml\.load\s*\(\s*[^,)]+\)')  # no Loader= kwarg
DANGEROUS_JS_RE = re.compile(
    r'\b(dangerouslySetInnerHTML|document\.write\s*\(|new\s+Function\s*\()'
)

VERIFY_FALSE_RE = re.compile(r'\bverify\s*=\s*False\b')
SSL_UNVERIFIED_RE = re.compile(r'\bssl\._create_unverified_context\s*\(')
URLLIB3_DISABLE_RE = re.compile(r'\burllib3\.disable_warnings\s*\(')
TIMEOUT_NONE_RE = re.compile(r'\btimeout\s*=\s*None\b')

LOG_CALL_RE = re.compile(r'\b(log|logger|structlog\.get_logger\(\))\.\w+\s*\(([^)]*)\)', re.DOTALL)
SECRET_LEAK_KEY_RE = re.compile(
    r'(Authorization\s*:\s*Bearer|password\s*=|api_key\s*=|secret\s*=|token\s*=)',
    re.IGNORECASE,
)
REDACT_HELPER_RE = re.compile(r'\bredact_\w*\s*\(')

SECRET_SHAPED_RE = re.compile(r'(sk-[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|[A-Za-z0-9+/]{32,}={0,2})')

UTILS_HTTP_PREFIX = "backend/src/utils/http"


def _is_excluded(virtual: str) -> bool:
    return any(virtual.startswith(p) for p in EXCLUDE_VIRTUAL_PREFIXES)


def _scan_dangerous_patterns(path: Path, virtual: str, source: str) -> Iterable[Finding]:
    is_python = path.suffix == ".py"
    is_jsx = path.suffix in {".ts", ".tsx", ".js", ".jsx"}
    for lineno, line in enumerate(source.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("//"):
            continue
        if is_python:
            for pattern, label in (
                (DANGEROUS_PYTHON_RE, "dangerous Python builtin"),
                (SHELL_TRUE_RE, "shell=True on subprocess call"),
                (YAML_LOAD_UNSAFE_RE, "yaml.load without explicit Loader="),
            ):
                m = pattern.search(line)
                if m:
                    yield Finding(
                        severity=Severity.ERROR,
                        file=path,
                        line=lineno,
                        rule="Q13.dangerous-pattern",
                        message=f"{label}: `{m.group(0).strip()}`",
                        suggestion="rewrite to a safe alternative; never execute untrusted strings",
                    )
        if is_jsx:
            m = DANGEROUS_JS_RE.search(line)
            if m:
                yield Finding(
                    severity=Severity.ERROR,
                    file=path,
                    line=lineno,
                    rule="Q13.dangerous-pattern",
                    message=f"banned JS pattern: `{m.group(0).strip()}`",
                    suggestion="render text content; never raw HTML or dynamic Function/document.write",
                )


def _scan_outbound_http(path: Path, virtual: str, source: str) -> Iterable[Finding]:
    if path.suffix != ".py":
        return
    for lineno, line in enumerate(source.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for pattern, rule, message, suggestion in (
            (VERIFY_FALSE_RE, "Q13.tls-verify-required", "verify=False disables TLS validation", "remove verify=False; use real CA bundle"),
            (SSL_UNVERIFIED_RE, "Q13.tls-verify-required", "ssl._create_unverified_context", "use ssl.create_default_context()"),
            (URLLIB3_DISABLE_RE, "Q13.tls-verify-required", "urllib3.disable_warnings", "remove the call; fix the underlying TLS error"),
        ):
            m = pattern.search(line)
            if m:
                yield Finding(
                    severity=Severity.ERROR,
                    file=path,
                    line=lineno,
                    rule=rule,
                    message=message,
                    suggestion=suggestion,
                )
        if not virtual.startswith(UTILS_HTTP_PREFIX):
            m = TIMEOUT_NONE_RE.search(line)
            if m and "httpx" in source[:line.find(m.group(0))][-200:].lower():
                yield Finding(
                    severity=Severity.ERROR,
                    file=path,
                    line=lineno,
                    rule="Q13.outbound-timeout-required",
                    message="httpx call uses timeout=None (unbounded wait)",
                    suggestion="set an explicit timeout via httpx.Timeout(...) or use the with_retry wrapper",
                )


def _scan_log_secret_leak(path: Path, virtual: str, source: str) -> Iterable[Finding]:
    if path.suffix != ".py":
        return
    for m in LOG_CALL_RE.finditer(source):
        body = m.group(2)
        if SECRET_LEAK_KEY_RE.search(body) and not REDACT_HELPER_RE.search(body):
            line = source[:m.start()].count("\n") + 1
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=line,
                rule="Q13.log-secret-leak",
                message="logger call may emit a secret-shaped value without redaction",
                suggestion="wrap value in a redact_*(value) helper from observability/logging.py",
            )


def _scan_secret_shaped(path: Path, virtual: str, source: str) -> Iterable[Finding]:
    if "tests/" in virtual or "/test_" in virtual or virtual.startswith("frontend/e2e/"):
        return
    for lineno, line in enumerate(source.splitlines(), 1):
        # require quotes on either side to reduce false positives
        if not (("'" in line) or ('"' in line)):
            continue
        m = SECRET_SHAPED_RE.search(line)
        if m and len(m.group(0)) >= 32:
            yield Finding(
                severity=Severity.WARN,
                file=path,
                line=lineno,
                rule="Q13.secret-shaped-literal",
                message=f"secret-shaped literal of length {len(m.group(0))}",
                suggestion="if real, move to env-var; if false-positive, ignore (gitleaks is the hard gate)",
            )


def _scan_file(path: Path, virtual: str) -> Iterable[Finding]:
    if _is_excluded(virtual):
        return
    if path.suffix not in SCANNED_EXTS:
        return
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    yield from _scan_dangerous_patterns(path, virtual, source)
    yield from _scan_outbound_http(path, virtual, source)
    yield from _scan_log_secret_leak(path, virtual, source)
    yield from _scan_secret_shaped(path, virtual, source)


def _run_gitleaks() -> Iterable[Finding]:
    if not shutil.which("gitleaks"):
        yield Finding(
            severity=Severity.WARN,
            file=Path("gitleaks"),
            line=0,
            rule="Q13.secret-detected",
            message="gitleaks binary not installed; secret scan skipped",
            suggestion="install gitleaks (Sprint H.0b Story 6) so this rule can enforce",
        )
        return
    config_arg: list[str] = []
    config_path = REPO_ROOT / ".gitleaks.toml"
    if config_path.exists():
        config_arg = ["--config", str(config_path)]
    try:
        result = subprocess.run(
            ["gitleaks", "detect", "--no-git", "--report-format", "json", "--report-path", "/dev/stdout", *config_arg],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        yield Finding(
            severity=Severity.WARN,
            file=Path("gitleaks"),
            line=0,
            rule="Q13.secret-detected",
            message=f"gitleaks subprocess error: {exc}",
            suggestion="investigate gitleaks installation",
        )
        return
    if result.returncode == 0:
        return
    try:
        findings = json.loads(result.stdout) if result.stdout.strip() else []
    except json.JSONDecodeError:
        yield Finding(
            severity=Severity.ERROR,
            file=Path("gitleaks"),
            line=0,
            rule="Q13.secret-detected",
            message="gitleaks reported failures but JSON parse failed; see gitleaks output",
            suggestion="run `gitleaks detect --no-git` manually to triage",
        )
        return
    for finding in findings:
        yield Finding(
            severity=Severity.ERROR,
            file=Path(finding.get("File", "?")),
            line=int(finding.get("StartLine", 0)),
            rule="Q13.secret-detected",
            message=f"{finding.get('RuleID', 'unknown-rule')}: {finding.get('Description', '')[:120]}",
            suggestion="rotate the secret AND remove it from git history before merge",
        )


def scan(roots: Iterable[Path], pretend_path: str | None, run_gitleaks: bool) -> int:
    total_errors = 0
    if run_gitleaks:
        for finding in _run_gitleaks():
            emit(finding)
            if finding.severity == Severity.ERROR:
                total_errors += 1
    for root in roots:
        if not root.exists():
            emit(Finding(
                severity=Severity.ERROR,
                file=root,
                line=0,
                rule="harness.target-missing",
                message=f"target path does not exist: {root}",
                suggestion="pass an existing file or directory via --target",
            ))
            return 2
        if root.is_file():
            virtual = pretend_path or (str(root.relative_to(REPO_ROOT)) if root.is_relative_to(REPO_ROOT) else root.name)
            files = [(root, virtual)]
        else:
            files = []
            for p in root.rglob("*"):
                if p.is_file() and p.suffix in SCANNED_EXTS:
                    virtual = str(p.relative_to(REPO_ROOT)) if p.is_relative_to(REPO_ROOT) else p.name
                    files.append((p, virtual))
        for path, virtual in files:
            for finding in _scan_file(path, virtual):
                emit(finding)
                if finding.severity == Severity.ERROR:
                    total_errors += 1
    return 1 if total_errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, action="append")
    parser.add_argument("--pretend-path", type=str)
    parser.add_argument("--no-gitleaks", action="store_true", help="Skip gitleaks subprocess (test mode).")
    args = parser.parse_args(argv)
    roots = tuple(args.target) if args.target else DEFAULT_ROOTS
    run_gitleaks = not args.no_gitleaks and not args.target  # default on full-repo scan only
    return scan(roots, args.pretend_path, run_gitleaks)


if __name__ == "__main__":
    sys.exit(main())
```

### Task 1.6: Run tests, expect green

```bash
python -m pytest tests/harness/checks/test_security_policy_a.py -v
```

Expected: all 11 cases pass.

### Task 1.7: Triage live-repo run

```bash
python .harness/checks/security_policy_a.py
```

Expected outcomes:

- `Q13.secret-detected` should be silent (gitleaks already ran in pre-commit since H.0b). If it fires, **rotate the leaked secret immediately** before any other action.
- `Q13.dangerous-pattern` may fire on legacy backend code that still uses `eval(` for ad-hoc query parsers — refactor or baseline.
- `Q13.tls-verify-required` MUST be silent — fix any callsite immediately.
- `Q13.outbound-timeout-required` may fire on a few dev-only scripts; tolerate via `# noqa` (deferred to H.1d.1) or wrap with `with_retry`.
- `Q13.log-secret-leak` may fire on auth-related logger calls; fix by routing through `redact_*`.

### Task 1.8: Run validate-fast

```bash
python tools/run_validate.py --fast
```

Expected: orchestrator picks up the new check; total wall time still < 30s.

### Task 1.9: Commit green

```bash
git add .harness/checks/security_policy_a.py
git commit -m "$(cat <<'EOF'
feat(green): H.1c.1 — security_policy_a enforces Q13 part A

Six rules: gitleaks subprocess wrapper (degrades to WARN if missing);
banned dangerous patterns on backend (eval/exec/os.system/shell=True/
pickle.loads/yaml.load-unsafe/__import__) and frontend (dangerouslySet
InnerHTML/new Function/document.write); TLS-verify-required (verify=
False/ssl unverified context/urllib3.disable_warnings); outbound-
timeout-required on httpx outside backend/src/utils/http.py; log-secret
-leak on logger calls without redact_* helper; secret-shaped literal
WARN. H-25 docstring covers missing/malformed/upstream-failed (gitleaks).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 1.10: Verify discovery

```bash
python tools/run_validate.py --fast 2>&1 | grep "check:security_policy_a"
```

Expected: orchestrator label printed.

---

# Story H.1c.2 — `security_policy_b.py` (Q13.B — auth + rate-limit + CSRF)

**Rule families enforced (3):**
1. Every FastAPI route under `backend/src/api/` whose HTTP verb is `POST`/`PUT`/`PATCH`/`DELETE` MUST declare a dependency on an authentication function. Heuristic: route handler signature includes a parameter typed via `Depends(get_current_user)`, `Depends(require_user)`, `Depends(require_admin)`, OR the function carries an `@authenticated` / `@requires(...)` decorator.
2. Every mutating route MUST be decorated with `@limiter.limit("...")` (slowapi) OR be listed in `.harness/security_policy.yaml.rate_limit_exempt`.
3. Every mutating route that accepts a request body MUST have a CSRF guard: either `csrf_protect: CsrfProtect = Depends()` parameter (fastapi-csrf-protect), OR be listed in `.harness/security_policy.yaml.csrf_exempt` (e.g., webhook endpoints with HMAC verification).

**Files:**
- Create: `.harness/security_policy.yaml` (extend, if H.0b created stub)
- Create: `.harness/checks/security_policy_b.py`
- Create: `tests/harness/fixtures/security_policy_b/violation/post_no_auth.py`
- Create: `tests/harness/fixtures/security_policy_b/violation/post_no_rate_limit.py`
- Create: `tests/harness/fixtures/security_policy_b/violation/post_no_csrf.py`
- Create: `tests/harness/fixtures/security_policy_b/compliant/post_full_protection.py`
- Create: `tests/harness/checks/test_security_policy_b.py`

### Task 2.1: Extend `.harness/security_policy.yaml`

Append (or create if H.0b left it empty):

```yaml
auth_dependency_names:
  - get_current_user
  - require_user
  - require_admin
  - require_tenant_admin

auth_decorator_names:
  - authenticated
  - requires

rate_limit_exempt:
  - GET:/healthz
  - GET:/metrics
  - GET:/version

csrf_exempt:
  - POST:/api/v4/webhooks/*
```

### Task 2.2: Create violation fixtures

```bash
mkdir -p tests/harness/fixtures/security_policy_b/{violation,compliant}
```

`violation/post_no_auth.py`:

```python
"""Q13.B violation — POST handler without auth dependency.

Pretend-path: backend/src/api/routes_v4.py
"""
from fastapi import APIRouter

router = APIRouter()


@router.post("/api/v4/incidents")
async def create_incident(payload: dict) -> dict:
    return {"ok": True}
```

`violation/post_no_rate_limit.py`:

```python
"""Q13.B violation — POST handler with auth but no @limiter.limit.

Pretend-path: backend/src/api/routes_v4.py
"""
from fastapi import APIRouter, Depends

router = APIRouter()


def require_user() -> None: ...


@router.post("/api/v4/incidents")
async def create_incident(payload: dict, user=Depends(require_user)) -> dict:
    return {"ok": True}
```

`violation/post_no_csrf.py`:

```python
"""Q13.B violation — POST with auth + rate limit but no CSRF guard.

Pretend-path: backend/src/api/routes_v4.py
"""
from fastapi import APIRouter, Depends, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


def require_user() -> None: ...


@router.post("/api/v4/incidents")
@limiter.limit("10/minute")
async def create_incident(request: Request, payload: dict, user=Depends(require_user)) -> dict:
    return {"ok": True}
```

### Task 2.3: Create compliant fixture

`compliant/post_full_protection.py`:

```python
"""Q13.B compliant — auth + rate limit + CSRF guard all wired.

Pretend-path: backend/src/api/routes_v4.py
"""
from fastapi import APIRouter, Depends, Request
from fastapi_csrf_protect import CsrfProtect
from slowapi import Limiter
from slowapi.util import get_remote_address

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


def require_user() -> None: ...


@router.post("/api/v4/incidents")
@limiter.limit("10/minute")
async def create_incident(
    request: Request,
    payload: dict,
    user=Depends(require_user),
    csrf_protect: CsrfProtect = Depends(),
) -> dict:
    return {"ok": True}
```

### Task 2.4: Write the failing test

Create `tests/harness/checks/test_security_policy_b.py`:

```python
"""H.1c.2 — security_policy_b check tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness._helpers import assert_check_fires, assert_check_silent

CHECK = "security_policy_b"
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / CHECK


@pytest.mark.parametrize(
    "fixture_name,expected_rule",
    [
        ("post_no_auth.py", "Q13.route-needs-auth"),
        ("post_no_rate_limit.py", "Q13.route-needs-rate-limit"),
        ("post_no_csrf.py", "Q13.route-needs-csrf"),
    ],
)
def test_violation_fires(fixture_name: str, expected_rule: str) -> None:
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / fixture_name,
        expected_rule=expected_rule,
        pretend_path="backend/src/api/routes_v4.py",
    )


def test_compliant_silent() -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / "post_full_protection.py",
        pretend_path="backend/src/api/routes_v4.py",
    )
```

### Task 2.5: Run failing test + commit red

```bash
python -m pytest tests/harness/checks/test_security_policy_b.py -v
git add tests/harness/fixtures/security_policy_b tests/harness/checks/test_security_policy_b.py .harness/security_policy.yaml
git commit -m "$(cat <<'EOF'
test(red): H.1c.2 — security_policy_b fixtures + assertions

Three violation fixtures (POST without auth dep; POST with auth but no
@limiter.limit; POST with auth+rate-limit but no CSRF guard) plus one
fully-protected compliant fixture. Policy yaml extended with auth/CSRF
dep names and exempt lists.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 2.6: Implement the check

Create `.harness/checks/security_policy_b.py`:

```python
#!/usr/bin/env python3
"""Q13.B — every mutating FastAPI route has auth + rate-limit + CSRF.

Three rules:
  Q13.route-needs-auth        — POST/PUT/PATCH/DELETE handler missing an auth
                                 dependency (function param via Depends(<auth_fn>)
                                 OR @authenticated/@requires decorator).
  Q13.route-needs-rate-limit  — mutating handler missing @limiter.limit decorator
                                 unless verb:path listed in rate_limit_exempt.
  Q13.route-needs-csrf        — mutating handler missing CsrfProtect dependency
                                 unless verb:path listed in csrf_exempt.

H-25:
  Missing input    — exit 2.
  Malformed input  — WARN harness.unparseable.
  Upstream failed  — none.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import sys
from pathlib import Path
from typing import Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from .harness.checks._common import Finding, Severity, emit, walk_python_files  # noqa: E402

DEFAULT_ROOTS = (REPO_ROOT / "backend" / "src" / "api",)
DEFAULT_POLICY = REPO_ROOT / ".harness" / "security_policy.yaml"
EXCLUDE = ("__pycache__", "tests/harness/fixtures")
MUTATING_VERBS = {"post", "put", "patch", "delete"}


def _load_policy(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _route_decorator_info(node: ast.AST) -> tuple[str, str] | None:
    """Returns (verb, path) if `node` is a `@router.<verb>("<path>")` decorator."""
    if not isinstance(node, ast.Call):
        return None
    if not (isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)):
        return None
    if node.func.value.id not in {"router", "app"}:
        return None
    verb = node.func.attr.lower()
    if verb not in MUTATING_VERBS and verb != "get":
        return None
    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
        return verb, node.args[0].value
    return None


def _has_auth_dep(fn: ast.FunctionDef | ast.AsyncFunctionDef, auth_dep_names: set[str], auth_dec_names: set[str]) -> bool:
    # decorator-based
    for dec in fn.decorator_list:
        name = None
        if isinstance(dec, ast.Name):
            name = dec.id
        elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
            name = dec.func.id
        if name and name in auth_dec_names:
            return True
    # parameter-based via Depends(...)
    args = list(fn.args.args) + list(fn.args.kwonlyargs)
    for arg in args:
        default = _arg_default(fn, arg)
        if default is None:
            continue
        if (
            isinstance(default, ast.Call)
            and isinstance(default.func, ast.Name)
            and default.func.id == "Depends"
            and default.args
        ):
            inner = default.args[0]
            if isinstance(inner, ast.Name) and inner.id in auth_dep_names:
                return True
    return False


def _arg_default(fn: ast.FunctionDef | ast.AsyncFunctionDef, arg: ast.arg) -> ast.AST | None:
    # python AST: defaults align with the *trailing* args; kwonly_defaults align 1:1 with kwonlyargs.
    args = fn.args.args
    if arg in args:
        idx = args.index(arg)
        defaults = fn.args.defaults
        offset = len(args) - len(defaults)
        if idx >= offset:
            return defaults[idx - offset]
        return None
    kwonly = fn.args.kwonlyargs
    if arg in kwonly:
        idx = kwonly.index(arg)
        kw_defaults = fn.args.kw_defaults
        return kw_defaults[idx] if idx < len(kw_defaults) else None
    return None


def _has_rate_limit_decorator(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for dec in fn.decorator_list:
        if (
            isinstance(dec, ast.Call)
            and isinstance(dec.func, ast.Attribute)
            and isinstance(dec.func.value, ast.Name)
            and dec.func.value.id == "limiter"
            and dec.func.attr == "limit"
        ):
            return True
    return False


def _has_csrf_dep(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    args = list(fn.args.args) + list(fn.args.kwonlyargs)
    for arg in args:
        if arg.annotation is None:
            continue
        ann_src = ast.dump(arg.annotation)
        if "CsrfProtect" in ann_src:
            return True
    return False


def _exempt(verb: str, path: str, exempt_list: list[str]) -> bool:
    key = f"{verb.upper()}:{path}"
    for entry in exempt_list:
        if fnmatch.fnmatchcase(key, entry):
            return True
    return False


def _scan_file(path: Path, virtual: str, policy: dict) -> Iterable[Finding]:
    if not (virtual.startswith("backend/src/api/") or path.parent.name == "api"):
        return
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, UnicodeDecodeError):
        return
    except SyntaxError:
        yield Finding(
            severity=Severity.WARN,
            file=path,
            line=1,
            rule="harness.unparseable",
            message=f"could not parse {path.name}",
            suggestion="fix syntax",
        )
        return

    auth_dep_names = set(policy.get("auth_dependency_names") or [])
    auth_dec_names = set(policy.get("auth_decorator_names") or [])
    rate_limit_exempt = list(policy.get("rate_limit_exempt") or [])
    csrf_exempt = list(policy.get("csrf_exempt") or [])

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            info = _route_decorator_info(dec)
            if info is None:
                continue
            verb, route_path = info
            if verb not in MUTATING_VERBS:
                continue
            line = node.lineno
            if not _has_auth_dep(node, auth_dep_names, auth_dec_names):
                yield Finding(
                    severity=Severity.ERROR,
                    file=path,
                    line=line,
                    rule="Q13.route-needs-auth",
                    message=f"{verb.upper()} {route_path} has no auth dependency",
                    suggestion=f"add `user = Depends({sorted(auth_dep_names)[0] if auth_dep_names else 'get_current_user'})`",
                )
            if not _has_rate_limit_decorator(node) and not _exempt(verb, route_path, rate_limit_exempt):
                yield Finding(
                    severity=Severity.ERROR,
                    file=path,
                    line=line,
                    rule="Q13.route-needs-rate-limit",
                    message=f"{verb.upper()} {route_path} missing @limiter.limit",
                    suggestion="add `@limiter.limit(\"<n>/minute\")` or list in security_policy.yaml.rate_limit_exempt",
                )
            if not _has_csrf_dep(node) and not _exempt(verb, route_path, csrf_exempt):
                yield Finding(
                    severity=Severity.ERROR,
                    file=path,
                    line=line,
                    rule="Q13.route-needs-csrf",
                    message=f"{verb.upper()} {route_path} missing CsrfProtect dependency",
                    suggestion="add `csrf_protect: CsrfProtect = Depends()` or list under csrf_exempt",
                )


def scan(roots: Iterable[Path], policy_path: Path, pretend_path: str | None) -> int:
    policy = _load_policy(policy_path)
    total_errors = 0
    for root in roots:
        if not root.exists():
            emit(Finding(
                severity=Severity.ERROR,
                file=root,
                line=0,
                rule="harness.target-missing",
                message=f"target path does not exist: {root}",
                suggestion="pass an existing file or directory via --target",
            ))
            return 2
        if root.is_file() and root.suffix == ".py":
            virtual = pretend_path or (str(root.relative_to(REPO_ROOT)) if root.is_relative_to(REPO_ROOT) else root.name)
            files = [(root, virtual)]
        else:
            files = [
                (p, str(p.relative_to(REPO_ROOT)))
                for p in walk_python_files(root, exclude=EXCLUDE)
            ]
        for path, virtual in files:
            for finding in _scan_file(path, virtual, policy):
                emit(finding)
                if finding.severity == Severity.ERROR:
                    total_errors += 1
    return 1 if total_errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, action="append")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--pretend-path", type=str)
    args = parser.parse_args(argv)
    roots = tuple(args.target) if args.target else DEFAULT_ROOTS
    return scan(roots, args.policy, args.pretend_path)


if __name__ == "__main__":
    sys.exit(main())
```

### Task 2.7: Run tests, expect green

```bash
python -m pytest tests/harness/checks/test_security_policy_b.py -v
```

### Task 2.8: Triage live-repo run

```bash
python .harness/checks/security_policy_b.py
```

Expected: significant `Q13.route-needs-rate-limit` and `Q13.route-needs-csrf` ERRORs across `routes_v4.py` (the existing routers were not built with these dependencies). Triage:

- For `Q13.route-needs-auth`: each missing route is a real bug; pair with backend lead. If exempt (e.g., public webhook), add to `csrf_exempt` AND tag the route with a `# noqa: Q13.route-needs-auth — explicit public endpoint` comment plus an ADR.
- For rate-limit / CSRF: stand-up the slowapi limiter + fastapi-csrf-protect middleware (separate PR, since this is non-trivial), then re-baseline.

### Task 2.9: Run validate-fast

```bash
python tools/run_validate.py --fast
```

### Task 2.10: Commit green

```bash
git add .harness/checks/security_policy_b.py
git commit -m "$(cat <<'EOF'
feat(green): H.1c.2 — security_policy_b enforces Q13 part B

AST scan of FastAPI route handlers under backend/src/api/. Three rules:
mutating routes (POST/PUT/PATCH/DELETE) must declare an auth dependency
(Depends(<auth_fn>) parameter or @authenticated/@requires decorator);
must carry @limiter.limit unless exempt; must declare CsrfProtect
dependency unless exempt. Allowlists honored from security_policy.yaml.
H-25 docstring covers missing/malformed/no-upstream.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Story H.1c.3 — `documentation_policy.py` (Q15)

**Rule families enforced (7):**
1. Every public function/class in the spine paths (`backend/src/api/`, `backend/src/storage/gateway.py`, `backend/src/models/api/`, `backend/src/models/agent/`, `backend/src/agents/**/runners/`, `tools/`, `.harness/checks/`, `.harness/generators/`) MUST have a docstring of ≥ 1 non-empty line.
2. Every public hook/lib/services TS export (under `frontend/src/{hooks,lib,services}/**`) MUST have a JSDoc comment immediately before its declaration. (Heuristic: look at the line above each `export const|function`.)
3. ADR file MUST exist when this PR adds/removes a spine dependency. Heuristic via `.harness/dependencies.yaml` diff vs `git show HEAD:.harness/dependencies.yaml` — if any line was added/removed, require a new file under `docs/decisions/<YYYY-MM-DD>-*.md` in the same commit.
4. ADR file MUST exist when this PR modifies any `.harness/*_policy.yaml` config (Q12, Q13, Q14, Q15, Q16, Q17, Q18, Q19). Same diff heuristic.
5. ADR file MUST exist when this PR modifies anything under `.harness/checks/` (changes the harness rule set itself).
6. `docs/api.md` MUST exist (presence check) and have at least one `## ` heading (smoke test of curated API guide).
7. `docs/decisions/_TEMPLATE.md` MUST exist (presence — H.0b Story 8 created it).

**Files:**
- Create: `.harness/documentation_policy.yaml` (extend if H.0b created stub)
- Create: `.harness/checks/documentation_policy.py`
- Create: `tests/harness/fixtures/documentation_policy/violation/missing_docstring.py`
- Create: `tests/harness/fixtures/documentation_policy/violation/missing_jsdoc.ts`
- Create: `tests/harness/fixtures/documentation_policy/compliant/with_docstring.py`
- Create: `tests/harness/fixtures/documentation_policy/compliant/with_jsdoc.ts`
- Create: `tests/harness/checks/test_documentation_policy.py`

### Task 3.1: Extend `.harness/documentation_policy.yaml`

```yaml
spine_python_paths:
  - backend/src/api/**
  - backend/src/storage/gateway.py
  - backend/src/models/api/**
  - backend/src/models/agent/**
  - backend/src/agents/**/runners/**
  - tools/**
  - .harness/checks/**
  - .harness/generators/**

frontend_jsdoc_paths:
  - frontend/src/hooks/**
  - frontend/src/lib/**
  - frontend/src/services/**

adr_required_on_change:
  - .harness/dependencies.yaml
  - .harness/performance_budgets.yaml
  - .harness/security_policy.yaml
  - .harness/accessibility_policy.yaml
  - .harness/documentation_policy.yaml
  - .harness/logging_policy.yaml
  - .harness/error_handling_policy.yaml
  - .harness/conventions_policy.yaml
  - .harness/typecheck_policy.yaml
  - .harness/checks/**
```

### Task 3.2: Create violation fixtures

```bash
mkdir -p tests/harness/fixtures/documentation_policy/{violation,compliant}
```

`violation/missing_docstring.py`:

```python
"""File-level docstring is fine; checking class+function docstring at the spine.

Pretend-path: backend/src/api/routes_v4.py
"""

from fastapi import APIRouter

router = APIRouter()


def list_incidents() -> list[dict]:
    return []


class IncidentResponse:
    pass
```

`violation/missing_jsdoc.ts`:

```ts
/* No JSDoc above the export.

Pretend-path: frontend/src/hooks/useFoo.ts
*/
export const useFoo = (id: string) => id;
```

### Task 3.3: Create compliant fixtures

`compliant/with_docstring.py`:

```python
"""Spine module with docstrings on every public symbol.

Pretend-path: backend/src/api/routes_v4.py
"""

from fastapi import APIRouter

router = APIRouter()


def list_incidents() -> list[dict]:
    """Return all incidents visible to the requesting tenant."""
    return []


class IncidentResponse:
    """Frozen response wrapper for a single incident."""
```

`compliant/with_jsdoc.ts`:

```ts
/* JSDoc above the export.

Pretend-path: frontend/src/hooks/useFoo.ts
*/

/** Return the foo identifier with caching applied. */
export const useFoo = (id: string) => id;
```

### Task 3.4: Write the failing test

Create `tests/harness/checks/test_documentation_policy.py`:

```python
"""H.1c.3 — documentation_policy check tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness._helpers import assert_check_fires, assert_check_silent

CHECK = "documentation_policy"
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / CHECK


@pytest.mark.parametrize(
    "fixture_name,expected_rule,pretend_path",
    [
        ("missing_docstring.py", "Q15.spine-docstring-required", "backend/src/api/routes_v4.py"),
        ("missing_jsdoc.ts", "Q15.frontend-jsdoc-required", "frontend/src/hooks/useFoo.ts"),
    ],
)
def test_violation_fires(fixture_name: str, expected_rule: str, pretend_path: str) -> None:
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / fixture_name,
        expected_rule=expected_rule,
        pretend_path=pretend_path,
    )


@pytest.mark.parametrize(
    "fixture_name,pretend_path",
    [
        ("with_docstring.py", "backend/src/api/routes_v4.py"),
        ("with_jsdoc.ts", "frontend/src/hooks/useFoo.ts"),
    ],
)
def test_compliant_silent(fixture_name: str, pretend_path: str) -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / fixture_name,
        pretend_path=pretend_path,
    )
```

### Task 3.5: Run failing test + commit red

```bash
python -m pytest tests/harness/checks/test_documentation_policy.py -v
git add tests/harness/fixtures/documentation_policy tests/harness/checks/test_documentation_policy.py .harness/documentation_policy.yaml
git commit -m "$(cat <<'EOF'
test(red): H.1c.3 — documentation_policy fixtures + assertions

Two violation fixtures (spine Python missing class+function docstring;
frontend hook missing JSDoc) plus two compliant counterparts. Policy
yaml extended with spine path globs + adr_required_on_change list.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 3.6: Implement the check

Create `.harness/checks/documentation_policy.py`:

```python
#!/usr/bin/env python3
"""Q15 — documentation discipline (docstrings + JSDoc + ADR triggers).

Seven rules:
  Q15.spine-docstring-required    — every public function/class in spine paths
                                     must have a non-empty docstring (first
                                     statement is `ast.Expr(ast.Constant(str))`).
  Q15.frontend-jsdoc-required     — every `export const|function` in
                                     frontend/src/{hooks,lib,services}/** must
                                     have a JSDoc comment (`/** ... */`)
                                     immediately preceding it.
  Q15.adr-required-on-change      — git diff on adr_required_on_change paths
                                     vs HEAD requires a new docs/decisions/<date>-*.md
                                     file in the staged changes (CI-time check).
  Q15.api-md-presence             — docs/api.md must exist with ≥ 1 `## ` heading.
  Q15.adr-template-presence       — docs/decisions/_TEMPLATE.md must exist.

H-25:
  Missing input    — exit 2.
  Malformed input  — WARN harness.unparseable.
  Upstream failed  — git binary missing → WARN; ADR-on-change rule degrades.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from .harness.checks._common import Finding, Severity, emit, walk_python_files  # noqa: E402

DEFAULT_ROOTS = (REPO_ROOT,)
DEFAULT_POLICY = REPO_ROOT / ".harness" / "documentation_policy.yaml"
EXCLUDE_VIRTUAL_PREFIXES = (
    "tests/harness/fixtures/",
    "frontend/dist/",
    "frontend/node_modules/",
    "backend/.venv/",
)
JS_SCANNED_EXTS = {".ts", ".tsx", ".js", ".jsx"}

JSDOC_RE = re.compile(r'/\*\*[\s\S]*?\*/')
EXPORT_DECL_RE = re.compile(r'^\s*export\s+(const|function|class|async\s+function)\s+(\w+)', re.MULTILINE)


def _load_policy(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _matches_any(virtual: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(virtual, g) for g in globs)


def _is_excluded(virtual: str) -> bool:
    return any(virtual.startswith(p) for p in EXCLUDE_VIRTUAL_PREFIXES)


def _scan_python_docstrings(path: Path, virtual: str, source: str) -> Iterable[Finding]:
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        yield Finding(
            severity=Severity.WARN,
            file=path,
            line=1,
            rule="harness.unparseable",
            message=f"could not parse {path.name}",
            suggestion="fix syntax",
        )
        return
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name.startswith("_"):
                continue  # private; not a public spine surface
            doc = ast.get_docstring(node, clean=False)
            if not doc or not doc.strip():
                yield Finding(
                    severity=Severity.ERROR,
                    file=path,
                    line=node.lineno,
                    rule="Q15.spine-docstring-required",
                    message=f"public {type(node).__name__} `{node.name}` missing docstring",
                    suggestion="add a one-line docstring describing purpose + return contract",
                )


def _scan_jsdoc(path: Path, virtual: str, source: str) -> Iterable[Finding]:
    for m in EXPORT_DECL_RE.finditer(source):
        decl_start = m.start()
        # search backwards for nearest /** ... */ within 200 chars
        window = source[max(0, decl_start - 400):decl_start]
        last_jsdoc = None
        for jm in JSDOC_RE.finditer(window):
            last_jsdoc = jm
        if last_jsdoc is None:
            line = source[:decl_start].count("\n") + 1
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=line,
                rule="Q15.frontend-jsdoc-required",
                message=f"export `{m.group(2)}` lacks JSDoc",
                suggestion="add a `/** ... */` comment immediately above the declaration",
            )


def _scan_file(path: Path, virtual: str, policy: dict) -> Iterable[Finding]:
    if _is_excluded(virtual):
        return
    spine = policy.get("spine_python_paths") or []
    front = policy.get("frontend_jsdoc_paths") or []
    if path.suffix == ".py" and _matches_any(virtual, spine):
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return
        yield from _scan_python_docstrings(path, virtual, source)
    if path.suffix in JS_SCANNED_EXTS and _matches_any(virtual, front):
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return
        yield from _scan_jsdoc(path, virtual, source)


def _scan_root_invariants(root: Path, policy: dict) -> Iterable[Finding]:
    api_md = root / "docs" / "api.md"
    if not api_md.exists():
        yield Finding(
            severity=Severity.ERROR,
            file=api_md,
            line=0,
            rule="Q15.api-md-presence",
            message="docs/api.md missing",
            suggestion="create docs/api.md with curated endpoint guide",
        )
    elif "## " not in api_md.read_text(encoding="utf-8"):
        yield Finding(
            severity=Severity.ERROR,
            file=api_md,
            line=1,
            rule="Q15.api-md-presence",
            message="docs/api.md has no `## ` heading",
            suggestion="add at least one heading to seed the guide",
        )
    adr_template = root / "docs" / "decisions" / "_TEMPLATE.md"
    if not adr_template.exists():
        yield Finding(
            severity=Severity.ERROR,
            file=adr_template,
            line=0,
            rule="Q15.adr-template-presence",
            message="docs/decisions/_TEMPLATE.md missing",
            suggestion="create the ADR template (Sprint H.0b Story 8)",
        )


def _scan_adr_on_change(policy: dict) -> Iterable[Finding]:
    if not shutil.which("git"):
        yield Finding(
            severity=Severity.WARN,
            file=Path("git"),
            line=0,
            rule="Q15.adr-required-on-change",
            message="git binary missing; ADR diff check skipped",
            suggestion="install git so this rule can enforce",
        )
        return
    try:
        diff = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return
    changed = [p for p in diff.stdout.splitlines() if p.strip()]
    triggers = policy.get("adr_required_on_change") or []
    triggered = [p for p in changed if any(fnmatch.fnmatchcase(p, t) for t in triggers)]
    if not triggered:
        return
    new_adr = [p for p in changed if p.startswith("docs/decisions/") and not p.endswith("_TEMPLATE.md")]
    if not new_adr:
        yield Finding(
            severity=Severity.ERROR,
            file=Path("docs/decisions/"),
            line=0,
            rule="Q15.adr-required-on-change",
            message=f"changes to {triggered[:3]} (and {max(0, len(triggered)-3)} others) require an ADR",
            suggestion="add docs/decisions/<YYYY-MM-DD>-<slug>.md based on _TEMPLATE.md in this commit",
        )


def scan(roots: Iterable[Path], policy_path: Path, pretend_path: str | None) -> int:
    policy = _load_policy(policy_path)
    total_errors = 0
    if any(root.is_dir() for root in roots):
        for finding in _scan_root_invariants(REPO_ROOT, policy):
            emit(finding)
            if finding.severity == Severity.ERROR:
                total_errors += 1
        for finding in _scan_adr_on_change(policy):
            emit(finding)
            if finding.severity == Severity.ERROR:
                total_errors += 1
    for root in roots:
        if not root.exists():
            emit(Finding(
                severity=Severity.ERROR,
                file=root,
                line=0,
                rule="harness.target-missing",
                message=f"target path does not exist: {root}",
                suggestion="pass an existing file or directory via --target",
            ))
            return 2
        if root.is_file():
            virtual = pretend_path or (str(root.relative_to(REPO_ROOT)) if root.is_relative_to(REPO_ROOT) else root.name)
            files = [(root, virtual)]
        else:
            files = []
            for p in root.rglob("*"):
                if p.is_file() and (p.suffix == ".py" or p.suffix in JS_SCANNED_EXTS):
                    virtual = str(p.relative_to(REPO_ROOT)) if p.is_relative_to(REPO_ROOT) else p.name
                    files.append((p, virtual))
        for path, virtual in files:
            for finding in _scan_file(path, virtual, policy):
                emit(finding)
                if finding.severity == Severity.ERROR:
                    total_errors += 1
    return 1 if total_errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, action="append")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--pretend-path", type=str)
    args = parser.parse_args(argv)
    roots = tuple(args.target) if args.target else DEFAULT_ROOTS
    return scan(roots, args.policy, args.pretend_path)


if __name__ == "__main__":
    sys.exit(main())
```

### Task 3.7: Run tests, expect green

```bash
python -m pytest tests/harness/checks/test_documentation_policy.py -v
```

### Task 3.8: Triage live-repo run

```bash
python .harness/checks/documentation_policy.py
```

Expected:

- `Q15.spine-docstring-required` will fire heavily — many existing routes/methods have no docstrings. Triage: write top-20 most-public; baseline the rest.
- `Q15.frontend-jsdoc-required` will fire on most hooks. Write JSDoc for the 5 most-used hooks; baseline the rest.
- `Q15.api-md-presence` MUST pass (H.0b-era follow-up if missing).
- `Q15.adr-template-presence` MUST pass.
- `Q15.adr-required-on-change` only fires during a real PR diff; OK if silent on a clean tree.

### Task 3.9: Run validate-fast

```bash
python tools/run_validate.py --fast
```

### Task 3.10: Commit green

```bash
git add .harness/checks/documentation_policy.py
git commit -m "$(cat <<'EOF'
feat(green): H.1c.3 — documentation_policy enforces Q15

Seven rules: spine Python public functions/classes need docstrings;
frontend hooks/lib/services exports need JSDoc; ADR required when
listed config files change (git diff); docs/api.md presence + at
least one heading; docs/decisions/_TEMPLATE.md presence. H-25
docstring covers missing/malformed/upstream-failed (git binary).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Story H.1c.4 — `logging_policy.py` (Q16)

**Rule families enforced (8):**
1. No `print(` calls in `backend/src/` (production code) outside `backend/src/observability/logging.py` (the configured sink).
2. No `console.log(` / `console.warn(` / `console.error(` / `console.debug(` calls in `frontend/src/` outside `frontend/src/lib/errorReporter.ts`.
3. Logger import discipline: `backend/src/` files that emit logs MUST use `import structlog` + `log = structlog.get_logger(__name__)`. Bare `import logging` BANNED on the spine (`api/`, `storage/`, `agents/**/runners/`, `learning/`, `models/api/`, `models/agent/`).
4. `log.<level>(` calls MUST use one of `debug`, `info`, `warning`, `error`, `critical` (no `warn`, no `panic`, no custom level).
5. Every `log.<level>(` call MUST pass an `event=` kwarg (string literal first positional acts as event name in structlog — accept either `log.info("event_name", ...)` OR `log.info(event="event_name", ...)`).
6. Every `log.<level>(` call inside a route handler MUST include at least one of `request_id=`, `tenant_id=`, `session_id=`, `correlation_id=` kwargs.
7. Every async function under `backend/src/agents/**/runners/` and `backend/src/workflows/runners/` MUST start its body with `with tracer.start_as_current_span(` (OpenTelemetry span — Q16.ε).
8. The `backend/src/observability/logging.py` module MUST export a function called `configure_logging` AND register a `redact_secrets` processor (presence check via grep).

**Files:**
- Create: `.harness/logging_policy.yaml` (extend if H.0b created stub)
- Create: `.harness/checks/logging_policy.py`
- Create: `tests/harness/fixtures/logging_policy/violation/uses_print.py`
- Create: `tests/harness/fixtures/logging_policy/violation/uses_console_log.tsx`
- Create: `tests/harness/fixtures/logging_policy/violation/bare_logging_import.py`
- Create: `tests/harness/fixtures/logging_policy/violation/log_warn_invalid_level.py`
- Create: `tests/harness/fixtures/logging_policy/violation/log_no_event.py`
- Create: `tests/harness/fixtures/logging_policy/violation/route_log_no_correlation.py`
- Create: `tests/harness/fixtures/logging_policy/violation/agent_runner_no_span.py`
- Create: `tests/harness/fixtures/logging_policy/compliant/structlog_with_event.py`
- Create: `tests/harness/fixtures/logging_policy/compliant/route_log_with_correlation.py`
- Create: `tests/harness/fixtures/logging_policy/compliant/agent_runner_with_span.py`
- Create: `tests/harness/fixtures/logging_policy/compliant/error_reporter_console.tsx`
- Create: `tests/harness/checks/test_logging_policy.py`

### Task 4.1: Extend `.harness/logging_policy.yaml`

```yaml
backend_logger_required_paths:
  - backend/src/api/**
  - backend/src/storage/**
  - backend/src/agents/**/runners/**
  - backend/src/learning/**
  - backend/src/models/api/**
  - backend/src/models/agent/**

bare_logging_banned_paths:
  - backend/src/api/**
  - backend/src/storage/**
  - backend/src/agents/**/runners/**
  - backend/src/learning/**

allowed_log_levels:
  - debug
  - info
  - warning
  - error
  - critical

required_correlation_kwargs:
  - request_id
  - tenant_id
  - session_id
  - correlation_id

frontend_console_allowed_files:
  - frontend/src/lib/errorReporter.ts

backend_print_allowed_files:
  - backend/src/observability/logging.py

otel_span_required_paths:
  - backend/src/agents/**/runners/**
  - backend/src/workflows/runners/**
```

### Task 4.2: Create violation fixtures

```bash
mkdir -p tests/harness/fixtures/logging_policy/{violation,compliant}
```

`violation/uses_print.py`:

```python
"""Q16 violation — print() in production source.

Pretend-path: backend/src/services/foo.py
"""
def foo() -> None:
    print("hello")
```

`violation/uses_console_log.tsx`:

```tsx
/* Q16 violation — console.log in production frontend.

Pretend-path: frontend/src/components/Foo.tsx
*/
export const Foo = () => {
  console.log("hello");
  return null;
};
```

`violation/bare_logging_import.py`:

```python
"""Q16 violation — bare logging import on spine path.

Pretend-path: backend/src/api/routes_v4.py
"""
import logging

log = logging.getLogger(__name__)


def handler() -> None:
    log.info("hi")
```

`violation/log_warn_invalid_level.py`:

```python
"""Q16 violation — log.warn (deprecated alias for warning).

Pretend-path: backend/src/services/foo.py
"""
import structlog

log = structlog.get_logger(__name__)


def foo() -> None:
    log.warn("event_x", attr=1)
```

`violation/log_no_event.py`:

```python
"""Q16 violation — log.info with no event name + no event= kwarg.

Pretend-path: backend/src/services/foo.py
"""
import structlog

log = structlog.get_logger(__name__)


def foo(value: int) -> None:
    log.info(amount=value)
```

`violation/route_log_no_correlation.py`:

```python
"""Q16 violation — route handler logs without any correlation kwarg.

Pretend-path: backend/src/api/routes_v4.py
"""
import structlog
from fastapi import APIRouter

router = APIRouter()
log = structlog.get_logger(__name__)


@router.get("/api/v4/foo")
async def foo() -> dict:
    log.info("foo_called", value=1)
    return {}
```

`violation/agent_runner_no_span.py`:

```python
"""Q16 violation — agent runner without OpenTelemetry span.

Pretend-path: backend/src/agents/log/runners/run.py
"""
async def run(payload: dict) -> dict:
    return {"ok": True}
```

### Task 4.3: Create compliant fixtures

`compliant/structlog_with_event.py`:

```python
"""Q16 compliant — structlog import + event-as-positional + valid level.

Pretend-path: backend/src/services/foo.py
"""
import structlog

log = structlog.get_logger(__name__)


def foo(value: int) -> None:
    log.info("foo_called", amount=value)
```

`compliant/route_log_with_correlation.py`:

```python
"""Q16 compliant — route handler logs with request_id correlation kwarg.

Pretend-path: backend/src/api/routes_v4.py
"""
import structlog
from fastapi import APIRouter

router = APIRouter()
log = structlog.get_logger(__name__)


@router.get("/api/v4/foo")
async def foo(request_id: str) -> dict:
    log.info("foo_called", value=1, request_id=request_id)
    return {}
```

`compliant/agent_runner_with_span.py`:

```python
"""Q16 compliant — agent runner opens an OTel span.

Pretend-path: backend/src/agents/log/runners/run.py
"""
from opentelemetry import trace

tracer = trace.get_tracer(__name__)


async def run(payload: dict) -> dict:
    with tracer.start_as_current_span("log_agent.run"):
        return {"ok": True}
```

`compliant/error_reporter_console.tsx`:

```tsx
/* Q16 compliant — console.warn allowed inside errorReporter.ts.

Pretend-path: frontend/src/lib/errorReporter.ts
*/
export const reportError = (err: unknown): void => {
  console.warn("[errorReporter]", err);
};
```

### Task 4.4: Write the failing test

Create `tests/harness/checks/test_logging_policy.py`:

```python
"""H.1c.4 — logging_policy check tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness._helpers import assert_check_fires, assert_check_silent

CHECK = "logging_policy"
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / CHECK


@pytest.mark.parametrize(
    "fixture_name,expected_rule,pretend_path",
    [
        ("uses_print.py", "Q16.no-print-in-prod", "backend/src/services/foo.py"),
        ("uses_console_log.tsx", "Q16.no-console-in-frontend", "frontend/src/components/Foo.tsx"),
        ("bare_logging_import.py", "Q16.no-bare-logging-on-spine", "backend/src/api/routes_v4.py"),
        ("log_warn_invalid_level.py", "Q16.invalid-log-level", "backend/src/services/foo.py"),
        ("log_no_event.py", "Q16.log-call-needs-event", "backend/src/services/foo.py"),
        ("route_log_no_correlation.py", "Q16.route-log-needs-correlation", "backend/src/api/routes_v4.py"),
        ("agent_runner_no_span.py", "Q16.runner-needs-otel-span", "backend/src/agents/log/runners/run.py"),
    ],
)
def test_violation_fires(fixture_name: str, expected_rule: str, pretend_path: str) -> None:
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / fixture_name,
        expected_rule=expected_rule,
        pretend_path=pretend_path,
    )


@pytest.mark.parametrize(
    "fixture_name,pretend_path",
    [
        ("structlog_with_event.py", "backend/src/services/foo.py"),
        ("route_log_with_correlation.py", "backend/src/api/routes_v4.py"),
        ("agent_runner_with_span.py", "backend/src/agents/log/runners/run.py"),
        ("error_reporter_console.tsx", "frontend/src/lib/errorReporter.ts"),
    ],
)
def test_compliant_silent(fixture_name: str, pretend_path: str) -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / fixture_name,
        pretend_path=pretend_path,
    )
```

### Task 4.5: Run failing test + commit red

```bash
python -m pytest tests/harness/checks/test_logging_policy.py -v
git add tests/harness/fixtures/logging_policy tests/harness/checks/test_logging_policy.py .harness/logging_policy.yaml
git commit -m "$(cat <<'EOF'
test(red): H.1c.4 — logging_policy fixtures + assertions

Seven violation fixtures (print in prod; console.log in frontend; bare
logging import on spine; log.warn invalid level; log call missing event;
route log missing correlation kwarg; agent runner missing OTel span)
plus four compliant counterparts. Policy yaml extended with required
levels, correlation kwargs, OTel-span paths.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 4.6: Implement the check (part 1 — top-level + helpers)

Create `.harness/checks/logging_policy.py`:

```python
#!/usr/bin/env python3
"""Q16 — logging discipline (structlog + OTel + redaction).

Eight rules:
  Q16.no-print-in-prod              — `print(` in backend/src outside observability/logging.py.
  Q16.no-console-in-frontend        — `console.<x>(` in frontend/src outside lib/errorReporter.ts.
  Q16.no-bare-logging-on-spine      — `import logging` on api/storage/agents/learning paths.
  Q16.invalid-log-level             — log.<x> where x not in {debug,info,warning,error,critical}.
  Q16.log-call-needs-event          — log.<x>() without first positional string OR `event=` kwarg.
  Q16.route-log-needs-correlation   — log call inside route handler missing one of
                                       request_id/tenant_id/session_id/correlation_id kwargs.
  Q16.runner-needs-otel-span        — async def under agents/**/runners/ or workflows/runners/
                                       does not call tracer.start_as_current_span as first stmt.
  Q16.observability-presence        — backend/src/observability/logging.py must export
                                       configure_logging AND mention `redact` processor.

H-25:
  Missing input    — exit 2.
  Malformed input  — WARN harness.unparseable.
  Upstream failed  — none.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import re
import sys
from pathlib import Path
from typing import Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from .harness.checks._common import Finding, Severity, emit, walk_python_files  # noqa: E402

DEFAULT_ROOTS = (REPO_ROOT / "backend" / "src", REPO_ROOT / "frontend" / "src")
DEFAULT_POLICY = REPO_ROOT / ".harness" / "logging_policy.yaml"
EXCLUDE_VIRTUAL_PREFIXES = (
    "tests/harness/fixtures/",
    "frontend/dist/",
    "frontend/node_modules/",
    "backend/.venv/",
)
JS_SCANNED_EXTS = {".ts", ".tsx", ".js", ".jsx"}

PRINT_RE = re.compile(r'\bprint\s*\(')
CONSOLE_RE = re.compile(r'\bconsole\.(log|warn|error|debug|info)\s*\(')


def _load_policy(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _matches_any(virtual: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(virtual, g) for g in globs)


def _is_excluded(virtual: str) -> bool:
    return any(virtual.startswith(p) for p in EXCLUDE_VIRTUAL_PREFIXES)


def _is_route_handler(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for dec in fn.decorator_list:
        if (
            isinstance(dec, ast.Call)
            and isinstance(dec.func, ast.Attribute)
            and isinstance(dec.func.value, ast.Name)
            and dec.func.value.id in {"router", "app"}
            and dec.func.attr.lower() in {"get", "post", "put", "patch", "delete"}
        ):
            return True
    return False


def _log_call_info(node: ast.Call) -> tuple[str, list[ast.AST], list[str]] | None:
    """If `node` is a log.<level>(...) call, return (level, positional args, kwargs)."""
    if not (isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)):
        return None
    if node.func.value.id not in {"log", "logger"}:
        return None
    return node.func.attr, list(node.args), [kw.arg or "" for kw in node.keywords]


def _scan_python(path: Path, virtual: str, source: str, policy: dict) -> Iterable[Finding]:
    print_allowed = policy.get("backend_print_allowed_files") or []
    bare_logging_banned = policy.get("bare_logging_banned_paths") or []
    allowed_levels = set(policy.get("allowed_log_levels") or ["debug", "info", "warning", "error", "critical"])
    required_correlation = set(policy.get("required_correlation_kwargs") or [])
    otel_span_paths = policy.get("otel_span_required_paths") or []

    if virtual not in print_allowed:
        for m in PRINT_RE.finditer(source):
            line = source[:m.start()].count("\n") + 1
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=line,
                rule="Q16.no-print-in-prod",
                message="`print(` in production source",
                suggestion="use structlog: `log = structlog.get_logger(__name__); log.info(...)`",
            )

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        yield Finding(
            severity=Severity.WARN,
            file=path,
            line=1,
            rule="harness.unparseable",
            message=f"could not parse {path.name}",
            suggestion="fix syntax",
        )
        return

    # Q16.no-bare-logging-on-spine
    if _matches_any(virtual, bare_logging_banned):
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "logging":
                        yield Finding(
                            severity=Severity.ERROR,
                            file=path,
                            line=node.lineno,
                            rule="Q16.no-bare-logging-on-spine",
                            message="`import logging` on spine path",
                            suggestion="use structlog: `import structlog; log = structlog.get_logger(__name__)`",
                        )
            if isinstance(node, ast.ImportFrom) and node.module == "logging":
                yield Finding(
                    severity=Severity.ERROR,
                    file=path,
                    line=node.lineno,
                    rule="Q16.no-bare-logging-on-spine",
                    message="`from logging import …` on spine path",
                    suggestion="use structlog",
                )

    # Q16.invalid-log-level / Q16.log-call-needs-event
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            info = _log_call_info(node)
            if info is None:
                continue
            level, args, kwargs = info
            if level not in allowed_levels:
                yield Finding(
                    severity=Severity.ERROR,
                    file=path,
                    line=node.lineno,
                    rule="Q16.invalid-log-level",
                    message=f"log.{level}(...) — `{level}` not in allowed levels",
                    suggestion=f"use one of {sorted(allowed_levels)}",
                )
            has_event_positional = (
                args and isinstance(args[0], ast.Constant) and isinstance(args[0].value, str)
            )
            has_event_kwarg = "event" in kwargs
            if not (has_event_positional or has_event_kwarg):
                yield Finding(
                    severity=Severity.ERROR,
                    file=path,
                    line=node.lineno,
                    rule="Q16.log-call-needs-event",
                    message=f"log.{level}(...) missing event name (positional string or event=)",
                    suggestion='log.info("event_name", attr=value)',
                )

    # Q16.route-log-needs-correlation
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_route_handler(node):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    info = _log_call_info(sub)
                    if info is None:
                        continue
                    _, _, kwargs = info
                    if not (set(kwargs) & required_correlation):
                        yield Finding(
                            severity=Severity.ERROR,
                            file=path,
                            line=sub.lineno,
                            rule="Q16.route-log-needs-correlation",
                            message=f"log call inside route handler missing one of {sorted(required_correlation)}",
                            suggestion="add request_id=... (or tenant/session/correlation) to the log call",
                        )

    # Q16.runner-needs-otel-span
    if _matches_any(virtual, otel_span_paths):
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef):
                if not _starts_with_span(node):
                    yield Finding(
                        severity=Severity.ERROR,
                        file=path,
                        line=node.lineno,
                        rule="Q16.runner-needs-otel-span",
                        message=f"async runner `{node.name}` does not open an OTel span",
                        suggestion='wrap body with `with tracer.start_as_current_span("<name>"):`',
                    )


def _starts_with_span(fn: ast.AsyncFunctionDef) -> bool:
    if not fn.body:
        return False
    first = fn.body[0]
    # tolerate a docstring before the with-block
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        if len(fn.body) < 2:
            return False
        first = fn.body[1]
    if isinstance(first, ast.With) or isinstance(first, ast.AsyncWith):
        for item in first.items:
            ce = item.context_expr
            if (
                isinstance(ce, ast.Call)
                and isinstance(ce.func, ast.Attribute)
                and ce.func.attr == "start_as_current_span"
            ):
                return True
    return False


def _scan_frontend(path: Path, virtual: str, source: str, policy: dict) -> Iterable[Finding]:
    allowed = policy.get("frontend_console_allowed_files") or []
    if virtual in allowed:
        return
    for m in CONSOLE_RE.finditer(source):
        line = source[:m.start()].count("\n") + 1
        yield Finding(
            severity=Severity.ERROR,
            file=path,
            line=line,
            rule="Q16.no-console-in-frontend",
            message=f"`console.{m.group(1)}(` in production frontend",
            suggestion="route via @/lib/errorReporter.ts",
        )


def _scan_observability_presence(root: Path) -> Iterable[Finding]:
    obs = root / "src" / "observability" / "logging.py"
    if not obs.exists():
        yield Finding(
            severity=Severity.ERROR,
            file=obs,
            line=0,
            rule="Q16.observability-presence",
            message="backend/src/observability/logging.py missing",
            suggestion="add the module (Sprint H.0b Story 9)",
        )
        return
    text = obs.read_text(encoding="utf-8")
    if "configure_logging" not in text:
        yield Finding(
            severity=Severity.ERROR,
            file=obs,
            line=1,
            rule="Q16.observability-presence",
            message="logging.py does not export configure_logging()",
            suggestion="define and export `configure_logging()`",
        )
    if "redact" not in text.lower():
        yield Finding(
            severity=Severity.ERROR,
            file=obs,
            line=1,
            rule="Q16.observability-presence",
            message="logging.py does not register a redact processor",
            suggestion="add a redact_secrets processor to structlog config",
        )


def _scan_file(path: Path, virtual: str, policy: dict) -> Iterable[Finding]:
    if _is_excluded(virtual):
        return
    if path.suffix == ".py":
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return
        yield from _scan_python(path, virtual, source, policy)
    elif path.suffix in JS_SCANNED_EXTS:
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return
        yield from _scan_frontend(path, virtual, source, policy)


def scan(roots: Iterable[Path], policy_path: Path, pretend_path: str | None) -> int:
    policy = _load_policy(policy_path)
    total_errors = 0
    backend_root = REPO_ROOT / "backend"
    if any(root.is_dir() for root in roots) and backend_root.exists():
        for finding in _scan_observability_presence(backend_root):
            emit(finding)
            if finding.severity == Severity.ERROR:
                total_errors += 1
    for root in roots:
        if not root.exists():
            emit(Finding(
                severity=Severity.ERROR,
                file=root,
                line=0,
                rule="harness.target-missing",
                message=f"target path does not exist: {root}",
                suggestion="pass an existing file or directory via --target",
            ))
            return 2
        if root.is_file():
            virtual = pretend_path or (str(root.relative_to(REPO_ROOT)) if root.is_relative_to(REPO_ROOT) else root.name)
            files = [(root, virtual)]
        else:
            files = []
            for p in root.rglob("*"):
                if p.is_file() and (p.suffix == ".py" or p.suffix in JS_SCANNED_EXTS):
                    virtual = str(p.relative_to(REPO_ROOT)) if p.is_relative_to(REPO_ROOT) else p.name
                    files.append((p, virtual))
        for path, virtual in files:
            for finding in _scan_file(path, virtual, policy):
                emit(finding)
                if finding.severity == Severity.ERROR:
                    total_errors += 1
    return 1 if total_errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, action="append")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--pretend-path", type=str)
    args = parser.parse_args(argv)
    roots = tuple(args.target) if args.target else DEFAULT_ROOTS
    return scan(roots, args.policy, args.pretend_path)


if __name__ == "__main__":
    sys.exit(main())
```

### Task 4.7: Run tests, expect green

```bash
python -m pytest tests/harness/checks/test_logging_policy.py -v
```

### Task 4.8: Triage live-repo run

```bash
python .harness/checks/logging_policy.py
```

Expected hot spots:

- `Q16.no-print-in-prod` may fire in CLI scripts under `tools/` — scope of this rule is `backend/src/`, not `tools/`, so should be quiet there.
- `Q16.log-call-needs-event` will likely fire on legacy log calls. Triage: add event names to top-20 chattiest call-sites; baseline rest.
- `Q16.route-log-needs-correlation` will fire on every route handler that logs without correlation context. Add `request_id` to logger binds via middleware — separate PR.
- `Q16.runner-needs-otel-span` will fire on every existing agent runner. Wrap top-3 critical runners (orchestrator, log_agent, k8s_agent); baseline rest.
- `Q16.observability-presence` MUST pass.

### Task 4.9: Write tracing helper if missing

If `Q16.runner-needs-otel-span` fires on **every** runner, the `tracer` symbol may be missing repo-wide. Confirm `backend/src/observability/tracing.py` exists with:

```python
from opentelemetry import trace
tracer = trace.get_tracer(__name__)
```

If not, file a tracking ticket and baseline this rule for Sprint H.1c (defer fix to follow-up).

### Task 4.10: Run validate-fast

```bash
python tools/run_validate.py --fast
```

### Task 4.11: Commit green

```bash
git add .harness/checks/logging_policy.py
git commit -m "$(cat <<'EOF'
feat(green): H.1c.4 — logging_policy enforces Q16

Eight rules: no print in backend/src (except observability/logging.py);
no console.* in frontend/src (except lib/errorReporter.ts); bare logging
import banned on spine; log levels constrained to debug/info/warning/
error/critical; log calls must have event name; route-handler log calls
must include a correlation kwarg; async runners under agents/**/runners
and workflows/runners must open an OTel span; observability/logging.py
must export configure_logging + register a redact processor. H-25
docstring covers missing/malformed/no-upstream.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 4.12: Verify discovery

```bash
python tools/run_validate.py --fast 2>&1 | grep "check:logging_policy"
```

---

# Story H.1c.5 — `error_handling_policy.py` (Q17)

**Rule families enforced (9):**
1. Functions in `backend/src/api/`, `backend/src/storage/gateway.py`, `backend/src/agents/**/runners/` whose name starts with `try_`, `attempt_`, `fetch_`, `parse_`, `validate_`, `lookup_` MUST return a `Result[T, E]` (annotation contains `Result[`) — these are the documented "expected outcome" surfaces.
2. `raise Exception(` / `raise BaseException(` BANNED — must raise a specific subclass from `backend/src/errors/` or stdlib equivalents.
3. Bare `except:` / `except Exception:` MUST NOT swallow — every except block MUST either re-raise OR call `log.error(...)` OR return a `Result.err(...)` value. Heuristic: an except body that contains neither `raise`, `log.error`/`log.warning`, nor `Result.err`/`Err(` is a swallow.
4. Every outbound `httpx.AsyncClient(...).get(...)`/`.post(...)`/`.request(...)` call site MUST be wrapped by `with_retry` (presence in same file OR caller chain) OR be inside `backend/src/utils/http.py` itself. Heuristic: the file imports `with_retry` from `backend.src.utils.http`.
5. Every FastAPI exception handler (`@app.exception_handler(...)`) MUST return a `JSONResponse` with `media_type="application/problem+json"` (Q17 RFC 7807).
6. Every FastAPI route raising via `HTTPException(...)` MUST pass `headers={"Content-Type": "application/problem+json"}` OR raise from a custom subclass listed in `.harness/error_handling_policy.yaml.problem_subclasses`.
7. Every page-level component under `frontend/src/pages/*.tsx` MUST be wrapped by an `<ErrorBoundary>` either at definition site or in `router.tsx`. Heuristic: the page file imports `ErrorBoundary` OR `router.tsx` wraps the page in `<ErrorBoundary>`.
8. `useQuery` / `useMutation` calls in `frontend/src/hooks/` MUST handle `.error` (assigned to const + referenced) OR pass an `onError` callback. Heuristic: the destructuring includes `error` AND that name is referenced again.
9. `frontend/src/main.tsx` (or `index.tsx`) MUST wrap the app root in `<ErrorBoundary>` (top-level catch-all).

**Files:**
- Create: `.harness/error_handling_policy.yaml` (extend if H.0b created stub)
- Create: `.harness/checks/error_handling_policy.py`
- Create: `tests/harness/fixtures/error_handling_policy/violation/api_no_result.py`
- Create: `tests/harness/fixtures/error_handling_policy/violation/raise_bare_exception.py`
- Create: `tests/harness/fixtures/error_handling_policy/violation/swallowed_except.py`
- Create: `tests/harness/fixtures/error_handling_policy/violation/outbound_no_retry.py`
- Create: `tests/harness/fixtures/error_handling_policy/violation/exception_handler_wrong_media.py`
- Create: `tests/harness/fixtures/error_handling_policy/violation/page_no_error_boundary.tsx`
- Create: `tests/harness/fixtures/error_handling_policy/violation/usequery_no_error_handling.tsx`
- Create: `tests/harness/fixtures/error_handling_policy/compliant/api_returns_result.py`
- Create: `tests/harness/fixtures/error_handling_policy/compliant/with_retry_outbound.py`
- Create: `tests/harness/fixtures/error_handling_policy/compliant/page_with_boundary.tsx`
- Create: `tests/harness/fixtures/error_handling_policy/compliant/usequery_handles_error.tsx`
- Create: `tests/harness/checks/test_error_handling_policy.py`

### Task 5.1: Extend `.harness/error_handling_policy.yaml`

```yaml
result_required_path_globs:
  - backend/src/api/**
  - backend/src/storage/gateway.py
  - backend/src/agents/**/runners/**

result_required_function_prefixes:
  - try_
  - attempt_
  - fetch_
  - parse_
  - validate_
  - lookup_

problem_subclasses:
  - ProblemHTTPException
  - DomainError
  - ValidationProblem

retry_helper_module: backend.src.utils.http
retry_helper_name: with_retry
```

### Task 5.2: Create violation fixtures

```bash
mkdir -p tests/harness/fixtures/error_handling_policy/{violation,compliant}
```

`violation/api_no_result.py`:

```python
"""Q17 violation — API surface function returns plain dict, not Result.

Pretend-path: backend/src/api/routes_v4.py
"""
async def fetch_incident(incident_id: str) -> dict:
    return {"id": incident_id}
```

`violation/raise_bare_exception.py`:

```python
"""Q17 violation — raise Exception(...) banned.

Pretend-path: backend/src/services/foo.py
"""
def explode() -> None:
    raise Exception("something")
```

`violation/swallowed_except.py`:

```python
"""Q17 violation — except block neither re-raises nor logs nor returns Result.

Pretend-path: backend/src/services/foo.py
"""
def safe_call() -> int:
    try:
        return 1 // 0
    except Exception:
        return 0
```

`violation/outbound_no_retry.py`:

```python
"""Q17 violation — outbound call without with_retry.

Pretend-path: backend/src/services/fetcher.py
"""
import httpx


async def fetch() -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.get("https://example.com")
        return resp.text
```

`violation/exception_handler_wrong_media.py`:

```python
"""Q17 violation — exception handler does not emit application/problem+json.

Pretend-path: backend/src/api/routes_v4.py
"""
from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI()


@app.exception_handler(ValueError)
async def handle_value_error(request, exc) -> JSONResponse:
    return JSONResponse(status_code=400, content={"error": str(exc)})
```

`violation/page_no_error_boundary.tsx`:

```tsx
/* Q17 violation — page component not wrapped in ErrorBoundary anywhere.

Pretend-path: frontend/src/pages/Incidents.tsx
*/
export const IncidentsPage = () => <div>incidents</div>;
```

`violation/usequery_no_error_handling.tsx`:

```tsx
/* Q17 violation — useQuery destructures only `data`; no error handling.

Pretend-path: frontend/src/hooks/useFoo.ts
*/
import { useQuery } from "@tanstack/react-query";

export const useFoo = () => {
  const { data } = useQuery({ queryKey: ["foo"], queryFn: () => Promise.resolve(1) });
  return data;
};
```

### Task 5.3: Create compliant fixtures

`compliant/api_returns_result.py`:

```python
"""Q17 compliant — fetch_* function returns Result[T, E].

Pretend-path: backend/src/api/routes_v4.py
"""
from backend.src.errors.Result import Result, Err, Ok


async def fetch_incident(incident_id: str) -> Result[dict, str]:
    if not incident_id:
        return Err("empty id")
    return Ok({"id": incident_id})
```

`compliant/with_retry_outbound.py`:

```python
"""Q17 compliant — outbound call wrapped with with_retry.

Pretend-path: backend/src/services/fetcher.py
"""
import httpx
from backend.src.utils.http import with_retry


@with_retry()
async def fetch() -> str:
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get("https://example.com")
        return resp.text
```

`compliant/page_with_boundary.tsx`:

```tsx
/* Q17 compliant — page wraps content in ErrorBoundary.

Pretend-path: frontend/src/pages/Incidents.tsx
*/
import { ErrorBoundary } from "@/components/ui/ErrorBoundary";

export const IncidentsPage = () => (
  <ErrorBoundary>
    <div>incidents</div>
  </ErrorBoundary>
);
```

`compliant/usequery_handles_error.tsx`:

```tsx
/* Q17 compliant — useQuery exposes error and consumer references it.

Pretend-path: frontend/src/hooks/useFoo.ts
*/
import { useQuery } from "@tanstack/react-query";

export const useFoo = () => {
  const { data, error } = useQuery({ queryKey: ["foo"], queryFn: () => Promise.resolve(1) });
  if (error) console.warn(error);
  return data;
};
```

### Task 5.4: Write the failing test

Create `tests/harness/checks/test_error_handling_policy.py`:

```python
"""H.1c.5 — error_handling_policy check tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness._helpers import assert_check_fires, assert_check_silent

CHECK = "error_handling_policy"
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / CHECK


@pytest.mark.parametrize(
    "fixture_name,expected_rule,pretend_path",
    [
        ("api_no_result.py", "Q17.api-must-return-result", "backend/src/api/routes_v4.py"),
        ("raise_bare_exception.py", "Q17.no-bare-exception", "backend/src/services/foo.py"),
        ("swallowed_except.py", "Q17.no-swallowed-except", "backend/src/services/foo.py"),
        ("outbound_no_retry.py", "Q17.outbound-needs-retry", "backend/src/services/fetcher.py"),
        ("exception_handler_wrong_media.py", "Q17.problem-json-required", "backend/src/api/routes_v4.py"),
        ("page_no_error_boundary.tsx", "Q17.page-needs-error-boundary", "frontend/src/pages/Incidents.tsx"),
        ("usequery_no_error_handling.tsx", "Q17.usequery-needs-error-handling", "frontend/src/hooks/useFoo.ts"),
    ],
)
def test_violation_fires(fixture_name: str, expected_rule: str, pretend_path: str) -> None:
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / fixture_name,
        expected_rule=expected_rule,
        pretend_path=pretend_path,
    )


@pytest.mark.parametrize(
    "fixture_name,pretend_path",
    [
        ("api_returns_result.py", "backend/src/api/routes_v4.py"),
        ("with_retry_outbound.py", "backend/src/services/fetcher.py"),
        ("page_with_boundary.tsx", "frontend/src/pages/Incidents.tsx"),
        ("usequery_handles_error.tsx", "frontend/src/hooks/useFoo.ts"),
    ],
)
def test_compliant_silent(fixture_name: str, pretend_path: str) -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / fixture_name,
        pretend_path=pretend_path,
    )
```

### Task 5.5: Run failing test + commit red

```bash
python -m pytest tests/harness/checks/test_error_handling_policy.py -v
git add tests/harness/fixtures/error_handling_policy tests/harness/checks/test_error_handling_policy.py .harness/error_handling_policy.yaml
git commit -m "$(cat <<'EOF'
test(red): H.1c.5 — error_handling_policy fixtures + assertions

Seven violation fixtures (api fn returning dict not Result; raise bare
Exception; swallowed except block; outbound httpx without with_retry;
exception handler not emitting problem+json; page without ErrorBoundary;
useQuery without error handling) plus four compliant counterparts.
Policy yaml extended with result-path globs, function prefixes, retry
helper, and problem subclass list.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 5.6: Implement the check

Create `.harness/checks/error_handling_policy.py`:

```python
#!/usr/bin/env python3
"""Q17 — error handling discipline (Result + retry + RFC 7807 + ErrorBoundary).

Nine rules:
  Q17.api-must-return-result       — functions in api/storage/agents-runners
                                      whose name starts with one of the prefixes
                                      must annotate return as `Result[...]`.
  Q17.no-bare-exception            — `raise Exception(...)` / `raise BaseException(...)`.
  Q17.no-swallowed-except          — except block that neither re-raises nor logs nor
                                      returns Result.err.
  Q17.outbound-needs-retry         — file does outbound httpx call without importing
                                      with_retry (and not located inside utils/http.py).
  Q17.problem-json-required        — exception_handler returning JSONResponse with no
                                      `media_type="application/problem+json"`.
  Q17.problem-json-on-httpexception — HTTPException raised without
                                      problem+json content-type (or subclass on allowlist).
  Q17.page-needs-error-boundary    — pages/*.tsx neither imports ErrorBoundary nor
                                      router.tsx wraps the page (file-local heuristic).
  Q17.usequery-needs-error-handling — useQuery/useMutation destructure missing `error`
                                      AND no onError kwarg.
  Q17.app-root-needs-error-boundary — frontend/src/main.tsx (or index.tsx) does not
                                      wrap root in <ErrorBoundary>.

H-25:
  Missing input    — exit 2.
  Malformed input  — WARN harness.unparseable.
  Upstream failed  — none.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import re
import sys
from pathlib import Path
from typing import Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from .harness.checks._common import Finding, Severity, emit, walk_python_files  # noqa: E402

DEFAULT_ROOTS = (REPO_ROOT / "backend" / "src", REPO_ROOT / "frontend" / "src")
DEFAULT_POLICY = REPO_ROOT / ".harness" / "error_handling_policy.yaml"
EXCLUDE_VIRTUAL_PREFIXES = (
    "tests/harness/fixtures/",
    "frontend/dist/",
    "frontend/node_modules/",
    "backend/.venv/",
)
JS_SCANNED_EXTS = {".ts", ".tsx", ".js", ".jsx"}
UTILS_HTTP_PREFIX = "backend/src/utils/http"

OUTBOUND_HTTPX_RE = re.compile(r'\bhttpx\.AsyncClient\b')
HTTPX_VERB_RE = re.compile(r'\b(?:client|cli|c)\.(get|post|put|patch|delete|request)\s*\(')
USE_QUERY_RE = re.compile(r'\b(useQuery|useMutation)\s*\(', re.MULTILINE)
USE_QUERY_DESTRUCT_RE = re.compile(r'const\s*\{\s*([^}]+?)\s*\}\s*=\s*(useQuery|useMutation)', re.DOTALL)


def _load_policy(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _matches_any(virtual: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(virtual, g) for g in globs)


def _is_excluded(virtual: str) -> bool:
    return any(virtual.startswith(p) for p in EXCLUDE_VIRTUAL_PREFIXES)


def _annotation_mentions(ann: ast.AST | None, name: str) -> bool:
    if ann is None:
        return False
    return name in ast.dump(ann)


def _scan_python(path: Path, virtual: str, source: str, policy: dict) -> Iterable[Finding]:
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        yield Finding(
            severity=Severity.WARN,
            file=path,
            line=1,
            rule="harness.unparseable",
            message=f"could not parse {path.name}",
            suggestion="fix syntax",
        )
        return

    result_path_globs = policy.get("result_required_path_globs") or []
    result_prefixes = tuple(policy.get("result_required_function_prefixes") or [])
    retry_module = policy.get("retry_helper_module") or "backend.src.utils.http"
    retry_name = policy.get("retry_helper_name") or "with_retry"
    problem_subclasses = set(policy.get("problem_subclasses") or [])

    in_result_path = _matches_any(virtual, result_path_globs)
    file_imports_with_retry = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == retry_module:
            for alias in node.names:
                if alias.name == retry_name:
                    file_imports_with_retry = True
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == retry_module:
                    file_imports_with_retry = True

    for node in ast.walk(tree):
        # Q17.api-must-return-result
        if (
            in_result_path
            and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith(result_prefixes)
        ):
            if not _annotation_mentions(node.returns, "Result"):
                yield Finding(
                    severity=Severity.ERROR,
                    file=path,
                    line=node.lineno,
                    rule="Q17.api-must-return-result",
                    message=f"{node.name} returns plain type; must use Result[T, E]",
                    suggestion="annotate return as Result[T, E] and return Ok(...)/Err(...)",
                )

        # Q17.no-bare-exception
        if isinstance(node, ast.Raise) and node.exc is not None:
            target = node.exc
            if isinstance(target, ast.Call) and isinstance(target.func, ast.Name):
                if target.func.id in {"Exception", "BaseException"}:
                    yield Finding(
                        severity=Severity.ERROR,
                        file=path,
                        line=node.lineno,
                        rule="Q17.no-bare-exception",
                        message=f"raise {target.func.id}(...)",
                        suggestion="raise a specific subclass from backend/src/errors/",
                    )

        # Q17.no-swallowed-except
        if isinstance(node, ast.Try):
            for handler in node.handlers:
                body_src = ast.dump(ast.Module(body=handler.body, type_ignores=[]))
                if not (
                    "Raise(" in body_src
                    or "log.error" in body_src
                    or "log.warning" in body_src
                    or "Result.err" in body_src
                    or "Err(" in body_src
                ):
                    yield Finding(
                        severity=Severity.ERROR,
                        file=path,
                        line=handler.lineno,
                        rule="Q17.no-swallowed-except",
                        message="except block swallows exception (no raise/log.error/Err return)",
                        suggestion="re-raise, log.error, or return Err(...) — never silently absorb",
                    )

        # Q17.problem-json-required
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                if (
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and dec.func.attr == "exception_handler"
                ):
                    body_src = source.splitlines()[node.lineno - 1: node.end_lineno or node.lineno + 20]
                    body_text = "\n".join(body_src)
                    if "application/problem+json" not in body_text:
                        yield Finding(
                            severity=Severity.ERROR,
                            file=path,
                            line=node.lineno,
                            rule="Q17.problem-json-required",
                            message=f"exception_handler `{node.name}` returns non-problem+json response",
                            suggestion='return JSONResponse(..., media_type="application/problem+json")',
                        )

        # Q17.problem-json-on-httpexception
        if isinstance(node, ast.Raise) and node.exc is not None:
            t = node.exc
            if isinstance(t, ast.Call) and isinstance(t.func, ast.Name) and t.func.id == "HTTPException":
                # check kwargs for headers={"Content-Type": "application/problem+json"}
                ok = False
                for kw in t.keywords:
                    if kw.arg == "headers" and isinstance(kw.value, ast.Dict):
                        for k, v in zip(kw.value.keys, kw.value.values):
                            if (
                                isinstance(k, ast.Constant) and k.value == "Content-Type"
                                and isinstance(v, ast.Constant) and "problem+json" in str(v.value)
                            ):
                                ok = True
                if not ok:
                    yield Finding(
                        severity=Severity.ERROR,
                        file=path,
                        line=node.lineno,
                        rule="Q17.problem-json-on-httpexception",
                        message="HTTPException raised without problem+json content-type",
                        suggestion='add headers={"Content-Type": "application/problem+json"} OR raise a problem subclass',
                    )

    # Q17.outbound-needs-retry
    if not virtual.startswith(UTILS_HTTP_PREFIX) and OUTBOUND_HTTPX_RE.search(source):
        if HTTPX_VERB_RE.search(source) and not file_imports_with_retry:
            line = source.find("httpx.AsyncClient")
            lineno = source[:line].count("\n") + 1 if line >= 0 else 1
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=lineno,
                rule="Q17.outbound-needs-retry",
                message="outbound httpx call without with_retry import",
                suggestion=f"from {retry_module} import {retry_name}; decorate the calling fn",
            )


def _scan_frontend(path: Path, virtual: str, source: str) -> Iterable[Finding]:
    if virtual.startswith("frontend/src/pages/") and path.suffix == ".tsx":
        if "ErrorBoundary" not in source:
            yield Finding(
                severity=Severity.ERROR,
                file=path,
                line=1,
                rule="Q17.page-needs-error-boundary",
                message=f"page {path.name} does not wrap content in ErrorBoundary",
                suggestion="import ErrorBoundary and wrap the root JSX",
            )
    if virtual.startswith("frontend/src/hooks/"):
        for m in USE_QUERY_RE.finditer(source):
            # find the destructuring binding
            window = source[max(0, m.start() - 80):m.start()]
            destruct = USE_QUERY_DESTRUCT_RE.search(window)
            if destruct is None:
                # treat as missing error handling
                line = source[:m.start()].count("\n") + 1
                yield Finding(
                    severity=Severity.ERROR,
                    file=path,
                    line=line,
                    rule="Q17.usequery-needs-error-handling",
                    message=f"{m.group(1)} call result not destructured for error",
                    suggestion="`const { data, error } = useQuery({ ... })` and react to error",
                )
                continue
            names = [n.strip().split(":")[0] for n in destruct.group(1).split(",")]
            if "error" not in names and "onError" not in source[m.start():m.start() + 400]:
                line = source[:m.start()].count("\n") + 1
                yield Finding(
                    severity=Severity.ERROR,
                    file=path,
                    line=line,
                    rule="Q17.usequery-needs-error-handling",
                    message=f"{m.group(1)} destructure does not include `error` and no onError callback",
                    suggestion="add `error` to destructure and surface it to the UI",
                )


def _scan_root_invariants(root: Path) -> Iterable[Finding]:
    main = root / "main.tsx"
    if not main.exists():
        main = root / "index.tsx"
    if not main.exists():
        return
    text = main.read_text(encoding="utf-8")
    if "ErrorBoundary" not in text:
        yield Finding(
            severity=Severity.ERROR,
            file=main,
            line=1,
            rule="Q17.app-root-needs-error-boundary",
            message=f"{main.name} does not wrap root in <ErrorBoundary>",
            suggestion="import { ErrorBoundary } and wrap RouterProvider",
        )


def _scan_file(path: Path, virtual: str, policy: dict) -> Iterable[Finding]:
    if _is_excluded(virtual):
        return
    if path.suffix == ".py":
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return
        yield from _scan_python(path, virtual, source, policy)
    elif path.suffix in JS_SCANNED_EXTS:
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return
        yield from _scan_frontend(path, virtual, source)


def scan(roots: Iterable[Path], policy_path: Path, pretend_path: str | None) -> int:
    policy = _load_policy(policy_path)
    total_errors = 0
    front_root = REPO_ROOT / "frontend" / "src"
    if any(root.is_dir() for root in roots) and front_root.exists():
        for finding in _scan_root_invariants(front_root):
            emit(finding)
            if finding.severity == Severity.ERROR:
                total_errors += 1
    for root in roots:
        if not root.exists():
            emit(Finding(
                severity=Severity.ERROR,
                file=root,
                line=0,
                rule="harness.target-missing",
                message=f"target path does not exist: {root}",
                suggestion="pass an existing file or directory via --target",
            ))
            return 2
        if root.is_file():
            virtual = pretend_path or (str(root.relative_to(REPO_ROOT)) if root.is_relative_to(REPO_ROOT) else root.name)
            files = [(root, virtual)]
        else:
            files = []
            for p in root.rglob("*"):
                if p.is_file() and (p.suffix == ".py" or p.suffix in JS_SCANNED_EXTS):
                    virtual = str(p.relative_to(REPO_ROOT)) if p.is_relative_to(REPO_ROOT) else p.name
                    files.append((p, virtual))
        for path, virtual in files:
            for finding in _scan_file(path, virtual, policy):
                emit(finding)
                if finding.severity == Severity.ERROR:
                    total_errors += 1
    return 1 if total_errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, action="append")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--pretend-path", type=str)
    args = parser.parse_args(argv)
    roots = tuple(args.target) if args.target else DEFAULT_ROOTS
    return scan(roots, args.policy, args.pretend_path)


if __name__ == "__main__":
    sys.exit(main())
```

### Task 5.7: Run tests, expect green

```bash
python -m pytest tests/harness/checks/test_error_handling_policy.py -v
```

### Task 5.8: Triage live-repo run

```bash
python .harness/checks/error_handling_policy.py
```

Expected hot spots:

- `Q17.api-must-return-result` will fire on many existing routes. Refactor top-3 incident-critical routes to return `Result`; baseline rest.
- `Q17.no-bare-exception` may fire in legacy code. Rewrite or baseline.
- `Q17.no-swallowed-except` may fire on existing try/except scaffolding. Each is a real concern; pair with backend lead.
- `Q17.outbound-needs-retry` — every file that calls httpx directly should import with_retry. Triage: refactor top-5 callsites; baseline rest.
- `Q17.problem-json-required` MUST be silent or trivially fixable.
- `Q17.page-needs-error-boundary` likely fires across pages/. Add ErrorBoundary import to each (trivial, 1-line each).
- `Q17.usequery-needs-error-handling` will fire on hooks. Add `, error` to destructure + surface in UI (separate small PRs).
- `Q17.app-root-needs-error-boundary` MUST be silent — fix immediately if it fires.

### Task 5.9: Run validate-fast

```bash
python tools/run_validate.py --fast
```

### Task 5.10: Commit green

```bash
git add .harness/checks/error_handling_policy.py
git commit -m "$(cat <<'EOF'
feat(green): H.1c.5 — error_handling_policy enforces Q17

Nine rules: api/storage/agents-runners functions with try_/attempt_/
fetch_/parse_/validate_/lookup_ prefix must return Result[T, E]; raise
Exception/BaseException banned; except blocks must re-raise/log/return
Err; outbound httpx without with_retry import banned (except utils/
http.py); FastAPI exception_handler must emit application/problem+json;
HTTPException must include problem+json content-type or use a problem
subclass; pages must wrap in ErrorBoundary; useQuery/useMutation must
expose `error` or onError; main.tsx/index.tsx must wrap root in
<ErrorBoundary>. H-25 docstring covers missing/malformed/no-upstream.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 5.11: Verify discovery

```bash
python tools/run_validate.py --fast 2>&1 | grep "check:error_handling_policy"
```

### Task 5.12: (Optional) refactor top-3 highest-impact routes to return Result

Pick three incident-critical routes that surface `Q17.api-must-return-result`. Refactor each to return `Result[T, E]` and translate `Ok`/`Err` into FastAPI responses + problem+json on the `Err` branch. Commit each as `refactor: H.1c.5 — <route> returns Result`.

---

## End-of-sprint acceptance verification

Run from the repo root:

```bash
# 1. All H.1c check tests pass.
python -m pytest tests/harness/checks/ -v

# 2. validate-fast picks up all five new checks (in addition to H.1a + H.1b).
python tools/run_validate.py --fast 2>&1 | grep -E "check:(security_policy_a|security_policy_b|documentation_policy|logging_policy|error_handling_policy)" | wc -l
# Expected: 5

# 3. validate-fast finishes under 30s.
time python tools/run_validate.py --fast
# Expected: real time < 30s. Combined check count now ~23. Use `--no-gitleaks`
# in CI mode if gitleaks subprocess pushes the budget.

# 4. Each check ships paired fixtures.
ls tests/harness/fixtures | sort | grep -E "^(security_policy|documentation_policy|logging_policy|error_handling_policy)"
# Expected:
#   documentation_policy error_handling_policy logging_policy
#   security_policy_a security_policy_b

# 5. Every violation fixture produces ≥ 1 ERROR.
for d in tests/harness/fixtures/*/violation; do
  rule_dir=$(basename $(dirname $d))
  for f in $d/*; do
    [ -f $f ] || continue
    out=$(python .harness/checks/${rule_dir}.py --target $f 2>/dev/null)
    echo "$out" | grep -q "^\[ERROR\]" || echo "FAIL: $f did not fire ERROR"
  done
done
# Expected: no FAIL output.

# 6. H-25 docstrings present on every new check.
for f in .harness/checks/{security_policy_a,security_policy_b,documentation_policy,logging_policy,error_handling_policy}.py; do
  grep -q "Missing input" $f || echo "MISSING H-25 docstring: $f"
done
# Expected: no MISSING output.

# 7. Output format conformance — meta-validator clean against H.1c checks.
python .harness/checks/output_format_conformance.py --target .harness/checks/security_policy_a.py
python .harness/checks/output_format_conformance.py --target .harness/checks/security_policy_b.py
python .harness/checks/output_format_conformance.py --target .harness/checks/documentation_policy.py
python .harness/checks/output_format_conformance.py --target .harness/checks/logging_policy.py
python .harness/checks/output_format_conformance.py --target .harness/checks/error_handling_policy.py
# Expected: each exits 0.
```

---

## Definition of Done — Sprint H.1c

- [ ] All 5 stories' tests pass under `pytest tests/harness/checks/ -v`.
- [ ] All 5 checks discovered by `tools/run_validate.py --fast`.
- [ ] `validate-fast` total wall time < 30s (with H.1a + H.1b + H.1c combined: 23 checks now firing — gitleaks subprocess may dominate; consider `--no-gitleaks` in CI fast tier).
- [ ] Every check has paired violation + compliant fixtures (H-24).
- [ ] Every check's docstring covers the three H-25 questions (with the explicit gitleaks/git-binary upstream-failed branch in security_policy_a + documentation_policy).
- [ ] `output_format_conformance.py` runs clean against every new check (H-16/H-23 binding).
- [ ] Live-repo runs triaged: each check either reports zero ERROR on the live repo, OR documented baseline entries exist (deferred to H.1d.1) with a tracking issue per baselined finding.
- [ ] Each story committed as red → green pair with the canonical commit message shape.

---

**Plan complete and saved to `docs/plans/2026-04-26-harness-sprint-h1c-tasks.md`.**

Two execution options:

1. **Subagent-Driven (this session)** — I dispatch fresh subagent per task, review between tasks, fast iteration.
2. **Parallel Session (separate)** — Open new session with `executing-plans`, batch execution with checkpoints.

Or **hold** and confirm before I author Sprint H.1d.
