"""Intermediate result model from a tool execution.

ToolResult captures the raw output and structured evidence from any tool
(kubectl, Elasticsearch, Prometheus, etc.) before it is converted to an
EvidencePin by the EvidencePinFactory.
"""

from pydantic import BaseModel
from typing import Any, Optional


class ToolResult(BaseModel):
    """Intermediate result from a tool execution. Converted to EvidencePin by the factory."""

    success: bool
    intent: str
    raw_output: str
    summary: str
    evidence_snippets: list[str]
    evidence_type: str
    domain: str
    severity: Optional[str] = None
    error: Optional[str] = None
    metadata: dict[str, Any] = {}
