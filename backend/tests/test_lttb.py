import pytest
import math
from src.utils.lttb import lttb_downsample, MAX_POINTS


class TestLTTBDownsample:
    def test_below_threshold_returns_copy(self):
        data = [(float(i), float(i * 2)) for i in range(50)]
        result = lttb_downsample(data)
        assert len(result) == 50

    def test_at_threshold_returns_copy(self):
        data = [(float(i), float(i)) for i in range(150)]
        result = lttb_downsample(data)
        assert len(result) == 150

    def test_above_threshold_downsamples(self):
        data = [(float(i), float(i)) for i in range(500)]
        result = lttb_downsample(data)
        assert len(result) == MAX_POINTS

    def test_preserves_first_and_last(self):
        data = [(float(i), math.sin(i * 0.1)) for i in range(300)]
        result = lttb_downsample(data, threshold=50)
        assert result[0] == data[0]
        assert result[-1] == data[-1]

    def test_custom_threshold(self):
        data = [(float(i), float(i)) for i in range(1000)]
        result = lttb_downsample(data, threshold=20)
        assert len(result) == 20

    def test_threshold_too_small_returns_all(self):
        data = [(float(i), float(i)) for i in range(100)]
        result = lttb_downsample(data, threshold=2)
        assert len(result) == 100

    def test_empty_data(self):
        assert lttb_downsample([]) == []

    def test_single_point(self):
        data = [(1.0, 2.0)]
        assert lttb_downsample(data) == [(1.0, 2.0)]

    def test_preserves_spikes(self):
        """LTTB should preferentially keep points that form large triangles (spikes)."""
        data = [(float(i), 0.0) for i in range(200)]
        data[100] = (100.0, 1000.0)  # Spike
        result = lttb_downsample(data, threshold=20)
        values = [v for _, v in result]
        assert max(values) == 1000.0, "LTTB should preserve the spike"

    def test_output_sorted_by_timestamp(self):
        data = [(float(i), math.sin(i * 0.05)) for i in range(500)]
        result = lttb_downsample(data, threshold=50)
        timestamps = [t for t, _ in result]
        assert timestamps == sorted(timestamps)
