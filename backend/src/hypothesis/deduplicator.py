"""Cluster similar error patterns into max N hypotheses."""

from __future__ import annotations

from collections import defaultdict

from src.models.hypothesis import Hypothesis

SEMANTIC_CLUSTERS = {
    "memory":     ["OOMKilled", "OutOfMemoryError", "MemoryLeak", "heap",
                   "GC overhead", "memory_limit", "OOMKilling", "java.lang.OutOfMemoryError"],
    "connection": ["ConnectionPool", "ConnectionTimeout", "ConnectionRefused",
                   "pool exhausted", "ECONNREFUSED", "socket", "connection reset",
                   "PoolExhausted"],
    "database":   ["SlowQuery", "DeadLock", "QueryTimeout", "lock wait",
                   "database", "deadlock"],
    "cpu":        ["CPUThrottling", "thread starvation", "high_cpu", "cpu_throttl"],
    "disk":       ["DiskPressure", "NoSpaceLeft", "ENOSPC", "disk full", "filesystem"],
    "network":    ["NetworkTimeout", "DNS", "ETIMEDOUT", "UnknownHost", "NoRouteToHost"],
    "config":     ["ConfigError", "InvalidConfig", "MissingEnv", "ConfigMap"],
}

SEVERITY_WEIGHTS = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def _classify_pattern(text: str) -> str:
    """Return the first matching cluster name, or 'uncategorized'."""
    lower = text.lower()
    for cluster_name, keywords in SEMANTIC_CLUSTERS.items():
        for keyword in keywords:
            if keyword.lower() in lower:
                return cluster_name
    return "uncategorized"


def deduplicate_patterns(patterns: list[dict], max_hypotheses: int = 3) -> list[Hypothesis]:
    """Cluster similar error patterns into max N hypotheses.

    Algorithm:
    1. For each pattern, get exception_type (or error_message as fallback)
    2. Match against SEMANTIC_CLUSTERS keywords (case-insensitive substring)
    3. First matching cluster wins for that pattern
    4. Unmatched patterns -> "uncategorized" cluster
    5. Score each cluster: sum(SEVERITY_WEIGHTS[severity] * frequency) for all patterns
    6. Sort clusters by score descending
    7. Take top max_hypotheses clusters
    8. Each cluster -> Hypothesis with sequential IDs

    Returns empty list if patterns is empty.
    """
    if not patterns:
        return []

    # Group patterns by cluster
    clusters: dict[str, list[dict]] = defaultdict(list)
    scores: dict[str, float] = defaultdict(float)

    for pat in patterns:
        text = pat.get("exception_type") or pat.get("error_message", "")
        category = _classify_pattern(text)
        clusters[category].append(pat)

        severity = pat.get("severity", "low")
        frequency = pat.get("frequency", 1)
        weight = SEVERITY_WEIGHTS.get(severity, 1)
        scores[category] += weight * frequency

    # Sort by score descending, take top N
    sorted_categories = sorted(scores, key=lambda c: scores[c], reverse=True)
    top = sorted_categories[:max_hypotheses]

    # Build Hypothesis objects
    result: list[Hypothesis] = []
    for i, cat in enumerate(top, start=1):
        result.append(
            Hypothesis(
                hypothesis_id=f"h{i}",
                category=cat,
                source_patterns=clusters[cat],
            )
        )

    return result
