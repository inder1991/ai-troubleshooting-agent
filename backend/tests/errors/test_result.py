"""Sprint H.0b Story 10 — Result[T, E] for expected outcomes (Q17 C)."""

from __future__ import annotations


def test_ok_holds_value() -> None:
    from src.errors.result import Ok
    r = Ok(42)
    assert r.is_ok()
    assert not r.is_err()
    assert r.unwrap() == 42


def test_err_holds_error() -> None:
    from src.errors.result import Err
    err_obj = ValueError("nope")
    r = Err(err_obj)
    assert r.is_err()
    assert not r.is_ok()
    assert r.unwrap_err() is err_obj


def test_ok_unwrap_err_raises() -> None:
    from src.errors.result import Ok
    r = Ok(1)
    import pytest
    with pytest.raises(Exception):
        r.unwrap_err()


def test_err_unwrap_raises() -> None:
    from src.errors.result import Err
    r = Err("oops")
    import pytest
    with pytest.raises(Exception):
        r.unwrap()


def test_result_pattern_match() -> None:
    """Idiomatic match-statement use."""
    from src.errors.result import Ok, Err, Result

    def classify(r: Result[int, str]) -> str:
        match r:
            case Ok(value=v):
                return f"got {v}"
            case Err(error=e):
                return f"failed: {e}"
            case _:
                return "?"

    assert classify(Ok(7)) == "got 7"
    assert classify(Err("boom")) == "failed: boom"
