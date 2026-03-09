"""Tests for SyslogListener — RFC 3164/5424 parsing, severity mapping, device correlation."""
import pytest
from unittest.mock import MagicMock, AsyncMock

from src.network.collectors.syslog_listener import (
    parse_syslog_message,
    _decode_pri,
    SyslogListener,
    SEVERITY_NAMES,
    FACILITY_NAMES,
)


# ── PRI Decoding ──

def test_decode_pri_kern_emergency():
    # PRI 0 = kern (0) + emergency (0)
    fac_code, fac_name, sev_code, sev_name = _decode_pri(0)
    assert fac_code == 0
    assert fac_name == "kern"
    assert sev_code == 0
    assert sev_name == "emergency"


def test_decode_pri_local0_warning():
    # PRI = 16*8 + 4 = 132 → local0 (16) + warning (4)
    fac_code, fac_name, sev_code, sev_name = _decode_pri(132)
    assert fac_code == 16
    assert fac_name == "local0"
    assert sev_code == 4
    assert sev_name == "warning"


def test_decode_pri_auth_info():
    # PRI = 4*8 + 6 = 38 → auth (4) + info (6)
    fac_code, fac_name, sev_code, sev_name = _decode_pri(38)
    assert fac_name == "auth"
    assert sev_name == "info"


# ── RFC 3164 Parsing ──

def test_parse_rfc3164_basic():
    raw = b"<134>Oct  5 14:23:01 myhost sshd[12345]: Accepted publickey for user"
    result = parse_syslog_message(raw)
    assert result is not None
    assert result["format"] == "rfc3164"
    # PRI 134 = 16*8 + 6 → local0, info
    assert result["facility"] == "local0"
    assert result["severity"] == "info"
    assert result["severity_code"] == 6
    assert result["hostname"] == "myhost"
    assert result["app_name"] == "sshd"
    assert result["proc_id"] == "12345"
    assert "Accepted publickey" in result["message"]


def test_parse_rfc3164_no_pid():
    raw = b"<14>Jan  1 00:00:00 router kernel: Device eth0 link up"
    result = parse_syslog_message(raw)
    assert result is not None
    assert result["format"] == "rfc3164"
    # PRI 14 = 1*8 + 6 → user, info
    assert result["facility"] == "user"
    assert result["severity"] == "info"
    assert result["hostname"] == "router"
    assert result["app_name"] == "kernel"
    assert "Device eth0 link up" in result["message"]


def test_parse_rfc3164_critical():
    raw = b"<26>Mar  9 12:00:00 fw01 snort[999]: Alert: potential intrusion detected"
    result = parse_syslog_message(raw)
    assert result is not None
    # PRI 26 = 3*8 + 2 → daemon, critical
    assert result["facility"] == "daemon"
    assert result["severity"] == "critical"


# ── RFC 5424 Parsing ──

def test_parse_rfc5424_basic():
    raw = b"<165>1 2023-10-05T14:23:01.000Z myhost myapp 12345 ID47 - Hello from RFC 5424"
    result = parse_syslog_message(raw)
    assert result is not None
    assert result["format"] == "rfc5424"
    # PRI 165 = 20*8 + 5 → local4, notice
    assert result["facility"] == "local4"
    assert result["severity"] == "notice"
    assert result["severity_code"] == 5
    assert result["hostname"] == "myhost"
    assert result["app_name"] == "myapp"
    assert "Hello from RFC 5424" in result["message"]


def test_parse_rfc5424_nilvalue():
    raw = b"<134>1 2023-10-05T14:23:01Z - - - - - Bare message"
    result = parse_syslog_message(raw)
    assert result is not None
    assert result["format"] == "rfc5424"
    assert result["hostname"] is None
    assert result["app_name"] is None


def test_parse_rfc5424_structured_data():
    raw = b'<165>1 2023-10-05T14:23:01Z host app - - [exampleSDID@32473 iut="3" eventSource="Application"] Test'
    result = parse_syslog_message(raw)
    assert result is not None
    assert result["format"] == "rfc5424"
    assert result["structured_data"] is not None


# ── Fallback Parsing ──

def test_parse_fallback_pri_only():
    raw = b"<13>Some message without proper format"
    result = parse_syslog_message(raw)
    assert result is not None
    assert result["format"] == "unknown"
    # PRI 13 = 1*8 + 5 → user, notice
    assert result["facility"] == "user"
    assert result["severity"] == "notice"
    assert "Some message" in result["message"]


def test_parse_invalid():
    assert parse_syslog_message(b"") is None
    assert parse_syslog_message(b"no pri field here") is None


# ── SyslogListener ──

def test_syslog_listener_init():
    bus = MagicMock()
    store = MagicMock()
    listener = SyslogListener(event_bus=bus, instance_store=store, port=10514)
    assert listener._port == 10514
    assert not listener.is_running
    assert listener.stats == {"received": 0, "errors": 0}


def test_syslog_listener_handle_invalid():
    bus = MagicMock()
    bus.publish = AsyncMock()
    store = MagicMock()
    listener = SyslogListener(event_bus=bus, instance_store=store)
    listener._handle_datagram(b"not a syslog message", ("10.0.0.1", 514))
    assert listener._recv_count == 1
    assert listener._error_count == 1
    bus.publish.assert_not_called()


def test_syslog_listener_device_correlation():
    bus = MagicMock()
    bus.publish = AsyncMock()
    device = MagicMock()
    device.device_id = "dev-123"
    store = MagicMock()
    store.get_device_by_ip = MagicMock(return_value=device)

    listener = SyslogListener(event_bus=bus, instance_store=store)
    # Feed a valid syslog message — the publish is fire-and-forget via create_task
    # so we just verify the store lookup happens
    listener._handle_datagram(
        b"<134>Oct  5 14:23:01 myhost sshd[12345]: test msg",
        ("10.0.0.1", 514),
    )
    assert listener._recv_count == 1
    assert listener._error_count == 0
    store.get_device_by_ip.assert_called_once_with("10.0.0.1")


# ── Severity/Facility Constants ──

def test_all_severities_defined():
    for code in range(8):
        assert code in SEVERITY_NAMES


def test_all_facilities_defined():
    for code in range(24):
        assert code in FACILITY_NAMES
