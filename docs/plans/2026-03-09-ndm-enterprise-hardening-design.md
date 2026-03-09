# NDM Enterprise Hardening — Design Document

**Date:** 2026-03-09
**Scope:** Fix 57 identified gaps (items 1-50 + 57, 58, 59, 61, 62, 64, 65)
**Excluded:** Multi-tenancy (#51), RBAC (#52), Audit trail (#53), Custom dashboards (#54), Forecasting (#55), CMDB integration (#56)

---

## Phase 1: Critical Fixes (Items 1-7)

### 1.1 Replace Fake Golden Signals with Real SNMP Data (#1)

**File:** `frontend/src/components/Network/NDMOverviewTab.tsx`
**Problem:** `Math.random()` generates CPU/Memory values.
**Fix:**
- Add backend endpoint `GET /api/collector/devices/aggregate-metrics` that queries latest SNMP-collected CPU/Mem/Temp from `metric_history` table, averaged across all devices (or tag-filtered devices).
- Frontend calls this endpoint; falls back to "No data" if no metrics collected yet.
- Add "Last updated: X ago" timestamp indicator.

**Backend changes:**
- `topology_store.py` — Add `aggregate_device_metrics(device_ids: list[str]) -> dict` method that queries `metric_history` for latest cpu_pct, mem_pct, temperature across given devices.
- `collector_endpoints.py` — Add `GET /api/collector/devices/aggregate-metrics?tag=env:prod` endpoint.

**Frontend changes:**
- `NDMOverviewTab.tsx` — Replace `Math.random()` with API call. Show "Collecting..." state if no data.

### 1.2 Fix Command Injection (#2)

**File:** `backend/src/tools/codebase_tools.py:52-57`
**Fix:** Replace `subprocess.run(cmd, shell=True)` with `subprocess.run(["grep", "-rn", pattern, ...], shell=False)`. Use list-form args to prevent injection.

### 1.3 Bounded Conversation/Application/ASN Dicts (#3)

**File:** `backend/src/network/flow_receiver.py`
**Problem:** `_conversations`, `_applications`, `_asn_stats` dicts grow unbounded.
**Fix:**
- Use `collections.OrderedDict` with max size (10,000 entries).
- On overflow, evict lowest-byte-count entry (LFU eviction).
- Add `_MAX_CONVERSATIONS = 10_000` constant.
- Reset all dicts on `flush()` (already done) — confirm.

### 1.4 InfluxDB Query Timeout (#4)

**File:** `backend/src/network/metrics_store.py`
**Fix:**
- Wrap all `query_api.query()` calls with `asyncio.wait_for(query, timeout=30.0)`.
- On timeout, raise `MetricsQueryTimeout` exception with context.
- Make timeout configurable via `INFLUXDB_QUERY_TIMEOUT` env var (default 30s).

### 1.5 InfluxDB Cardinality Control (#5)

**File:** `backend/src/network/metrics_store.py:93-96`
**Fix:**
- Replace raw IP tags with /24 CIDR aggregation: `tag("src_subnet", ip_to_/24(flow.src_ip))`.
- Keep raw IPs as fields (not tags) for drill-down queries.
- Add `FLOW_TAG_AGGREGATION_PREFIX` env var (default 24).

### 1.6 SNMP Engine Resource Leak (#6)

**File:** `backend/src/network/snmp_collector.py`
**Fix:**
- Add `engine.close_dispatcher()` in `finally` block of `_walk_interfaces()` and `walk_arp_table()`.
- Use context manager pattern: `with self._engine_context(device) as engine:` that auto-closes.

### 1.7 SNMP Walk Timeout (#7)

**File:** `backend/src/network/snmp_collector.py:143-169`
**Fix:**
- Wrap `_walk_interfaces()` with `asyncio.wait_for(self._walk_interfaces(device), timeout=60.0)`.
- On timeout, log warning and return partial results collected so far.
- Add `SNMP_WALK_TIMEOUT` env var (default 60s).

---

## Phase 2: Event Bus & Pipeline Hardening (Items 8-16)

### 2.1 Dead Letter Queue (#8)

**File:** `backend/src/network/event_bus/redis_bus.py`, `event_processor.py`
**Fix:**
- On handler exception, XADD failed event to `{channel}:dlq` stream.
- Add `GET /api/system/dlq` endpoint to view/replay failed events.
- DLQ stream trimmed at 10,000 entries.
- `MemoryEventBus` stores DLQ in separate deque per channel.

### 2.2 Backpressure Mechanism (#9)

**File:** `backend/src/network/event_bus/redis_bus.py`, `memory_bus.py`
**Fix:**
- RedisEventBus: Check stream length before XADD. If > 80% of MAXLEN, reject with `BackpressureError`.
- MemoryEventBus: When queue > 80% capacity, `publish()` raises `BackpressureError`.
- Callers (trap/syslog listeners) catch `BackpressureError`, increment `events_dropped` counter, log warning.
- Expose `event_bus_pressure_ratio` Prometheus gauge.

### 2.3 NetFlow Template Cache TTL (#10)

**File:** `backend/src/network/flow_receiver.py:73,150-165`
**Fix:**
- Add `_template_timestamps` dict tracking last-seen time per template.
- On template lookup, if age > 3600s (1 hour), evict and request re-template.
- Add `_MAX_TEMPLATES = 500` cap.

### 2.4 Alert Deduplication Across Rules (#11)

**File:** `backend/src/network/alert_engine.py:331-336`
**Fix:**
- Add `_active_fingerprints: dict[str, float]` keyed by `(entity_id, metric_name, severity)`.
- Before firing, check if fingerprint exists within dedup window (5 min).
- If exists, skip fire but update timestamp.
- Different from cooldown (which is per-rule); this is cross-rule.

### 2.5 Escalation Respects Acknowledgment (#12)

**File:** `backend/src/network/alert_engine.py:427-431`
**Fix:**
- In `check_escalations()`, skip alerts where `acknowledged == True`.
- Add `unacknowledge()` method for re-opening alerts.

### 2.6 Knowledge Graph Path Finding Bounds (#13)

**File:** `backend/src/network/knowledge_graph.py:305-306`
**Fix:**
- Add `max_iterations=1000` parameter to `find_k_shortest_paths()`.
- Use `itertools.islice(nx.shortest_simple_paths(...), max_iterations)` instead of `list()`.
- Add `max_depth=15` parameter to limit path length.

### 2.7 SQLite Connection Pooling (#14)

**File:** `backend/src/network/topology_store.py:43-49`
**Fix:**
- Replace per-call `_conn()` with connection pool using `queue.Queue(maxsize=5)`.
- Add `_get_conn()` / `_return_conn()` methods.
- Set `PRAGMA busy_timeout=10000` (10s).
- Use `threading.Lock` for cache access.

### 2.8 SNMP Credential Security (#15)

**File:** `backend/src/api/collector_endpoints.py:124-132`
**Fix:**
- Never log community strings or auth keys (redact in debug output).
- Store credentials encrypted at rest (use existing Fernet key from `.fernet_dev_key`).
- Add `X-Sensitive` header warning on credential endpoints.
- Validate TLS when `REQUIRE_TLS=true` env var is set.

### 2.9 Discovery Concurrency Limit (#16)

**File:** `backend/src/network/discovery_engine.py:69-70`
**Fix:**
- Add `asyncio.Semaphore(50)` for concurrent ping probes.
- Add `DISCOVERY_MAX_CONCURRENT_PROBES` env var (default 50).
- Log skipped probes count when semaphore throttles.

---

## Phase 3: Backend Reliability (Items 17-36)

### 3.1 API Pagination (#17, #22)

**Files:** `collector_endpoints.py`, `flow_endpoints.py`
**Fix:**
- Add `PaginatedResponse` model: `{ items: list, total: int, page: int, limit: int, has_more: bool }`.
- All list endpoints accept `?page=1&limit=25` (default limit=25, max limit=100).
- `topology_store.py` list methods accept `offset` and `limit` params with SQL `LIMIT ? OFFSET ?`.
- Flow endpoints: limit query results (default 50).

### 3.2 Error Boundary Info (#18 — frontend, covered in Phase 5)

### 3.3 Real-time Syslog Streaming (#19 — frontend, covered in Phase 5)

### 3.4 Topology Zoom/Pan (#20 — frontend, covered in Phase 5)

### 3.5 OID MIB Lookup (#21 — frontend+backend, covered in Phase 5)

### 3.6 API Authentication (#23)

**File:** `backend/src/api/main.py`
**Fix:**
- Add API key authentication middleware.
- `X-API-Key` header validated against `API_KEYS` env var (comma-separated).
- Exclude `/health`, `/metrics` from auth.
- Return 401 with `{"error": "unauthorized"}` on missing/invalid key.

### 3.7 Health Check Endpoints (#24)

**File:** `backend/src/api/main.py`
**Fix:**
- `GET /health` — returns `{"status": "healthy/degraded/unhealthy", "components": {...}}`.
- `GET /health/ready` — checks SQLite writable, InfluxDB reachable, event bus connected.
- `GET /health/live` — returns 200 if event loop responsive (runs microtask within 1s).

### 3.8 Flow Sampling Compensation (#25)

**File:** `backend/src/network/flow_receiver.py`
**Fix:**
- Parse `sampling_interval` from NetFlow v9 template (field type 34).
- Multiply `bytes` and `packets` by `sampling_rate` before aggregation.
- Add `sampling_rate` field to `FlowRecord`.
- Default sampling_rate = 1 (no sampling).

### 3.9 Alert Flapping Detection (#26)

**File:** `backend/src/network/alert_engine.py`
**Fix:**
- Track state transitions per (rule_id, entity_id) in `_state_transitions: dict[str, list[float]]`.
- If > 5 transitions in 5 minutes, suppress and mark as "flapping".
- Add `flapping` state to alert lifecycle.
- Auto-resolve flapping after 15 min of stable state.

### 3.10 Syslog Timestamp Parsing (#27)

**File:** `backend/src/network/collectors/syslog_listener.py`
**Fix:**
- Parse RFC 3164 timestamps: `MMM DD HH:MM:SS` → datetime.
- Parse RFC 5424 timestamps: ISO 8601 → datetime.
- Use parsed timestamp as event timestamp (fallback to receive time if unparseable).
- Store as `event_timestamp` (device clock) and `received_timestamp` (server clock).

### 3.11 IPv6 Syslog Support (#28)

**File:** `backend/src/network/collectors/syslog_listener.py:258`
**Fix:**
- Listen on both `0.0.0.0` and `::` (dual-stack).
- Create two DatagramProtocol endpoints if IPv6 available.
- Parse IPv6 source addresses in device correlation.

### 3.12 Message Size Validation (#29)

**Files:** `syslog_listener.py`, `trap_listener.py`
**Fix:**
- Add `MAX_MESSAGE_SIZE = 8192` constant.
- Truncate datagrams exceeding max before parsing.
- Increment `oversized_messages` counter.

### 3.13 UDP Buffer Tuning (#30)

**File:** `backend/src/network/collectors/trap_listener.py:333-336`
**Fix:**
- Set `SO_RCVBUF = 4 * 1024 * 1024` (4MB) on UDP socket after creation.
- Add `UDP_RECV_BUFFER_SIZE` env var.
- Log actual buffer size after setting (OS may cap it).

### 3.14 SNMP Counter Wraparound (#31)

**File:** `backend/src/network/snmp_collector.py:75-82`
**Fix:**
- Detect counter width: if value > 2^32, use 64-bit wraparound.
- Store `_counter_width` per (device_id, oid) after first collection.
- Add `HC` (High Capacity) OID variants for ifHCInOctets/ifHCOutOctets.

### 3.15 Batch Write Error Recovery (#32)

**File:** `backend/src/network/metrics_store.py:186-189`
**Fix:**
- On batch write failure, store failed batch in local retry queue.
- Retry on next flush cycle (max 3 retries).
- After 3 failures, write to DLQ file and alert.
- Add `metrics_write_failures_total` Prometheus counter.

### 3.16 TTLCache Thread Safety (#33)

**File:** `backend/src/network/topology_store.py:34`
**Fix:**
- Add `threading.Lock` protecting `_cache` access.
- Use lock in `_invalidate_cache()`, cache reads, and cache writes.

### 3.17 Monitor Per-Pass Timing (#34)

**File:** `backend/src/network/monitor.py:176-196`
**Fix:**
- Wrap each pass in timing context: `start = time.time(); await pass(); duration = time.time() - start`.
- Store `_pass_durations: dict[str, float]` with keys like `probe`, `adapter`, `snmp`, etc.
- Expose in `/api/monitor/status` response and Prometheus histograms.

### 3.18 Graceful Shutdown Timeout (#35)

**File:** `backend/src/network/monitor.py:148-163`
**Fix:**
- In `stop()`, use `asyncio.wait_for(task, timeout=10.0)` per task.
- On timeout, force cancel and log warning.
- Add `SHUTDOWN_TIMEOUT` env var (default 10s).

### 3.19 Streaming IPAM Import (#36)

**File:** `backend/src/network/ipam_ingestion.py:40-50`
**Fix:**
- Add `MAX_IMPORT_SIZE = 50 * 1024 * 1024` (50MB) check before parsing.
- Process CSV in chunks of 1000 rows using generator.
- Return progress stats after each chunk: `{"processed": 1000, "total_estimate": 5000, "errors": [...]}`.

---

## Phase 4: Input Validation & API Quality (Items 37-50)

### 4.1 Search Debouncing (#37 — frontend, Phase 5)

### 4.2 Column Sorting (#38 — frontend, Phase 5)

### 4.3 Chart Drill-Through (#39 — frontend, Phase 5)

### 4.4 Virtual Scrolling (#40 — frontend, Phase 5)

### 4.5 Saved Filters (#41 — frontend, Phase 5)

### 4.6 URL Tab Routing (#42 — frontend, Phase 5)

### 4.7 Toast Notifications Instead of alert() (#43 — frontend, Phase 5)

### 4.8 Responsive Detail Panel (#44 — frontend, Phase 5)

### 4.9 Accessibility — ARIA Labels (#45 — frontend, Phase 5)

### 4.10 Color-Blind Safe Status (#46 — frontend, Phase 5)

### 4.11 Design Token Consistency (#47 — frontend, Phase 5)

### 4.12 Input Validation (#48)

**Files:** `collector_endpoints.py`, `flow_endpoints.py`
**Fix:**
- Add Pydantic validators:
  - IP address: `ipaddress.ip_address(v)` validation.
  - CIDR: `ipaddress.ip_network(v, strict=False)` + prefix length 8-32.
  - Port: `1 <= port <= 65535`.
  - SNMP version: `Literal["1", "2c", "3"]`.
  - Flow window: regex `^\d+[smhd]$` (e.g., "1h", "30m").
  - MAC address: regex `^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$` (optional field).
- Return 422 with field-level error messages.

### 4.13 Mock Quality in Tests (#49)

**Files:** All test files in `backend/tests/`
**Fix:**
- Replace permissive `AsyncMock()` with `spec=RealClass` mocks.
- Add `assert_called_with()` for critical method calls.
- Add negative tests: empty inputs, None values, boundary values.
- Add concurrent access tests using `asyncio.gather()`.

### 4.14 Integration Tests (#50)

**File:** New `backend/tests/test_integration_pipeline.py`
**Fix:**
- Test: IPAM import -> KG load -> discovery candidates -> alert evaluation.
- Test: SNMP collection -> metric write -> alert fire -> notification dispatch.
- Test: Flow ingest -> aggregation -> flush -> InfluxDB write (mocked).
- Test: Concurrent topology store writes (5 writers, verify consistency).
- Test: Event bus publish -> processor -> store write cycle.

---

## Phase 5: Frontend UX Hardening (Items 18-21, 37-47)

### 5.1 Error Boundary (#18)

**File:** `frontend/src/components/Network/DeviceMonitoring.tsx`
**Fix:**
- Create `NDMErrorBoundary` component wrapping each tab's content.
- On error, show "This tab encountered an error. Click to retry." with stack trace in dev mode.
- Log errors to console with component name context.

### 5.2 Real-Time Syslog Streaming (#19)

**File:** `frontend/src/components/Network/NDMSyslogTab.tsx`
**Fix:**
- Connect to existing WebSocket (`/ws`) for syslog channel.
- New syslog events prepended to top of list with fade-in animation.
- "Pause stream" toggle to freeze auto-scroll.
- Keep polling as fallback when WebSocket disconnects.

**Backend:**
- `event_processor.py` — On syslog event, also broadcast via WebSocket: `ws_manager.broadcast({"type": "syslog", "data": event})`.

### 5.3 Topology Zoom/Pan (#20)

**File:** `frontend/src/components/Network/NDMTopologyTab.tsx`
**Fix:**
- Add SVG transform state: `{ scale, translateX, translateY }`.
- Mouse wheel → zoom (scale 0.25x to 4x).
- Mouse drag on background → pan.
- Zoom controls: +/- buttons and "Fit to screen" reset button.
- Pinch-to-zoom on touch devices.

### 5.4 OID MIB Registry (#21)

**Backend:** `backend/src/network/collectors/mib_registry.py` (new)
- Hardcoded dict of ~200 common OIDs → human names (IF-MIB, SNMPv2-MIB, HOST-RESOURCES-MIB, CISCO-*, JUNIPER-*).
- `GET /api/collector/mib/lookup?oid=1.3.6.1.6.3.1.1.5.3` → `{"name": "linkDown", "description": "..."}`.

**Frontend:** `NDMTrapsTab.tsx`
- On load, batch-lookup unique OIDs from displayed traps.
- Show human-readable name with raw OID in tooltip.

### 5.5 Pagination on Tables (#17)

**Files:** `NDMDevicesTab.tsx`, `NDMInterfacesTab.tsx`, `NDMSyslogTab.tsx`, `NDMTrapsTab.tsx`
**Fix:**
- Add `PaginationBar` component: `< 1 2 3 ... 10 >` with rows-per-page selector (25/50/100).
- Server-side pagination using `?page=N&limit=M` params.
- Show "Showing 1-25 of 1,234 devices".

### 5.6 Search Debouncing (#37)

**Files:** `NDMDevicesTab.tsx`, `NDMInterfacesTab.tsx`, `NDMSyslogTab.tsx`
**Fix:**
- Debounce search input with 300ms delay.
- Show "Searching..." indicator during debounce.

### 5.7 Column Sorting (#38)

**Files:** `NDMDevicesTab.tsx`, `NDMInterfacesTab.tsx`
**Fix:**
- Clickable column headers with sort indicator (arrow up/down).
- Support multi-column sort: shift+click adds secondary sort.
- Sort state: `{ field: string, direction: 'asc' | 'desc' }[]`.

### 5.8 Chart Drill-Through (#39)

**File:** `NDMNetFlowTab.tsx`
**Fix:**
- Top Talkers bar: click IP → filter conversations table to that IP.
- Application donut: click slice → filter conversations to that app/port.
- Protocol bar: click → filter by protocol.
- "Clear filter" button to reset.

### 5.9 Virtual Scrolling (#40)

**Files:** `NDMSyslogTab.tsx`, `NDMInterfacesTab.tsx`
**Fix:**
- Use `react-window` (`FixedSizeList`) for tables with > 100 rows.
- Row height: 40px fixed.
- Overscan: 10 rows.
- Keep header sticky outside virtual list.

### 5.10 Saved Filters (#41)

**Fix:**
- Store filter presets in `localStorage` keyed by `ndm-filters`.
- "Save current filter" button → name + criteria saved.
- Filter dropdown shows saved presets.
- Max 20 saved filters.

### 5.11 URL Tab Routing (#42)

**File:** `DeviceMonitoring.tsx`
**Fix:**
- Use `useSearchParams()` for tab state: `?tab=netflow&timeRange=1h`.
- Browser back/forward navigates between tabs.
- Shareable URLs: `/network/monitoring?tab=syslog&severity=critical`.

### 5.12 Toast Notifications (#43)

**File:** `NDMDevicesTab.tsx`
**Fix:**
- Replace `alert()` calls with toast component.
- Toast types: success (green), error (red), info (cyan), warning (amber).
- Auto-dismiss after 5s. Stack up to 3 toasts.
- Position: bottom-right.

### 5.13 Responsive Detail Panel (#44)

**File:** `DeviceDetailPanel.tsx`
**Fix:**
- Width: `min(520px, 90vw)` for mobile support.
- On mobile (<768px): full-screen overlay instead of side panel.
- Horizontal scroll on interface table within panel.

### 5.14 Accessibility (#45, #46)

**All NDM components:**
- Add `aria-label` to all interactive elements (buttons, status indicators, chart regions).
- Add `role="status"` to loading spinners.
- Add `aria-live="polite"` to auto-refreshing data regions.
- Connect `<label htmlFor>` to `<input id>` in all forms.
- Add text labels alongside color indicators: `"UP"` / `"DOWN"` text badges.
- Add `<title>` elements to SVG topology chart.
- Keyboard navigation: Tab through table rows, Enter to select, Escape to close panels.

### 5.15 Design Tokens (#47)

**File:** New `frontend/src/styles/tokens.ts`
**Fix:**
- Define color tokens: `bg.primary`, `bg.surface`, `bg.elevated`, `border.subtle`, `border.accent`, `text.primary`, `text.secondary`, `status.up`, `status.down`, `status.warning`.
- Replace all hardcoded `#0a1a1f`, `rgba(7,182,213,...)` etc. with token references.
- Single source of truth for dark theme.

---

## Phase 6: Enterprise Features (Items 57-65, selected)

### 6.1 Bulk Actions (#57)

**Frontend:** All tab components with tables.
**Fix:**
- Add checkbox column to device/interface tables.
- "Select all" checkbox in header.
- Bulk action toolbar appears on selection: "Tag selected", "Test selected", "Delete selected".
- Confirmation modal for destructive actions.

**Backend:**
- `POST /api/collector/devices/bulk-action` with body: `{ device_ids: [...], action: "tag|test|delete", params: {...} }`.

### 6.2 Log Aggregation (#58)

**File:** `NDMSyslogTab.tsx`, `event_store.py`
**Fix:**
- Backend: Add `query_syslog_aggregated(window, group_by=["message_template"])` method.
- Group similar messages by template (strip numbers/IPs from message, hash remainder).
- Show: "Interface eth0 down" (47 occurrences in last 1h) with expand to see individual entries.
- Frontend: Toggle between "Raw" and "Aggregated" view.

### 6.3 Flow Stitching (#59)

**File:** `backend/src/network/flow_receiver.py`
**Fix:**
- Track active flows by `(src_ip, dst_ip, src_port, dst_port, protocol)` 5-tuple.
- Merge forward/reverse flows into biflow record.
- Calculate round-trip time from SYN-ACK timing if available.
- Add `biflow_bytes`, `biflow_packets` to conversation output.
- Evict unmatched flows after 120s timeout.

### 6.4 Circuit Breaker for Adapters (#61)

**File:** `backend/src/network/monitor.py`, new `backend/src/network/circuit_breaker.py`
**Fix:**
- Implement circuit breaker with 3 states: CLOSED (normal), OPEN (failing), HALF_OPEN (testing).
- Thresholds: 5 consecutive failures → OPEN. After 60s → HALF_OPEN. 1 success → CLOSED.
- Per adapter instance circuit breaker.
- When OPEN, skip adapter and log warning.
- Expose circuit breaker state in `/api/monitor/status`.

### 6.5 Structured Logging (#62)

**All backend files.**
**Fix:**
- Add `structlog` to `requirements.txt`.
- Configure JSON output with: timestamp, level, logger, message, and context fields.
- Add `correlation_id` to all event processing paths.
- Add `device_id`, `event_type` context to collector logs.
- Keep human-readable format for development (`STRUCTURED_LOGS=false`).

### 6.6 Device Relationship Tracking (#64)

**File:** `backend/src/network/models.py`, `topology_store.py`
**Fix:**
- Add `DeviceRelationship` model: `{ id, source_device_id, target_device_id, relationship_type, metadata }`.
- Relationship types: `"backup_for"`, `"member_of_cluster"`, `"stacked_with"`, `"virtual_chassis"`.
- New table `device_relationships` in topology_store.
- API: `POST/GET/DELETE /api/collector/device-relationships`.
- Frontend: Show relationships in DeviceDetailPanel overview tab.

### 6.7 ASN-to-Name and Geo Mapping (#65)

**File:** `backend/src/network/flow_receiver.py`, new `backend/src/network/asn_registry.py`
**Fix:**
- Bundle static ASN→name mapping (top 5000 ASNs from public data).
- `asn_registry.py`: `lookup_asn(asn: int) -> { name: str, country: str }`.
- Enrich `get_asn_breakdown()` output with `asn_name` and `country` fields.
- Frontend: Show "AS64512 (Example Corp, US)" instead of "AS64512".

---

## Architecture Principles

1. **All env vars have sensible defaults** — system works out-of-box without configuration.
2. **All new features degrade gracefully** — missing Redis falls back to MemoryEventBus, missing InfluxDB returns empty metrics, etc.
3. **No breaking API changes** — new fields are additive; existing endpoints keep working.
4. **Tests for every fix** — each item includes test cases covering the specific bug/gap.

## Testing Strategy

- Each phase includes its own test files.
- Integration tests in Phase 4 cover cross-component scenarios.
- All existing 2228 tests must continue passing.
- Target: 0 failures after each phase.

## Implementation Order

```
Phase 1 (Critical) ──→ Phase 2 (Event Bus) ──→ Phase 3 (Backend) ──→ Phase 4 (Validation) ──→ Phase 5 (Frontend) ──→ Phase 6 (Enterprise)
     7 items              9 items                 12 items              6 items                15 items               7 items
```

Total: 56 items across 6 phases.
