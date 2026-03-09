"""Syslog UDP listener — stateless receiver for RFC 3164 and RFC 5424.

Listens for syslog messages on a configurable UDP port, parses both
BSD-style (RFC 3164) and structured (RFC 5424) formats, maps the source
IP to a known device via ``InstanceStore.get_device_by_ip()``, and
publishes structured events to the event bus.

No local storage is performed; all state lives in the event bus
downstream consumers.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

# ── Syslog severity codes (RFC 5424 Section 6.2.1) ───────────────────

SEVERITY_NAMES: dict[int, str] = {
    0: "emergency",
    1: "alert",
    2: "critical",
    3: "error",
    4: "warning",
    5: "notice",
    6: "info",
    7: "debug",
}

# ── Syslog facility codes (RFC 5424 Section 6.2.1) ───────────────────

FACILITY_NAMES: dict[int, str] = {
    0: "kern",
    1: "user",
    2: "mail",
    3: "daemon",
    4: "auth",
    5: "syslog",
    6: "lpr",
    7: "news",
    8: "uucp",
    9: "cron",
    10: "authpriv",
    11: "ftp",
    12: "ntp",
    13: "security",
    14: "console",
    15: "solaris-cron",
    16: "local0",
    17: "local1",
    18: "local2",
    19: "local3",
    20: "local4",
    21: "local5",
    22: "local6",
    23: "local7",
}

# ── RFC 3164 pattern ─────────────────────────────────────────────────
# <PRI>TIMESTAMP HOSTNAME APP-NAME[PID]: MESSAGE
# Timestamp: "Mmm dd HH:MM:SS" (BSD format)
_RFC3164_RE = re.compile(
    r"^<(\d{1,3})>"
    r"(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+"  # timestamp
    r"(\S+)\s+"                                     # hostname
    r"(\S+?)(?:\[(\d+)\])?:\s*"                     # app_name[pid]
    r"(.*)",                                        # message
    re.DOTALL,
)

# ── RFC 5424 pattern ─────────────────────────────────────────────────
# <PRI>VERSION TIMESTAMP HOSTNAME APP-NAME PROCID MSGID SD MSG
_RFC5424_RE = re.compile(
    r"^<(\d{1,3})>"
    r"(\d+)\s+"                  # version
    r"(\S+)\s+"                  # timestamp (ISO 8601 or "-")
    r"(\S+)\s+"                  # hostname
    r"(\S+)\s+"                  # app-name
    r"(\S+)\s+"                  # procid
    r"(\S+)\s+"                  # msgid
    r"(-|(?:\[.+?\])+)\s*"      # structured data
    r"(.*)",                     # msg
    re.DOTALL,
)


def _decode_pri(pri: int) -> tuple[int, str, int, str]:
    """Decode a PRI value into (facility_code, facility_name, severity_code, severity_name)."""
    facility_code = pri >> 3
    severity_code = pri & 0x07
    facility_name = FACILITY_NAMES.get(facility_code, "unknown(%d)" % facility_code)
    severity_name = SEVERITY_NAMES.get(severity_code, "unknown(%d)" % severity_code)
    return facility_code, facility_name, severity_code, severity_name


def parse_syslog_message(raw: bytes) -> dict[str, Any] | None:
    """Parse a raw syslog datagram into structured fields.

    Supports both RFC 3164 (BSD) and RFC 5424 (structured) formats.
    Returns ``None`` if the message cannot be parsed at all.
    """
    try:
        text = raw.decode("utf-8", errors="replace").rstrip("\n\r")
    except Exception:
        return None

    if not text or not text.startswith("<"):
        return None

    # Determine format: RFC 5424 has a version digit immediately after ">"
    # e.g. "<165>1 ..." vs RFC 3164 "<165>Oct ..."
    after_pri_idx = text.index(">") + 1
    if after_pri_idx >= len(text):
        return None

    char_after_pri = text[after_pri_idx]

    # ── RFC 5424 ──────────────────────────────────────────────────────
    if char_after_pri.isdigit():
        match = _RFC5424_RE.match(text)
        if match:
            pri = int(match.group(1))
            _, facility_name, severity_code, severity_name = _decode_pri(pri)
            return {
                "format": "rfc5424",
                "facility": facility_name,
                "severity": severity_name,
                "severity_code": severity_code,
                "hostname": _nilvalue(match.group(4)),
                "app_name": _nilvalue(match.group(5)),
                "proc_id": _nilvalue(match.group(6)),
                "msg_id": _nilvalue(match.group(7)),
                "structured_data": _nilvalue(match.group(8)),
                "message": match.group(9).strip() if match.group(9) else "",
                "timestamp_raw": match.group(3),
            }

    # ── RFC 3164 (BSD) ────────────────────────────────────────────────
    match = _RFC3164_RE.match(text)
    if match:
        pri = int(match.group(1))
        _, facility_name, severity_code, severity_name = _decode_pri(pri)
        return {
            "format": "rfc3164",
            "facility": facility_name,
            "severity": severity_name,
            "severity_code": severity_code,
            "hostname": match.group(3),
            "app_name": match.group(4),
            "proc_id": match.group(5),
            "message": match.group(6).strip() if match.group(6) else "",
            "timestamp_raw": match.group(2),
        }

    # ── Fallback: at least extract PRI ────────────────────────────────
    pri_match = re.match(r"^<(\d{1,3})>(.*)", text, re.DOTALL)
    if pri_match:
        pri = int(pri_match.group(1))
        _, facility_name, severity_code, severity_name = _decode_pri(pri)
        return {
            "format": "unknown",
            "facility": facility_name,
            "severity": severity_name,
            "severity_code": severity_code,
            "hostname": None,
            "app_name": None,
            "proc_id": None,
            "message": pri_match.group(2).strip(),
        }

    return None


def _nilvalue(value: str | None) -> str | None:
    """Replace the RFC 5424 NILVALUE sentinel ``-`` with ``None``."""
    if value is None or value == "-":
        return None
    return value


# ── UDP Protocol ──────────────────────────────────────────────────────

class _SyslogDatagramProtocol(asyncio.DatagramProtocol):
    """Low-level asyncio datagram protocol wired to :class:`SyslogListener`."""

    def __init__(self, listener: SyslogListener) -> None:
        self._listener = listener

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:  # type: ignore[override]
        self._listener._transport = transport

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self._listener._handle_datagram(data, addr)

    def error_received(self, exc: Exception) -> None:
        logger.error("Syslog listener socket error: %s", exc)

    def connection_lost(self, exc: Exception | None) -> None:
        if exc:
            logger.warning("Syslog listener connection lost: %s", exc)


# ── Timestamp parsing ─────────────────────────────────────────────────

# RFC 3164 timestamp: "Mar  9 12:34:56"
_RFC3164_TS_RE = re.compile(
    r"^(\w{3})\s+(\d{1,2})\s+(\d{2}):(\d{2}):(\d{2})$"
)

_MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def _parse_timestamp(raw: str | None) -> float:
    """Parse a syslog timestamp string into a Unix epoch float.

    Handles:
    - RFC 3164: ``Mar  9 12:34:56`` — uses the current year.
    - RFC 5424: ``2026-03-09T12:34:56.000Z`` — ISO 8601 format.
    - Fallback: returns ``time.time()`` if parsing fails.
    """
    if not raw:
        return time.time()

    # Try RFC 5424 (ISO 8601)
    try:
        # Handle both 'Z' suffix and '+00:00' timezone offsets
        cleaned = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        return dt.timestamp()
    except (ValueError, TypeError):
        pass

    # Try RFC 3164 (BSD)
    m = _RFC3164_TS_RE.match(raw)
    if m:
        try:
            month_name, day, hour, minute, second = m.groups()
            month = _MONTH_MAP.get(month_name)
            if month:
                now = datetime.now(tz=timezone.utc)
                dt = datetime(
                    year=now.year, month=month, day=int(day),
                    hour=int(hour), minute=int(minute), second=int(second),
                    tzinfo=timezone.utc,
                )
                return dt.timestamp()
        except (ValueError, TypeError):
            pass

    # Fallback
    return time.time()


# ── Public API ────────────────────────────────────────────────────────

class SyslogListener:
    """Stateless syslog UDP receiver.

    Binds to a UDP port, parses incoming syslog messages in both
    RFC 3164 (BSD) and RFC 5424 (structured) formats, resolves the
    source IP to a device through ``instance_store``, and publishes
    structured events to the ``event_bus``.

    Messages larger than ``MAX_MESSAGE_SIZE`` bytes are truncated.

    Configuration
    ~~~~~~~~~~~~~
    * ``SYSLOG_LISTENER_PORT`` — override the default listening port (514).
    * ``SYSLOG_LISTENER_ENABLED`` — set to ``"false"`` to skip binding.

    Usage::

        listener = SyslogListener(event_bus, instance_store)
        await listener.start()
        ...
        await listener.stop()
    """

    MAX_MESSAGE_SIZE = 8192

    def __init__(
        self,
        event_bus: Any,
        instance_store: Any,
        port: int = 514,
        listen_ipv6: bool = False,
    ) -> None:
        env_port = os.environ.get("SYSLOG_LISTENER_PORT")
        self._port: int = int(env_port) if env_port else port
        self._enabled: bool = os.environ.get(
            "SYSLOG_LISTENER_ENABLED", "true"
        ).lower() not in ("false", "0", "no")
        self._event_bus = event_bus
        self._instance_store = instance_store
        self._transport: asyncio.DatagramTransport | None = None
        self._transport_v6: asyncio.DatagramTransport | None = None
        self._listen_ipv6: bool = listen_ipv6
        self._recv_count: int = 0
        self._error_count: int = 0

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def start(self) -> None:
        """Bind the UDP socket and begin receiving syslog messages."""
        if not self._enabled:
            logger.info("Syslog listener disabled via SYSLOG_LISTENER_ENABLED")
            return

        import socket as _socket

        loop = asyncio.get_running_loop()
        try:
            transport, _ = await loop.create_datagram_endpoint(
                lambda: _SyslogDatagramProtocol(self),
                local_addr=("0.0.0.0", self._port),
            )
            self._transport = transport  # type: ignore[assignment]
            logger.info(
                "Syslog listener started on UDP port %d", self._port
            )
        except OSError as exc:
            logger.error(
                "Failed to bind syslog listener on UDP port %d: %s",
                self._port,
                exc,
            )

        # IPv6 dual-stack support
        if self._listen_ipv6 and _socket.has_ipv6:
            try:
                transport_v6, _ = await loop.create_datagram_endpoint(
                    lambda: _SyslogDatagramProtocol(self),
                    local_addr=("::", self._port),
                    family=_socket.AF_INET6,
                )
                self._transport_v6 = transport_v6  # type: ignore[assignment]
                logger.info(
                    "Syslog IPv6 listener started on UDP port %d", self._port
                )
            except OSError as exc:
                logger.warning(
                    "Failed to bind syslog IPv6 listener on UDP port %d: %s",
                    self._port,
                    exc,
                )

    async def stop(self) -> None:
        """Close the UDP socket and stop receiving."""
        if self._transport is not None:
            self._transport.close()
            self._transport = None
        if self._transport_v6 is not None:
            self._transport_v6.close()
            self._transport_v6 = None
        logger.info(
            "Syslog listener stopped (received=%d, errors=%d)",
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
                "Syslog message from %s exceeds MAX_MESSAGE_SIZE (%d > %d), truncating",
                addr[0], len(data), self.MAX_MESSAGE_SIZE,
            )
            data = data[:self.MAX_MESSAGE_SIZE]
            truncated = True

        parsed = parse_syslog_message(data)
        if parsed is None:
            self._error_count += 1
            logger.debug(
                "Dropped unparseable syslog message from %s (%d bytes)",
                addr[0],
                len(data),
            )
            return

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
            "facility": parsed.get("facility"),
            "severity": parsed.get("severity"),
            "severity_code": parsed.get("severity_code"),
            "hostname": parsed.get("hostname"),
            "app_name": parsed.get("app_name"),
            "message": parsed.get("message", ""),
            "timestamp": _parse_timestamp(parsed.get("timestamp_raw")),
            "truncated": truncated,
        }

        # Fire-and-forget publish
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._publish(event))
        except RuntimeError:
            logger.debug("No running event loop; syslog event dropped")

    async def _publish(self, event: dict[str, Any]) -> None:
        """Publish a syslog event to the event bus, swallowing errors."""
        try:
            await self._event_bus.publish("syslog", event)
        except Exception as exc:
            self._error_count += 1
            logger.error(
                "Failed to publish syslog event %s: %s",
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
