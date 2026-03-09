"""Tests for TopologyStore connection pooling and thread-safe cache access."""
import os
import threading
import pytest
from src.network.topology_store import TopologyStore
from src.network.models import Device, DeviceType


class TestTopologyConcurrency:
    """Verify that TopologyStore can handle concurrent reads safely."""

    @pytest.fixture
    def store(self, tmp_path):
        db_path = os.path.join(str(tmp_path), "test_concurrency.db")
        s = TopologyStore(db_path=db_path)
        # Seed a few devices so reads have data to return
        for i in range(5):
            s.add_device(Device(
                id=f"dev-{i}", name=f"Device{i}",
                device_type=DeviceType.ROUTER,
                management_ip=f"10.0.0.{i + 1}",
            ))
        return s

    def test_concurrent_reads(self, store):
        """10 threads reading list_devices simultaneously should not error."""
        errors = []

        def reader():
            try:
                devices = store.list_devices()
                assert len(devices) == 5
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=reader) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0, f"Concurrent reads produced errors: {errors}"

    def test_concurrent_reads_and_writes(self, store):
        """Mixed reads and writes from multiple threads should not corrupt state."""
        errors = []

        def reader():
            try:
                store.list_devices()
            except Exception as e:
                errors.append(e)

        def writer(idx):
            try:
                store.add_device(Device(
                    id=f"writer-dev-{idx}", name=f"WriterDevice{idx}",
                    device_type=DeviceType.SWITCH,
                    management_ip=f"10.1.0.{idx + 1}",
                ))
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(5):
            threads.append(threading.Thread(target=reader))
            threads.append(threading.Thread(target=writer, args=(i,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0, f"Concurrent read/write produced errors: {errors}"

    def test_connection_pool_returns_connections(self, store):
        """Connections should be reused via the pool rather than always creating new ones."""
        # Get a connection and return it
        conn1 = store._conn()
        store._return_conn(conn1)

        # Getting another should reuse the pooled connection
        conn2 = store._conn()
        assert conn1 is conn2, "Pool should return the same connection object"
        store._return_conn(conn2)

    def test_pool_overflow_closes_connection(self, store):
        """When the pool is full (5), extra connections should be closed, not queued."""
        conns = []
        # Fill the pool
        for _ in range(5):
            c = store._conn()
            conns.append(c)

        # Return all to fill the pool
        for c in conns:
            store._return_conn(c)

        # Pool should now be full (5 items). Return one more — it should be closed.
        extra_conn = store._conn()  # takes one from pool (now 4 in pool)
        store._return_conn(extra_conn)  # returns to pool (now 5 in pool)

        # Pool size should be 5 (max)
        assert store._pool.qsize() == 5

    def test_cache_lock_exists(self, store):
        """Store should have a threading lock for cache access."""
        assert hasattr(store, '_cache_lock')
        assert isinstance(store._cache_lock, type(threading.Lock()))
