"""Generic server-side pagination helpers."""
from __future__ import annotations

import math
from typing import Any, List

from pydantic import BaseModel


class PaginatedResponse(BaseModel):
    """Envelope returned by paginated list endpoints."""

    items: List[Any]
    total: int
    page: int
    limit: int
    pages: int


def paginate(
    items: list,
    page: int = 1,
    limit: int = 25,
) -> PaginatedResponse:
    """Slice *items* into a single page and return a PaginatedResponse.

    Parameters
    ----------
    items:
        The full list of items to paginate.
    page:
        1-based page number.
    limit:
        Maximum items per page.  Capped at 100.
    """
    # Cap limit at 100
    if limit > 100:
        limit = 100

    total = len(items)
    pages = math.ceil(total / limit) if limit > 0 else 0

    start = (page - 1) * limit
    end = start + limit
    page_items = items[start:end]

    return PaginatedResponse(
        items=page_items,
        total=total,
        page=page,
        limit=limit,
        pages=pages,
    )
