"""Eval runner — replay labelled incidents and compute aggregate metrics.

Usage:
    python -m eval.runner --corpus backend/eval/incidents --out report.json

Status: **scaffold**. The metric layer (``metrics.py``) is complete and
fully tested; loading labelled cases + driving a replay supervisor is
gated on the eval corpus (≥10 labelled incidents). Per the Phase-4 gate
decision, corpus < 10 -> this runner emits an empty report and exits 0
rather than failing CI or claiming a spurious result.

When the corpus fills up:
  1. Drop the ``_load_corpus`` stub and parse the YAML incidents.
  2. Wire ``build_supervisor_for_replay(c)`` to the factory once it
     exists (blocked on the orchestration swap into run_v5).
  3. Remove the sentinel in ``run_eval``.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from eval.metrics import Case, EvalReport, build_report


_CORPUS_MIN: int = 10


def _load_corpus(corpus_dir: Path) -> list[Case]:
    """Load labelled cases from YAML files in ``corpus_dir``.

    Stub: returns []. The YAML parser + replay wiring land once the
    corpus has been populated.
    """
    return []


async def run_eval(corpus_dir: str = "backend/eval/incidents") -> EvalReport:
    corpus = _load_corpus(Path(corpus_dir))
    if len(corpus) < _CORPUS_MIN:
        # Honest "no corpus" report — not a fake pass.
        return EvalReport(
            top1_accuracy=0.0,
            ece=0.0,
            high_confidence_wrong_count=0,
            total_cases=len(corpus),
        )
    return build_report(corpus)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Run the eval harness.")
    p.add_argument("--corpus", default="backend/eval/incidents")
    p.add_argument("--out", default=None, help="Write JSON report to this path.")
    args = p.parse_args(argv)

    import asyncio
    report = asyncio.run(run_eval(args.corpus))
    payload = asdict(report)
    if args.out:
        Path(args.out).write_text(json.dumps(payload, indent=2))
    else:
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
