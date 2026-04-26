"""Q9 compliant — Hypothesis-decorated test covering calibrate.

Pretend-path: backend/tests/learning/test_calibrator.py
"""
from hypothesis import given, strategies as st


def calibrate(score: float) -> float:
    return max(0.0, min(1.0, score))


@given(st.floats(allow_nan=False, allow_infinity=False))
def test_calibrate_in_range(score: float) -> None:
    assert 0.0 <= calibrate(score) <= 1.0
