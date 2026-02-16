import json
import pytest
from src.agents.log_processing import HeuristicPatternMatcher, TieredLogProcessor


class TestHeuristicPatternMatcher:
    def setup_method(self):
        self.matcher = HeuristicPatternMatcher()

    def test_detect_connection_timeout(self):
        results = self.matcher.match("ERROR: connection timed out to host db-primary:5432")
        assert len(results) == 1
        assert results[0]["pattern"] == "connection_timeout"

    def test_detect_oom_killed(self):
        results = self.matcher.match("Container was OOMKilled with exit code 137")
        assert len(results) == 1
        assert results[0]["pattern"] == "oom_killed"

    def test_detect_crash_loop(self):
        results = self.matcher.match("Pod entered CrashLoopBackOff state")
        assert len(results) == 1
        assert results[0]["pattern"] == "crash_loop"

    def test_no_match(self):
        results = self.matcher.match("INFO: Application started successfully on port 8080")
        assert len(results) == 0


class TestTieredLogProcessor:
    def setup_method(self):
        self.processor = TieredLogProcessor()

    def test_tier1_ecs_parsing(self):
        ecs_line = json.dumps({"level": "ERROR", "message": "Connection refused", "@timestamp": "2026-01-01T00:00:00Z"})
        result = self.processor.process_line(ecs_line)
        assert result["tier"] == 1
        assert result["level"] == "ERROR"
        assert result["message"] == "Connection refused"

    def test_tier3_heuristic_fallback(self):
        raw_line = "2026-01-01 ERROR connection timed out to db-primary"
        result = self.processor.process_line(raw_line)
        assert result["tier"] == 3
        assert result["level"] == "ERROR"
        assert len(result["heuristic_matches"]) == 1
        assert result["heuristic_matches"][0]["pattern"] == "connection_timeout"

    def test_tier3_no_match_unknown_level(self):
        raw_line = "Some random log line with no known pattern"
        result = self.processor.process_line(raw_line)
        assert result["tier"] == 3
        assert result["level"] == "UNKNOWN"
        assert len(result["heuristic_matches"]) == 0

    def test_process_batch(self):
        lines = [
            json.dumps({"level": "INFO", "message": "healthy"}),
            "ERROR: OOMKilled container",
            "plain log line",
        ]
        results = self.processor.process_batch(lines)
        assert len(results) == 3
        assert results[0]["tier"] == 1
        assert results[1]["tier"] == 3
        assert results[1]["level"] == "ERROR"
        assert results[2]["tier"] == 3
        assert results[2]["level"] == "UNKNOWN"
