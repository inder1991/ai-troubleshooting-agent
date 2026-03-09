"""Tests for SNMPTrapListener — packet parsing, event structure, device correlation."""
import pytest
from unittest.mock import MagicMock, AsyncMock

from src.network.collectors.trap_listener import (
    parse_snmpv2c_trap,
    _decode_oid,
    _decode_integer,
    _parse_ber_length,
    _severity_for_oid,
    SNMPTrapListener,
)


# ── BER Helpers ──

def test_decode_oid_basic():
    # OID 1.3.6.1.2.1.1.3.0 in BER:
    # first byte = 1*40 + 3 = 43 = 0x2B
    # 6, 1, 2, 1, 1, 3, 0
    data = bytes([0x2B, 6, 1, 2, 1, 1, 3, 0])
    result = _decode_oid(data)
    assert result == "1.3.6.1.2.1.1.3.0"


def test_decode_oid_empty():
    assert _decode_oid(b"") == ""


def test_decode_integer():
    # 42 as a single byte signed integer
    assert _decode_integer(bytes([42])) == 42
    # 0
    assert _decode_integer(b"") == 0
    # 256
    assert _decode_integer(bytes([0x01, 0x00])) == 256


def test_parse_ber_length_short_form():
    # Short form: length < 128 encoded in single byte
    data = bytes([10])  # length = 10
    length, offset = _parse_ber_length(data, 0)
    assert length == 10
    assert offset == 1


def test_parse_ber_length_long_form():
    # Long form: 0x82 means 2 bytes follow for length
    data = bytes([0x82, 0x01, 0x00])  # length = 256
    length, offset = _parse_ber_length(data, 0)
    assert length == 256
    assert offset == 3


def test_parse_ber_length_truncated():
    with pytest.raises(ValueError):
        _parse_ber_length(b"", 0)


# ── Severity Mapping ──

def test_severity_linkdown():
    assert _severity_for_oid("1.3.6.1.6.3.1.1.5.3") == "critical"


def test_severity_auth_failure():
    assert _severity_for_oid("1.3.6.1.6.3.1.1.5.5") == "warning"


def test_severity_coldstart():
    assert _severity_for_oid("1.3.6.1.6.3.1.1.5.1") == "info"


def test_severity_unknown():
    assert _severity_for_oid("1.2.3.4.5") == "info"


def test_severity_none():
    assert _severity_for_oid(None) == "info"


# ── SNMPv2c Trap PDU Parsing ──

def _build_snmpv2c_trap() -> bytes:
    """Build a minimal SNMPv2c trap PDU for testing.

    Structure:
    SEQUENCE {
        INTEGER (version = 1 for v2c)
        OCTET STRING (community = "public")
        [7] SNMPv2-Trap-PDU {
            INTEGER (request-id = 0)
            INTEGER (error-status = 0)
            INTEGER (error-index = 0)
            SEQUENCE OF {  -- VarBindList
                SEQUENCE {  -- VarBind: sysUpTime.0
                    OID 1.3.6.1.2.1.1.3.0
                    TimeTicks 12345
                }
                SEQUENCE {  -- VarBind: snmpTrapOID.0
                    OID 1.3.6.1.6.3.1.1.4.1.0
                    OID 1.3.6.1.6.3.1.1.5.3 (linkDown)
                }
            }
        }
    }
    """
    def ber_int(val):
        if val == 0:
            return bytes([0x02, 0x01, 0x00])
        data = val.to_bytes((val.bit_length() + 8) // 8, 'big', signed=True)
        return bytes([0x02, len(data)]) + data

    def ber_oid(dotted):
        parts = [int(x) for x in dotted.split('.')]
        encoded = bytes([parts[0] * 40 + parts[1]])
        for p in parts[2:]:
            if p < 128:
                encoded += bytes([p])
            else:
                segments = []
                while p > 0:
                    segments.append(p & 0x7F)
                    p >>= 7
                segments.reverse()
                for i, s in enumerate(segments):
                    if i < len(segments) - 1:
                        encoded += bytes([s | 0x80])
                    else:
                        encoded += bytes([s])
        return bytes([0x06, len(encoded)]) + encoded

    def ber_timeticks(val):
        data = val.to_bytes(4, 'big')
        return bytes([0x43, len(data)]) + data

    def ber_octet_string(s):
        data = s.encode('utf-8')
        return bytes([0x04, len(data)]) + data

    def ber_sequence(contents):
        return bytes([0x30, len(contents)]) + contents

    # VarBind 1: sysUpTime.0 = TimeTicks(12345)
    vb1 = ber_sequence(ber_oid("1.3.6.1.2.1.1.3.0") + ber_timeticks(12345))
    # VarBind 2: snmpTrapOID.0 = OID(linkDown)
    vb2 = ber_sequence(ber_oid("1.3.6.1.6.3.1.1.4.1.0") + ber_oid("1.3.6.1.6.3.1.1.5.3"))
    varbind_list = ber_sequence(vb1 + vb2)

    # PDU
    pdu_content = ber_int(0) + ber_int(0) + ber_int(0) + varbind_list
    pdu = bytes([0xA7, len(pdu_content)]) + pdu_content

    # Message
    msg_content = ber_int(1) + ber_octet_string("public") + pdu
    return ber_sequence(msg_content)


def test_parse_snmpv2c_trap_valid():
    data = _build_snmpv2c_trap()
    result = parse_snmpv2c_trap(data)
    assert result is not None
    assert result["community"] == "public"
    assert result["trap_oid"] == "1.3.6.1.6.3.1.1.5.3"
    assert result["uptime"] == 12345
    assert len(result["varbinds"]) == 2


def test_parse_snmpv2c_trap_invalid():
    assert parse_snmpv2c_trap(b"\x00\x01\x02") is None
    assert parse_snmpv2c_trap(b"") is None


def test_parse_snmpv2c_trap_wrong_version():
    # Build a valid-ish packet but with version=0 (v1, not v2c)
    data = bytes([0x30, 5, 0x02, 1, 0, 0x04, 0])  # version=0
    assert parse_snmpv2c_trap(data) is None


# ── Trap Listener ──

def test_trap_listener_init():
    bus = MagicMock()
    store = MagicMock()
    listener = SNMPTrapListener(event_bus=bus, instance_store=store, port=10162)
    assert listener._port == 10162
    assert not listener.is_running
    assert listener.stats == {"received": 0, "errors": 0}


def test_trap_listener_handle_invalid_packet():
    bus = MagicMock()
    bus.publish = AsyncMock()
    store = MagicMock()
    listener = SNMPTrapListener(event_bus=bus, instance_store=store)
    listener._handle_datagram(b"\x00\x01\x02", ("192.168.1.1", 162))
    assert listener._recv_count == 1
    assert listener._error_count == 1
    bus.publish.assert_not_called()


def test_trap_listener_stats():
    bus = MagicMock()
    store = MagicMock()
    listener = SNMPTrapListener(event_bus=bus, instance_store=store)
    listener._recv_count = 10
    listener._error_count = 2
    assert listener.stats == {"received": 10, "errors": 2}
