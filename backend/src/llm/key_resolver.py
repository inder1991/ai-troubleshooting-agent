"""Pick the right ``ANTHROPIC_API_KEY`` for a given call.

Operators map keys to **logical names** (``premium``, ``cheap``, ``billing-team-a``)
in the Helm chart — the chart never hardcodes model names because Anthropic
ships new models faster than chart releases. The mapping from
``(agent_role, model_id)`` → ``key_name`` lives in the Postgres
``agent_model_routes`` table and is editable via the Settings UI.

This module is the **resolver**: given a key name (or no name → default), it
returns the actual API key string from environment.

Env-var convention rendered by the chart::

    ANTHROPIC_API_KEY                 # the default — required
    ANTHROPIC_API_KEY_PREMIUM         # named override (operator-chosen)
    ANTHROPIC_API_KEY_CHEAP           # named override (operator-chosen)
    ANTHROPIC_API_KEY_BILLING_TEAM_A  # name lower-kebab → upper-snake

Lookup order (first hit wins):

    1. If ``key_name`` is provided and non-empty → look up
       ``ANTHROPIC_API_KEY_<KEY_NAME.upper().replace('-','_')>``.
    2. Else (or if the named env var is missing/empty) → ``ANTHROPIC_API_KEY``.

Raises ``MissingKeyError`` only if BOTH the named key (when requested) AND
the default are missing — operator misconfiguration.

Note on the DB-backed routes table: this module does **not** read it. The
plan ships the routes table + Settings UI as a follow-up app PR. Until that
lands, callers pass ``key_name=None`` and everything uses the default key —
identical behaviour to the pre-multi-key world.
"""
from __future__ import annotations

import os
from typing import Optional

DEFAULT_ENV_VAR = "ANTHROPIC_API_KEY"
NAMED_ENV_PREFIX = "ANTHROPIC_API_KEY_"


class MissingKeyError(RuntimeError):
    """Raised when no usable key is found in environment.

    This is operator misconfiguration, not a transient runtime error — the
    caller should surface it loudly rather than retry.
    """


def _normalize(name: str) -> str:
    """Render a logical key name into its env-var form.

    ``premium``           → ``ANTHROPIC_API_KEY_PREMIUM``
    ``billing-team-a``    → ``ANTHROPIC_API_KEY_BILLING_TEAM_A``
    ``Cheap_Models``      → ``ANTHROPIC_API_KEY_CHEAP_MODELS``
    """
    sanitized = name.strip().upper().replace("-", "_")
    return f"{NAMED_ENV_PREFIX}{sanitized}"


def key_for(key_name: Optional[str] = None) -> str:
    """Return the Anthropic API key to use.

    Parameters
    ----------
    key_name :
        Logical name from the routes table (or None to force the default).
        Empty string is treated identically to None.
    """
    if key_name:
        env_var = _normalize(key_name)
        named = os.environ.get(env_var, "").strip()
        if named:
            return named
        # Named requested but not provided — fall through to default. The
        # operator may intentionally leave a name unmapped (e.g. "cheap" not
        # provisioned in dev). Falling back is safer than crashing.

    default = os.environ.get(DEFAULT_ENV_VAR, "").strip()
    if default:
        return default

    if key_name:
        hint = f" (or the named key '{_normalize(key_name)}' if you intended a named override)"
    else:
        hint = ""
    raise MissingKeyError(f"No Anthropic API key available. Set {DEFAULT_ENV_VAR}{hint}.")


def available_named_keys() -> list[str]:
    """Return logical names of every named key currently in env.

    Useful for the Settings UI to populate the ``key_name`` dropdown when
    creating a routes-table row.
    """
    names = []
    for env_var in os.environ:
        if env_var.startswith(NAMED_ENV_PREFIX) and env_var != DEFAULT_ENV_VAR:
            logical = env_var[len(NAMED_ENV_PREFIX):].lower().replace("_", "-")
            if os.environ[env_var].strip():
                names.append(logical)
    return sorted(names)
