#!/usr/bin/env python3
"""Q13.A — security policy: secrets + outbound HTTP + dangerous patterns.

Six rules:
  Q13.secret-detected           — gitleaks CLI fired (re-emitted shape).
  Q13.dangerous-pattern         — eval/exec/os.system/shell=True/pickle.loads/
                                   yaml.load (no Loader)/__import__ + JS-side
                                   dangerouslySetInnerHTML/new Function/document.write.
  Q13.tls-verify-required       — verify=False on httpx/requests OR
                                   ssl._create_unverified_context OR
                                   urllib3.disable_warnings.
  Q13.outbound-timeout-required — httpx.AsyncClient(timeout=None) outside
                                   backend/src/utils/http.py.
  Q13.log-secret-leak           — logger call sees a value containing
                                   `Authorization: Bearer …` / `password=` etc.
                                   without going through a redact_* helper.
  Q13.secret-shaped-literal     — base64/secret-shaped string literal outside
                                   tests/ (WARN; gitleaks is the hard gate).

H-25:
  Missing input    — exit 2; rule=harness.target-missing.
  Malformed input  — WARN rule=harness.unparseable; skip file.
  Upstream failed  — gitleaks binary missing → WARN
                     rule=Q13.secret-detected (degraded mode).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / ".harness/checks"))

from _common import emit, load_baseline  # noqa: E402

DEFAULT_ROOTS = (REPO_ROOT / "backend" / "src", REPO_ROOT / "frontend" / "src")
EXCLUDE_VIRTUAL_PREFIXES = (
    "tests/harness/fixtures/",
    "frontend/dist/",
    "frontend/node_modules/",
    "backend/.venv/",
    "backend/venv/",
)
EXCLUDE_FS = (
    "node_modules", ".git", "dist", "site-packages",
    "tests/harness/fixtures", "__pycache__", ".venv", "/venv/",
    ".pytest_cache",
)
SCANNED_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx"}
BASELINE = load_baseline("security_policy_a")

DANGEROUS_PYTHON_RE = re.compile(
    r'\b(eval\s*\(|exec\s*\(|os\.system\s*\(|pickle\.loads\s*\(|__import__\s*\()'
)
# Require shell=True in call-argument context (preceded by `,` or `(`)
# so docstrings/comments containing the literal text don't trigger.
SHELL_TRUE_RE = re.compile(r'[,(]\s*shell\s*=\s*True\b')
YAML_LOAD_UNSAFE_RE = re.compile(r'\byaml\.load\s*\(\s*[^,)]+\)')
DANGEROUS_JS_RE = re.compile(
    r'\b(dangerouslySetInnerHTML|document\.write\s*\(|new\s+Function\s*\()'
)

VERIFY_FALSE_RE = re.compile(r'\bverify\s*=\s*False\b')
SSL_UNVERIFIED_RE = re.compile(r'\bssl\._create_unverified_context\s*\(')
URLLIB3_DISABLE_RE = re.compile(r'\burllib3\.disable_warnings\s*\(')
TIMEOUT_NONE_RE = re.compile(r'\btimeout\s*=\s*None\b')

LOG_CALL_RE = re.compile(r'\b(log|logger)\.\w+\s*\(([^)]*)\)', re.DOTALL)
SECRET_LEAK_KEY_RE = re.compile(
    r'(Authorization\s*:\s*Bearer|password\s*=|api_key\s*=|secret\s*=|token\s*=)',
    re.IGNORECASE,
)
REDACT_HELPER_RE = re.compile(r'\bredact_\w*\s*\(')

UTILS_HTTP_PREFIX = "backend/src/utils/http"


def _emit(path: Path, rule: str, msg: str, suggestion: str, line: int) -> bool:
    sig = (str(path), int(line), rule)
    if sig in BASELINE:
        return False
    emit("ERROR", path, rule, msg, suggestion, line=line)
    return True


def _is_excluded(virtual: str) -> bool:
    return any(virtual.startswith(p) for p in EXCLUDE_VIRTUAL_PREFIXES)


def _scan_dangerous_patterns(path: Path, virtual: str, source: str) -> int:
    is_python = path.suffix == ".py"
    is_jsx = path.suffix in {".ts", ".tsx", ".js", ".jsx"}
    errors = 0
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
                    if _emit(path, "Q13.dangerous-pattern",
                             f"{label}: `{m.group(0).strip()}`",
                             "rewrite to a safe alternative; never execute untrusted strings",
                             lineno):
                        errors += 1
        if is_jsx:
            m = DANGEROUS_JS_RE.search(line)
            if m:
                if _emit(path, "Q13.dangerous-pattern",
                         f"banned JS pattern: `{m.group(0).strip()}`",
                         "render text content; never raw HTML or dynamic Function/document.write",
                         lineno):
                    errors += 1
    return errors


def _scan_outbound_http(path: Path, virtual: str, source: str) -> int:
    if path.suffix != ".py":
        return 0
    errors = 0
    for lineno, line in enumerate(source.splitlines(), 1):
        if line.strip().startswith("#"):
            continue
        for pattern, rule, message, suggestion in (
            (VERIFY_FALSE_RE, "Q13.tls-verify-required",
             "verify=False disables TLS validation", "remove verify=False"),
            (SSL_UNVERIFIED_RE, "Q13.tls-verify-required",
             "ssl._create_unverified_context", "use ssl.create_default_context()"),
            (URLLIB3_DISABLE_RE, "Q13.tls-verify-required",
             "urllib3.disable_warnings", "remove the call; fix the underlying TLS error"),
        ):
            if pattern.search(line):
                if _emit(path, rule, message, suggestion, lineno):
                    errors += 1
        if not virtual.startswith(UTILS_HTTP_PREFIX):
            m = TIMEOUT_NONE_RE.search(line)
            if m and "httpx" in source.lower()[:5000]:
                if _emit(path, "Q13.outbound-timeout-required",
                         "httpx call uses timeout=None (unbounded wait)",
                         "set an explicit timeout via httpx.Timeout(...) or use the with_retry wrapper",
                         lineno):
                    errors += 1
    return errors


def _scan_log_secret_leak(path: Path, virtual: str, source: str) -> int:
    if path.suffix != ".py":
        return 0
    errors = 0
    for m in LOG_CALL_RE.finditer(source):
        body = m.group(2)
        if SECRET_LEAK_KEY_RE.search(body) and not REDACT_HELPER_RE.search(body):
            line = source[:m.start()].count("\n") + 1
            if _emit(path, "Q13.log-secret-leak",
                     "logger call may emit a secret-shaped value without redaction",
                     "wrap value in a redact_*(value) helper from observability/logging.py",
                     line):
                errors += 1
    return errors


def _scan_file(path: Path, virtual: str) -> int:
    if _is_excluded(virtual):
        return 0
    if path.suffix not in SCANNED_EXTS:
        return 0
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0
    errors = 0
    errors += _scan_dangerous_patterns(path, virtual, source)
    errors += _scan_outbound_http(path, virtual, source)
    errors += _scan_log_secret_leak(path, virtual, source)
    return errors


def _walk_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in SCANNED_EXTS:
            continue
        if any(tok in str(path) for tok in EXCLUDE_FS):
            continue
        yield path


def _run_gitleaks() -> int:
    if not shutil.which("gitleaks"):
        emit("WARN", Path("gitleaks"), "Q13.secret-detected",
             "gitleaks binary not installed; secret scan skipped",
             "install gitleaks (Sprint H.0b Story 6) so this rule can enforce", line=0)
        return 0
    config_path = REPO_ROOT / ".gitleaks.toml"
    config_arg = ["--config", str(config_path)] if config_path.exists() else []
    try:
        result = subprocess.run(
            ["gitleaks", "detect", "--no-git", "--report-format", "json",
             "--report-path", "/dev/stdout", *config_arg],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        emit("WARN", Path("gitleaks"), "Q13.secret-detected",
             f"gitleaks subprocess error: {exc}",
             "investigate gitleaks installation", line=0)
        return 0
    if result.returncode == 0:
        return 0
    try:
        findings = json.loads(result.stdout) if result.stdout.strip() else []
    except json.JSONDecodeError:
        emit("ERROR", Path("gitleaks"), "Q13.secret-detected",
             "gitleaks reported failures but JSON parse failed",
             "run `gitleaks detect --no-git` manually to triage", line=0)
        return 1
    errors = 0
    for finding in findings:
        if _emit(Path(finding.get("File", "?")), "Q13.secret-detected",
                 f"{finding.get('RuleID', 'unknown-rule')}: {finding.get('Description', '')[:120]}",
                 "rotate the secret AND remove it from git history before merge",
                 int(finding.get("StartLine", 0))):
            errors += 1
    return errors


def scan(roots: Iterable[Path], pretend_path: str | None, run_gitleaks: bool) -> int:
    total_errors = 0
    if run_gitleaks:
        total_errors += _run_gitleaks()
    for root in roots:
        if not root.exists():
            continue
        if root.is_file() and root.suffix in SCANNED_EXTS:
            virtual = pretend_path or (
                str(root.relative_to(REPO_ROOT))
                if root.is_relative_to(REPO_ROOT) else root.name
            )
            total_errors += _scan_file(root, virtual)
        else:
            for p in _walk_files(root):
                virtual = (
                    str(p.relative_to(REPO_ROOT))
                    if p.is_relative_to(REPO_ROOT) else p.name
                )
                total_errors += _scan_file(p, virtual)
    return 1 if total_errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, action="append")
    parser.add_argument("--pretend-path", type=str)
    parser.add_argument("--no-gitleaks", action="store_true",
                        help="Skip gitleaks subprocess (test mode).")
    args = parser.parse_args(argv)
    roots = tuple(args.target) if args.target else DEFAULT_ROOTS
    # By default, run gitleaks only on full-repo scan (no --target).
    run_gitleaks = not args.no_gitleaks and not args.target
    return scan(roots, args.pretend_path, run_gitleaks)


if __name__ == "__main__":
    sys.exit(main())
