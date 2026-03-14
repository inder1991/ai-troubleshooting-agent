"""Shared graph traversal utilities for diagnostic pipeline."""
from __future__ import annotations
from collections import defaultdict, deque
from src.agents.cluster.state import DiagnosticGraph


def bfs_reachable(graph: DiagnosticGraph, start_id: str) -> set[str]:
    adj: dict[str, set[str]] = defaultdict(set)
    for edge in graph.edges:
        adj[edge.from_id].add(edge.to_id)
    visited = set()
    queue = deque([start_id])
    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        for neighbor in adj.get(current, set()):
            if neighbor not in visited:
                queue.append(neighbor)
    return visited


def graph_has_path(graph: DiagnosticGraph, from_id: str, to_id: str) -> bool:
    return to_id in bfs_reachable(graph, from_id)
