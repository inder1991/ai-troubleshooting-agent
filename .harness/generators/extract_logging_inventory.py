#!/usr/bin/env python3
"""Generator — logging inventory.

Reads backend/src/observability/logging.py to detect structlog processors and
tracing init. Walks spine python files to count `log.<level>(...)` calls and
their correlation kwargs (request_id/tenant_id/session_id/correlation_id).

Output: .harness/generated/logging_inventory.json
Schema: .harness/schemas/generated/logging_inventory.schema.json

H-25:
  Missing input    — exit 0 with empty defaults.
  Malformed input  — skip silently.
  Upstream failed  — none.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / ".harness/generators"))

from _common import iter_python_files, write_generated  # noqa: E402

PROCESSOR_RE = re.compile(r'(?:processors\s*=\s*\[)([^\]]*)\]', re.DOTALL)
PROCESSOR_NAME_RE = re.compile(r'\b([A-Z][\w]+|redact_secrets|add_log_level|add_logger_name|JSONRenderer|TimeStamper)\b')
TRACING_RE = re.compile(r'(?:trace\.set_tracer_provider|TracerProvider\s*\(|init_tracing\s*\()')

LOG_LEVELS = {"info", "warning", "error", "debug", "critical", "exception"}
CORRELATION_KEYS = {"request_id", "tenant_id", "session_id", "correlation_id", "trace_id", "span_id"}


def _extract_processors(text: str) -> list[str]:
    m = PROCESSOR_RE.search(text)
    if not m:
        return []
    body = m.group(1)
    seen: list[str] = []
    for p in PROCESSOR_NAME_RE.findall(body):
        if p not in seen:
            seen.append(p)
    return seen


def _is_log_call(node: ast.AST) -> tuple[str | None, list[str]] | None:
    if not isinstance(node, ast.Call):
        return None
    if not isinstance(node.func, ast.Attribute):
        return None
    level = node.func.attr
    if level not in LOG_LEVELS:
        return None
    kwargs = sorted(kw.arg for kw in node.keywords if kw.arg in CORRELATION_KEYS)
    return level, kwargs


def _scan(root: Path) -> dict:
    """Build {structlog_processors, tracing_initialized, log_calls}."""
    log_cfg = root / "backend" / "src" / "observability" / "logging.py"
    processors: list[str] = []
    tracing = False
    if log_cfg.exists():
        try:
            text = log_cfg.read_text(encoding="utf-8")
            processors = _extract_processors(text)
            tracing = bool(TRACING_RE.search(text))
        except (OSError, UnicodeDecodeError):
            pass
    spine_root = root / "backend" / "src"
    log_calls: list[dict] = []
    if spine_root.exists():
        for path in iter_python_files(spine_root, exclude=("__pycache__", "/venv/", ".venv", "tests")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (OSError, UnicodeDecodeError, SyntaxError):
                continue
            for node in ast.walk(tree):
                info = _is_log_call(node)
                if info is None:
                    continue
                level, kwargs = info
                event = ""
                if (
                    node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    event = node.args[0].value
                log_calls.append({
                    "file": str(path.relative_to(root)),
                    "level": level,
                    "event": event,
                    "correlation_kwargs": kwargs,
                })
    log_calls.sort(key=lambda e: (e["file"], e["level"], e["event"]))
    return {
        "structlog_processors": processors,
        "tracing_initialized": tracing,
        "log_calls": log_calls,
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
    out_path = write_generated("logging_inventory", payload)
    print(f"[INFO] wrote logging_inventory ({len(payload['log_calls'])} calls) → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
