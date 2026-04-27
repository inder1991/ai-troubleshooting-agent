"""Shared helpers for .harness/checks/ scripts.

Spine paths (#10): checks should resolve their default scan roots via
`spine_paths(role, fallback)` instead of hardcoding `REPO_ROOT / "backend"`.
This lets a consumer override paths via `.harness/spine_paths.yaml` without
forking the check. The fallback is the previous hardcoded value, kept for
backward compat with consumers that don't yet ship spine_paths.yaml.

Per H-16 / H-23, every check emits structured one-line records:

    [SEVERITY] file=<path>:<line> rule=<rule-id> message="..." suggestion="..."

`emit()` is the single point where that format is constructed, so
changing the format later is a one-file change.

`load_baseline(rule_file_stem)` returns the set of (file, line, rule)
tuples the check should suppress. Per H.1d.6 — first-class baselining of
H.1a/b/c live-repo violations until the underlying code can be migrated.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterable, Literal

Severity = Literal["ERROR", "WARN", "INFO"]

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_baseline(rule_file_stem: str) -> set[tuple[str, int, str]]:
    """Load `.harness/baselines/<rule_file_stem>_baseline.json` and return a
    set of (file, line, rule) tuples for filtering.

    Each baseline entry must have at least {file, line, rule} keys; extras
    ignored. Empty set on missing/unparseable file (the surrounding check
    pipeline still surfaces real findings; `harness_policy_schema` in
    H.1d.4 will yell loudly about a malformed baseline).
    """
    baseline_path = REPO_ROOT / ".harness/baselines" / f"{rule_file_stem}_baseline.json"
    if not baseline_path.exists():
        return set()
    try:
        data = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(data, list):
        return set()
    out: set[tuple[str, int, str]] = set()
    for entry in data:
        if isinstance(entry, dict) and {"file", "line", "rule"} <= set(entry.keys()):
            out.add((str(entry["file"]), int(entry["line"]), str(entry["rule"])))
    return out


def emit(
    severity: Severity,
    file: Path | str,
    rule: str,
    message: str,
    suggestion: str,
    line: int | None = None,
    out=sys.stdout,
) -> None:
    """Write one structured violation record (H-16 / H-23 format)."""
    location = f"{file}:{line}" if line is not None else str(file)
    safe_msg = message.replace('"', "'")
    safe_sug = suggestion.replace('"', "'")
    print(
        f'[{severity}] file={location} rule={rule} '
        f'message="{safe_msg}" suggestion="{safe_sug}"',
        file=out,
    )


def walk_files(
    roots: Iterable[Path],
    suffixes: tuple[str, ...],
    skip_dirs: tuple[str, ...] = ("node_modules", ".git", "__pycache__", ".venv"),
) -> Iterable[Path]:
    """Yield every file under any of the roots whose suffix matches.

    H-25: handles missing roots silently (no exception) — upstream may
    not have a frontend/ or backend/ layout in every repo.
    """
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in suffixes:
                continue
            if any(part in skip_dirs for part in path.parts):
                continue
            yield path


_SPINE_PATHS_CACHE: dict | None = None


def _load_spine_paths() -> dict:
    """Read .harness/spine_paths.yaml once per process; cache the result."""
    global _SPINE_PATHS_CACHE
    if _SPINE_PATHS_CACHE is not None:
        return _SPINE_PATHS_CACHE
    spine_yaml = REPO_ROOT / ".harness" / "spine_paths.yaml"
    if not spine_yaml.exists():
        _SPINE_PATHS_CACHE = {}
        return _SPINE_PATHS_CACHE
    try:
        import yaml  # local import — kept off the top-level so checks
                     # without a yaml dep aren't penalized
        data = yaml.safe_load(spine_yaml.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001 — best-effort; missing yaml lib falls through
        data = {}
    _SPINE_PATHS_CACHE = data
    return data


def spine_paths(role: str, fallback: tuple[str, ...]) -> tuple[Path, ...]:
    """Resolve the consumer's spine paths for `role`.

    Reads `.harness/spine_paths.yaml`; if `role` is declared there,
    returns those paths (relative resolution against REPO_ROOT). Otherwise
    returns `fallback` (which is the historical hardcoded default —
    typically `("backend/src",)` or similar). Always returns a tuple of
    Path objects, regardless of whether each path exists on disk.

    Example:
        DEFAULT_ROOTS = spine_paths("backend_api", ("backend/src/api",))
    """
    data = _load_spine_paths()
    raw = data.get(role) if isinstance(data, dict) else None
    chosen = raw if isinstance(raw, list) and raw else list(fallback)
    return tuple(REPO_ROOT / p for p in chosen)
