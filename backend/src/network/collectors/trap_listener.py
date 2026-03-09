"""SNMPv2c trap listener — stateless UDP receiver.

Listens for SNMPv2c Trap PDUs on a configurable UDP port, parses the
BER/TLV-encoded payload without any external SNMP library, maps the
source IP to a known device via ``InstanceStore.get_device_by_ip()``,
and publishes structured ``TrapEvent`` dicts to the event bus.

No local storage is performed; all state lives in the event bus
downstream consumers.
"""
from __future__ import annotations

import asyncio
import logging
import os
import struct
import time
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

# ── Well-known trap OIDs and their severity mapping ───────────────────

_SEVERITY_BY_OID: dict[str, str] = {
    "1.3.6.1.6.3.1.1.5.1": "info",       # coldStart
    "1.3.6.1.6.3.1.1.5.2": "info",       # warmStart
    "1.3.6.1.6.3.1.1.5.3": "critical",   # linkDown
    "1.3.6.1.6.3.1.1.5.4": "info",       # linkUp
    "1.3.6.1.6.3.1.1.5.5": "warning",    # authenticationFailure
    "1.3.6.1.6.3.1.1.5.6": "info",       # egpNeighborLoss
}

# Standard varbind OIDs carried in every SNMPv2c trap
_SYSUPTIME_OID = "1.3.6.1.2.1.1.3.0"
_SNMPTRAP_OID = "1.3.6.1.6.3.1.1.4.1.0"

# ── BER tag constants ─────────────────────────────────────────────────

_TAG_SEQUENCE = 0x30
_TAG_INTEGER = 0x02
_TAG_OCTET_STRING = 0x04
_TAG_NULL = 0x05
_TAG_OID = 0x06
_TAG_SNMPV2_TRAP_PDU = 0xA7
_TAG_TIMETICKS = 0x43
_TAG_COUNTER32 = 0x41
_TAG_GAUGE32 = 0x42
_TAG_COUNTER64 = 0x46
_TAG_IP_ADDRESS = 0x40


# ── Minimal BER parser ───────────────────────────────────────────────

def _parse_ber_length(data: bytes, offset: int) -> tuple[int, int]:
    """Return (length, new_offset) after parsing a BER length field."""
    if offset >= len(data):
        raise ValueError("Truncated BER length at offset %d" % offset)
    first = data[offset]
    if first & 0x80 == 0:
        return first, offset + 1
    num_bytes = first & 0x7F
    if num_bytes == 0 or offset + 1 + num_bytes > len(data):
        raise ValueError("Invalid BER long-form length at offset %d" % offset)
    length = int.from_bytes(data[offset + 1: offset + 1 + num_bytes], "big")
    return length, offset + 1 + num_bytes


def _parse_ber_tag(data: bytes, offset: int) -> tuple[int, int, int]:
    """Return (tag, content_length, content_offset)."""
    if offset >= len(data):
        raise ValueError("Truncated BER tag at offset %d" % offset)
    tag = data[offset]
    length, content_start = _parse_ber_length(data, offset + 1)
    return tag, length, content_start


