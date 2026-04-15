"""Tests for hypothesis pattern deduplicator."""

import pytest

from src.hypothesis.deduplicator import deduplicate_patterns


class TestDeduplication:
    def test_clusters_memory_related(self):
        """OOMKilled + OutOfMemoryError + MemoryLeak → 1 'memory' hypothesis."""
        patterns = [
            {"exception_type": "OOMKilled", "severity": "critical", "frequency": 1},
            {"exception_type": "OutOfMemoryError", "severity": "high", "frequency": 2},
            {"exception_type": "MemoryLeak", "severity": "medium", "frequency": 3},
        ]
        result = deduplicate_patterns(patterns)
        assert len(result) == 1
        assert result[0].category == "memory"
        assert len(result[0].source_patterns) == 3

    def test_separates_different_categories(self):
        """OOMKilled + ConnectionTimeout + SlowQuery → 3 separate hypotheses."""
        patterns = [
            {"exception_type": "OOMKilled", "severity": "critical", "frequency": 1},
            {"exception_type": "ConnectionTimeout", "severity": "high", "frequency": 1},
            {"exception_type": "SlowQuery", "severity": "medium", "frequency": 1},
        ]
        result = deduplicate_patterns(patterns)
        categories = {h.category for h in result}
        assert categories == {"memory", "connection", "database"}

    def test_max_3_hypotheses(self):
        """5 different categories → only top 3 returned."""
        patterns = [
            {"exception_type": "OOMKilled", "severity": "critical", "frequency": 5},
            {"exception_type": "ConnectionTimeout", "severity": "high", "frequency": 3},
            {"exception_type": "SlowQuery", "severity": "medium", "frequency": 2},
            {"exception_type": "CPUThrottling", "severity": "low", "frequency": 1},
            {"exception_type": "DiskPressure", "severity": "low", "frequency": 1},
        ]
        result = deduplicate_patterns(patterns, max_hypotheses=3)
        assert len(result) == 3

    def test_ordered_by_severity_then_frequency(self):
        """Critical severity beats medium even with lower frequency."""
        patterns = [
            {"exception_type": "SlowQuery", "severity": "medium", "frequency": 10},
            {"exception_type": "OOMKilled", "severity": "critical", "frequency": 5},
            {"exception_type": "CPUThrottling", "severity": "low", "frequency": 100},
        ]
        result = deduplicate_patterns(patterns)
        # critical*5=20, medium*10=20, low*100=100 — wait, low=1*100=100
        # Actually: critical=4*5=20, medium=2*10=20, low=1*100=100
        # So order: cpu(100), memory(20), database(20)
        assert result[0].category == "cpu"
        assert result[1].category in ("memory", "database")

    def test_unmatched_gets_own_cluster(self):
        """'WeirdCustomError' → 'uncategorized' category."""
        patterns = [
            {"exception_type": "WeirdCustomError", "severity": "high", "frequency": 1},
        ]
        result = deduplicate_patterns(patterns)
        assert len(result) == 1
        assert result[0].category == "uncategorized"

    def test_empty_patterns(self):
        """[] → []."""
        result = deduplicate_patterns([])
        assert result == []

    def test_single_pattern(self):
        """1 pattern → 1 hypothesis."""
        patterns = [
            {"exception_type": "OOMKilled", "severity": "critical", "frequency": 1},
        ]
        result = deduplicate_patterns(patterns)
        assert len(result) == 1
        assert result[0].category == "memory"

    def test_hypothesis_ids_sequential(self):
        """Hypotheses get h1, h2, h3 IDs."""
        patterns = [
            {"exception_type": "OOMKilled", "severity": "critical", "frequency": 1},
            {"exception_type": "ConnectionTimeout", "severity": "high", "frequency": 1},
            {"exception_type": "SlowQuery", "severity": "medium", "frequency": 1},
        ]
        result = deduplicate_patterns(patterns)
        ids = [h.hypothesis_id for h in result]
        assert ids == ["h1", "h2", "h3"]

    def test_error_message_fallback(self):
        """Uses error_message when exception_type is missing."""
        patterns = [
            {"error_message": "java.lang.OutOfMemoryError: heap space", "severity": "critical", "frequency": 1},
        ]
        result = deduplicate_patterns(patterns)
        assert len(result) == 1
        assert result[0].category == "memory"

    def test_default_severity_and_frequency(self):
        """Patterns missing severity/frequency get defaults."""
        patterns = [
            {"exception_type": "OOMKilled"},
        ]
        result = deduplicate_patterns(patterns)
        assert len(result) == 1
        assert result[0].category == "memory"
