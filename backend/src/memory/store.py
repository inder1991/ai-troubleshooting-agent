import json
import os
from typing import Optional
from .models import IncidentFingerprint, SimilarIncident


class MemoryStore:
    def __init__(self, store_path: str = "./data/memory/incidents.json"):
        self._store_path = store_path
        os.makedirs(os.path.dirname(store_path), exist_ok=True)
        if not os.path.exists(store_path):
            with open(store_path, "w") as f:
                json.dump([], f)

    def _load(self) -> list[dict]:
        with open(self._store_path) as f:
            return json.load(f)

    def _save(self, data: list[dict]) -> None:
        with open(self._store_path, "w") as f:
            json.dump(data, f, default=str)

    def store_incident(self, fingerprint: IncidentFingerprint) -> None:
        data = self._load()
        data.append(fingerprint.model_dump(mode="json"))
        self._save(data)

    def find_similar(self, current: IncidentFingerprint, threshold: float = 0.5) -> list[SimilarIncident]:
        stored = self._load()
        results = []
        for item in stored:
            fp = IncidentFingerprint.model_validate(item)
            score = self._signal_match(current, fp)
            if score >= threshold:
                results.append(SimilarIncident(
                    fingerprint=fp, similarity_score=score, match_type="signal"
                ))
        return sorted(results, key=lambda x: x.similarity_score, reverse=True)[:5]

    def _signal_match(self, a: IncidentFingerprint, b: IncidentFingerprint) -> float:
        """Jaccard similarity on error patterns + services + symptoms."""
        sets_a = set(a.error_patterns + a.affected_services + a.symptom_categories)
        sets_b = set(b.error_patterns + b.affected_services + b.symptom_categories)
        if not sets_a and not sets_b:
            return 0.0
        intersection = sets_a & sets_b
        union = sets_a | sets_b
        return len(intersection) / len(union) if union else 0.0

    def is_novel(self, fingerprint: IncidentFingerprint) -> bool:
        """Only store if signal_match < 0.8 against all stored."""
        stored = self._load()
        for item in stored:
            fp = IncidentFingerprint.model_validate(item)
            if self._signal_match(fingerprint, fp) >= 0.8:
                return False
        return True

    def list_all(self) -> list[IncidentFingerprint]:
        return [IncidentFingerprint.model_validate(item) for item in self._load()]
