# KG Architecture Overhaul — Phase 5: Visualization (Frontend Layout Engine + Real-Time)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move layout computation from backend to frontend. Backend exports semantic data (type, group, rank, relationships) — frontend decides positions. Add pluggable layout algorithms (force-directed, hierarchical, geographic). Add WebSocket-driven real-time topology updates. Add interface-level detail views.

**Architecture:** New `topology/layout/` package in frontend with pluggable algorithms. Backend `/api/v5/topology` exports layout hints instead of pixel coordinates. WebSocket at `/api/v5/topology/stream` pushes delta events. ReactFlow renders using new layout engine.

**Tech Stack:** React, TypeScript, ReactFlow, D3-force (force-directed), dagre (hierarchical), WebSocket, existing LiveTopologyView.

**Design Doc:** `docs/plans/2026-03-16-kg-architecture-overhaul-design.md`

**Depends on:** Phases 1-4 complete (repository, Neo4j, events, discovery).

---

## Task 1: Backend — Semantic Topology Export (v5 API)

**Files:**
- Create: `backend/src/api/topology_v5.py`
- Test: `backend/tests/test_topology_v5_api.py`

Export topology with layout hints (algorithm recommendation, grouping strategy) instead of pixel coordinates. Uses Neo4jRepository.get_topology_export() or SQLiteRepository as fallback.

**Endpoint:** `GET /api/v5/topology`

**Response format:**
```json
{
  "nodes": [
    {"id": "rtr-01", "type": "device", "hostname": "rtr-01", "vendor": "cisco",
     "device_type": "ROUTER", "site_id": "dc-east", "group": "onprem",
     "rank": 2, "status": "healthy", "confidence": 0.9,
     "metrics": {"cpu_pct": 45.2, "memory_pct": 62.1}}
  ],
  "edges": [
    {"id": "e-rtr-01-sw-01", "source": "rtr-01", "target": "sw-01",
     "source_interface": "rtr-01:Gi0/0", "target_interface": "sw-01:Gi0/48",
     "edge_type": "physical", "protocol": "lldp", "confidence": 0.95,
     "metrics": {"utilization": 32, "speed": "1G"}}
  ],
  "groups": [
    {"id": "onprem", "label": "On-Premises DC", "accent": "#e09f3e", "device_count": 15}
  ],
  "layout_hints": {"algorithm": "force_directed", "grouping": "site"},
  "topology_version": "abc123",
  "device_count": 35,
  "edge_count": 42
}
```

**No pixel positions.** Frontend computes layout.

**Tests:** endpoint returns correct structure, nodes have required fields, edges have required fields, layout_hints present.

**Commit:** `feat(api): v5 topology export with layout hints, no pixel coordinates`

---

## Task 2: Frontend — Layout Engine Interface

**Files:**
- Create: `frontend/src/components/Observatory/topology/layout/LayoutEngine.ts`
- Create: `frontend/src/components/Observatory/topology/layout/types.ts`

**Types:**
```typescript
// types.ts
export type LayoutAlgorithm = 'force_directed' | 'hierarchical' | 'geographic' | 'radial';

export interface ApiNode {
  id: string;
  type: string;
  hostname: string;
  vendor: string;
  device_type: string;
  site_id: string;
  group: string;
  rank: number;
  status: string;
  confidence: number;
  metrics?: Record<string, number>;
}

export interface ApiEdge {
  id: string;
  source: string;
  target: string;
  source_interface: string;
  target_interface: string;
  edge_type: string;
  protocol: string;
  confidence: number;
  metrics?: Record<string, any>;
}

export interface ApiGroup {
  id: string;
  label: string;
  accent: string;
  device_count: number;
}

export interface LayoutInput {
  nodes: ApiNode[];
  edges: ApiEdge[];
  groups: ApiGroup[];
  algorithm: LayoutAlgorithm;
  canvasWidth: number;
  canvasHeight: number;
}

export interface LayoutOutput {
  nodes: Node[];  // ReactFlow nodes with positions
  edges: Edge[];  // ReactFlow edges with styles
}
```

