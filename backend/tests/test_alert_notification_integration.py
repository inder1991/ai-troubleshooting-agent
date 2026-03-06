"""Integration test: alert fires -> dispatcher receives it."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.network.alert_engine import AlertEngine
from src.network.notification_dispatcher import NotificationDispatcher
from src.network.models import (
    NotificationChannel,
    NotificationRouting,
    ChannelType,
)


@pytest.fixture
def engine_with_dispatcher():
    metrics = MagicMock()
    async def fake_query(device_id, metric, **kw):
        if metric == "packet_loss":
            return [{"value": 1.0, "time": "2026-03-06T00:00:00Z"}]
        return []
    metrics.query_device_metrics = fake_query
    metrics.write_alert_event = AsyncMock()

    engine = AlertEngine(metrics, load_defaults=True)
    dispatcher = NotificationDispatcher()
    dispatcher.add_channel(NotificationChannel(
        id="wh-test", name="Test", channel_type=ChannelType.WEBHOOK,
        config={"url": "https://example.com/hook"},
    ))
    dispatcher.add_routing(NotificationRouting(
        id="rt-test", severity_filter=["critical"], channel_ids=["wh-test"],
    ))
    engine.set_dispatcher(dispatcher)
    return engine, dispatcher


@pytest.mark.asyncio
async def test_fired_alert_triggers_dispatch(engine_with_dispatcher):
    engine, dispatcher = engine_with_dispatcher
    with pytest.importorskip("unittest.mock").patch.object(
        dispatcher, "_send_webhook", new_callable=AsyncMock
    ) as mock_send:
        alerts = await engine.evaluate_all(["device-1"])
        assert len(alerts) > 0
        mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_no_dispatch_when_no_dispatcher():
    metrics = MagicMock()
    async def fake_query(device_id, metric, **kw):
        if metric == "packet_loss":
            return [{"value": 1.0, "time": "2026-03-06T00:00:00Z"}]
        return []
    metrics.query_device_metrics = fake_query
    metrics.write_alert_event = AsyncMock()

    engine = AlertEngine(metrics, load_defaults=True)
    alerts = await engine.evaluate_all(["device-1"])
    assert len(alerts) > 0
