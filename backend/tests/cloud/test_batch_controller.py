"""Tests for dynamic batch size controller."""
import pytest
from src.cloud.sync.batch_controller import BatchSizeController


class TestBatchSizeController:
    def test_default_size(self):
        ctrl = BatchSizeController()
        assert ctrl.size == 500

    def test_grows_on_fast_commit(self):
        ctrl = BatchSizeController(default_size=500, max_size=2000)
        ctrl.on_success(duration_ms=100.0)
        assert ctrl.size == 600

    def test_shrinks_on_slow_commit(self):
        ctrl = BatchSizeController(default_size=500)
        ctrl.on_success(duration_ms=3000.0)
        assert ctrl.size == 250

    def test_shrinks_on_error(self):
        ctrl = BatchSizeController(default_size=500)
        ctrl.on_error()
        assert ctrl.size == 250

    def test_respects_min_size(self):
        ctrl = BatchSizeController(default_size=100, min_size=50)
        ctrl.on_error()
        ctrl.on_error()
        ctrl.on_error()
        assert ctrl.size >= 50

    def test_respects_max_size(self):
        ctrl = BatchSizeController(default_size=1900, max_size=2000)
        ctrl.on_success(duration_ms=50.0)
        assert ctrl.size <= 2000

    def test_stable_on_normal_duration(self):
        ctrl = BatchSizeController(default_size=500)
        ctrl.on_success(duration_ms=500.0)
        assert ctrl.size == 500
