"""Tests for syslog message template aggregation."""
import pytest
import time

from src.network.collectors.syslog_aggregator import SyslogAggregator


class TestSyslogAggregator:
    def test_aggregate_identical_messages(self):
        """Identical messages from the same device should aggregate."""
        agg = SyslogAggregator()
        for _ in range(5):
            agg.add("10.0.0.1", "Link up on interface eth0", "warning", "local0")

        groups = agg.get_groups()
        assert len(groups) == 1
        assert groups[0]["count"] == 5
        assert groups[0]["device_ip"] == "10.0.0.1"

    def test_aggregate_similar_messages(self):
        """Messages with same template but different values should aggregate."""
        agg = SyslogAggregator()
        agg.add("10.0.0.1", "Interface GigabitEthernet0/1 changed state to up", "notice", "local0")
        agg.add("10.0.0.1", "Interface GigabitEthernet0/2 changed state to up", "notice", "local0")
        agg.add("10.0.0.1", "Interface GigabitEthernet0/3 changed state to up", "notice", "local0")

        groups = agg.get_groups()
        # These should group by template
        assert len(groups) == 1
        assert groups[0]["count"] == 3

    def test_different_devices_separate_groups(self):
        """Same message from different devices should be separate groups."""
        agg = SyslogAggregator()
        agg.add("10.0.0.1", "Link down on eth0", "error", "local0")
        agg.add("10.0.0.2", "Link down on eth0", "error", "local0")

        groups = agg.get_groups()
        assert len(groups) == 2

    def test_different_severities_separate(self):
        """Same message with different severities should be separate groups."""
        agg = SyslogAggregator()
        agg.add("10.0.0.1", "Interface flapping", "warning", "local0")
        agg.add("10.0.0.1", "Interface flapping", "error", "local0")

        groups = agg.get_groups()
        assert len(groups) == 2

    def test_group_includes_sample_messages(self):
        """Each group should include a sample of recent messages."""
        agg = SyslogAggregator()
        for i in range(10):
            agg.add("10.0.0.1", f"Error {100 + i} on interface", "error", "local0")

        groups = agg.get_groups()
        assert len(groups) == 1
        assert "samples" in groups[0]
        assert len(groups[0]["samples"]) <= 5  # max 5 samples

    def test_clear_resets(self):
        """clear() should remove all aggregated groups."""
        agg = SyslogAggregator()
        agg.add("10.0.0.1", "test", "info", "local0")
        assert len(agg.get_groups()) == 1
        agg.clear()
        assert len(agg.get_groups()) == 0

    def test_template_extraction(self):
        """_extract_template should replace numbers/IPs with placeholders."""
        agg = SyslogAggregator()
        tpl = agg._extract_template("BGP peer 192.168.1.1 down after 3600 seconds")
        assert "192.168.1.1" not in tpl
        assert "3600" not in tpl
        assert "<IP>" in tpl or "<NUM>" in tpl

    def test_max_groups_bounded(self):
        """Should not exceed MAX_GROUPS."""
        agg = SyslogAggregator(max_groups=5)
        for i in range(20):
            agg.add(f"10.0.{i}.1", f"unique message {i}", "info", "local0")
        assert len(agg._groups) <= 5
