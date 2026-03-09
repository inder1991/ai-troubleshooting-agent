"""Tests for YAML profile loading and sysObjectID matching."""
import pytest
from pathlib import Path

from src.network.collectors.profile_loader import ProfileLoader, PROFILES_DIR


@pytest.fixture
def loader():
    pl = ProfileLoader()
    pl.load_all()
    return pl


class TestProfileLoading:
    def test_loads_profiles_from_directory(self, loader):
        profiles = loader.profiles
        assert len(profiles) > 0
        # Check that base profiles exist
        assert "_base" in profiles
        assert "_generic-if" in profiles
        assert "_generic-ip" in profiles

    def test_loads_vendor_profiles(self, loader):
        names = set(loader.profiles.keys())
        assert "cisco-catalyst" in names
        assert "cisco-ios-xe" in names
        assert "arista-eos" in names
        assert "palo-alto" in names
        assert "juniper-junos" in names
        assert "generic" in names

    def test_list_profiles_excludes_base(self, loader):
        listed = loader.list_profiles()
        names = [p.name for p in listed]
        assert "_base" not in names
        assert "_generic-if" not in names
        assert "cisco-catalyst" in names

    def test_profile_has_metrics(self, loader):
        cisco = loader.get("cisco-catalyst")
        assert cisco is not None
        assert len(cisco.metrics) > 0
        assert cisco.vendor == "cisco"
        assert cisco.device_type == "switch"

    def test_profile_extends_base(self, loader):
        """Verify that extends inheritance works — cisco-catalyst should have base metrics."""
        cisco = loader.get("cisco-catalyst")
        metric_names = [m.symbol.name for m in cisco.metrics if m.symbol]
        # sysUpTimeInstance comes from _base.yaml
        assert "sysUpTimeInstance" in metric_names

    def test_profile_has_metadata_fields(self, loader):
        cisco = loader.get("cisco-catalyst")
        assert "name" in cisco.metadata_fields  # from _base
        assert "vendor" in cisco.metadata_fields

    def test_generic_profile_has_wildcard(self, loader):
        generic = loader.get("generic")
        assert "*" in generic.sysobjectid

    def test_load_all_returns_count(self):
        pl = ProfileLoader()
        count = pl.load_all()
        assert count >= 6  # At least 6 vendor profiles


class TestSysObjectIDMatching:
    def test_exact_cisco_match(self, loader):
        # Cisco Catalyst OID
        profile = loader.match("1.3.6.1.4.1.9.1.123")
        assert profile is not None
        assert profile.name == "cisco-catalyst"

    def test_cisco_c9000_match(self, loader):
        profile = loader.match("1.3.6.1.4.1.9.12.3.1.3.1234")
        assert profile is not None
        assert profile.vendor == "cisco"

    def test_arista_match(self, loader):
        profile = loader.match("1.3.6.1.4.1.30065.1.3011.7048.20.18")
        assert profile is not None
        assert profile.name == "arista-eos"

    def test_palo_alto_match(self, loader):
        profile = loader.match("1.3.6.1.4.1.25461.2.3.1")
        assert profile is not None
        assert profile.name == "palo-alto"

    def test_juniper_match(self, loader):
        profile = loader.match("1.3.6.1.4.1.2636.1.1.1.2.123")
        assert profile is not None
        assert profile.name == "juniper-junos"

    def test_unknown_oid_falls_back_to_generic(self, loader):
        profile = loader.match("1.3.6.1.4.1.99999.1.1")
        assert profile is not None
        assert profile.name == "generic"

    def test_empty_oid_returns_generic(self, loader):
        profile = loader.match("")
        assert profile is not None
        assert profile.name == "generic"

    def test_none_oid_returns_generic(self, loader):
        profile = loader.match(None)
        assert profile is not None
        assert profile.name == "generic"

    def test_specific_match_wins_over_wildcard(self, loader):
        """More specific sysObjectID patterns should match before '*'."""
        # A Cisco OID should match cisco-catalyst, not generic
        profile = loader.match("1.3.6.1.4.1.9.1.999")
        assert profile.name != "generic"

    def test_get_nonexistent_profile(self, loader):
        assert loader.get("nonexistent") is None


class TestPatternSpecificity:
    def test_wildcard_only_is_zero(self):
        assert ProfileLoader._pattern_specificity("*") == 0

    def test_exact_oid_high_specificity(self):
        spec = ProfileLoader._pattern_specificity("1.3.6.1.4.1.9.1.123")
        assert spec > 5

    def test_trailing_wildcard_moderate(self):
        spec = ProfileLoader._pattern_specificity("1.3.6.1.4.1.9.1.*")
        assert spec > 0
        assert spec < ProfileLoader._pattern_specificity("1.3.6.1.4.1.9.1.123")


class TestOIDMatching:
    def test_exact_match(self):
        assert ProfileLoader._oid_matches("1.3.6.1.4.1.9.1.123", "1.3.6.1.4.1.9.1.123")

    def test_wildcard_match(self):
        assert ProfileLoader._oid_matches("1.3.6.1.4.1.9.1.456", "1.3.6.1.4.1.9.1.*")

    def test_full_wildcard(self):
        assert ProfileLoader._oid_matches("anything", "*")

    def test_no_match(self):
        assert not ProfileLoader._oid_matches("1.3.6.1.4.1.9.1.123", "1.3.6.1.4.1.30065.*")
