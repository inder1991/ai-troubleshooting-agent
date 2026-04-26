"""Fixture: secret-shaped literal in log call should fire Q16.secret-shaped-log-literal."""

import logging

log = logging.getLogger(__name__)


def go():
    log.info("user posted Authorization: Bearer abc123")
