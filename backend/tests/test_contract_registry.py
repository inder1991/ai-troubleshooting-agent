"""ContractRegistry — YAML manifest loading, dedupe, version resolution."""

from pathlib import Path

import pytest

from src.contracts.registry import ContractRegistry, ManifestLoadError

FIXTURES = Path(__file__).parent / "fixtures" / "manifests"


def _copy(src_name: str, dest: Path) -> None:
    dest.write_text((FIXTURES / src_name).read_text())


def test_load_valid_manifest(tmp_path):
    _copy("good_agent.yaml", tmp_path / "good_agent.yaml")
    reg = ContractRegistry()
    reg.load_all(tmp_path)
    c = reg.get("good_agent", version=1)
    assert c.name == "good_agent"
    assert reg.list()[0].name == "good_agent"


def test_load_invalid_manifest_raises(tmp_path):
    _copy("bad_agent.yaml", tmp_path / "bad_agent.yaml")
    reg = ContractRegistry()
    with pytest.raises(ManifestLoadError) as exc_info:
        reg.load_all(tmp_path)
    assert "bad_agent" in str(exc_info.value)


def test_get_missing_raises(tmp_path):
    reg = ContractRegistry()
    reg.load_all(tmp_path)
    with pytest.raises(KeyError):
        reg.get("nonexistent", version=1)


def test_get_missing_version_raises(tmp_path):
    _copy("good_agent.yaml", tmp_path / "good_agent.yaml")
    reg = ContractRegistry()
    reg.load_all(tmp_path)
    with pytest.raises(KeyError):
        reg.get("good_agent", version=99)


def test_duplicate_name_version_raises(tmp_path):
    src = (FIXTURES / "good_agent.yaml").read_text()
    (tmp_path / "good_agent.yaml").write_text(src)
    (tmp_path / "good_agent_dup.yaml").write_text(src)
    reg = ContractRegistry()
    with pytest.raises(ManifestLoadError) as exc_info:
        reg.load_all(tmp_path)
    assert "duplicate" in str(exc_info.value).lower()


def test_list_returns_latest_per_name(tmp_path):
    _copy("good_agent.yaml", tmp_path / "a_v1.yaml")
    v2 = (FIXTURES / "good_agent.yaml").read_text().replace("version: 1", "version: 2")
    (tmp_path / "a_v2.yaml").write_text(v2)
    reg = ContractRegistry()
    reg.load_all(tmp_path)
    latest = reg.list()
    assert len(latest) == 1
    assert latest[0].version == 2


def test_list_all_versions_returns_both(tmp_path):
    _copy("good_agent.yaml", tmp_path / "a_v1.yaml")
    v2 = (FIXTURES / "good_agent.yaml").read_text().replace("version: 1", "version: 2")
    (tmp_path / "a_v2.yaml").write_text(v2)
    reg = ContractRegistry()
    reg.load_all(tmp_path)
    assert {c.version for c in reg.list_all_versions()} == {1, 2}


def test_non_mapping_yaml_raises(tmp_path):
    (tmp_path / "scalar.yaml").write_text("just a string\n")
    reg = ContractRegistry()
    with pytest.raises(ManifestLoadError):
        reg.load_all(tmp_path)
