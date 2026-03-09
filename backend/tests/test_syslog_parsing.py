"""Tests for syslog timestamp parsing (#27)."""

import time
from datetime import datetime, timezone

import pytest

from src.network.collectors.syslog_listener import _parse_timestamp


class TestRFC3164Timestamp:
    """RFC 3164 BSD-style timestamps: 'Mar  9 12:34:56'."""

    def test_parse_rfc3164_basic(self):
        ts = _parse_timestamp("Mar  9 12:34:56")
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        assert dt.month == 3
        assert dt.day == 9
        assert dt.hour == 12
        assert dt.minute == 34
        assert dt.second == 56

    def test_parse_rfc3164_uses_current_year(self):
        ts = _parse_timestamp("Jan 15 08:00:00")
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        expected_year = datetime.now(tz=timezone.utc).year
        assert dt.year == expected_year

    def test_parse_rfc3164_single_digit_day(self):
        ts = _parse_timestamp("Dec  1 00:00:00")
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        assert dt.month == 12
        assert dt.day == 1

    def test_parse_rfc3164_double_digit_day(self):
        ts = _parse_timestamp("Oct 25 23:59:59")
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        assert dt.month == 10
        assert dt.day == 25
        assert dt.hour == 23
        assert dt.minute == 59
        assert dt.second == 59


class TestRFC5424Timestamp:
    """RFC 5424 ISO 8601 timestamps: '2026-03-09T12:34:56.000Z'."""

    def test_parse_rfc5424_with_z(self):
        ts = _parse_timestamp("2026-03-09T12:34:56.000Z")
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        assert dt.year == 2026
        assert dt.month == 3
        assert dt.day == 9
        assert dt.hour == 12
        assert dt.minute == 34
        assert dt.second == 56

    def test_parse_rfc5424_without_fractional(self):
        ts = _parse_timestamp("2026-03-09T12:34:56Z")
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        assert dt.year == 2026
        assert dt.month == 3
        assert dt.day == 9

    def test_parse_rfc5424_with_offset(self):
        ts = _parse_timestamp("2026-03-09T12:34:56+00:00")
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        assert dt.year == 2026
        assert dt.month == 3
        assert dt.hour == 12


class TestTimestampFallback:
    """Fallback behavior for unparseable timestamps."""

    def test_fallback_returns_current_time_for_garbage(self):
        before = time.time()
        ts = _parse_timestamp("this is not a timestamp")
        after = time.time()
        assert before <= ts <= after

    def test_fallback_returns_current_time_for_none(self):
        before = time.time()
        ts = _parse_timestamp(None)
        after = time.time()
        assert before <= ts <= after

    def test_fallback_returns_current_time_for_empty(self):
        before = time.time()
        ts = _parse_timestamp("")
        after = time.time()
        assert before <= ts <= after
