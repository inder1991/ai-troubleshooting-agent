"""Fixture: f-string in logger.info should fire Q16.f-string-in-log."""

import logging

log = logging.getLogger(__name__)


def go(user_id):
    log.info(f"user {user_id} logged in")