```typescript
// LayoutEngine.ts
import { Node, Edge } from 'reactflow';
import { LayoutInput, LayoutOutput } from './types';
import { forceDirectedLayout } from './forceDirected';
import { hierarchicalLayout } from './hierarchical';

export function computeLayout(input: LayoutInput): LayoutOutput {
  switch (input.algorithm) {
    case 'force_directed':
      return forceDirectedLayout(input);
    case 'hierarchical':
      return hierarchicalLayout(input);
    default:
      return hierarchicalLayout(input);
  }
}

export function recommendAlgorithm(nodeCount: number, hasGeo: boolean): LayoutAlgorithm {
  if (hasGeo) return 'geographic';
  if (nodeCount <= 50) return 'force_directed';
  return 'hierarchical';
}
```

**Commit:** `feat(frontend): layout engine interface and types`

---

## Task 3: Frontend — Hierarchical Layout (Dagre)

**Files:**
- Create: `frontend/src/components/Observatory/topology/layout/hierarchical.ts`

Uses dagre for tier-based layout. Devices sorted by rank within groups.

```typescript
import dagre from 'dagre';
import { Node, Edge } from 'reactflow';
import { LayoutInput, LayoutOutput, ApiNode } from './types';
import { getEdgeStyle, getEdgeLabel } from '../styles/edgeStyles';

export function hierarchicalLayout(input: LayoutInput): LayoutOutput {
  const { nodes, edges, groups, canvasWidth } = input;

  // Build per-group dagre sub-graphs
  const groupGraphs: Record<string, dagre.graphlib.Graph> = {};

  for (const group of groups) {
    const g = new dagre.graphlib.Graph();
    g.setGraph({ rankdir: 'TB', ranksep: 100, nodesep: 40, marginx: 30, marginy: 30 });
    g.setDefaultEdgeLabel(() => ({}));

    const memberNodes = nodes.filter(n => n.group === group.id);
    for (const node of memberNodes) {
      g.setNode(node.id, { width: 180, height: 90, rank: node.rank });
    }

    for (const edge of edges) {
      const srcGroup = nodes.find(n => n.id === edge.source)?.group;
      const tgtGroup = nodes.find(n => n.id === edge.target)?.group;
      if (srcGroup === group.id && tgtGroup === group.id) {
        g.setEdge(edge.source, edge.target);
      }
    }

    dagre.layout(g);
    groupGraphs[group.id] = g;
  }

  // Position groups on canvas, build ReactFlow nodes/edges
  // ... (group arrangement, parent/child relationships, edge styling)
}
```

**Commit:** `feat(frontend): hierarchical layout using dagre`

---

## Task 4: Frontend — Force-Directed Layout (D3)

**Files:**
- Create: `frontend/src/components/Observatory/topology/layout/forceDirected.ts`

Uses D3-force simulation with group clustering.

```typescript
import * as d3 from 'd3-force';
import { LayoutInput, LayoutOutput } from './types';

export function forceDirectedLayout(input: LayoutInput): LayoutOutput {
  // D3 force simulation with:
  // - link force (connected nodes attract)
  // - charge force (all nodes repel)
  // - group clustering force (same group nodes cluster)
  // - center force
  // - collision prevention
  // Run 300 ticks, then freeze positions
  // Convert to ReactFlow nodes with group containers
}
```

**Commit:** `feat(frontend): force-directed layout using D3-force`

---

## Task 5: Frontend — Edge Styling System

**Files:**
- Create: `frontend/src/components/Observatory/topology/styles/edgeStyles.ts`

Centralized edge styling based on edge_type, utilization, stale status.