def _decode_oid(data: bytes) -> str:
    """Decode a BER-encoded OID value (content bytes, no tag/length)."""
    if len(data) < 1:
        return ""
    components: list[int] = []
    first_byte = data[0]
    components.append(first_byte // 40)
    components.append(first_byte % 40)

    value = 0
    for b in data[1:]:
        value = (value << 7) | (b & 0x7F)
        if b & 0x80 == 0:
            components.append(value)
            value = 0

    return ".".join(str(c) for c in components)


def _decode_integer(data: bytes) -> int:
    """Decode a BER INTEGER value (content bytes, signed)."""
    if not data:
        return 0
    return int.from_bytes(data, "big", signed=True)


def _decode_value(tag: int, data: bytes) -> Any:
    """Decode a BER value given its tag and raw content bytes."""
    if tag == _TAG_INTEGER:
        return _decode_integer(data)
    if tag == _TAG_OCTET_STRING:
        try:
            return data.decode("utf-8", errors="replace")
        except Exception:
            return data.hex()
    if tag == _TAG_OID:
        return _decode_oid(data)
    if tag == _TAG_NULL:
        return None
    if tag == _TAG_TIMETICKS:
        return int.from_bytes(data, "big", signed=False) if data else 0
    if tag in (_TAG_COUNTER32, _TAG_GAUGE32):
        return int.from_bytes(data, "big", signed=False) if data else 0
    if tag == _TAG_COUNTER64:
        return int.from_bytes(data, "big", signed=False) if data else 0
    if tag == _TAG_IP_ADDRESS:
        if len(data) == 4:
            return ".".join(str(b) for b in data)
        return data.hex()
    # Unknown tag — return hex representation
    return data.hex()


def _parse_varbinds(data: bytes, offset: int, end: int) -> list[tuple[str, Any]]:
    """Parse a SEQUENCE OF VarBind from *data[offset:end]*.

    Each VarBind is SEQUENCE { OID, value }.
    Returns list of (oid_string, decoded_value).
    """
    varbinds: list[tuple[str, Any]] = []
    while offset < end:
        # Each varbind is a SEQUENCE
        tag, length, content_start = _parse_ber_tag(data, offset)
        if tag != _TAG_SEQUENCE:
            break
        varbind_end = content_start + length

        # OID
        oid_tag, oid_len, oid_content_start = _parse_ber_tag(data, content_start)
        if oid_tag != _TAG_OID:
            offset = varbind_end
            continue
        oid_str = _decode_oid(data[oid_content_start: oid_content_start + oid_len])

        # Value
        val_offset = oid_content_start + oid_len
        if val_offset < varbind_end:
            val_tag, val_len, val_content_start = _parse_ber_tag(data, val_offset)
            value = _decode_value(val_tag, data[val_content_start: val_content_start + val_len])
        else:
            value = None

        varbinds.append((oid_str, value))
        offset = varbind_end

    return varbinds


def parse_snmpv2c_trap(data: bytes) -> dict[str, Any] | None:
    """Parse an SNMPv2c Trap PDU from raw bytes.

    Returns a dict with keys ``community``, ``trap_oid``, ``varbinds``,
    ``uptime``, and ``enterprise_oid``, or ``None`` if the packet is not
    a valid SNMPv2c trap.
    """
    try:
        offset = 0
        # Outer SEQUENCE
        tag, msg_len, offset = _parse_ber_tag(data, offset)
        if tag != _TAG_SEQUENCE:
            return None
        msg_end = offset + msg_len

        # Version (INTEGER, should be 1 for v2c)
        tag, ver_len, ver_start = _parse_ber_tag(data, offset)
        if tag != _TAG_INTEGER:
            return None
        version = _decode_integer(data[ver_start: ver_start + ver_len])
        if version != 1:  # SNMPv2c = version 1 (0-indexed)
            logger.debug("Ignoring SNMP version %d (expected v2c = 1)", version)
            return None
        offset = ver_start + ver_len

        # Community string (OCTET STRING)
        tag, comm_len, comm_start = _parse_ber_tag(data, offset)
        if tag != _TAG_OCTET_STRING:
            return None
        community = data[comm_start: comm_start + comm_len].decode("utf-8", errors="replace")
        offset = comm_start + comm_len

        # PDU type (should be 0xA7 for SNMPv2-Trap-PDU)
        tag, pdu_len, pdu_start = _parse_ber_tag(data, offset)
        if tag != _TAG_SNMPV2_TRAP_PDU:
            return None
        pdu_end = pdu_start + pdu_len

        # Request ID (INTEGER)
        tag, rid_len, rid_start = _parse_ber_tag(data, pdu_start)
        offset = rid_start + rid_len

        # Error Status (INTEGER)
        tag, es_len, es_start = _parse_ber_tag(data, offset)
        offset = es_start + es_len

        # Error Index (INTEGER)
        tag, ei_len, ei_start = _parse_ber_tag(data, offset)
        offset = ei_start + ei_len

        # VarBind list (SEQUENCE OF)
        tag, vbl_len, vbl_start = _parse_ber_tag(data, offset)
        if tag != _TAG_SEQUENCE:
            return None
        vbl_end = vbl_start + vbl_len

        varbinds = _parse_varbinds(data, vbl_start, vbl_end)

        # Extract well-known fields
        trap_oid: str | None = None
        uptime: int | None = None
        enterprise_oid: str | None = None

        for oid, value in varbinds:
            if oid == _SNMPTRAP_OID and isinstance(value, str):
                trap_oid = value
            elif oid == _SYSUPTIME_OID:
                uptime = value if isinstance(value, int) else None

        # The trap OID often doubles as the enterprise OID prefix
        if trap_oid:
            parts = trap_oid.rsplit(".", 1)
            if len(parts) == 2:
                enterprise_oid = parts[0]

        return {
            "community": community,
            "trap_oid": trap_oid,
            "uptime": uptime,
            "enterprise_oid": enterprise_oid,
            "varbinds": varbinds,
        }

    except (ValueError, IndexError, struct.error) as exc:
        logger.debug("Failed to parse SNMPv2c trap PDU: %s", exc)
        return None


def _severity_for_oid(oid: str | None) -> str:
    """Map a trap OID to a severity level, defaulting to ``'info'``."""
    if oid is None:
        return "info"
    return _SEVERITY_BY_OID.get(oid, "info")


# ── UDP Protocol ──────────────────────────────────────────────────────

class _TrapDatagramProtocol(asyncio.DatagramProtocol):
    """Low-level asyncio datagram protocol wired to :class:`SNMPTrapListener`."""

    def __init__(self, listener: SNMPTrapListener) -> None:
        self._listener = listener

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:  # type: ignore[override]
        self._listener._transport = transport

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self._listener._handle_datagram(data, addr)

    def error_received(self, exc: Exception) -> None:
        logger.error("Trap listener socket error: %s", exc)

    def connection_lost(self, exc: Exception | None) -> None:
        if exc:
            logger.warning("Trap listener connection lost: %s", exc)


# ── Public API ────────────────────────────────────────────────────────

class SNMPTrapListener:
    """Stateless SNMPv2c trap receiver.

    Binds to a UDP port, parses incoming SNMPv2c Trap PDUs using a
    lightweight BER decoder (no ``pysnmp`` dependency), resolves the
    source IP to a device through ``instance_store``, and publishes
    structured events to the ``event_bus``.

    Messages larger than ``MAX_MESSAGE_SIZE`` bytes are truncated.

    Configuration
    ~~~~~~~~~~~~~
    * ``TRAP_LISTENER_PORT`` — override the default listening port (162).
    * ``TRAP_LISTENER_ENABLED`` — set to ``"false"`` to skip binding.

    Usage::

        listener = SNMPTrapListener(event_bus, instance_store)
        await listener.start()
        ...
        await listener.stop()
    """

    MAX_MESSAGE_SIZE = 8192

    def __init__(
        self,
        event_bus: Any,
        instance_store: Any,
        port: int = 162,
    ) -> None:
        env_port = os.environ.get("TRAP_LISTENER_PORT")
        self._port: int = int(env_port) if env_port else port
        self._enabled: bool = os.environ.get(
            "TRAP_LISTENER_ENABLED", "true"
        ).lower() not in ("false", "0", "no")
        self._event_bus = event_bus
        self._instance_store = instance_store
        self._transport: asyncio.DatagramTransport | None = None
        self._recv_count: int = 0
        self._error_count: int = 0

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def start(self) -> None:
        """Bind the UDP socket and begin receiving traps."""
        if not self._enabled:
            logger.info("SNMP trap listener disabled via TRAP_LISTENER_ENABLED")
            return

        loop = asyncio.get_running_loop()
        try:
            transport, _ = await loop.create_datagram_endpoint(
                lambda: _TrapDatagramProtocol(self),
                local_addr=("0.0.0.0", self._port),
            )
            self._transport = transport  # type: ignore[assignment]
            logger.info(
                "SNMP trap listener started on UDP port %d", self._port
            )
        except OSError as exc:
            logger.error(
                "Failed to bind SNMP trap listener on UDP port %d: %s",
                self._port,
                exc,
            )

    async def stop(self) -> None:
        """Close the UDP socket and stop receiving."""
        if self._transport is not None:
            self._transport.close()
            self._transport = None
            logger.info(
                "SNMP trap listener stopped (received=%d, errors=%d)",
                self._recv_count,
                self._error_count,
            )

    # ── Datagram handling ─────────────────────────────────────────────

    def _handle_datagram(self, data: bytes, addr: tuple[str, int]) -> None:
        """Process a single incoming UDP datagram.

        Parsing and device lookup are synchronous; the event bus publish
        is scheduled as a fire-and-forget coroutine.
        """
        self._recv_count += 1

        # Message size validation
        truncated = False
        if len(data) > self.MAX_MESSAGE_SIZE:
            logger.warning(
                "Trap message from %s exceeds MAX_MESSAGE_SIZE (%d > %d), truncating",
                addr[0], len(data), self.MAX_MESSAGE_SIZE,
            )
            data = data[:self.MAX_MESSAGE_SIZE]
            truncated = True

        parsed = parse_snmpv2c_trap(data)
        if parsed is None:
            self._error_count += 1
            logger.debug(
                "Dropped non-SNMPv2c packet from %s (%d bytes)",
                addr[0],
                len(data),
            )
            return

        trap_oid: str | None = parsed.get("trap_oid")
        severity = _severity_for_oid(trap_oid)

        # Derive a human-readable value from the first non-standard varbind
        trap_value: Any = None
        for oid, value in parsed.get("varbinds", []):
            if oid not in (_SYSUPTIME_OID, _SNMPTRAP_OID):
                trap_value = value
                break

        # Resolve device (read-only lookup, may return None)
        device = None
        try:
            device = self._instance_store.get_device_by_ip(addr[0])
        except Exception as exc:
            logger.debug("Device lookup failed for %s: %s", addr[0], exc)

        event: dict[str, Any] = {
            "event_id": str(uuid4()),
            "device_ip": addr[0],
            "device_id": device.device_id if device else None,
            "oid": trap_oid,
            "value": trap_value,
            "severity": severity,
            "timestamp": time.time(),
            "raw_pdu": data.hex(),
            "truncated": truncated,
        }

        # Fire-and-forget publish
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._publish(event))
        except RuntimeError:
            logger.debug("No running event loop; trap event dropped")

    async def _publish(self, event: dict[str, Any]) -> None:
        """Publish a trap event to the event bus, swallowing errors."""
        try:
            await self._event_bus.publish("traps", event)
        except Exception as exc:
            self._error_count += 1
            logger.error(
                "Failed to publish trap event %s: %s",
                event.get("event_id", "?"),
                exc,
            )

    # ── Introspection ─────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        """Return ``True`` if the listener is actively receiving."""
        return self._transport is not None

    @property
    def stats(self) -> dict[str, int]:
        """Return basic counters for monitoring."""
        return {
            "received": self._recv_count,
            "errors": self._error_count,
        }
