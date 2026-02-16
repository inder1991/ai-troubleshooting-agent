import re
import json

HEURISTIC_PATTERNS = {
    "connection_timeout": r"(?i)(connection\s*timed?\s*out|ETIMEDOUT|connect\s+ECONNREFUSED)",
    "oom_killed": r"(?i)(OOMKilled|out\s*of\s*memory|Cannot\s+allocate\s+memory)",
    "crash_loop": r"(?i)(CrashLoopBackOff|back-off\s+restarting)",
    "permission_denied": r"(?i)(permission\s+denied|EACCES|403\s+Forbidden)",
    "dns_failure": r"(?i)(NXDOMAIN|dns\s+resolution|could\s+not\s+resolve)",
    "disk_pressure": r"(?i)(DiskPressure|no\s+space\s+left|ENOSPC)",
    "image_pull": r"(?i)(ImagePullBackOff|ErrImagePull|image\s+not\s+found)",
}


class HeuristicPatternMatcher:
    def __init__(self):
        self._compiled = {k: re.compile(v) for k, v in HEURISTIC_PATTERNS.items()}

    def match(self, text: str) -> list[dict]:
        results = []
        for name, pattern in self._compiled.items():
            m = pattern.search(text)
            if m:
                results.append({"pattern": name, "match": m.group(), "start": m.start()})
        return results


class TieredLogProcessor:
    def __init__(self):
        self._heuristic = HeuristicPatternMatcher()

    def process_line(self, line: str) -> dict:
        # Tier 1: ECS JSON parsing
        try:
            data = json.loads(line)
            if isinstance(data, dict) and ("level" in data or "message" in data or "@timestamp" in data):
                return {"tier": 1, **data}
        except (json.JSONDecodeError, TypeError):
            pass

        # Tier 3: Heuristic fallback
        matches = self._heuristic.match(line)
        return {
            "tier": 3,
            "raw": line,
            "heuristic_matches": matches,
            "level": "ERROR" if matches else "UNKNOWN",
        }

    def process_batch(self, lines: list[str]) -> list[dict]:
        return [self.process_line(line) for line in lines]