```typescript
const EDGE_STYLES: Record<string, React.CSSProperties> = {
  physical: { stroke: '#22c55e', strokeWidth: 3 },
  logical: { stroke: '#22c55e', strokeWidth: 2, strokeDasharray: '4,2' },
  tunnel: { stroke: '#06b6d4', strokeWidth: 3, strokeDasharray: '10,5' },
  ha_peer: { stroke: '#f59e0b', strokeWidth: 2, strokeDasharray: '6,4' },
  mpls: { stroke: '#f59e0b', strokeWidth: 4 },
  stale: { stroke: '#64748b', strokeWidth: 1, strokeDasharray: '2,4', opacity: 0.4 },
  down: { stroke: '#ef4444', strokeWidth: 4, strokeDasharray: '6,3' },
};

export function getEdgeStyle(edge: ApiEdge): React.CSSProperties { ... }
export function getEdgeLabel(edge: ApiEdge): string { ... }
```

**Commit:** `feat(frontend): centralized edge styling system`

---

## Task 6: Frontend — WebSocket Real-Time Updates

**Files:**
- Create: `frontend/src/components/Observatory/topology/realtime/TopologyStreamManager.ts`
- Modify: `frontend/src/components/Observatory/topology/LiveTopologyView.tsx`

WebSocket connection to `/api/v5/topology/stream` for real-time delta events. Merges deltas into React state without full reload.

```typescript
export class TopologyStreamManager {
  private ws: WebSocket | null = null;
  private onDelta: (delta: TopologyDelta) => void;

  connect(url: string): void { ... }
  disconnect(): void { ... }
}

// In LiveTopologyView: useLiveTopology() hook
// Initial load via REST, real-time updates via WebSocket
```

**Commit:** `feat(frontend): WebSocket real-time topology updates`

---

## Task 7: Frontend — Migrate LiveTopologyView to New Layout Engine

**Files:**
- Modify: `frontend/src/components/Observatory/topology/LiveTopologyView.tsx`

Remove backend-computed positions. Use `computeLayout()` from the new layout engine. Keep all existing interactions (hover, blast radius, path trace, context menu, keyboard shortcuts).

**Changes:**
1. Fetch from `/api/v5/topology` (no positions)
2. Call `computeLayout()` with response data + canvas dimensions
3. Apply returned ReactFlow nodes/edges
4. Connect WebSocket for real-time updates
5. Keep existing filters, interactions, keyboard shortcuts

**Commit:** `feat(frontend): migrate LiveTopologyView to frontend layout engine`

---

## Task 8: Backend — WebSocket Endpoint

**Files:**
- Modify: `backend/src/api/topology_v5.py`

Add WebSocket endpoint that bridges EventBus topology events to connected clients using the `WebSocketTopologyPublisher` from Phase 3.

```python
@router.websocket("/api/v5/topology/stream")
async def topology_stream(websocket: WebSocket):
    await websocket.accept()
    client_id = str(uuid.uuid4())
    ws_publisher.register(client_id, websocket)
    try:
        while True:
            await websocket.receive_text()  # Keep alive
    except WebSocketDisconnect:
        ws_publisher.unregister(client_id)
```

**Commit:** `feat(api): WebSocket endpoint for real-time topology stream`

---

## Task 9: Full Regression Test

Run all tests across all 5 phases.

---

## Summary

| Task | What | Layer |
|------|------|-------|
| 1 | v5 API — semantic export | Backend |
| 2 | Layout engine interface | Frontend |
| 3 | Hierarchical layout (dagre) | Frontend |
| 4 | Force-directed layout (D3) | Frontend |
| 5 | Edge styling system | Frontend |
| 6 | WebSocket real-time updates | Frontend |
| 7 | Migrate LiveTopologyView | Frontend |
| 8 | WebSocket endpoint | Backend |
| 9 | Full regression test | Both |

**After Phase 5 is complete:**
The entire KG architecture overhaul is done:
- Phase 1: Repository layer (decoupled from storage)
- Phase 2: Neo4j graph database (Cypher queries)
- Phase 3: Event bus (Kafka + WebSocket real-time)
- Phase 4: Discovery adapters (SNMP/LLDP/AWS + BFS crawler)
- Phase 5: Frontend visualization (pluggable layouts + real-time)
