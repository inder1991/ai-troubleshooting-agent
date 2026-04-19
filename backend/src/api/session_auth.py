"""Session-ownership enforcement (PR-A / SDET audit Bug #6).

The app does not currently have a first-class authentication surface —
all routes are open in single-tenant dev/demo deployments. That's fine
there, but in managed multi-tenant deployments (future work), a
session ID guessed by an attacker would give them write access to
another tenant's investigation, including the `/chat` endpoint which
dispatches user actions to the agents.

This module provides a feature-flag-gated ownership check:

  * At session creation, the route layer captures an ``owner_id`` from
    the request — either a JWT claim (production), or the
    ``X-Session-Owner`` header (dev / test), or ``"anonymous"`` when
    neither is set.
  * The owner is persisted alongside the session in Redis.
  * Sensitive routes call ``require_session_owner(session_id, request)``
    at the top; if ``SESSION_OWNERSHIP_CHECK=on`` and the caller is
    not the recorded owner, the call 403s.

Default: ``SESSION_OWNERSHIP_CHECK=off`` — zero behavior change for
single-tenant installs. Managed deployments set it to ``on`` in their
values overlay.
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import HTTPException, Request

__all__ = [
    "extract_owner_id",
    "enforce_session_owner",
    "SESSION_OWNER_HEADER",
    "ownership_check_enabled",
]

SESSION_OWNER_HEADER = "X-Session-Owner"
_ANONYMOUS = "anonymous"


def ownership_check_enabled() -> bool:
    """Feature-flag read — default OFF so existing single-tenant
    deployments see no behavior change."""
    return os.environ.get("SESSION_OWNERSHIP_CHECK", "off").lower() == "on"


def extract_owner_id(request: Request) -> str:
    """Return the caller's owner identifier.

    Precedence:
      1. ``request.state.owner_id`` — set by a future auth middleware
         that parses JWT claims / session cookies. Preferred in
         production.
      2. ``X-Session-Owner`` header — useful in dev + test contexts
         and in programmatic clients that handle auth outside of this
         service.
      3. ``"anonymous"`` — the always-on fallback. With the feature
         flag off, every caller is effectively anonymous; with it on,
         ``anonymous`` never matches a real owner, so anonymous
         callers can't access any owned session.
    """
    owner = getattr(request.state, "owner_id", None)
    if isinstance(owner, str) and owner:
        return owner
    header_val = request.headers.get(SESSION_OWNER_HEADER)
    if header_val:
        return header_val.strip()
    return _ANONYMOUS


def enforce_session_owner(
    session: Optional[dict],
    request: Request,
) -> None:
    """Raise HTTPException(403) when the caller isn't the session owner.

    No-op when the feature flag is off or when the session doesn't have
    an ``owner_id`` recorded (backfills gracefully).
    """
    if not ownership_check_enabled():
        return
    if session is None:
        return
    recorded = session.get("owner_id")
    if not recorded:
        # Legacy session that pre-dates ownership tracking — allow, so
        # turning the flag on mid-flight doesn't nuke in-flight
        # investigations. New sessions created after flag-on always
        # carry owner_id.
        return
    caller = extract_owner_id(request)
    if caller != recorded:
        raise HTTPException(
            status_code=403,
            detail="You do not have access to this session.",
        )
