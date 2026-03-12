"""Pydantic models for cloud integration entities."""
from __future__ import annotations

from enum import IntEnum
from typing import Any

from pydantic import BaseModel, Field


class SyncTier(IntEnum):
    FAST = 1       # 10 min — core topology
    SLOW = 2       # 30 min — attached resources
    VERY_SLOW = 3  # 6 hr  — IAM, tags, flow logs


# ── Layer 1: Cloud Account ──


class CloudAccount(BaseModel):
    account_id: str
    provider: str  # aws | azure | oracle | gcp
    display_name: str
    native_account_id: str | None = None
    credential_handle: str
    auth_method: str  # iam_role | access_key | azure_sp | oci_config
    regions: list[str]
    org_parent_id: str | None = None
    sync_enabled: bool = True
    sync_config: dict[str, Any] | None = None
    last_sync_status: str = "never"  # never | ok | error | paused
    last_sync_error: str | None = None
    consecutive_failures: int = 0
    created_at: str | None = None
    updated_at: str | None = None


# ── Layer 2: Cloud Resources ──


class CloudResource(BaseModel):
    resource_id: str
    provider: str
    account_id: str
    region: str
    resource_type: str
    native_id: str
    name: str | None = None
    raw_compressed: bytes = b""
    raw_preview: str | None = None
    tags: dict[str, str] | None = None
    sync_tier: int = SyncTier.FAST
    last_seen_ts: str | None = None
    resource_hash: str | None = None
    source: str | None = None
    sync_job_id: str | None = None
    mapper_version: int = 1
    is_deleted: bool = False
    deleted_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class CloudResourceRelation(BaseModel):
    relation_id: str
    source_resource_id: str
    target_resource_id: str
    relation_type: str  # attached_to | member_of | applied_to | etc.
    metadata: dict[str, Any] | None = None
    last_seen_ts: str | None = None
    relation_hash: str | None = None
    is_deleted: bool = False
    deleted_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


# ── Sync Jobs ──


class CloudSyncJob(BaseModel):
    sync_job_id: str
    account_id: str
    tier: int
    started_at: str
    finished_at: str | None = None
    status: str = "queued"  # queued | running | completed | failed | paused
    items_seen: int = 0
    items_created: int = 0
    items_updated: int = 0
    items_deleted: int = 0
    api_calls: int = 0
    errors: list[dict[str, Any]] | None = None
    created_at: str | None = None


# ── Driver Envelope ──


class DiscoveredItem(BaseModel):
    native_id: str
    name: str | None = None
    raw: dict[str, Any]
    tags: dict[str, str] = Field(default_factory=dict)


class DiscoveredRelation(BaseModel):
    source_native_id: str
    target_native_id: str
    relation_type: str
    metadata: dict[str, Any] | None = None


class RateLimitInfo(BaseModel):
    calls_made: int
    remaining: int | None = None
    reset_at: float | None = None


class DiscoveryBatch(BaseModel):
    account_id: str
    region: str
    resource_type: str
    source: str
    items: list[DiscoveredItem]
    relations: list[DiscoveredRelation] = Field(default_factory=list)
    rate_limit_info: RateLimitInfo | None = None


class DriverHealth(BaseModel):
    connected: bool
    latency_ms: float
    identity: str = ""
    permissions_ok: bool = False
    missing_permissions: list[str] = Field(default_factory=list)
    message: str = ""


# ── Policy Store Models ──


class PolicyGroup(BaseModel):
    policy_group_id: str
    name: str
    provider: str | None = None
    source_type: str  # security_group | nacl | firewall_ruleset
    cloud_resource_id: str | None = None
    description: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class PolicyRule(BaseModel):
    rule_id: str
    policy_group_id: str
    direction: str  # inbound | outbound
    action: str     # allow | deny
    protocol: str   # tcp | udp | icmp | all
    port_range_start: int | None = None
    port_range_end: int | None = None
    source_cidr: str | None = None
    dest_cidr: str | None = None
    priority: int | None = None
    description: str | None = None
    created_at: str | None = None


class PolicyAttachment(BaseModel):
    attachment_id: str
    policy_group_id: str
    target_resource_id: str
    target_type: str  # eni | subnet | instance
    created_at: str | None = None


# ── Canonical Mapper Models ──


class RouteEntry(BaseModel):
    destination_cidr: str
    target_type: str  # gateway | instance | nat | peering | tgw | local
    target_id: str


class NetworkSegment(BaseModel):
    """AWS VPC / Azure VNet / Oracle VCN."""
    id: str
    name: str
    cidr_blocks: list[str]
    provider: str
    account_id: str
    region: str
    cloud_resource_id: str


class SubnetSegment(BaseModel):
    id: str
    name: str
    cidr: str
    network_segment_id: str
    availability_zone: str | None = None
    cloud_resource_id: str


class RoutingTable(BaseModel):
    id: str
    name: str
    network_segment_id: str
    routes: list[RouteEntry] = Field(default_factory=list)
    cloud_resource_id: str
