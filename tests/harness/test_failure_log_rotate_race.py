"""B10 (v1.1.1) — _rotate_failure_log must hold LOCK_EX over the rename.

B2 (v1.1.0) put fcntl.LOCK_EX around append. The rotate path was
unguarded — two parallel validate-fast processes could both observe
size > cap and both rename onto .1, clobbering the first rotation's
bytes.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _rotate_worker(log_path_str: str) -> None:
    sys.path.insert(0, str(REPO_ROOT))
    from tools import run_validate
    run_validate.FAILURE_LOG_PATH = Path(log_path_str)
    run_validate.FAILURE_LOG_MAX_BYTES = 100
    run_validate._rotate_failure_log()


def test_concurrent_rotates_dont_lose_entries():
    """10 concurrent rotate calls must not corrupt the .1 file."""
    with tempfile.TemporaryDirectory() as td:
        log = Path(td) / "log.jsonl"
        with log.open("w") as fh:
            for i in range(50):
                fh.write(json.dumps({"i": i}) + "\n")
        size_before = log.stat().st_size
        assert size_before > 100

        with mp.Pool(10) as pool:
            pool.map(_rotate_worker, [str(log)] * 10)

        rotated = log.with_suffix(log.suffix + ".1")
        assert rotated.exists(), "rotation never produced .1"
        assert rotated.stat().st_size == size_before, (
            f".1 size {rotated.stat().st_size} != original {size_before}; "
            "concurrent rotates clobbered each other"
        )
        if log.exists():
            assert log.stat().st_size < size_before
