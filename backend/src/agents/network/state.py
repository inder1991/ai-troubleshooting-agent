"""LangGraph shared state for network diagnosis pipeline."""
from __future__ import annotations
import operator
from typing import Annotated, Optional, TypedDict


class NetworkPipelineState(TypedDict, total=False):
    """State dict flowing through the LangGraph network diagnosis pipeline."""
    # Input
    flow_id: str
    src_ip: str
    dst_ip: str
    port: int
    protocol: str
    session_id: str

    # Resolution
    src_device: Optional[dict]
    dst_device: Optional[dict]
    src_subnet: Optional[dict]
    dst_subnet: Optional[dict]
    resolution_status: str  # "resolved" | "ambiguous" | "failed"
    ambiguous_candidates: list[dict]

    # Path discovery
    candidate_paths: list[dict]
    traced_path: Optional[dict]
    trace_method: str
    final_path: Optional[dict]

    # Firewalls
    firewalls_in_path: list[dict]
    firewall_verdicts: Annotated[list[dict], operator.add]

    # Enterprise constructs in path
    nacls_in_path: list[dict]
    load_balancers_in_path: list[dict]
    vpn_segments: list[dict]
    nacl_verdicts: Annotated[list[dict], operator.add]
    vpc_boundary_crossings: list[dict]

    # NAT
    nat_translations: Annotated[list[dict], operator.add]
    identity_chain: list[dict]

    # Trace
    trace_id: Optional[str]
    trace_hops: list[dict]
    routing_loop_detected: bool

    # Diagnosis
    diagnosis_status: str  # "running" | "complete" | "no_path_known" | "ambiguous" | "error"
    confidence: float
    confidence_breakdown: Optional[dict]  # { path_confidence, path_source, firewall_confidence, contradiction_bonus, penalties, overall }
    evidence: Annotated[list[dict], operator.add]
    contradictions: list[dict]
    next_steps: list[str]
    executive_summary: str
    error: Optional[str]
