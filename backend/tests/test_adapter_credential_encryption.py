"""Regression test: adapter api_key must be encrypted in SQLite."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.network.topology_store import TopologyStore
from src.network.models import AdapterInstance, FirewallVendor


def _temp_store() -> TopologyStore:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return TopologyStore(db_path=path)


def test_api_key_not_stored_in_plaintext():
    """Save an adapter, read raw SQLite -- api_key column must NOT be plaintext."""
    store = _temp_store()
    plaintext_key = "sk-super-secret-paloalto-token-12345"

    instance = AdapterInstance(
        instance_id="test-inst-1",
        label="Test PAN",
        vendor=FirewallVendor.PALO_ALTO,
        api_endpoint="https://pan.example.com",
        api_key=plaintext_key,
    )
    store.save_adapter_instance(instance)

    # Read raw SQLite row
    conn = store._conn()
    try:
        row = conn.execute(
            "SELECT api_key FROM adapter_instances WHERE instance_id=?",
            ("test-inst-1",),
        ).fetchone()
        raw_stored = row["api_key"]
    finally:
        conn.close()

    assert raw_stored != plaintext_key, (
        f"api_key stored in plaintext! raw={raw_stored}"
    )


def test_api_key_roundtrip():
    """Save and retrieve an adapter -- api_key should be decrypted back to original."""
    store = _temp_store()
    plaintext_key = "sk-another-secret-key-67890"

    instance = AdapterInstance(
        instance_id="test-inst-2",
        label="Test AWS",
        vendor=FirewallVendor.AWS_SG,
        api_endpoint="https://aws.example.com",
        api_key=plaintext_key,
    )
    store.save_adapter_instance(instance)

    loaded = store.get_adapter_instance("test-inst-2")
    assert loaded is not None
    assert loaded.api_key == plaintext_key, (
        f"Decrypted key doesn't match: {loaded.api_key}"
    )


def test_list_adapter_instances_decrypts():
    """list_adapter_instances should also decrypt api_keys."""
    store = _temp_store()
    plaintext_key = "sk-list-test-key"

    instance = AdapterInstance(
        instance_id="test-inst-3",
        label="Test ZS",
        vendor=FirewallVendor.ZSCALER,
        api_endpoint="https://zs.example.com",
        api_key=plaintext_key,
    )
    store.save_adapter_instance(instance)

    instances = store.list_adapter_instances()
    assert len(instances) == 1
    assert instances[0].api_key == plaintext_key


def test_list_adapter_instances_by_vendor_decrypts():
    """list_adapter_instances_by_vendor should also decrypt api_keys."""
    store = _temp_store()
    plaintext_key = "sk-vendor-filter-key-99999"

    instance = AdapterInstance(
        instance_id="test-inst-4",
        label="Test PAN Vendor",
        vendor=FirewallVendor.PALO_ALTO,
        api_endpoint="https://pan-vendor.example.com",
        api_key=plaintext_key,
    )
    store.save_adapter_instance(instance)

    instances = store.list_adapter_instances_by_vendor(FirewallVendor.PALO_ALTO.value)
    assert len(instances) == 1
    assert instances[0].api_key == plaintext_key, (
        f"Decrypted key doesn't match: {instances[0].api_key}"
    )


def test_corrupted_api_key_returns_empty_string():
    """Corrupted (non-Fernet) api_key in SQLite should gracefully fall back to empty string."""
    store = _temp_store()
    plaintext_key = "sk-will-be-corrupted-key"

    instance = AdapterInstance(
        instance_id="test-inst-5",
        label="Test Corrupt",
        vendor=FirewallVendor.AWS_SG,
        api_endpoint="https://corrupt.example.com",
        api_key=plaintext_key,
    )
    store.save_adapter_instance(instance)

    # Directly overwrite the raw SQLite row with garbage (non-Fernet) data
    conn = store._conn()
    try:
        conn.execute(
            "UPDATE adapter_instances SET api_key=? WHERE instance_id=?",
            ("not-valid-fernet-garbage-XYZ!!!", "test-inst-5"),
        )
        conn.commit()
    finally:
        conn.close()

    loaded = store.get_adapter_instance("test-inst-5")
    assert loaded is not None
    assert loaded.api_key == "", (
        f"Corrupted api_key should fall back to empty string, got: {loaded.api_key!r}"
    )
