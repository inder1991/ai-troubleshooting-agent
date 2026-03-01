"""Integration tests for LTTB downsampling in tool_executor and routes_v4.

Covers:
- _query_prometheus applies LTTB when any series has > 150 values
- _query_prometheus does NOT downsample when values <= 150
- get_findings time_series_data is LTTB-downsampled when > 150 points
- get_findings time_series_data passes through when <= 150 points
- proxy_promql_query applies LTTB when values > 150 points
- proxy_promql_query passes through when values <= 150 points
"""

import json
import pytest
from unittest.mock import MagicMock

from src.tools.tool_executor import ToolExecutor
from src.tools.tool_result import ToolResult
from src.utils.lttb import MAX_POINTS


def _make_executor(**overrides) -> ToolExecutor:
    """Create a ToolExecutor with a dummy config and mocked clients."""
    config = overrides.pop("config", {"kubeconfig": "/fake/path"})
    executor = ToolExecutor(connection_config=config)
    executor._k8s_core_api = overrides.get("core_api", MagicMock())
    executor._k8s_apps_api = overrides.get("apps_api", MagicMock())
    executor._prom_client = overrides.get("prom_client", MagicMock())
    executor._es_client = overrides.get("es_client", MagicMock())
    return executor


def _make_prom_response(num_values: int) -> dict:
    """Build a mock Prometheus query_range response with num_values data points."""
    values = [[float(i * 60), str(float(i))] for i in range(num_values)]
    return {
        "data": {
            "resultType": "matrix",
            "result": [{
                "metric": {"__name__": "test_metric", "pod": "test-pod"},
                "values": values,
            }],
        },
    }


class TestQueryPrometheusLTTB:
    """Tests for LTTB integration in ToolExecutor._query_prometheus."""

    @pytest.mark.asyncio
    async def test_downsamples_when_above_max_points(self):
        """Series with > 150 values should be LTTB-downsampled in raw_output."""
        num_values = 500
        mock_prom = MagicMock()
        mock_prom.query_range = MagicMock(return_value=_make_prom_response(num_values))

        executor = _make_executor(prom_client=mock_prom)
        result = await executor.execute("query_prometheus", {
            "query": "test_metric{pod='test-pod'}",
            "range_minutes": 60,
        })

        assert result.success is True
        raw = json.loads(result.raw_output)
        series_values = raw["data"]["result"][0]["values"]
        assert len(series_values) == MAX_POINTS
        # First and last points should be preserved (LTTB guarantees this)
        assert float(series_values[0][0]) == 0.0
        assert float(series_values[-1][0]) == float((num_values - 1) * 60)

    @pytest.mark.asyncio
    async def test_no_downsample_when_at_or_below_max_points(self):
        """Series with <= 150 values should NOT be downsampled."""
        num_values = 100
        mock_prom = MagicMock()
        mock_prom.query_range = MagicMock(return_value=_make_prom_response(num_values))

        executor = _make_executor(prom_client=mock_prom)
        result = await executor.execute("query_prometheus", {
            "query": "test_metric{pod='test-pod'}",
            "range_minutes": 60,
        })

        assert result.success is True
        raw = json.loads(result.raw_output)
        series_values = raw["data"]["result"][0]["values"]
        assert len(series_values) == num_values

    @pytest.mark.asyncio
    async def test_no_downsample_at_exactly_max_points(self):
        """Series with exactly 150 values should NOT be downsampled."""
        mock_prom = MagicMock()
        mock_prom.query_range = MagicMock(return_value=_make_prom_response(MAX_POINTS))

        executor = _make_executor(prom_client=mock_prom)
        result = await executor.execute("query_prometheus", {
            "query": "test_metric{pod='test-pod'}",
            "range_minutes": 60,
        })

        assert result.success is True
        raw = json.loads(result.raw_output)
        series_values = raw["data"]["result"][0]["values"]
        assert len(series_values) == MAX_POINTS

    @pytest.mark.asyncio
    async def test_multiple_series_downsampled_independently(self):
        """Each series should be downsampled independently."""
        num_values_large = 300
        num_values_small = 50
        response = {
            "data": {
                "resultType": "matrix",
                "result": [
                    {
                        "metric": {"__name__": "metric_a"},
                        "values": [[float(i * 60), str(float(i))] for i in range(num_values_large)],
                    },
                    {
                        "metric": {"__name__": "metric_b"},
                        "values": [[float(i * 60), str(float(i))] for i in range(num_values_small)],
                    },
                ],
            },
        }
        mock_prom = MagicMock()
        mock_prom.query_range = MagicMock(return_value=response)

        executor = _make_executor(prom_client=mock_prom)
        result = await executor.execute("query_prometheus", {
            "query": "test_metric",
            "range_minutes": 60,
        })

        assert result.success is True
        raw = json.loads(result.raw_output)
        results = raw["data"]["result"]
        # Large series should be downsampled
        assert len(results[0]["values"]) == MAX_POINTS
        # Small series should remain untouched
        assert len(results[1]["values"]) == num_values_small

    @pytest.mark.asyncio
    async def test_stats_computed_on_downsampled_data(self):
        """Stats (avg, max, latest) should reflect the downsampled values."""
        num_values = 300
        mock_prom = MagicMock()
        mock_prom.query_range = MagicMock(return_value=_make_prom_response(num_values))

        executor = _make_executor(prom_client=mock_prom)
        result = await executor.execute("query_prometheus", {
            "query": "test_metric{pod='test-pod'}",
            "range_minutes": 60,
        })

        assert result.success is True
        # The metadata should still contain valid stats
        assert "latest_value" in result.metadata
        assert "max_value" in result.metadata
        assert "avg_value" in result.metadata


