"""Dynamically adjusts batch size based on DB write performance."""
from __future__ import annotations


class BatchSizeController:
    def __init__(
        self, default_size: int = 500, min_size: int = 50, max_size: int = 2000
    ):
        self._current = default_size
        self._min = min_size
        self._max = max_size

    @property
    def size(self) -> int:
        return self._current

    def on_success(self, duration_ms: float) -> None:
        if duration_ms < 200 and self._current < self._max:
            self._current = min(self._current + 100, self._max)
        elif duration_ms > 2000:
            self._current = max(self._current // 2, self._min)

    def on_error(self) -> None:
        self._current = max(self._current // 2, self._min)
