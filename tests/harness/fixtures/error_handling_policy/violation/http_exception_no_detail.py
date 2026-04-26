"""Fixture: HTTPException without detail should fire Q17.http-exception-needs-detail."""

from fastapi import HTTPException


def go():
    raise HTTPException(status_code=404)
