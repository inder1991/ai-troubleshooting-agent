# Cloud Integration Redesign -- Full Architecture Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement the corresponding implementation plan task-by-task.

**Goal:** Replace the broken cloud integration layer (no SDKs, manual CRUD, no auto-discovery, security policies mixed into adapter_registry) with a production-grade, provider-agnostic three-layer architecture that discovers ALL cloud resources (security, network, infrastructure) from AWS, Azure, Oracle, and future providers.

**Architecture:** Three-layer design -- CloudAccount (control plane) -> cloud_resources (raw canonical inventory) -> Internal Stores (topology_store, policy_store, tag_store). Provider-agnostic drivers, tiered sync (10min/30min/6hr), soft deletion, gzip compression, SQLite-safe DB worker thread, per-account concurrency guard, per-service adaptive rate limiting, sensitive data redaction, mapper versioning, and full observability.

**Tech Stack:** Python 3.11+, FastAPI, SQLite (WAL mode), boto3 (AWS), azure-mgmt-* (Azure), oci (Oracle), gzip, hashlib (sha256), asyncio + ThreadPoolExecutor

**Provider Priority:** AWS first (template for others), then Azure, Oracle, GCP

---

## Table of Contents

1. [Architecture Overview](#section-1-architecture-overview)
2. [Data Model](#section-2-data-model)
3. [Soft Deletion & Staleness Detection](#section-3-soft-deletion--staleness-detection)
4. [Tiered Sync Strategy](#section-4-tiered-sync-strategy)
5. [Production Schema (SQLite-Compatible)](#section-5-production-schema)
6. [Driver Contract & Envelope](#section-6-driver-contract--envelope)
7. [Sync Engine -- 4 Risks Addressed](#section-7-sync-engine--4-risks-addressed)
8. [CloudResourceMapper](#section-8-cloudresourcemapper)
9. [policy_store](#section-9-policy_store)
10. [Global Integrations Changes](#section-10-global-integrations-changes)
11. [Frontend Cloud Resources View](#section-11-frontend-cloud-resources-view)
12. [SQLite Performance & Concurrency](#section-12-sqlite-performance--concurrency)
13. [Raw JSON Growth Control](#section-13-raw-json-growth-control)
14. [Sync Job Locking & Stale Recovery](#section-14-sync-job-locking--stale-recovery)
15. [Driver Health Check with Permission Validation](#section-15-driver-health-check-with-permission-validation)
16. [Observability, Metrics & Sensitive Data](#section-16-observability-metrics--sensitive-data)
17. [Adaptive Per-Service Rate Limiting](#section-17-adaptive-per-service-rate-limiting)
18. [SQLite Safety & Operational Hardening](#section-18-sqlite-safety--operational-hardening)

---

## Section 1: Architecture Overview

**Approach A+** -- Three-layer cloud integration with provider-agnostic sync, canonical resource inventory, and policy/topology separation.

```
Global Integrations UI
        |
        v
Layer 1: CloudAccount  (control plane)
        |  provider, credentials (encrypted), regions, org_parent, sync_config
        |
        v
CloudSyncScheduler  (background job manager)
        |  per-account interval, manual trigger, health tracking
        |
        v
CloudProviderDriver  (provider-agnostic interface)
        |-- AWSDriver       (boto3)
        |-- AzureDriver     (azure-mgmt-*)
        |-- OracleDriver    (oci)
        +-- (future: GCPDriver)
        |
        v
Resource Discovery  (describe_* APIs per driver)
        |  VPCs, Subnets, SGs, NACLs, Route Tables,
        |  ENIs, ELBs, TGWs, VPNs, Direct Connects,
        |  Instances, IAM policies, tags
        |
        v
Layer 2: cloud_resources  (raw canonical inventory)
        |  resource_id, provider, account_id, region,
        |  resource_type, native_id, raw_json, tags, last_seen
        |  -> replay, diff detection, debugging, re-mapping
        |
        v
CloudResourceMapper  (raw -> canonical translation)
        |  AWS VPC -> NetworkSegment
        |  Azure VNet -> NetworkSegment
        |  AWS SG -> PolicyGroup
        |  AWS RouteTable -> RoutingTable
        |  AWS ENI -> Interface
        |  AWS TGW -> Router
        |
        v
Layer 3: Internal Stores
+--------------------------------------+
|  topology_store   (network graph)    |
|  policy_store     (security policies)|
|  tag_store        (resource tags)    |
+--------------------------------------+
        |
        v
EventBus  (resource_created, resource_updated, resource_deleted)
        |
        v
NetworkChat / Diagnostics / Alerts / Views
```

**Key principles:**
- Drivers are stateless -- they just call cloud APIs and return raw data
- `cloud_resources` is the single source of truth for what the cloud has
- Mapper is the only place that knows how to translate AWS/Azure/Oracle concepts to internal models
- `policy_store` is new -- separates security policies (SGs, NACLs, firewall rules) from network adapters (Palo Alto, Checkpoint)
- EventBus broadcasts changes so downstream consumers (chat, alerts, topology views) react in real-time

---

## Section 2: Data Model

### cloud_resources table

```sql
CREATE TABLE cloud_resources (
    resource_id       TEXT PRIMARY KEY,     -- internal UUID
    provider          TEXT NOT NULL,        -- aws | azure | oracle | gcp
    account_id        TEXT NOT NULL,        -- FK -> cloud_accounts
    region            TEXT NOT NULL,        -- us-east-1, westeurope, etc.
    resource_type     TEXT NOT NULL,        -- vpc | subnet | security_group | nacl | ...
    native_id         TEXT NOT NULL,        -- vpc-abc123, sg-def456
    name              TEXT,                 -- Name tag or display name
    raw_json          TEXT NOT NULL,        -- full describe_* API response
    tags              TEXT,                 -- JSON: {"env": "prod", "team": "backend"}
    sync_tier         INTEGER DEFAULT 1,   -- 1=fast, 2=slow, 3=very_slow
    last_seen         TEXT NOT NULL,        -- ISO timestamp from last sync
    is_deleted        INTEGER DEFAULT 0,   -- soft delete flag
    deleted_at        TEXT,                 -- when marked deleted
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,

    UNIQUE(provider, account_id, region, native_id)
);
```

### cloud_resource_relations table

```sql
CREATE TABLE cloud_resource_relations (
    relation_id          TEXT PRIMARY KEY,
    source_resource_id   TEXT NOT NULL REFERENCES cloud_resources(resource_id),
    target_resource_id   TEXT NOT NULL REFERENCES cloud_resources(resource_id),
    relation_type        TEXT NOT NULL,     -- attached_to | member_of | applied_to |
                                            -- routes_to | peered_with | target_of
    metadata             TEXT,              -- JSON: extra context per relation
    last_seen            TEXT NOT NULL,
    is_deleted           INTEGER DEFAULT 0,
    deleted_at           TEXT,

    UNIQUE(source_resource_id, target_resource_id, relation_type)
);
CREATE INDEX idx_crr_source ON cloud_resource_relations(source_resource_id);
CREATE INDEX idx_crr_target ON cloud_resource_relations(target_resource_id);
CREATE INDEX idx_crr_type   ON cloud_resource_relations(relation_type);
```

### Relation types for AWS networking

| Source | Target | relation_type | Example |
|---|---|---|---|
| Subnet | VPC | `member_of` | subnet-456 -> vpc-111 |
| ENI | Subnet | `attached_to` | eni-123 -> subnet-456 |
| Instance | ENI | `has_interface` | i-789 -> eni-123 |
| SecurityGroup | ENI | `applied_to` | sg-222 -> eni-123 |
| RouteTable | Subnet | `associated_with` | rtb-333 -> subnet-456 |
| RouteTable | VPC | `member_of` | rtb-333 -> vpc-111 |
| TGW | VPC | `attached_to` | tgw-444 -> vpc-111 |
| VPCPeering | VPC | `peered_with` | pcx-555 -> vpc-111 |
| ELB | Subnet | `deployed_in` | elb-666 -> subnet-456 |
| ELB | TargetGroup | `routes_to` | elb-666 -> tg-777 |
| NATGateway | Subnet | `deployed_in` | nat-888 -> subnet-456 |

This enables: graph traversal for topology building, reachability queries ("which SGs are applied to instances in this subnet?"), and impact analysis ("what breaks if this VPC goes down?").

---

## Section 3: Soft Deletion & Staleness Detection

### Flow

```
Sync cycle starts for account X, region Y
    |
    v
Driver calls describe_vpcs, describe_subnets, etc.
    |
    v
For each resource returned:
    UPSERT into cloud_resources
    SET last_seen = NOW()
    SET is_deleted = 0  (resurrect if previously marked)
    |
    v
After sync completes:
    SELECT * FROM cloud_resources
    WHERE account_id = X
      AND region = Y
      AND resource_type IN (types synced this cycle)
      AND is_deleted = 0
      AND last_seen < (NOW - 2 * sync_interval)
    |
    v
    Mark is_deleted = 1, deleted_at = NOW()
    |
    v
    Emit event: resource_deleted
    |
    v
    CloudResourceMapper removes from topology_store / policy_store
```

**Why 2 cycles, not 1:** Transient API failures or throttling shouldn't cause false deletions. If a resource is missing for 2 consecutive sync cycles, it's genuinely gone.

**Hard purge:** Resources with `is_deleted = 1` AND `deleted_at` older than 30 days get permanently deleted by a weekly cleanup job. This preserves audit trail.

Same logic applies to `cloud_resource_relations` -- relations not seen for 2 cycles get soft-deleted.

---

## Section 4: Tiered Sync Strategy

### Tier Definitions

| Tier | Resources | Default Interval | Rationale |
|---|---|---|---|
| **Tier 1 (fast)** | VPCs, Subnets, Security Groups, NACLs, Route Tables | 10 min | Core topology, changes are high-impact, APIs are lightweight |
| **Tier 2 (slow)** | ENIs, Instances, ELBs, TGW attachments, VPN tunnels, NAT Gateways, Peerings | 30 min | Larger result sets, change less frequently |
| **Tier 3 (very slow)** | IAM policies, resource tags (full refresh), flow log configs, Direct Connects | 6 hours | Heavy APIs, rarely change, tags bulk-synced |

### Sync Scheduler Logic

```python
class CloudSyncScheduler:
    """Manages per-account, per-tier sync jobs."""

    async def run_loop(self):
        while True:
            for account in self.list_enabled_accounts():
                for tier in [1, 2, 3]:
                    if self.is_due(account, tier):
                        asyncio.create_task(
                            self.sync_account_tier(account, tier)
                        )
            await asyncio.sleep(60)  # check every minute

    def is_due(self, account, tier) -> bool:
        last_sync = self.get_last_sync(account, tier)
        interval = account.sync_config.get(f"tier_{tier}_interval",
            {1: 600, 2: 1800, 3: 21600}[tier]  # defaults in seconds
        )
        return (now() - last_sync).total_seconds() >= interval
```

### Manual Sync

- "Sync Now" button triggers all tiers immediately for that account
- Rate-limited: max 1 manual sync per account per 2 minutes
- Shows progress indicator per tier in the UI

### Throttling & Error Handling

- Each driver implements `get_rate_limit()` -- respects AWS API rate limits
- Exponential backoff on throttle errors (429/503)
- Per-account sync health tracked: `last_sync_status`, `last_sync_error`, `consecutive_failures`
- After 5 consecutive failures, sync pauses and alerts the user

---

## Section 5: Production Schema

SQLite-compatible now, Postgres-migration-ready:

- `jsonb` -> `TEXT` with JSON functions (SQLite's `json()` / `json_extract()`)
- `timestamptz` -> `TEXT` (ISO 8601, same as all other tables)
- `uuid` -> `TEXT` (UUID strings, same pattern as existing stores)
- `GIN indexes` -> standard B-tree indexes on extracted JSON paths
- `boolean` -> `INTEGER` (0/1, SQLite convention)
- `gen_random_uuid()` -> Python-side `uuid.uuid4()`

### cloud_accounts

```sql
CREATE TABLE cloud_accounts (
    account_id          TEXT PRIMARY KEY,      -- internal UUID
    provider            TEXT NOT NULL,          -- aws | azure | oracle | gcp
    display_name        TEXT NOT NULL,
    native_account_id   TEXT,                   -- AWS account ID, Azure subscription, etc.
    credential_handle   TEXT NOT NULL,          -- encrypted ref via CredentialResolver
    auth_method         TEXT NOT NULL,          -- iam_role | access_key | azure_sp | oci_config
    regions             TEXT NOT NULL,          -- JSON array: ["us-east-1", "eu-west-1"]
    org_parent_id       TEXT,                   -- FK -> cloud_accounts (for Organizations)
    sync_enabled        INTEGER DEFAULT 1,
    sync_config         TEXT,                   -- JSON: tier intervals, overrides
    last_sync_status    TEXT DEFAULT 'never',   -- never | ok | error | paused
    last_sync_error     TEXT,
    consecutive_failures INTEGER DEFAULT 0,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);
```

### cloud_resources (SQLite-adapted)

```sql
CREATE TABLE cloud_resources (
    resource_id         TEXT PRIMARY KEY,       -- UUID
    provider            TEXT NOT NULL,
    account_id          TEXT NOT NULL REFERENCES cloud_accounts(account_id),
    region              TEXT NOT NULL,
    resource_type       TEXT NOT NULL,
    native_id           TEXT NOT NULL,
    name                TEXT,
    raw_json            TEXT NOT NULL,          -- full API response (jsonb -> TEXT)
    tags                TEXT,                   -- JSON object
    sync_tier           INTEGER DEFAULT 1,
    last_seen_ts        TEXT NOT NULL,          -- ISO 8601
    resource_hash       TEXT,                   -- sha256(raw_json) for change detection
    source              TEXT,                   -- e.g. 'aws-describe-vpcs'
    sync_job_id         TEXT,                   -- FK -> cloud_sync_jobs
    is_deleted          INTEGER DEFAULT 0,
    deleted_at          TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    UNIQUE(provider, account_id, region, native_id)
);
CREATE INDEX idx_cr_account_region_type ON cloud_resources(account_id, region, resource_type);
CREATE INDEX idx_cr_last_seen ON cloud_resources(account_id, region, last_seen_ts);
CREATE INDEX idx_cr_native ON cloud_resources(provider, native_id);
CREATE INDEX idx_cr_deleted ON cloud_resources(is_deleted) WHERE is_deleted = 0;
```

### cloud_resource_relations (SQLite-adapted)

```sql
CREATE TABLE cloud_resource_relations (
    relation_id         TEXT PRIMARY KEY,
    source_resource_id  TEXT NOT NULL REFERENCES cloud_resources(resource_id) ON DELETE CASCADE,
    target_resource_id  TEXT NOT NULL REFERENCES cloud_resources(resource_id) ON DELETE CASCADE,
    relation_type       TEXT NOT NULL,
    metadata            TEXT,                   -- JSON
    last_seen_ts        TEXT NOT NULL,
    relation_hash       TEXT,                   -- sha256(source+target+type+metadata)
    is_deleted          INTEGER DEFAULT 0,
    deleted_at          TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    UNIQUE(source_resource_id, target_resource_id, relation_type)
);
CREATE INDEX idx_crr_source ON cloud_resource_relations(source_resource_id);
CREATE INDEX idx_crr_target ON cloud_resource_relations(target_resource_id);
CREATE INDEX idx_crr_type   ON cloud_resource_relations(relation_type);
```

### cloud_sync_jobs (audit & tracing)

```sql
CREATE TABLE cloud_sync_jobs (
    sync_job_id     TEXT PRIMARY KEY,          -- UUID
    account_id      TEXT NOT NULL REFERENCES cloud_accounts(account_id),
    tier            INTEGER NOT NULL,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    status          TEXT DEFAULT 'queued',     -- queued | running | completed | failed | paused
    items_seen      INTEGER DEFAULT 0,
    items_created   INTEGER DEFAULT 0,
    items_updated   INTEGER DEFAULT 0,
    items_deleted   INTEGER DEFAULT 0,
    api_calls       INTEGER DEFAULT 0,
    errors          TEXT,                      -- JSON array of error objects
    created_at      TEXT NOT NULL
);
CREATE INDEX idx_sync_jobs_account ON cloud_sync_jobs(account_id, started_at);
```

**Change detection via `resource_hash`:** On each sync, driver returns raw JSON. We compute `sha256(raw_json)`. If hash matches stored `resource_hash` -> skip update (no write, no event). This dramatically reduces write I/O and false change events on large accounts.

---

## Section 6: Driver Contract & Envelope

### Abstract interface

```python
class CloudProviderDriver(ABC):
    """Provider-agnostic interface for cloud resource discovery."""

    @abstractmethod
    async def discover(
        self,
        account: CloudAccount,
        region: str,
        resource_types: list[str],
    ) -> AsyncIterator[DiscoveryBatch]:
        """Yield batches of discovered resources.

        Handles pagination and retries internally.
        Respects provider rate limits.
        """
        ...

    @abstractmethod
    async def health_check(self, account: CloudAccount) -> DriverHealth:
        """Validate credentials and connectivity."""
        ...

    @abstractmethod
    def supported_resource_types(self) -> dict[str, int]:
        """Return {resource_type: sync_tier} for this provider."""
        ...
```

### Standardized envelope

```python
@dataclass
class DiscoveryBatch:
    account_id: str
    region: str
    resource_type: str
    source: str                    # e.g. 'aws-describe-vpcs'
    items: list[DiscoveredItem]
    relations: list[DiscoveredRelation]   # relations found in this batch
    rate_limit_info: RateLimitInfo | None

@dataclass
class DiscoveredItem:
    native_id: str
    name: str | None
    raw: dict                      # original API JSON
    tags: dict[str, str]

@dataclass
class DiscoveredRelation:
    source_native_id: str
    target_native_id: str
    relation_type: str
    metadata: dict | None

@dataclass
class RateLimitInfo:
    calls_made: int
    remaining: int | None
    reset_at: float | None         # unix timestamp
```

**Key design decisions:**
- Relations are returned alongside items in the same batch -- this ensures **transactional consistency**. The sync engine upserts resources and relations in a single SQLite transaction per batch.
- Drivers handle pagination internally -- the sync engine never sees `next_token`.
- `source` field traces exactly which API call produced the data.

### AWS Driver resource types

```python
class AWSDriver(CloudProviderDriver):
    def supported_resource_types(self) -> dict[str, int]:
        return {
            # Tier 1 (10 min) -- core topology
            "vpc": 1,
            "subnet": 1,
            "security_group": 1,
            "nacl": 1,
            "route_table": 1,
            # Tier 2 (30 min) -- attached resources
            "eni": 2,
            "instance": 2,
            "elb": 2,
            "target_group": 2,
            "tgw": 2,
            "tgw_attachment": 2,
            "vpn_connection": 2,
            "nat_gateway": 2,
            "vpc_peering": 2,
            # Tier 3 (6 hr) -- slow-changing
            "iam_policy": 3,
            "direct_connect": 3,
            "flow_log_config": 3,
        }
```

---

## Section 7: Sync Engine -- 4 Risks Addressed

### Risk 1: Single-process scheduler / HA

```
CloudSyncScheduler
    |
    |-- sync_lock (per account+tier)
    |   SQLite: cloud_sync_jobs with status='running'
    |   Before starting: check no running job for this account+tier
    |   If found and started_at > 15 min ago -> mark as failed (stale lock)
    |
    |-- Leader election (future, multi-node)
    |   For now: single-process is fine (SQLite is single-writer anyway)
    |   Migration path: move sync_jobs to Postgres -> use pg_advisory_lock
    |   Or: Redis-based distributed lock (SETNX with TTL)
    |
    +-- Idempotent sync
        Same resource discovered twice -> UPSERT by (provider, account_id, region, native_id)
        Same relation discovered twice -> UPSERT by (source, target, type)
        Even if two syncs overlap, data converges correctly
```

**Practical approach for now:** SQLite is single-writer, so duplicate syncs aren't possible within one process. The `cloud_sync_jobs` table with `status='running'` acts as a logical lock. Stale lock recovery at 15 minutes handles crashes. When we move to Postgres, we add `pg_advisory_lock` or Redis `SETNX`.

### Risk 2: raw_json storage & query cost

Three mitigations:
1. **`resource_hash`** -- Only write `raw_json` when hash changes. Most syncs are no-ops.
2. **Query discipline** -- `raw_json` is never in SELECT for list queries. Only fetched for single-resource detail views. Index queries use `resource_type`, `native_id`, `tags` (extracted).
3. **Archival** -- Soft-deleted resources older than 30 days: move `raw_json` to `cloud_resource_archive` table (or drop it), keep the metadata row for audit.

### Risk 3: Adaptive rate limiting with jitter

```python
class AdaptiveRateLimiter:
    """Per-driver rate limiter with exponential backoff + jitter."""

    def __init__(self, base_delay: float = 0.1, max_delay: float = 30.0):
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._consecutive_throttles = 0

    async def on_success(self, rate_limit_info: RateLimitInfo | None):
        self._consecutive_throttles = 0
        if rate_limit_info and rate_limit_info.remaining is not None:
            # Proactive slow-down when approaching limit
            if rate_limit_info.remaining < 10:
                await asyncio.sleep(1.0)

    async def on_throttle(self):
        self._consecutive_throttles += 1
        delay = min(
            self._base_delay * (2 ** self._consecutive_throttles),
            self._max_delay,
        )
        # Add jitter: +/-25% randomization
        jitter = delay * 0.25 * (2 * random.random() - 1)
        await asyncio.sleep(delay + jitter)
```

Each driver wraps every API call through this limiter. AWS drivers additionally respect `Retry-After` headers and the per-service rate limits (e.g., EC2 `describe_*` has different limits than IAM).

### Risk 4: Transactional resource + relation upserts

```python
async def _process_batch(self, batch: DiscoveryBatch, sync_job_id: str):
    """Upsert resources and relations in a single transaction."""
    with self._store.transaction() as conn:
        for item in batch.items:
            resource_hash = sha256(json.dumps(item.raw, sort_keys=True))
            existing_hash = conn.execute(
                "SELECT resource_hash FROM cloud_resources WHERE provider=? AND account_id=? AND region=? AND native_id=?",
                (batch.provider, batch.account_id, batch.region, item.native_id)
            ).fetchone()

            if existing_hash and existing_hash[0] == resource_hash:
                # No change -- just touch last_seen_ts
                conn.execute("UPDATE cloud_resources SET last_seen_ts=?, sync_job_id=? WHERE ...", ...)
            else:
                # UPSERT resource
                conn.execute("INSERT OR REPLACE INTO cloud_resources ...", ...)

        # Relations in same transaction
        for rel in batch.relations:
            source_id = self._resolve_resource_id(conn, rel.source_native_id, ...)
            target_id = self._resolve_resource_id(conn, rel.target_native_id, ...)
            if source_id and target_id:
                conn.execute("INSERT OR REPLACE INTO cloud_resource_relations ...", ...)
```

Resources and their relations are always committed together. No broken graph edges. If the transaction fails, nothing is written -- the next sync cycle retries cleanly.

---

## Section 8: CloudResourceMapper

The mapper is the **only place** that knows how to translate cloud-native concepts to internal models. No other code should touch `raw_json` for mapping purposes.

### Canonical models (provider-agnostic)

```python
# These are what topology_store and policy_store deal with.
# Cloud-native terms (VPC, VNet, VCN) never leak past the mapper.

@dataclass
class NetworkSegment:       # AWS VPC, Azure VNet, Oracle VCN
    id: str
    name: str
    cidr_blocks: list[str]
    provider: str
    account_id: str
    region: str
    cloud_resource_id: str  # FK back to cloud_resources

@dataclass
class SubnetSegment:        # AWS Subnet, Azure Subnet, Oracle Subnet
    id: str
    name: str
    cidr: str
    network_segment_id: str
    availability_zone: str | None
    cloud_resource_id: str

@dataclass
class PolicyGroup:          # AWS SG, Azure NSG, Oracle NSG
    id: str
    name: str
    provider: str
    rules: list[PolicyRule]
    cloud_resource_id: str

@dataclass
class PolicyRule:           # Individual rule within a PolicyGroup
    rule_id: str
    direction: str          # inbound | outbound
    action: str             # allow | deny
    protocol: str           # tcp | udp | icmp | all
    port_range: tuple[int, int] | None
    source_cidr: str | None
    dest_cidr: str | None
    priority: int | None    # Azure/Oracle have priority, AWS does not

@dataclass
class RoutingTable:         # AWS RouteTable, Azure RouteTable
    id: str
    name: str
    network_segment_id: str
    routes: list[RouteEntry]
    cloud_resource_id: str

@dataclass
class RouteEntry:
    destination_cidr: str
    target_type: str        # gateway | instance | nat | peering | tgw | local
    target_id: str

# Similar for: Interface (ENI), Router (TGW), LoadBalancer, NATGateway, etc.
```

### Mapper interface

```python
class CloudResourceMapper:
    """Translates cloud_resources rows into canonical models
    and writes to topology_store / policy_store."""

    _MAPPERS: dict[str, Callable] = {
        "vpc":            "_map_network_segment",
        "subnet":         "_map_subnet",
        "security_group": "_map_policy_group",
        "nacl":           "_map_policy_group",
        "route_table":    "_map_routing_table",
        "eni":            "_map_interface",
        "instance":       "_map_compute_node",
        "elb":            "_map_load_balancer",
        "tgw":            "_map_router",
        "nat_gateway":    "_map_nat_gateway",
        "vpc_peering":    "_map_peering",
        "vpn_connection": "_map_vpn",
    }

    def map_resource(self, resource: CloudResource) -> None:
        handler = self._MAPPERS.get(resource.resource_type)
        if handler:
            getattr(self, handler)(resource)

    def _map_network_segment(self, resource: CloudResource):
        raw = json.loads(resource.raw_json)
        segment = NetworkSegment(
            id=resource.resource_id,
            name=resource.name or raw.get("VpcId"),
            cidr_blocks=_extract_cidrs(raw, resource.provider),
            provider=resource.provider,
            account_id=resource.account_id,
            region=resource.region,
            cloud_resource_id=resource.resource_id,
        )
        self._topology_store.upsert_network_segment(segment)
```

### Provider-specific extraction in small helper functions

```python
def _extract_cidrs(raw: dict, provider: str) -> list[str]:
    if provider == "aws":
        return [raw.get("CidrBlock", "")] + [
            a["CidrBlock"] for a in raw.get("CidrBlockAssociationSet", [])
        ]
    elif provider == "azure":
        return raw.get("address_space", {}).get("address_prefixes", [])
    elif provider == "oracle":
        return [raw.get("cidr_block", "")]
```

### Mapping runs after each sync batch

```
Sync batch committed to cloud_resources
        |
        v
For each new/updated resource in batch:
    CloudResourceMapper.map_resource(resource)
        |
        v
    Writes to topology_store OR policy_store
        |
        v
    EventBus.emit("resource_mapped", {resource_id, resource_type, action})
```

---

## Section 9: policy_store

New store. Security policies (SGs, NACLs, firewall rules) are **policy objects**, not adapters.

### Schema

```sql
CREATE TABLE policy_groups (
    policy_group_id     TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    provider            TEXT,                  -- aws | azure | oracle | null (on-prem)
    source_type         TEXT NOT NULL,         -- security_group | nacl | firewall_ruleset
    cloud_resource_id   TEXT,                  -- FK -> cloud_resources (null for on-prem)
    description         TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE TABLE policy_rules (
    rule_id             TEXT PRIMARY KEY,
    policy_group_id     TEXT NOT NULL REFERENCES policy_groups(policy_group_id) ON DELETE CASCADE,
    direction           TEXT NOT NULL,         -- inbound | outbound
    action              TEXT NOT NULL,         -- allow | deny
    protocol            TEXT NOT NULL,         -- tcp | udp | icmp | all
    port_range_start    INTEGER,
    port_range_end      INTEGER,
    source_cidr         TEXT,
    dest_cidr           TEXT,
    priority            INTEGER,              -- null for AWS (evaluate-all), set for Azure/Oracle
    description         TEXT,
    created_at          TEXT NOT NULL
);
CREATE INDEX idx_pr_group ON policy_rules(policy_group_id);

CREATE TABLE policy_attachments (
    attachment_id       TEXT PRIMARY KEY,
    policy_group_id     TEXT NOT NULL REFERENCES policy_groups(policy_group_id) ON DELETE CASCADE,
    target_resource_id  TEXT NOT NULL,         -- cloud_resource_id of ENI/Subnet/Instance
    target_type         TEXT NOT NULL,         -- eni | subnet | instance
    created_at          TEXT NOT NULL
);
CREATE INDEX idx_pa_group ON policy_attachments(policy_group_id);
CREATE INDEX idx_pa_target ON policy_attachments(target_resource_id);
```

### How tools query policy_store

The network chat `firewall_tools` now query `policy_store` instead of `adapter_registry`:

```python
# Before (broken model):
adapter = adapter_registry.get("sg-123")  # SG is NOT an adapter
rules = await adapter.get_rules()

# After (correct model):
group = policy_store.get_policy_group(cloud_resource_id="sg-123")
rules = policy_store.list_rules(group.policy_group_id)
attachments = policy_store.list_attachments(group.policy_group_id)
```

`adapter_registry` continues to hold actual vendor adapters (Palo Alto, Checkpoint, Cisco) for on-prem firewalls. Cloud security policies flow through `policy_store`.

---

## Section 10: Global Integrations Changes

### Backend changes

Add cloud provider service types:

```python
service_type: Literal[
    "elk", "jira", "confluence", "remedy", "github",
    "aws", "azure", "oracle", "gcp",  # NEW
]
```

Add cloud-specific defaults to `DEFAULT_GLOBAL_INTEGRATIONS`:

```python
{
    "id": "cloud-aws",
    "name": "Amazon Web Services",
    "service_type": "aws",
    "enabled": False,
    "base_url": "",
    "auth_method": "iam_role",           # or "access_key"
    "auth_credential_handle": None,
    "config": {
        "auth_method": "iam_role",
        "role_arn": "",
        "external_id": "",              # auto-generated UUID for security
        "regions": [],
        "org_management": False,        # discover member accounts?
        "sync_config": {
            "tier_1_interval": 600,
            "tier_2_interval": 1800,
            "tier_3_interval": 21600,
        },
    },
}
```

### Credential schemas per provider

| Provider | IAM Role method | Access Key method |
|---|---|---|
| AWS | `role_arn` + `external_id` (we generate) | `aws_access_key_id` + `aws_secret_access_key` |
| Azure | `tenant_id` + `client_id` + `client_secret` | Same (Azure SP is always key-based) |
| Oracle | `tenancy_ocid` + `user_ocid` + `fingerprint` + `private_key` | Same (OCI uses key pairs) |

All credentials encrypted via existing `CredentialResolver` -> stored as `auth_credential_handle`.

### Frontend: Settings -> Global Integrations

Add cloud provider cards to `GlobalIntegrationsSection.tsx`:

- **AWS** card: icon `cloud` (orange accent), fields for auth method toggle (IAM Role / Access Key), role ARN, external ID display, region multi-select, Organizations toggle
- **Azure** card: icon `cloud` (blue accent), tenant ID, client ID, client secret, subscription filter
- **Oracle** card: icon `cloud` (red accent), tenancy OCID, user OCID, key upload

Each card gets a "Test Connection" button that calls the driver's `health_check()` and shows latency + account identity.

---

## Section 11: Frontend Cloud Resources View

Current view is manual CRUD. Redesign to show **discovered resources** from `cloud_resources`:

### Layout

```
+-----------------------------------------------------+
|  Cloud Resources                                     |
|  [Account Selector v] [Region Filter v] [Sync Now]  |
+-----------------------------------------------------+
|  Tabs: VPCs | Subnets | Security Groups | NACLs |   |
|        Route Tables | ENIs | Load Balancers | TGWs   |
+-----------------------------------------------------+
|  +--------------+ +--------------+ +--------------+  |
|  | vpc-abc123   | | vpc-def456   | | vpc-ghi789   |  |
|  | 10.0.0.0/16  | | 172.16.0.0/  | | 192.168.0.0/ |  |
|  | us-east-1    | | eu-west-1    | | ap-south-1   |  |
|  | 4 subnets    | | 2 subnets    | | 6 subnets    |  |
|  | Last seen:   | | Last seen:   | | Last seen:   |  |
|  |  2m ago      | |  2m ago      | |  2m ago      |  |
|  +--------------+ +--------------+ +--------------+  |
+-----------------------------------------------------+
|  Sync Status: * Tier 1: 2m ago  * Tier 2: 15m ago   |
|               * Tier 3: 4h ago  | Next sync: 8m      |
+-----------------------------------------------------+
```

### Key UX changes

- Resources are **read-only** (discovered, not manually created). No more inline "Add" forms for cloud resources.
- Clicking a resource shows detail panel with raw JSON, relations graph, applied policies, and tags.
- "Sync Now" button triggers immediate all-tier sync for selected account.
- Sync status bar shows per-tier last sync time and health.
- Stale/deleted resources shown with dimmed opacity and "Not seen since..." badge.

---

## Section 12: SQLite Performance & Concurrency

### PRAGMAs on every connection

```python
def _conn(self) -> sqlite3.Connection:
    conn = sqlite3.connect(self._db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
```

`WAL` enables concurrent reads during writes. `busy_timeout=30000` prevents immediate `SQLITE_BUSY` failures -- retries for 30 seconds. `synchronous=NORMAL` gives a ~2x write speedup with minimal durability risk under WAL.

### Chunked batch upserts (500 items per transaction)

```python
BATCH_CHUNK_SIZE = 500

async def _process_batch(self, batch: DiscoveryBatch, sync_job_id: str):
    """Upsert resources and relations in chunked transactions."""
    # Phase 1: Build in-memory native_id -> resource_id cache for this batch
    native_id_cache: dict[str, str] = {}

    # Pre-load existing mappings for this account+region
    with self._store.conn() as conn:
        rows = conn.execute(
            "SELECT native_id, resource_id FROM cloud_resources "
            "WHERE account_id=? AND region=? AND is_deleted=0",
            (batch.account_id, batch.region),
        ).fetchall()
        native_id_cache = {r["native_id"]: r["resource_id"] for r in rows}

    # Phase 2: Chunk items into groups of BATCH_CHUNK_SIZE
    for chunk_start in range(0, len(batch.items), BATCH_CHUNK_SIZE):
        chunk = batch.items[chunk_start:chunk_start + BATCH_CHUNK_SIZE]

        with self._store.conn() as conn:
            for item in chunk:
                resource_hash = sha256(
                    json.dumps(item.raw, sort_keys=True).encode()
                ).hexdigest()

                existing = native_id_cache.get(item.native_id)
                if existing:
                    # Check hash -- skip write if unchanged
                    stored_hash = conn.execute(
                        "SELECT resource_hash FROM cloud_resources WHERE resource_id=?",
                        (existing,),
                    ).fetchone()
                    if stored_hash and stored_hash[0] == resource_hash:
                        conn.execute(
                            "UPDATE cloud_resources SET last_seen_ts=?, sync_job_id=? "
                            "WHERE resource_id=?",
                            (now_iso(), sync_job_id, existing),
                        )
                        continue

                resource_id = existing or str(uuid.uuid4())
                raw_blob = self._compress_raw(item.raw)
                conn.execute(
                    "INSERT OR REPLACE INTO cloud_resources (...) VALUES (...)",
                    (resource_id, ..., raw_blob, resource_hash, ...),
                )
                native_id_cache[item.native_id] = resource_id

    # Phase 3: Relations -- chunked, using in-memory cache (zero extra DB lookups)
    for chunk_start in range(0, len(batch.relations), BATCH_CHUNK_SIZE):
        rel_chunk = batch.relations[chunk_start:chunk_start + BATCH_CHUNK_SIZE]

        with self._store.conn() as conn:
            for rel in rel_chunk:
                source_id = native_id_cache.get(rel.source_native_id)
                target_id = native_id_cache.get(rel.target_native_id)
                if source_id and target_id:
                    conn.execute(
                        "INSERT OR REPLACE INTO cloud_resource_relations (...) VALUES (...)",
                        (...),
                    )
```

**Key points:**
- Native ID -> resource_id resolved from in-memory cache -- zero N x DB lookups per relation
- Each chunk is its own transaction (~500 rows) -- write lock held briefly, readers stay responsive
- `resource_hash` skips full write for unchanged resources (most syncs are 80%+ no-ops)

---

## Section 13: Raw JSON Growth Control

### Compression strategy

```python
import gzip
import json

MAX_INLINE_JSON_BYTES = 4096  # 4KB threshold

def _compress_raw(self, raw: dict) -> bytes:
    """Gzip-compress raw JSON. Stored as BLOB in SQLite."""
    return gzip.compress(json.dumps(raw, sort_keys=True).encode("utf-8"))

def _decompress_raw(self, blob: bytes) -> dict:
    """Decompress raw JSON BLOB back to dict."""
    return json.loads(gzip.decompress(blob).decode("utf-8"))
```

### Schema change: `raw_json` -> `raw_compressed` BLOB + `raw_preview` TEXT

```sql
CREATE TABLE cloud_resources (
    ...
    raw_compressed  BLOB NOT NULL,        -- gzip(raw_json), ~70-90% smaller
    raw_preview     TEXT,                  -- first 512 chars of JSON for quick display
    ...
);
```

- List queries never touch `raw_compressed` -- only `raw_preview` for hover/summary
- Detail view decompresses on demand
- Typical AWS `describe_vpcs` response: ~2KB raw -> ~400 bytes compressed
- ENI-heavy accounts: ~5KB per ENI -> ~800 bytes compressed

### Archival

Resources with `is_deleted=1` AND `deleted_at` older than retention period (default 30 days):
1. Move `raw_compressed` to `cloud_resource_archive` table (or drop it entirely)
2. Keep metadata row (resource_id, native_id, provider, timestamps) for audit
3. Run weekly via cleanup job

---

## Section 14: Sync Job Locking & Stale Recovery

### Lock acquisition with retry backoff

```python
async def _acquire_sync_lock(
    self, account_id: str, tier: int
) -> str | None:
    """Try to acquire sync lock. Returns sync_job_id or None."""
    STALE_THRESHOLD_SECONDS = 900  # 15 minutes
    MAX_LOCK_ATTEMPTS = 3
    RETRY_BACKOFF_SECONDS = [2, 5, 10]

    for attempt in range(MAX_LOCK_ATTEMPTS):
        with self._store.conn() as conn:
            # Check for existing running job
            running = conn.execute(
                "SELECT sync_job_id, started_at FROM cloud_sync_jobs "
                "WHERE account_id=? AND tier=? AND status='running' "
                "ORDER BY started_at DESC LIMIT 1",
                (account_id, tier),
            ).fetchone()

            if running:
                age = (now() - parse_iso(running["started_at"])).total_seconds()
                if age < STALE_THRESHOLD_SECONDS:
                    return None  # legitimate running job, skip

                # Stale lock -- reclaim
                conn.execute(
                    "UPDATE cloud_sync_jobs SET status='failed', "
                    "finished_at=?, errors=? WHERE sync_job_id=?",
                    (now_iso(), json.dumps([{"error": "stale_lock_reclaimed"}]),
                     running["sync_job_id"]),
                )
                # Backoff before reclaim to avoid thundering herd
                await asyncio.sleep(RETRY_BACKOFF_SECONDS[attempt])
                continue

            # No running job -- create one
            job_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO cloud_sync_jobs (sync_job_id, account_id, tier, "
                "started_at, status, created_at) VALUES (?, ?, ?, ?, 'running', ?)",
                (job_id, account_id, tier, now_iso(), now_iso()),
            )
            return job_id

    return None  # failed after retries
```

### Job lifecycle

```
acquire_lock -> status='running'
    |
    |-- success -> status='completed', finished_at, items_seen/created/updated/deleted, api_calls
    |
    |-- error -> status='failed', finished_at, errors=[{type, message, traceback}]
    |           increment account.consecutive_failures
    |           if consecutive_failures >= 5 -> status='paused', alert user
    |
    +-- stale (15 min) -> reclaimed by next scheduler check with backoff
```

---

## Section 15: Driver Health Check with Permission Validation

### Contract

```python
@dataclass
class DriverHealth:
    connected: bool
    latency_ms: float
    identity: str              # e.g. "arn:aws:iam::123456:role/DebugDuckRole"
    permissions_ok: bool
    missing_permissions: list[str]   # e.g. ["ec2:DescribeNetworkInterfaces"]
    message: str

class AWSDriver(CloudProviderDriver):

    # Minimal permissions required per tier
    _REQUIRED_PERMISSIONS = {
        1: [
            "ec2:DescribeVpcs",
            "ec2:DescribeSubnets",
            "ec2:DescribeSecurityGroups",
            "ec2:DescribeNetworkAcls",
            "ec2:DescribeRouteTables",
        ],
        2: [
            "ec2:DescribeNetworkInterfaces",
            "ec2:DescribeInstances",
            "elasticloadbalancing:DescribeLoadBalancers",
            "elasticloadbalancing:DescribeTargetGroups",
            "ec2:DescribeTransitGateways",
            "ec2:DescribeVpnConnections",
            "ec2:DescribeNatGateways",
            "ec2:DescribeVpcPeeringConnections",
        ],
        3: [
            "iam:ListPolicies",
            "ec2:DescribeFlowLogs",
            "directconnect:DescribeConnections",
        ],
    }

    async def health_check(self, account: CloudAccount) -> DriverHealth:
        start = time.monotonic()
        try:
            sts = boto3.client("sts", **self._get_credentials(account))
            identity = sts.get_caller_identity()
            latency = (time.monotonic() - start) * 1000

            # Test actual permissions via dry-run
            missing = []
            ec2 = boto3.client("ec2", **self._get_credentials(account))
            for tier, perms in self._REQUIRED_PERMISSIONS.items():
                for perm in perms:
                    if not await self._test_permission(ec2, perm):
                        missing.append(perm)

            return DriverHealth(
                connected=True,
                latency_ms=latency,
                identity=identity["Arn"],
                permissions_ok=len(missing) == 0,
                missing_permissions=missing,
                message="All permissions verified" if not missing
                    else f"Missing {len(missing)} permissions",
            )
        except Exception as e:
            return DriverHealth(
                connected=False,
                latency_ms=(time.monotonic() - start) * 1000,
                identity="",
                permissions_ok=False,
                missing_permissions=[],
                message=str(e),
            )

    async def _test_permission(self, ec2, permission: str) -> bool:
        """Test a single permission via dry-run or minimal API call."""
        action = permission.split(":")[1]
        try:
            # EC2 dry-run pattern
            method = getattr(ec2, self._action_to_method(action), None)
            if method:
                method(DryRun=True, MaxResults=5)
        except ec2.exceptions.ClientError as e:
            if "DryRunOperation" in str(e):
                return True   # permission exists
            if "UnauthorizedOperation" in str(e):
                return False  # permission denied
        return True  # assume ok if no dry-run support
```

Frontend shows this as:

```
AWS Integration: * Connected (45ms)
Identity: arn:aws:iam::123456:role/DebugDuckRole
Permissions: Warning Missing 2 -- ec2:DescribeNetworkInterfaces, iam:ListPolicies
             [Tier 1: OK] [Tier 2: FAIL] [Tier 3: FAIL]
```

---

## Section 16: Observability, Metrics & Sensitive Data

### Metrics emitted per sync job

```python
# Emitted via MetricsCollector (existing Prometheus exporter)
cloud_sync_duration_seconds{account, tier, status}
cloud_sync_api_calls_total{account, tier, service}
cloud_sync_items_processed{account, tier, action}  # action=created|updated|deleted|unchanged
cloud_sync_errors_total{account, tier, error_type}
cloud_resource_events_emitted{event_type}           # resource_created|updated|deleted
cloud_resource_count{account, region, resource_type, is_deleted}
```

All metrics tagged with `sync_job_id` for trace correlation.

### Sensitive data redaction

```python
_REDACT_KEYS = frozenset({
    "Password", "Secret", "PrivateKey", "AccessKey", "SecretKey",
    "Token", "Credential", "AuthToken", "ConnectionString",
})

def _redact_raw(self, raw: dict) -> dict:
    """Deep-redact sensitive fields before storing raw_json."""
    def _walk(obj):
        if isinstance(obj, dict):
            return {
                k: "***REDACTED***" if any(s in k for s in _REDACT_KEYS) else _walk(v)
                for k, v in obj.items()
            }
        if isinstance(obj, list):
            return [_walk(item) for item in obj]
        return obj
    return _walk(raw)
```

Redaction runs **before** compression and storage. Original secrets never hit disk. Logged: `"Redacted N fields from {resource_type} {native_id}"`.

### Mapper versioning

```sql
ALTER TABLE cloud_resources ADD COLUMN mapper_version INTEGER DEFAULT 1;
```

When mapper logic changes (e.g., v1 -> v2 of how SGs map to PolicyGroups), bump version. Re-map query:

```sql
SELECT * FROM cloud_resources WHERE mapper_version < 2 AND is_deleted = 0;
```

This enables re-running the mapper on historical data for ML/AI debugging without re-syncing from cloud APIs.

---

## Section 17: Adaptive Per-Service Rate Limiting

### Service-specific base rates

```python
# AWS API rate limits differ significantly per service
_AWS_SERVICE_LIMITS: dict[str, dict] = {
    "ec2": {
        "base_rate": 20,        # requests/second
        "burst": 100,
        "throttle_backoff": 1.0,
    },
    "elasticloadbalancing": {
        "base_rate": 10,
        "burst": 40,
        "throttle_backoff": 2.0,
    },
    "iam": {
        "base_rate": 5,         # IAM is heavily throttled
        "burst": 15,
        "throttle_backoff": 3.0,
    },
    "directconnect": {
        "base_rate": 5,
        "burst": 10,
        "throttle_backoff": 2.0,
    },
    "sts": {
        "base_rate": 10,
        "burst": 50,
        "throttle_backoff": 1.0,
    },
}

class AdaptiveRateLimiter:
    def __init__(self, service_limits: dict = _AWS_SERVICE_LIMITS):
        self._limits = service_limits
        self._throttle_counts: dict[str, int] = defaultdict(int)
        self._last_call: dict[str, float] = {}

    async def acquire(self, service: str):
        """Wait if needed to respect per-service rate limit."""
        limit = self._limits.get(service, {"base_rate": 10, "burst": 50})
        min_interval = 1.0 / limit["base_rate"]

        last = self._last_call.get(service, 0)
        elapsed = time.monotonic() - last
        if elapsed < min_interval:
            await asyncio.sleep(min_interval - elapsed)

        self._last_call[service] = time.monotonic()

    async def on_throttle(self, service: str):
        """Exponential backoff with jitter on throttle."""
        self._throttle_counts[service] += 1
        limit = self._limits.get(service, {"throttle_backoff": 1.0})
        base = limit["throttle_backoff"]
        delay = min(base * (2 ** self._throttle_counts[service]), 60.0)
        jitter = delay * 0.25 * (2 * random.random() - 1)
        await asyncio.sleep(delay + jitter)

    def on_success(self, service: str):
        self._throttle_counts[service] = 0
```

Each driver call goes through `await rate_limiter.acquire("ec2")` before making the API call.

---

## Section 18: SQLite Safety & Operational Hardening

### 1. Async-safe DB access via worker thread

All cloud_store DB operations funnel through a dedicated DB worker thread. No direct `sqlite3` calls from async tasks.

```python
import asyncio
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from functools import partial

class CloudStore:
    """Thread-safe SQLite store for cloud resources.

    All DB operations run on a single dedicated thread via executor.
    This avoids sqlite3 thread-safety issues and 'database is locked' errors.
    """

    def __init__(self, db_path: str = "data/debugduck.db"):
        self._db_path = db_path
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cloud-db")
        # Connection lives on the worker thread only
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        """Called only from worker thread."""
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA busy_timeout=30000")
            self._conn.execute("PRAGMA temp_store=MEMORY")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    async def execute(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        """Run SQL on the DB worker thread."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor,
            partial(self._sync_execute, sql, params),
        )

    def _sync_execute(self, sql: str, params: tuple) -> list[sqlite3.Row]:
        conn = self._get_conn()
        cursor = conn.execute(sql, params)
        conn.commit()
        return cursor.fetchall()

    async def execute_batch(self, operations: list[tuple[str, tuple]]) -> None:
        """Run multiple SQL statements in a single transaction on worker thread."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            self._executor,
            partial(self._sync_batch, operations),
        )

    def _sync_batch(self, operations: list[tuple[str, tuple]]) -> None:
        conn = self._get_conn()
        try:
            for sql, params in operations:
                conn.execute(sql, params)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
```

**Why single-thread executor, not `aiosqlite`:** `aiosqlite` is a thin wrapper that still has edge cases with WAL + concurrent access. A dedicated worker thread with a single connection is the safest model for SQLite. All reads and writes serialize through it -- no locking surprises.

### 2. Dynamic batch size with backoff

```python
class BatchSizeController:
    """Dynamically adjusts batch size based on DB write performance."""

    def __init__(self, default_size: int = 500, min_size: int = 50, max_size: int = 2000):
        self._current = default_size
        self._min = min_size
        self._max = max_size
        self._consecutive_errors = 0

    @property
    def size(self) -> int:
        return self._current

    def on_success(self, duration_ms: float):
        self._consecutive_errors = 0
        # If batch committed fast (<200ms), try larger batches
        if duration_ms < 200 and self._current < self._max:
            self._current = min(self._current + 100, self._max)
        # If batch was slow (>2s), shrink
        elif duration_ms > 2000:
            self._current = max(self._current // 2, self._min)

    def on_error(self):
        """Shrink on OperationalError (locked, busy)."""
        self._consecutive_errors += 1
        self._current = max(self._current // 2, self._min)
```

Sync engine uses `batch_controller.size` instead of hardcoded 500. Adapts to actual DB performance on the machine.

### 3. WAL housekeeping

```python
class WALMonitor:
    """Periodic WAL checkpoint and size monitoring."""

    WAL_SIZE_ALERT_MB = 100
    CHECKPOINT_INTERVAL_SECONDS = 300  # 5 minutes

    async def run_loop(self, store: CloudStore):
        while True:
            await asyncio.sleep(self.CHECKPOINT_INTERVAL_SECONDS)
            try:
                # Incremental checkpoint -- non-blocking
                result = await store.execute("PRAGMA wal_checkpoint(PASSIVE)")
                # result: (busy, log_pages, checkpointed_pages)

                # Check WAL file size
                wal_path = store._db_path + "-wal"
                if os.path.exists(wal_path):
                    wal_size_mb = os.path.getsize(wal_path) / (1024 * 1024)
                    if wal_size_mb > self.WAL_SIZE_ALERT_MB:
                        logger.warning(
                            "WAL file large: %.1f MB (threshold: %d MB). "
                            "Attempting TRUNCATE checkpoint.",
                            wal_size_mb, self.WAL_SIZE_ALERT_MB,
                        )
                        # TRUNCATE -- blocks briefly but reclaims space
                        await store.execute("PRAGMA wal_checkpoint(TRUNCATE)")

                    # Emit metric
                    metrics.gauge("cloud_store.wal_size_mb", wal_size_mb)

            except Exception as e:
                logger.warning("WAL checkpoint failed: %s", e)
```

Runs as a background task alongside the sync scheduler. PASSIVE checkpoints every 5 minutes (non-blocking). Escalates to TRUNCATE only when WAL exceeds threshold.

### 4. BLOB handling -- consistent bytes, no base64

```python
# Writing compressed BLOB
raw_bytes = gzip.compress(json.dumps(item.raw, sort_keys=True).encode("utf-8"))
conn.execute(
    "INSERT INTO cloud_resources (..., raw_compressed, ...) VALUES (..., ?, ...)",
    (..., raw_bytes, ...),  # sqlite3 handles bytes as BLOB natively
)

# Reading compressed BLOB
row = conn.execute(
    "SELECT raw_compressed FROM cloud_resources WHERE resource_id=?"
).fetchone()
raw_dict = json.loads(gzip.decompress(row["raw_compressed"]).decode("utf-8"))
```

SQLite's Python driver stores `bytes` as BLOB natively -- no base64 encoding needed. Schema declares `raw_compressed BLOB NOT NULL`. Confirmed: both `sqlite3` and `aiosqlite` handle this correctly without wrapper overhead.

### 5. Per-account concurrency guard

```python
class SyncConcurrencyGuard:
    """Ensures max 1 concurrent sync per account across all tiers."""

    def __init__(self):
        self._active: dict[str, asyncio.Lock] = {}

    def get_lock(self, account_id: str) -> asyncio.Lock:
        if account_id not in self._active:
            self._active[account_id] = asyncio.Lock()
        return self._active[account_id]

# In CloudSyncScheduler:
async def sync_account_tier(self, account: CloudAccount, tier: int):
    lock = self._concurrency_guard.get_lock(account.account_id)

    if lock.locked():
        logger.debug(
            "Skipping sync for account %s tier %d -- another tier is running",
            account.account_id, tier,
        )
        return

    async with lock:
        job_id = await self._acquire_sync_lock(account.account_id, tier)
        if not job_id:
            return
        await self._run_sync(account, tier, job_id)
```

**Effect:** If Tier 1 sync is running for account X, Tier 2 won't start until Tier 1 finishes. Prevents stacking expensive parallel syncs against the same cloud account (which would also hit API rate limits harder).

The `cloud_sync_jobs` table lock (Section 14) prevents duplicate same-tier runs. This asyncio Lock prevents cross-tier overlap per account.