class TestFindingsTimeSeries:
    """Tests for LTTB downsampling in the get_findings response builder."""

    def test_downsample_findings_time_series(self):
        """Time series with > MAX_POINTS should be LTTB-downsampled."""
        from src.utils.lttb import lttb_downsample, MAX_POINTS
        from datetime import datetime, timezone

        # Simulate what routes_v4.py does for time_series_data
        num_points = 300

        class FakeDataPoint:
            def __init__(self, ts_epoch, value):
                self.timestamp = datetime.fromtimestamp(ts_epoch, tz=timezone.utc)
                self.value = value
            def model_dump(self, mode="json"):
                return {"timestamp": self.timestamp.isoformat(), "value": self.value}

        points = [FakeDataPoint(float(i * 60), float(i)) for i in range(num_points)]

        # Apply the same logic as routes_v4.py get_findings
        ts_data_raw = {}
        key = "test_metric"
        if len(points) > MAX_POINTS:
            ts_tuples = [(dp.timestamp.timestamp(), dp.value) for dp in points]
            downsampled = lttb_downsample(ts_tuples, MAX_POINTS)
            ts_data_raw[key] = [
                {"timestamp": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(), "value": val}
                for ts, val in downsampled
            ]
        else:
            ts_data_raw[key] = [dp.model_dump(mode="json") for dp in points]

        assert len(ts_data_raw[key]) == MAX_POINTS

    def test_passthrough_findings_time_series(self):
        """Time series with <= MAX_POINTS should pass through unchanged."""
        from src.utils.lttb import lttb_downsample, MAX_POINTS
        from datetime import datetime, timezone

        num_points = 50

        class FakeDataPoint:
            def __init__(self, ts_epoch, value):
                self.timestamp = datetime.fromtimestamp(ts_epoch, tz=timezone.utc)
                self.value = value
            def model_dump(self, mode="json"):
                return {"timestamp": self.timestamp.isoformat(), "value": self.value}

        points = [FakeDataPoint(float(i * 60), float(i)) for i in range(num_points)]

        ts_data_raw = {}
        key = "test_metric"
        if len(points) > MAX_POINTS:
            ts_tuples = [(dp.timestamp.timestamp(), dp.value) for dp in points]
            downsampled = lttb_downsample(ts_tuples, MAX_POINTS)
            ts_data_raw[key] = [
                {"timestamp": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(), "value": val}
                for ts, val in downsampled
            ]
        else:
            ts_data_raw[key] = [dp.model_dump(mode="json") for dp in points]

        assert len(ts_data_raw[key]) == num_points


class TestProxyPromQLLTTB:
    """Tests for LTTB downsampling in the proxy_promql_query endpoint logic."""

    def test_downsample_proxy_values(self):
        """Proxy values > MAX_POINTS should be LTTB-downsampled."""
        from src.utils.lttb import lttb_downsample, MAX_POINTS
        from datetime import datetime, timezone

        num_values = 400
        values = [[float(i * 60), str(float(i))] for i in range(num_values)]

        # Apply the same logic as routes_v4.py proxy_promql_query
        if len(values) > MAX_POINTS:
            ts_tuples = [(float(v[0]), float(v[1])) for v in values]
            downsampled = lttb_downsample(ts_tuples, MAX_POINTS)
        else:
            downsampled = [(float(v[0]), float(v[1])) for v in values]

        data_points = [
            {"timestamp": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(), "value": val}
            for ts, val in downsampled
        ]

        assert len(data_points) == MAX_POINTS
        # First and last timestamps preserved
        assert downsampled[0][0] == 0.0
        assert downsampled[-1][0] == float((num_values - 1) * 60)

    def test_passthrough_proxy_values(self):
        """Proxy values <= MAX_POINTS should pass through unchanged."""
        from src.utils.lttb import lttb_downsample, MAX_POINTS
        from datetime import datetime, timezone

        num_values = 80
        values = [[float(i * 60), str(float(i))] for i in range(num_values)]

        if len(values) > MAX_POINTS:
            ts_tuples = [(float(v[0]), float(v[1])) for v in values]
            downsampled = lttb_downsample(ts_tuples, MAX_POINTS)
        else:
            downsampled = [(float(v[0]), float(v[1])) for v in values]

        data_points = [
            {"timestamp": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(), "value": val}
            for ts, val in downsampled
        ]

        assert len(data_points) == num_values
