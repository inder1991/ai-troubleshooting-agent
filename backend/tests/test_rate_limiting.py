"""Tests for API rate limiting with slowapi."""

import pytest
from slowapi import Limiter


class TestRateLimiterSetup:
    """Verify that the rate limiter is properly attached to the FastAPI app."""

    def test_limiter_attached_to_app_state(self):
        """app.state.limiter should exist and be a Limiter instance."""
        from src.api.main import app

        assert hasattr(app.state, "limiter"), "app.state.limiter is not set"
        assert isinstance(app.state.limiter, Limiter), (
            f"app.state.limiter should be a Limiter, got {type(app.state.limiter)}"
        )

    def test_limiter_has_default_limits(self):
        """The limiter should have default_limits configured."""
        from src.api.main import app

        limiter = app.state.limiter
        assert limiter._default_limits, "Limiter default_limits should not be empty"

    def test_limiter_importable_from_main(self):
        """limiter should be importable directly from src.api.main."""
        from src.api.main import limiter

        assert isinstance(limiter, Limiter), (
            f"Imported limiter should be a Limiter, got {type(limiter)}"
        )
