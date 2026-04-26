"""Fixture: re-raise without `from exc` should fire Q17.reraise-without-from."""


def fetch():
    try:
        return _do()
    except ValueError as exc:
        raise RuntimeError("wrapped failure")


def _do():
    return 1
