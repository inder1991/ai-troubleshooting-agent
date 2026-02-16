import pytest
import os
import tempfile
from src.memory.models import IncidentFingerprint, SimilarIncident
from src.memory.store import MemoryStore


class TestIncidentFingerprint:
    def test_create(self):
        fp = IncidentFingerprint(session_id="s-123", error_patterns=["ConnectionTimeout"],
                                 affected_services=["order-svc"], symptom_categories=["connection_timeout"])
        assert fp.fingerprint_id is not None
        assert fp.session_id == "s-123"


class TestMemoryStore:
    @pytest.fixture
    def store(self, tmp_path):
        return MemoryStore(store_path=str(tmp_path / "test_incidents.json"))

    def test_store_and_list(self, store):
        fp = IncidentFingerprint(session_id="s-1", error_patterns=["timeout"])
        store.store_incident(fp)
        assert len(store.list_all()) == 1

    def test_find_similar(self, store):
        fp1 = IncidentFingerprint(session_id="s-1", error_patterns=["timeout"],
                                  affected_services=["order-svc"], symptom_categories=["connection_timeout"])
        store.store_incident(fp1)
        current = IncidentFingerprint(session_id="s-2", error_patterns=["timeout"],
                                      affected_services=["order-svc"], symptom_categories=["connection_timeout"])
        similar = store.find_similar(current, threshold=0.5)
        assert len(similar) >= 1
        assert similar[0].similarity_score > 0.5

    def test_find_no_match(self, store):
        fp1 = IncidentFingerprint(session_id="s-1", error_patterns=["timeout"])
        store.store_incident(fp1)
        current = IncidentFingerprint(session_id="s-2", error_patterns=["oom_killed"],
                                      affected_services=["payment-svc"])
        similar = store.find_similar(current, threshold=0.5)
        assert len(similar) == 0

    def test_is_novel(self, store):
        fp = IncidentFingerprint(session_id="s-1", error_patterns=["timeout"], affected_services=["order-svc"])
        assert store.is_novel(fp) is True
        store.store_incident(fp)
        same = IncidentFingerprint(session_id="s-2", error_patterns=["timeout"], affected_services=["order-svc"])
        assert store.is_novel(same) is False

    def test_signal_match_jaccard(self, store):
        a = IncidentFingerprint(session_id="a", error_patterns=["A", "B"], symptom_categories=["X"])
        b = IncidentFingerprint(session_id="b", error_patterns=["B", "C"], symptom_categories=["X"])
        score = store._signal_match(a, b)
        # intersection={B, X}=2, union={A,B,C,X}=4, score=0.5
        assert abs(score - 0.5) < 0.01
