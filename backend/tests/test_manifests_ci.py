"""CI-enforced invariants on shipped agent manifests."""

from pathlib import Path

from src.contracts.registry import ContractRegistry

MANIFESTS_DIR = Path(__file__).parent.parent / "src" / "agents" / "manifests"


def test_manifests_directory_exists():
    assert MANIFESTS_DIR.is_dir(), f"expected {MANIFESTS_DIR}"


def test_all_manifests_load():
    reg = ContractRegistry()
    reg.load_all(MANIFESTS_DIR)
    assert len(reg.list()) >= 1


def test_log_agent_manifest_present():
    reg = ContractRegistry()
    reg.load_all(MANIFESTS_DIR)
    c = reg.get("log_agent", version=1)
    assert c.category == "observability"
    assert "service_name" in c.input_schema["properties"]


def test_minimum_manifest_count():
    reg = ContractRegistry()
    reg.load_all(MANIFESTS_DIR)
    assert len(reg.list()) >= 10, f"got {len(reg.list())}"
