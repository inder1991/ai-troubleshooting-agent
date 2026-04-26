"""Fixture: silent except pass should fire Q17.no-pass-in-except."""


def fetch():
    try:
        return _do()
    except ValueError:
        pass


def _do():
    return 1
