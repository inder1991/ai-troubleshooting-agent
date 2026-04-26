"""Fixture: structured logger calls with lazy formatting and no secrets."""

import logging

log = logging.getLogger(__name__)


def handle_request(user_id):
    log.info("user %s logged in", user_id)
    try:
        return _do()
    except ValueError as exc:
        log.exception("do failed: %s", exc)
        return None


def _do():
    return 1
