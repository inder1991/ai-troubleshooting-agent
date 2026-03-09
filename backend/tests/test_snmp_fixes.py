"""Tests for SNMP engine cleanup and walk timeout."""
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

# Ensure the module-level names exist for patching even when pysnmp
# is not installed.  We set them to MagicMock sentinels before importing
# the module under test.
import src.network.snmp_collector as snmp_mod

# If pysnmp is not installed, the module-level names won't exist.
# Seed them so patch() targets are valid.
for _name in (
    "SnmpEngine", "bulk_cmd", "CommunityData", "UdpTransportTarget",
    "ContextData", "ObjectType", "ObjectIdentity", "UsmUserData", "get_cmd",
):
    if not hasattr(snmp_mod, _name):
        setattr(snmp_mod, _name, MagicMock())


@pytest.mark.asyncio
async def test_walk_interfaces_closes_engine():
    from src.network.snmp_collector import SNMPCollector, SNMPDeviceConfig

    collector = SNMPCollector.__new__(SNMPCollector)
    cfg = SNMPDeviceConfig(
        device_id="d1", ip="10.0.0.1", community="public",
        version="2c", port=161,
    )

    mock_engine = MagicMock()
    mock_engine.close_dispatcher = MagicMock()

    with patch.object(snmp_mod, "_PYSNMP_AVAILABLE", True), \
         patch.object(snmp_mod, "SnmpEngine", return_value=mock_engine), \
         patch.object(snmp_mod, "UdpTransportTarget", return_value=MagicMock()), \
         patch.object(snmp_mod, "CommunityData", return_value=MagicMock()), \
         patch.object(snmp_mod, "ContextData", return_value=MagicMock()), \
         patch.object(snmp_mod, "ObjectType", return_value=MagicMock()), \
         patch.object(snmp_mod, "ObjectIdentity", return_value=MagicMock()), \
         patch.object(snmp_mod, "bulk_cmd", new_callable=AsyncMock) as mock_bulk:
        # Return a truthy err_indication so the walk loop exits immediately
        mock_bulk.return_value = ("noSuchInstance", None, None, [])
        await collector._walk_interfaces(cfg)
        mock_engine.close_dispatcher.assert_called_once()


@pytest.mark.asyncio
async def test_walk_interfaces_closes_engine_on_error():
    from src.network.snmp_collector import SNMPCollector, SNMPDeviceConfig

    collector = SNMPCollector.__new__(SNMPCollector)
    cfg = SNMPDeviceConfig(
        device_id="d1", ip="10.0.0.1", community="public",
        version="2c", port=161,
    )

    mock_engine = MagicMock()
    with patch.object(snmp_mod, "_PYSNMP_AVAILABLE", True), \
         patch.object(snmp_mod, "SnmpEngine", return_value=mock_engine), \
         patch.object(snmp_mod, "UdpTransportTarget", return_value=MagicMock()), \
         patch.object(snmp_mod, "CommunityData", return_value=MagicMock()), \
         patch.object(snmp_mod, "ContextData", return_value=MagicMock()), \
         patch.object(snmp_mod, "ObjectType", return_value=MagicMock()), \
         patch.object(snmp_mod, "ObjectIdentity", return_value=MagicMock()), \
         patch.object(snmp_mod, "bulk_cmd", side_effect=Exception("timeout")):
        await collector._walk_interfaces(cfg)
        mock_engine.close_dispatcher.assert_called_once()
