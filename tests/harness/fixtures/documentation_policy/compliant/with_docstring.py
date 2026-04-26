"""Spine module with docstrings on every public symbol.

Pretend-path: backend/src/api/routes_v4.py
"""

from fastapi import APIRouter

router = APIRouter()


def list_incidents() -> list[dict]:
    """Return all incidents visible to the requesting tenant."""
    return []


class IncidentResponse:
    """Frozen response wrapper for a single incident."""
