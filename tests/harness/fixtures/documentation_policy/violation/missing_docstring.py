"""File-level docstring is fine; checking class+function docstring at the spine.

Pretend-path: backend/src/api/routes_v4.py
"""

from fastapi import APIRouter

router = APIRouter()


def list_incidents() -> list[dict]:
    return []


class IncidentResponse:
    pass
