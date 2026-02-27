"""Abstract ClusterClient — platform adapter for K8s and OpenShift."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel, Field


# Object count caps from design doc
OBJECT_CAPS = {
    "events": 500,
    "pods": 1000,
    "log_lines": 2000,
    "metric_points": 500,
    "nodes": 500,
    "pvcs": 500,
}


class QueryResult(BaseModel):
    """Standard result wrapper with truncation tracking."""
    data: list[Any] = Field(default_factory=list)
    total_available: int = 0
    returned: int = 0
    truncated: bool = False
    sort_order: str = "severity_desc"


class ClusterClient(ABC):
    """Abstract base class for cluster interaction. Read-only contract."""

    @abstractmethod
    async def detect_platform(self) -> dict[str, str]:
        """Return {"platform": "kubernetes"|"openshift", "version": "1.28.3"}."""
        ...

    @abstractmethod
    async def list_namespaces(self) -> QueryResult:
        ...

    @abstractmethod
    async def list_nodes(self) -> QueryResult:
        ...

    @abstractmethod
    async def list_pods(self, namespace: str = "") -> QueryResult:
        ...

    @abstractmethod
    async def list_events(self, namespace: str = "", field_selector: str = "") -> QueryResult:
        ...

    @abstractmethod
    async def list_pvcs(self, namespace: str = "") -> QueryResult:
        ...

    @abstractmethod
    async def get_api_health(self) -> dict[str, Any]:
        ...

    @abstractmethod
    async def query_prometheus(self, query: str, time_range: str = "1h") -> QueryResult:
        ...

    @abstractmethod
    async def query_logs(self, index: str, query: dict, max_lines: int = 2000) -> QueryResult:
        ...

    # OpenShift-specific (return empty on vanilla K8s)
    async def get_cluster_operators(self) -> QueryResult:
        return QueryResult()

    async def get_machine_sets(self) -> QueryResult:
        return QueryResult()

    async def get_routes(self, namespace: str = "") -> QueryResult:
        return QueryResult()

    async def close(self) -> None:
        pass
