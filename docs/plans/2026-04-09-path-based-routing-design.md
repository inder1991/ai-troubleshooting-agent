# Path-Based Routing — Design

**Goal:** Replace the frontend's `viewState` string-based navigation with React Router v6 path-based routing, enabling deep linking, bookmarking, browser history, and self-sufficient view components that load their own data from URL params.

**Context:** The frontend currently uses a `ViewState` type with 35+ string values and a `handleNavigate` callback to switch between views. There are no URL paths — navigating away or refreshing loses all state. This is not production-ready.

---

## 1. Decisions Made

| Decision | Choice | Reasoning |
|----------|--------|-----------|
| Routing library | React Router v6 | Battle-tested, clean nested layouts via `<Outlet>`, widely known |
| Route scope | All 35+ views get URL paths | Every view should be bookmarkable/shareable in production |
| Route structure | Nested hierarchy by domain | `/network/topology`, `/database/monitoring` — not 35 flat routes |
| Layout approach | Root layout + section layouts with `<Outlet>` | Sidebar always visible, section sub-nav for grouped routes |
| Sidebar | Restructure to match URL hierarchy | Groups align with route structure for consistency |
| Error handling | 404 page + contextual errors | `/bad-path` → 404; `/investigations/bad-id` → "Investigation not found" |
| Data loading | Route components fetch own data from URL params | No more prop drilling from App.tsx |
| Investigation routes | Fetch state from API + reconnect WebSocket | Sessions restored from `/api/v4/session/{id}/status` + `/findings` |
| Migration strategy | Incremental with compatibility adapter | Add router first, migrate sections one at a time |

---

## 2. Route Map

```
/                                    → Home/Dashboard
/how-it-works                        → How It Works

/investigations                      → Sessions list
/investigations/:sessionId           → Active investigation (War Room)
/investigations/:sessionId/dossier   → Post-mortem dossier

/network                             → Network overview
/network/topology                    → Live topology
/network/adapters                    → Adapter management
/network/monitoring                  → Observatory
/network/ipam                        → IPAM
/network/flows                       → Flow analysis
/network/security                    → Security resources
/network/mib-browser                 → MIB browser
/network/cloud                       → Cloud resources

/database                            → DB overview
/database/connections                → Connections
/database/diagnostics                → Diagnostics
/database/monitoring                 → Monitoring
/database/schema                     → Schema
/database/operations                 → Operations

/clusters                            → K8s cluster registry
/clusters/recommendations            → Recommendations
/clusters/diagnostics                → Cluster diagnostics

/agents                              → Agent catalog
/agents/matrix                       → Agent matrix

/workflows                           → Workflow builder
/workflows/runs                      → Workflow runs

/settings                            → Settings
/settings/integrations               → Integrations
/audit                               → Audit log

*                                    → 404 Not Found
```

---

## 3. Router Architecture

```
<BrowserRouter>
  <Routes>
    <Route element={<AppLayout />}>              // Sidebar + TopBar + <Outlet>
      <Route index element={<HomePage />} />
      <Route path="how-it-works" element={<HowItWorks />} />

      <Route path="investigations" element={<SessionsList />} />
      <Route path="investigations/:sessionId" element={<InvestigationView />} />
      <Route path="investigations/:sessionId/dossier" element={<DossierView />} />

      <Route path="network" element={<NetworkLayout />}>
        <Route index element={<NetworkOverview />} />
        <Route path="topology" element={<LiveTopology />} />
        <Route path="adapters" element={<NetworkAdapters />} />
        <Route path="monitoring" element={<Observatory />} />
        <Route path="ipam" element={<IPAM />} />
        <Route path="flows" element={<FlowAnalysis />} />
        <Route path="security" element={<SecurityResources />} />
        <Route path="mib-browser" element={<MIBBrowser />} />
        <Route path="cloud" element={<CloudResources />} />
      </Route>

      <Route path="database" element={<DatabaseLayout />}>
        <Route index element={<DBOverview />} />
        <Route path="connections" element={<DBConnections />} />
        <Route path="diagnostics" element={<DBDiagnostics />} />
        <Route path="monitoring" element={<DBMonitoring />} />
        <Route path="schema" element={<DBSchema />} />
        <Route path="operations" element={<DBOperations />} />
      </Route>

      <Route path="clusters" element={<ClustersLayout />}>
        <Route index element={<ClusterRegistry />} />
        <Route path="recommendations" element={<Recommendations />} />
        <Route path="diagnostics" element={<ClusterDiagnostics />} />
      </Route>

      <Route path="agents" element={<AgentsLayout />}>
        <Route index element={<AgentCatalog />} />
        <Route path="matrix" element={<AgentMatrix />} />
      </Route>

      <Route path="workflows" element={<WorkflowsLayout />}>
        <Route index element={<WorkflowBuilder />} />
        <Route path="runs" element={<WorkflowRuns />} />
      </Route>

      <Route path="settings" element={<SettingsLayout />}>
        <Route index element={<Settings />} />
        <Route path="integrations" element={<Integrations />} />
      </Route>

      <Route path="audit" element={<AuditLog />} />
      <Route path="*" element={<NotFound />} />
    </Route>
  </Routes>
</BrowserRouter>
```

### Layout Components

