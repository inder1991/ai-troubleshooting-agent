"""Fixture: bare except with no log should fire Q16.bare-except-no-log."""

import logging

log = logging.getLogger(__name__)


def fetch():
    try:
        return _do()
    except Exception:
        return None


def _do():
    return 1
