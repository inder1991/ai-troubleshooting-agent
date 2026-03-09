"""Tests for fidelity-based data merger."""
import time
import pytest

from src.network.collectors.data_merger import merge_collected_data, FIDELITY
from src.network.collectors.models import CollectedData


def _make_data(protocol: str, **kwargs) -> CollectedData:
    return CollectedData(
        device_id="dev-1",
        protocol=protocol,
        timestamp=time.time(),
        **kwargs,
    )


class TestMergeCollectedData:
    def test_empty_returns_none(self):
        assert merge_collected_data([]) is None

    def test_single_result_passthrough(self):
        data = _make_data("snmp", cpu_pct=42.0)
        merged = merge_collected_data([data])
        assert merged is data

    def test_higher_fidelity_wins_for_overlapping(self):
        snmp = _make_data("snmp", cpu_pct=50.0, mem_pct=60.0)
        gnmi = _make_data("gnmi", cpu_pct=55.0, mem_pct=None)

        merged = merge_collected_data([snmp, gnmi])
        # gNMI has higher fidelity, so its cpu_pct wins
        assert merged.cpu_pct == 55.0
        # mem_pct only in SNMP, so it fills the gap
        assert merged.mem_pct == 60.0

    def test_fills_gaps_from_lower_fidelity(self):
        gnmi = _make_data("gnmi", cpu_pct=55.0, temperature=None)
        snmp = _make_data("snmp", cpu_pct=50.0, temperature=42.5)

        merged = merge_collected_data([gnmi, snmp])
        assert merged.cpu_pct == 55.0       # gNMI wins
        assert merged.temperature == 42.5   # SNMP fills gap

    def test_interface_metrics_merged(self):
        gnmi = _make_data("gnmi", interface_metrics={"eth0": {"in_octets": 100}})
        snmp = _make_data("snmp", interface_metrics={"eth0": {"in_octets": 90}, "eth1": {"in_octets": 200}})

        merged = merge_collected_data([gnmi, snmp])
        assert "eth0" in merged.interface_metrics  # gNMI version
        assert merged.interface_metrics["eth0"]["in_octets"] == 100  # gNMI wins
        assert "eth1" in merged.interface_metrics  # SNMP fills gap

    def test_metadata_merged(self):
        gnmi = _make_data("gnmi", metadata={"vendor": "arista"})
        snmp = _make_data("snmp", metadata={"vendor": "arista", "serial": "ABC123"})

        merged = merge_collected_data([gnmi, snmp])
        assert merged.metadata["vendor"] == "arista"
        assert merged.metadata["serial"] == "ABC123"

    def test_custom_metrics_merged(self):
        gnmi = _make_data("gnmi", custom_metrics={"bgp_peers": 5})
        snmp = _make_data("snmp", custom_metrics={"bgp_peers": 4, "cpu_temp": 45})

        merged = merge_collected_data([gnmi, snmp])
        assert merged.custom_metrics["bgp_peers"] == 5  # gNMI wins
        assert merged.custom_metrics["cpu_temp"] == 45   # SNMP fills

    def test_fidelity_ordering(self):
        assert FIDELITY["gnmi"] > FIDELITY["snmp"]
        assert FIDELITY["restconf"] > FIDELITY["snmp"]
        assert FIDELITY["snmp"] > FIDELITY["ssh_cli"]

    def test_three_source_merge(self):
        ssh = _make_data("ssh_cli", uptime_seconds=1000, cpu_pct=30.0)
        snmp = _make_data("snmp", uptime_seconds=1001, cpu_pct=None, temperature=35.0)
        gnmi = _make_data("gnmi", uptime_seconds=None, cpu_pct=45.0)

        merged = merge_collected_data([ssh, snmp, gnmi])
        assert merged.cpu_pct == 45.0       # gNMI
        assert merged.temperature == 35.0   # SNMP
        assert merged.uptime_seconds == 1001  # SNMP (higher fidelity than SSH)