- **`AppLayout`** — Always renders: restructured sidebar (with `<NavLink>`) + top bar + `<Outlet>`. Some routes (investigation, dossier) hide the sidebar.
- **`NetworkLayout`**, **`DatabaseLayout`**, etc. — Render section-specific sub-navigation tabs + `<Outlet>` for child routes.

### Investigation Route Data Loading

When navigating to `/investigations/:sessionId`:
1. `useParams()` extracts `sessionId`
2. Fetch `/api/v4/session/{id}/status` + `/api/v4/session/{id}/findings` on mount
3. If session is active → reconnect WebSocket at `/ws/troubleshoot/{sessionId}`
4. If session not found → show "Investigation not found" with link to `/investigations`

---

## 4. Sidebar Restructuring

Current sidebar uses `NavView` type with `onNavigate` callback. New sidebar uses `<NavLink>` from React Router with `to` props.

**New sidebar groups (matching URL hierarchy):**

| Group | Items |
|-------|-------|
| Entry | Dashboard (`/`), Sessions (`/investigations`) |
| Diagnostics | App (`/investigations` with capability), Database (`/database/diagnostics`), Network (form), Cluster (form) |
| Code | PR Review (form), Issue Fixer (form) |
| Network | Topology, Adapters, Devices, IPAM, Flows, Security, Cloud |
| Database | Overview, Connections, Monitoring, Schema, Operations |
| Monitoring | Observatory, MIB Browser |
| Clusters | Registry, Recommendations |
| Agents | Catalog, Matrix |
| Workflows | Builder, Runs |
| System | Settings, Integrations, Audit Log |

**Form-triggering items** (app-diagnostics, network-troubleshooting, etc.) navigate to a route like `/investigations/new?capability=troubleshoot_app` or render the form inline. This replaces the `selectedCapability` state in `handleNavigate`.

---

## 5. Migration Strategy (Incremental)

### Phase 1: Foundation
- Install `react-router-dom` v6
- Create `router.tsx` with route config
- Create `AppLayout` with restructured sidebar using `<NavLink>`
- Add compatibility adapter: route changes update context so existing components work
- Add `NotFound` page
- Update `main.tsx` to wrap with `<BrowserRouter>`

### Phase 2: Migrate Investigations (highest value)
- `SessionsList` → self-sufficient, fetches sessions on mount
- `InvestigationView` → loads from `useParams().sessionId`, fetches state, reconnects WebSocket
- `DossierView` → loads from `useParams().sessionId`
- Remove investigation prop drilling

### Phase 3: Migrate Network section
- Create `NetworkLayout` with sub-nav + `<Outlet>`
- Each network view fetches own data on mount
- Remove network prop drilling

### Phase 4: Migrate Database section
- Create `DatabaseLayout` with sub-nav + `<Outlet>`
- Each DB view becomes self-sufficient

### Phase 5: Migrate remaining sections
- Clusters, Agents, Workflows, Settings, Audit
- Simpler views — mostly standalone without complex state

### Phase 6: Cleanup
- Remove compatibility adapter
- Remove `ViewState` type, `handleNavigate`, all prop drilling
- Remove old view switching logic from `App.tsx`
- Update `api.ts` — replace hardcoded `API_BASE_URL` with relative paths

---

## 6. Files Changed

| File | Action | Description |
|------|--------|-------------|
| `frontend/package.json` | **MODIFY** | Add `react-router-dom` v6 |
| `frontend/src/router.tsx` | **CREATE** | Route config with all routes |
| `frontend/src/main.tsx` | **MODIFY** | Wrap with `<BrowserRouter>` |
| `frontend/src/App.tsx` | **MODIFY** | Replace view switching with `<Outlet>`, remove old logic |
| `frontend/src/layouts/AppLayout.tsx` | **CREATE** | Root layout: sidebar + topbar + `<Outlet>` |
| `frontend/src/layouts/NetworkLayout.tsx` | **CREATE** | Network sub-nav + `<Outlet>` |
| `frontend/src/layouts/DatabaseLayout.tsx` | **CREATE** | Database sub-nav + `<Outlet>` |
| `frontend/src/layouts/ClustersLayout.tsx` | **CREATE** | Clusters sub-nav + `<Outlet>` |
| `frontend/src/layouts/AgentsLayout.tsx` | **CREATE** | Agents sub-nav + `<Outlet>` |
| `frontend/src/layouts/WorkflowsLayout.tsx` | **CREATE** | Workflows sub-nav + `<Outlet>` |
| `frontend/src/layouts/SettingsLayout.tsx` | **CREATE** | Settings sub-nav + `<Outlet>` |
| `frontend/src/pages/NotFound.tsx` | **CREATE** | 404 page |
| `frontend/src/components/Layout/SidebarNav.tsx` | **MODIFY** | Replace `onNavigate` with `<NavLink>`, restructure groups |
| `frontend/src/components/Investigation/*` | **MODIFY** | Fetch data from route params instead of props |
| `frontend/src/services/api.ts` | **MODIFY** | Replace hardcoded `API_BASE_URL` with relative paths |
| All view components | **MODIFY** | Each becomes self-sufficient |

## What Does NOT Change
- Backend API — no changes
- WebSocket protocol — same endpoint, reconnect logic moves into component
- Vite proxy config — already routes `/api` and `/ws` correctly
- Component internal logic — only data sourcing changes
