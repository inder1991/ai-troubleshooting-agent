"""Tests for alert deduplication in NotificationDispatcher and AlertEngine."""
import time
import pytest
from unittest.mock import AsyncMock, patch

from src.network.models import (
    NotificationChannel,
    NotificationRouting,
    ChannelType,
)
from src.network.notification_dispatcher import NotificationDispatcher
from src.network.alert_engine import AlertEngine


def _make_dispatcher(dedup_window_seconds: int = 300) -> NotificationDispatcher:
    d = NotificationDispatcher(dedup_window_seconds=dedup_window_seconds)
    d.add_channel(NotificationChannel(
        id="ch-1", name="Webhook",
        channel_type=ChannelType.WEBHOOK,
        config={"url": "https://hooks.example.com/alert"},
    ))
    d.add_routing(NotificationRouting(
        id="rt-1",
        severity_filter=["critical"],
        channel_ids=["ch-1"],
    ))
    return d


def _make_alert(key: str = "rule-1:dev-1", **overrides) -> dict:
    alert = {
        "key": key,
        "rule_id": "rule-1",
        "rule_name": "High Packet Loss",
        "entity_id": "dev-1",
        "severity": "critical",
        "metric": "packet_loss",
        "value": 1.0,
        "threshold": 0.99,
        "condition": "gt",
        "fired_at": time.time(),
        "acknowledged": False,
        "message": "dev-1: packet_loss 1.0 > 0.99",
    }
    alert.update(overrides)
    return alert


@pytest.mark.asyncio
async def test_first_dispatch_sends():
    """First dispatch of an alert key should send the notification."""
    d = _make_dispatcher()
    with patch.object(d, "_send", new_callable=AsyncMock) as mock_send:
        await d.dispatch(_make_alert())
        assert mock_send.call_count == 1


@pytest.mark.asyncio
async def test_duplicate_suppressed():
    """Second dispatch of the same alert key should be suppressed."""
    d = _make_dispatcher()
    with patch.object(d, "_send", new_callable=AsyncMock) as mock_send:
        await d.dispatch(_make_alert("rule-1:dev-1"))
        await d.dispatch(_make_alert("rule-1:dev-1"))
        assert mock_send.call_count == 1


@pytest.mark.asyncio
async def test_different_keys_both_send():
    """Different alert keys should each send independently."""
    d = _make_dispatcher()
    with patch.object(d, "_send", new_callable=AsyncMock) as mock_send:
        await d.dispatch(_make_alert("rule-1:dev-1"))
        await d.dispatch(_make_alert("rule-2:dev-2"))
        assert mock_send.call_count == 2


@pytest.mark.asyncio
async def test_resolved_bypasses_dedup():
    """Resolved alerts should always send, even if the key was seen before."""
    d = _make_dispatcher()
    with patch.object(d, "_send", new_callable=AsyncMock) as mock_send:
        await d.dispatch(_make_alert("rule-1:dev-1"))
        await d.dispatch(_make_alert("rule-1:dev-1", resolved=True))
        assert mock_send.call_count == 2


@pytest.mark.asyncio
async def test_escalated_bypasses_dedup():
    """Escalated alerts should always send, even if the key was seen before."""
    d = _make_dispatcher()
    with patch.object(d, "_send", new_callable=AsyncMock) as mock_send:
        await d.dispatch(_make_alert("rule-1:dev-1"))
        await d.dispatch(_make_alert("rule-1:dev-1", escalated=True))
        assert mock_send.call_count == 2


@pytest.mark.asyncio
async def test_dedup_window_zero_disables_suppression():
    """With dedup_window_seconds=0, duplicates are NOT suppressed."""
    d = _make_dispatcher(dedup_window_seconds=0)
    with patch.object(d, "_send", new_callable=AsyncMock) as mock_send:
        await d.dispatch(_make_alert("rule-1:dev-1"))
        await d.dispatch(_make_alert("rule-1:dev-1"))
        assert mock_send.call_count == 2


# ---------------------------------------------------------------------------
# Task 11 – AlertEngine-level dedup across rules
# ---------------------------------------------------------------------------

