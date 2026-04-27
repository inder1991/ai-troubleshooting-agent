#!/usr/bin/env python3
"""B16 / Q21 — HARNESS_CARD.version must match .harness-version.

One rule:
  Q21.harness-card-version-mismatch
      The version field in `.harness/HARNESS_CARD.yaml` is hand-
      maintained, so it silently drifts from the consumer-facing
      `.harness-version` pin. Bumping the pin without also bumping the
      card (or vice versa) leaves consumers reading a stale "what does
      this harness cover?" manifest.

This check enforces parity between the two by stripping the leading
`v` from the pin (`.harness-version` writes `v1.1.1`; the card writes
`1.1.1`).

H-25:
  Missing input    — return 0 silently if either file is absent (early
                     bootstrap).
  Malformed input  — WARN harness.unparseable on yaml errors.
  Upstream failed  — none.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / ".harness/checks"))

from _common import emit  # noqa: E402

CARD = REPO_ROOT / ".harness/HARNESS_CARD.yaml"
PIN = REPO_ROOT / ".harness-version"


def main() -> int:
    """Compare HARNESS_CARD.version with .harness-version; emit Q21 on drift."""
    if not CARD.exists() or not PIN.exists():
        return 0
    pin_raw = PIN.read_text(encoding="utf-8").strip()
    pin = pin_raw.lstrip("v")
    try:
        card = yaml.safe_load(CARD.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        emit("WARN", CARD, "harness.unparseable",
             f"could not parse {CARD.name}: {exc}", "fix YAML syntax",
             line=1)
        return 0
    card_v = str(card.get("version", "")).strip()
    if pin != card_v:
        emit("ERROR", CARD, "Q21.harness-card-version-mismatch",
             f"HARNESS_CARD.version={card_v!r} but .harness-version={pin_raw!r}",
             f"bump HARNESS_CARD.yaml `version` to {pin!r} in the same commit",
             line=1)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
