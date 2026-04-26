"""Synthetic test file for generator inventory."""
from hypothesis import given, strategies as st


def test_smoke() -> None:
    assert 1 == 1


@given(st.integers())
def test_property(x: int) -> None:
    assert x == x
