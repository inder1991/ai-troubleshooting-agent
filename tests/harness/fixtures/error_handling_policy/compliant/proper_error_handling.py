"""Fixture: handles errors with chain, narrow types, and detail."""

from fastapi import HTTPException


class FetchError(RuntimeError):
    """Domain error for fetch failures."""


def fetch():
    try:
        return _do()
    except ValueError as exc:
        raise FetchError("fetch failed") from exc


def lookup(item_id: int):
    if item_id < 0:
        raise HTTPException(status_code=404, detail="item not found")
    return item_id


def _do():
    return 1