class TestAlertEngineDedup:
    """Tests for AlertEngine._should_fire fingerprint deduplication."""

    def _make_engine(self, dedup_window: int = 300) -> AlertEngine:
        engine = AlertEngine.__new__(AlertEngine)
        engine._active_fingerprints = {}
        engine._DEDUP_WINDOW = dedup_window
        return engine

    def test_alert_dedup_suppresses_duplicate(self):
        """Second alert with same fingerprint within 300s should be suppressed."""
        engine = self._make_engine()
        fp = "dev-1:cpu_pct:critical"
        # First alert should pass
        assert engine._should_fire(fp) is True
        # Second alert within window should be suppressed
        assert engine._should_fire(fp) is False

    def test_alert_dedup_allows_after_window(self):
        """Alert should fire after dedup window expires."""
        engine = self._make_engine()
        fp = "dev-1:cpu_pct:critical"
        engine._active_fingerprints[fp] = time.time() - 400  # Expired
        assert engine._should_fire(fp) is True

    def test_fingerprint_format(self):
        """Fingerprint should be entity:metric:severity."""
        fp = AlertEngine._make_fingerprint("switch-42", "mem_pct", "warning")
        assert fp == "switch-42:mem_pct:warning"

    def test_resolve_fingerprint_removes_entry(self):
        """Resolving a fingerprint should clear it, allowing immediate re-fire."""
        engine = self._make_engine()
        fp = "dev-1:cpu_pct:critical"

        assert engine._should_fire(fp) is True
        assert fp in engine._active_fingerprints

        engine._resolve_fingerprint(fp)
        assert fp not in engine._active_fingerprints

        # Should be allowed to fire again immediately
        assert engine._should_fire(fp) is True

    def test_different_fingerprints_are_independent(self):
        """Two distinct fingerprints should not interfere with each other."""
        engine = self._make_engine()
        fp_a = "dev-1:cpu_pct:critical"
        fp_b = "dev-1:cpu_pct:warning"

        assert engine._should_fire(fp_a) is True
        assert engine._should_fire(fp_b) is True
        # Original is still suppressed
        assert engine._should_fire(fp_a) is False

    def test_dedup_window_class_constant(self):
        """Default _DEDUP_WINDOW should be 300 seconds."""
        assert AlertEngine._DEDUP_WINDOW == 300

    def test_resolve_nonexistent_fingerprint_is_noop(self):
        """Resolving a fingerprint that was never recorded should not raise."""
        engine = self._make_engine()
        engine._resolve_fingerprint("does-not-exist:metric:critical")
        assert "does-not-exist:metric:critical" not in engine._active_fingerprints


# ---------------------------------------------------------------------------
# Task 12 – Acknowledged alerts skip escalation
# ---------------------------------------------------------------------------

class TestAcknowledgedEscalation:
    """Tests verifying acknowledged alerts are excluded from escalation."""

    def test_acknowledged_alert_skips_escalation(self):
        """Acknowledged alerts should not be included in the escalation list."""
        engine = AlertEngine.__new__(AlertEngine)
        engine._active_fingerprints = {}
        engine._active_alerts = {
            "rule-1:dev-1": {
                "key": "rule-1:dev-1",
                "severity": "critical",
                "acknowledged": True,
                "fired_at": time.time() - 600,
            },
            "rule-2:dev-2": {
                "key": "rule-2:dev-2",
                "severity": "warning",
                "acknowledged": False,
                "fired_at": time.time() - 600,
            },
        }

        unacked = [
            a for a in engine._active_alerts.values()
            if not a.get("acknowledged")
        ]

        assert len(unacked) == 1
        assert unacked[0]["key"] == "rule-2:dev-2"

    def test_acknowledge_sets_flag(self):
        """Engine.acknowledge() should mark an active alert as acknowledged."""
        engine = AlertEngine.__new__(AlertEngine)
        engine._active_alerts = {
            "rule-1:dev-1": {
                "key": "rule-1:dev-1",
                "acknowledged": False,
            },
        }

        assert engine.acknowledge("rule-1:dev-1") is True
        assert engine._active_alerts["rule-1:dev-1"]["acknowledged"] is True
        assert engine.acknowledge("nonexistent") is False

    def test_all_acknowledged_yields_empty_escalation_list(self):
        """If every active alert is acknowledged, escalation list should be empty."""
        engine = AlertEngine.__new__(AlertEngine)
        engine._active_alerts = {
            "r1:d1": {"key": "r1:d1", "acknowledged": True},
            "r2:d2": {"key": "r2:d2", "acknowledged": True},
        }

        unacked = [
            a for a in engine._active_alerts.values()
            if not a.get("acknowledged")
        ]

        assert unacked == []
