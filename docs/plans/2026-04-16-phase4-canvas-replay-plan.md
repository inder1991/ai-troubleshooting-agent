# Phase 4: Canvas Replay Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a read-only DAG visualization to RunDetailPage as a toggle alongside the card list, with live status updates, failure path highlighting, pan/zoom, and bidirectional node↔card highlighting.

**Architecture:** elkjs (WASM) computes layered DAG positions from step dependencies. Hand-built SVG renders nodes/edges with status-driven coloring. `useDagViewport` handles pan/zoom. Failure path computed via graph traversal. All data from existing `useRunEvents` hook — no backend changes.

**Tech Stack:** elkjs, SVG, React, Vitest + RTL, Tailwind `wr-*` tokens.

---

## Batch Map

| Batch | Tasks | Description |
|-------|-------|-------------|
| A | 1-2 | Domain types + dependency extraction (shared utility) |
| B | 3-4 | elkjs layout hook + failure path computation |
| C | 5-6 | DagNode + DagEdge SVG renderers |
| D | 7-8 | useDagViewport + DagView container |
| E | 9-10 | RunDetailPage toggle + bidirectional highlighting |
| F | 11-12 | Live edge animation + flow particles |
| G | 13 | Final verification + non-impact + PR |

---

## Task 1: Domain types + `dagTypes.ts`

**Files:**
- Create: `frontend/src/components/Workflows/Runs/DagView/dagTypes.ts`
- Test: `frontend/src/components/Workflows/Runs/DagView/__tests__/dagTypes.test.ts`

```ts
// dagTypes.ts
import type { StepRunStatus } from '../../../../types';

export interface DagNode {
  id: string;
  agent: string;
  agentVersion: number | 'latest';
  status: StepRunStatus;
  duration_ms?: number;
  error?: { type?: string; message?: string };
}

export interface DagEdge {
  source: string;
  target: string;
}

export interface DagModel {
  nodes: DagNode[];
  edges: DagEdge[];
}

export interface PositionedNode extends DagNode {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface PositionedEdge extends DagEdge {
  points: Array<{ x: number; y: number }>;
}

export interface PositionedDag {
  nodes: PositionedNode[];
  edges: PositionedEdge[];
  width: number;
  height: number;
}
```

Tests: type-only validation — create sample data conforming to each interface, assert shape. This is mostly a structural commit.

**Commit:** `feat(dag): domain types for canvas replay`

---

## Task 2: `dagHelpers.ts` — dependency extraction + failure path

**Files:**
- Create: `frontend/src/components/Workflows/Runs/DagView/dagHelpers.ts`
- Test: `frontend/src/components/Workflows/Runs/DagView/__tests__/dagHelpers.test.ts`

This is a **shared domain utility**, NOT a copy of `StepList.tsx`'s `extractStepDependencies`. Rewrite from scratch with hardened edge-case handling.

```ts
// dagHelpers.ts
import type { StepSpec, MappingExpr, PredicateExpr } from '../../../../types';
import type { DagNode, DagEdge, DagModel } from './dagTypes';

/** Collect all node_ids referenced by a step (inputs + when + fallback). */
export function extractDependencies(step: StepSpec): string[] {
  const deps = new Set<string>();
  // 1. Input mapping refs
  for (const v of Object.values(step.inputs ?? {})) {
    collectMappingRefs(v, deps);
  }
  // 2. Predicate/when refs
  collectPredicateRefs(step.when, deps);
  // 3. Fallback step ref
  if (step.fallback_step_id) deps.add(step.fallback_step_id);
  return Array.from(deps);
}

function collectMappingRefs(m: MappingExpr | undefined, out: Set<string>): void {
  if (!m || typeof m !== 'object') return;
  if ('ref' in m) {
    const r = (m as any).ref;
    if (r?.from === 'node' && r.node_id) out.add(r.node_id);
    return;
  }
  if ('literal' in m) return;
  if ('op' in m && 'args' in m) {
    for (const a of (m as any).args ?? []) collectMappingRefs(a, out);
  }
}

function collectPredicateRefs(p: PredicateExpr | undefined, out: Set<string>): void {
  if (!p) return;
  const pp = p as Record<string, unknown>;
  const op = pp.op as string;
  if (op === 'and' || op === 'or') {
    for (const a of (pp.args ?? []) as PredicateExpr[]) collectPredicateRefs(a, out);
  } else if (op === 'not') {
    collectPredicateRefs((pp.args as PredicateExpr[])?.[0] ?? pp.arg as PredicateExpr, out);
  } else {
    // eq, in, exists — args are MappingExpr[]
    for (const a of (pp.args ?? []) as MappingExpr[]) collectMappingRefs(a, out);
  }
}

/** Build a DagModel from steps + step run statuses. */
export function buildDagModel(
  steps: StepSpec[],
  statusMap: Map<string, { status: StepRunStatus; duration_ms?: number; error?: any }>,
): DagModel {
  const stepIds = new Set(steps.map(s => s.id));
  const nodes: DagNode[] = steps.map(s => {
    const info = statusMap.get(s.id);
    return {
      id: s.id,
      agent: s.agent,
      agentVersion: s.agent_version,
      status: info?.status ?? 'pending',
      duration_ms: info?.duration_ms,
      error: info?.error,
    };
  });
  const edges: DagEdge[] = [];
  for (const step of steps) {
    const deps = extractDependencies(step);
    for (const dep of deps) {
      if (stepIds.has(dep)) {
        edges.push({ source: dep, target: step.id });
      }
    }
  }
  return { nodes, edges };
}

/** Compute failure path: upstream causal chain + downstream blast radius. */
export function computeFailurePath(
  model: DagModel,
): { highlighted: Set<string>; dimmed: Set<string> } {
  const failedIds = model.nodes.filter(n => n.status === 'failed').map(n => n.id);
  if (failedIds.length === 0) return { highlighted: new Set(), dimmed: new Set() };

  // Build adjacency: forward (source→targets) and backward (target→sources)
  const forward = new Map<string, string[]>();
  const backward = new Map<string, string[]>();
  for (const e of model.edges) {
    forward.set(e.source, [...(forward.get(e.source) ?? []), e.target]);
    backward.set(e.target, [...(backward.get(e.target) ?? []), e.source]);
  }

  const highlighted = new Set<string>();

  // Walk upstream (causal chain)
  function walkUp(id: string) {
    if (highlighted.has(id)) return;
    highlighted.add(id);
    for (const src of backward.get(id) ?? []) walkUp(src);
  }
  // Walk downstream (blast radius)
  function walkDown(id: string) {
    if (highlighted.has(id)) return;
    highlighted.add(id);
    for (const tgt of forward.get(id) ?? []) walkDown(tgt);
  }

  for (const fid of failedIds) {
    walkUp(fid);
    walkDown(fid);
  }

  const allIds = new Set(model.nodes.map(n => n.id));
  const dimmed = new Set([...allIds].filter(id => !highlighted.has(id)));

  return { highlighted, dimmed };
}

/** Check if a given edge is on the failure path. */
export function isEdgeOnFailurePath(
  edge: DagEdge,
  highlighted: Set<string>,
): boolean {
  return highlighted.has(edge.source) && highlighted.has(edge.target);
}
```

**Tests (minimum 12):**
1. `extractDependencies`: step with node ref in inputs → returns node_id
2. `extractDependencies`: step with `when` predicate containing node ref → returns node_id
3. `extractDependencies`: step with `fallback_step_id` → includes it
4. `extractDependencies`: step with nested `and/or` predicates → finds deep refs
5. `extractDependencies`: step with `not` wrapper → finds inner refs
6. `extractDependencies`: step with transform (coalesce) containing refs → finds them
7. `extractDependencies`: step with only literal inputs → returns empty
8. `buildDagModel`: 3 steps with chain A→B→C → correct edges
9. `buildDagModel`: ref to nonexistent step → edge excluded
10. `computeFailurePath`: linear chain A→B(fail)→C → highlights all three, nothing dimmed
11. `computeFailurePath`: branching: A→B(fail), A→C(success) → A,B highlighted; C dimmed
12. `computeFailurePath`: no failures → empty highlighted set
13. `isEdgeOnFailurePath`: edge between two highlighted nodes → true

**Commit:** `feat(dag): dependency extraction + failure path computation`

---

## Task 3: `useElkLayout` hook

**Files:**
- Create: `frontend/src/components/Workflows/Runs/DagView/useElkLayout.ts`
- Test: `frontend/src/components/Workflows/Runs/DagView/__tests__/useElkLayout.test.ts`

**Install elkjs first:**
```bash
cd frontend && npm install elkjs
```

```ts
// useElkLayout.ts
import { useMemo, useState, useEffect } from 'react';
import ELK from 'elkjs/lib/elk.bundled.js';
import type { DagModel, PositionedDag, PositionedNode, PositionedEdge } from './dagTypes';

const NODE_WIDTH = 200;
const NODE_HEIGHT = 80;

const elk = new ELK();

/** Structural key: changes only when node IDs or edges change, never on status. */
function structuralKey(model: DagModel): string {
  const nk = model.nodes.map(n => n.id).sort().join(',');
  const ek = model.edges.map(e => `${e.source}->${e.target}`).sort().join(',');
  return `${nk}|${ek}`;
}

export function useElkLayout(model: DagModel): {
  layout: PositionedDag | null;
  loading: boolean;
  error: Error | null;
} {
  const key = useMemo(() => structuralKey(model), [model]);
  const [layout, setLayout] = useState<PositionedDag | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function compute() {
      setLoading(true);
      setError(null);
      try {
        const graph = {
          id: 'root',
          layoutOptions: {
            'elk.algorithm': 'layered',
            'elk.direction': 'DOWN',
            'elk.layered.spacing.nodeNodeBetweenLayers': '60',
            'elk.spacing.nodeNode': '30',
            'elk.edgeRouting': 'ORTHOGONAL',
          },
          children: model.nodes.map(n => ({
            id: n.id,
            width: NODE_WIDTH,
            height: NODE_HEIGHT,
          })),
          edges: model.edges.map((e, i) => ({
            id: `e${i}`,
            sources: [e.source],
            targets: [e.target],
          })),
        };

        const result = await elk.layout(graph);

        if (cancelled) return;

        const posNodes: PositionedNode[] = (result.children ?? []).map(c => {
          const orig = model.nodes.find(n => n.id === c.id)!;
          return {
            ...orig,
            x: c.x ?? 0,
            y: c.y ?? 0,
            width: c.width ?? NODE_WIDTH,
            height: c.height ?? NODE_HEIGHT,
          };
        });

        const posEdges: PositionedEdge[] = (result.edges ?? []).map(e => {
          const origIdx = model.edges.findIndex(
            oe => oe.source === e.sources?.[0] && oe.target === e.targets?.[0]
          );
          const orig = model.edges[origIdx] ?? { source: e.sources?.[0] ?? '', target: e.targets?.[0] ?? '' };
          const sections = (e as any).sections ?? [];
          const points: Array<{ x: number; y: number }> = [];
          for (const sec of sections) {
            if (sec.startPoint) points.push(sec.startPoint);
            if (sec.bendPoints) points.push(...sec.bendPoints);
            if (sec.endPoint) points.push(sec.endPoint);
          }
          return { ...orig, points };
        });

        setLayout({
          nodes: posNodes,
          edges: posEdges,
          width: result.width ?? 800,
          height: result.height ?? 600,
        });
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err : new Error(String(err)));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    compute();
    return () => { cancelled = true; };
  }, [key]); // Only recompute when structural key changes

  return { layout, loading, error };
}
```

**Tests (minimum 5):**
1. Returns positioned nodes with x/y/width/height after layout.
2. Returns positioned edges with points array.
3. Layout dimensions (width/height) are positive.
4. Memoization: same structural key → no re-layout (verify effect doesn't re-run).
5. Status change on a node does NOT change structural key.

Note: elkjs runs in Node.js for tests (WASM bundle works in both environments). If WASM fails in Vitest, mock `elkjs` to return deterministic positions and test the hook logic separately.

**Commit:** `feat(dag): elk layout hook with structural memoization`

---

## Task 4: `computeFailurePath` integration test + edge helpers

**Files:**
- Modify: `frontend/src/components/Workflows/Runs/DagView/dagHelpers.ts` (add edge status helper)
- Test: `frontend/src/components/Workflows/Runs/DagView/__tests__/dagHelpers.test.ts` (extend)

Add edge color helper:

```ts
import type { StepRunStatus } from '../../../../types';

export type EdgeStatus = 'pending' | 'active' | 'completed' | 'failed';

/** Determine edge visual status based on source node status. */
export function edgeStatus(sourceStatus: StepRunStatus): EdgeStatus {
  switch (sourceStatus) {
    case 'running': return 'active';
    case 'success': return 'completed';
    case 'failed': return 'failed';
    default: return 'pending';
  }
}
```

**Additional tests:**
1. `edgeStatus`: running → active, success → completed, failed → failed, pending → pending, skipped → pending
2. `computeFailurePath` with diamond graph: A→B, A→C, B→D, C→D, B fails → B,A,D highlighted; C dimmed
3. `computeFailurePath` with multiple failures: union of paths
4. `isEdgeOnFailurePath` with edge between highlighted and non-highlighted → false

**Commit:** `feat(dag): edge status helpers + failure path integration tests`

---

## Task 5: `DagNode.tsx` — SVG node renderer

**Files:**
- Create: `frontend/src/components/Workflows/Runs/DagView/DagNode.tsx`
- Test: `frontend/src/components/Workflows/Runs/DagView/__tests__/DagNode.test.tsx`

```tsx
// DagNode.tsx
import type { PositionedNode } from './dagTypes';
import type { StepRunStatus } from '../../../../types';

interface DagNodeProps {
  node: PositionedNode;
  dimmed?: boolean;
  highlighted?: boolean;
  selected?: boolean;
  onClick?: (nodeId: string) => void;
}

const STATUS_FILL: Record<StepRunStatus, string> = {
  pending: '#525252',   // neutral-600
  running: '#d97706',   // amber-600
  success: '#059669',   // emerald-600
  failed: '#dc2626',    // red-600
  skipped: '#6b7280',   // gray-500
  cancelled: '#64748b', // slate-500
};

const STATUS_STROKE: Record<StepRunStatus, string> = {
  pending: '#737373',
  running: '#f59e0b',
  success: '#10b981',
  failed: '#ef4444',
  skipped: '#9ca3af',
  cancelled: '#94a3b8',
};

function formatDuration(ms: number): string {
  if (ms < 1000) return '<1s';
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

export function DagNode({ node, dimmed, highlighted, selected, onClick }: DagNodeProps) {
  const fill = STATUS_FILL[node.status] ?? STATUS_FILL.pending;
  const stroke = STATUS_STROKE[node.status] ?? STATUS_STROKE.pending;
  const opacity = dimmed ? 0.2 : 1;

  return (
    <g
      data-testid={`dag-node-${node.id}`}
      transform={`translate(${node.x}, ${node.y})`}
      opacity={opacity}
      onClick={() => onClick?.(node.id)}
      style={{ cursor: onClick ? 'pointer' : 'default' }}
      role="button"
      tabIndex={0}
      aria-label={`Step ${node.id}: ${node.status}`}
    >
      {/* Node rectangle */}
      <rect
        width={node.width}
        height={node.height}
        rx={8}
        fill={fill}
        stroke={selected ? '#e09f3e' : stroke}
        strokeWidth={selected ? 3 : 2}
      />

      {/* Pulse animation for running */}
      {node.status === 'running' && (
        <rect
          width={node.width}
          height={node.height}
          rx={8}
          fill="none"
          stroke={stroke}
          strokeWidth={2}
          className="animate-pulse"
        />
      )}

      {/* Step ID */}
      <text
        x={10} y={22}
        fill="white" fontSize={13} fontWeight={600}
      >
        {node.id}
      </text>

      {/* Agent name */}
      <text
        x={10} y={40}
        fill="rgba(255,255,255,0.7)" fontSize={11}
      >
        {node.agent}@{node.agentVersion}
      </text>

      {/* Status + duration row */}
      <text
        x={10} y={58}
        fill="rgba(255,255,255,0.7)" fontSize={11}
      >
        {node.status}
        {node.duration_ms != null && ` · ${formatDuration(node.duration_ms)}`}
      </text>

      {/* Error indicator */}
      {node.status === 'failed' && (
        <text
          x={node.width - 24} y={22}
          fill="#fca5a5" fontSize={16}
          data-testid={`dag-node-error-${node.id}`}
        >
          ⚠
        </text>
      )}

      {/* Failure path highlight glow */}
      {highlighted && (
        <rect
          width={node.width + 4}
          height={node.height + 4}
          x={-2} y={-2}
          rx={10}
          fill="none"
          stroke={node.status === 'failed' ? '#ef4444' : '#f59e0b'}
          strokeWidth={2}
          strokeDasharray="6 3"
        />
      )}
    </g>
  );
}
```

**Tests (minimum 6):**
1. Renders rect with correct fill for each status.
2. Running node has `animate-pulse` class.
3. Failed node shows ⚠ error indicator.
4. Dimmed node has opacity 0.2.
5. Click calls onClick with nodeId.
6. Selected node has accent stroke (#e09f3e).
7. Shows duration text when `duration_ms` set.

**Commit:** `feat(dag): SVG node renderer with status coloring`

---

## Task 6: `DagEdge.tsx` — SVG edge renderer

**Files:**
- Create: `frontend/src/components/Workflows/Runs/DagView/DagEdge.tsx`
- Test: `frontend/src/components/Workflows/Runs/DagView/__tests__/DagEdge.test.tsx`

```tsx
// DagEdge.tsx
import type { PositionedEdge } from './dagTypes';
import type { EdgeStatus } from './dagHelpers';

interface DagEdgeProps {
  edge: PositionedEdge;
  edgeStatus: EdgeStatus;
  dimmed?: boolean;
  onFailurePath?: boolean;
}

const EDGE_COLORS: Record<EdgeStatus, string> = {
  pending: '#525252',
  active: '#d97706',
  completed: '#059669',
  failed: '#dc2626',
};

function pointsToPath(points: Array<{ x: number; y: number }>): string {
  if (points.length === 0) return '';
  const [first, ...rest] = points;
  return `M ${first.x} ${first.y} ` + rest.map(p => `L ${p.x} ${p.y}`).join(' ');
}

export function DagEdge({ edge, edgeStatus: status, dimmed, onFailurePath }: DagEdgeProps) {
  const color = EDGE_COLORS[status] ?? EDGE_COLORS.pending;
  const d = pointsToPath(edge.points);
  const opacity = dimmed ? 0.1 : 1;
  const edgeId = `edge-${edge.source}-${edge.target}`;

  return (
    <g data-testid={edgeId} opacity={opacity}>
      {/* Base edge line */}
      <path
        d={d}
        fill="none"
        stroke={color}
        strokeWidth={onFailurePath ? 3 : 2}
        markerEnd="url(#arrowhead)"
      />

      {/* Flow particles (animated dash) for active edges */}
      {status === 'active' && (
        <path
          d={d}
          fill="none"
          stroke="white"
          strokeWidth={2}
          strokeDasharray="4 8"
          strokeOpacity={0.6}
          className="dag-flow-particle"
        />
      )}

      {/* Progressive coloring glow for completed edges */}
      {status === 'completed' && (
        <path
          d={d}
          fill="none"
          stroke={EDGE_COLORS.completed}
          strokeWidth={4}
          strokeOpacity={0.3}
        />
      )}
    </g>
  );
}
```

CSS animation (add to `frontend/src/index.css`):
```css
@keyframes dag-flow {
  to { stroke-dashoffset: -24; }
}
.dag-flow-particle {
  animation: dag-flow 0.8s linear infinite;
}
```

**Tests (minimum 5):**
1. Renders path element with correct `d` attribute from points.
2. Pending edge → neutral color.
3. Active edge → amber + flow particle path with `dag-flow-particle` class.
4. Completed edge → emerald + glow path.
5. Dimmed edge → opacity 0.1.

**Commit:** `feat(dag): SVG edge renderer with progressive coloring + flow particles`

---

## Task 7: `useDagViewport` hook

**Files:**
- Create: `frontend/src/components/Workflows/Runs/DagView/useDagViewport.ts`
- Test: `frontend/src/components/Workflows/Runs/DagView/__tests__/useDagViewport.test.ts`

```ts
// useDagViewport.ts
import { useState, useCallback, useRef } from 'react';

export interface ViewportState {
  x: number;
  y: number;
  zoom: number;
}

const MIN_ZOOM = 0.25;
const MAX_ZOOM = 3;
const ZOOM_STEP = 0.1;

export function useDagViewport(graphWidth: number, graphHeight: number) {
  const [viewport, setViewport] = useState<ViewportState>({ x: 0, y: 0, zoom: 1 });
  const isPanning = useRef(false);
  const panStart = useRef({ x: 0, y: 0 });

  const fitToView = useCallback((containerWidth: number, containerHeight: number) => {
    if (graphWidth === 0 || graphHeight === 0) return;
    const pad = 40;
    const scaleX = (containerWidth - pad * 2) / graphWidth;
    const scaleY = (containerHeight - pad * 2) / graphHeight;
    const zoom = Math.min(scaleX, scaleY, MAX_ZOOM);
    const x = (containerWidth - graphWidth * zoom) / 2;
    const y = (containerHeight - graphHeight * zoom) / 2;
    setViewport({ x, y, zoom: Math.max(zoom, MIN_ZOOM) });
  }, [graphWidth, graphHeight]);

  const zoomTo = useCallback((delta: number) => {
    setViewport(v => ({
      ...v,
      zoom: Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, v.zoom + delta)),
    }));
  }, []);

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -ZOOM_STEP : ZOOM_STEP;
    zoomTo(delta);
  }, [zoomTo]);

  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    isPanning.current = true;
    panStart.current = { x: e.clientX, y: e.clientY };
    (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
  }, []);

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    if (!isPanning.current) return;
    const dx = e.clientX - panStart.current.x;
    const dy = e.clientY - panStart.current.y;
    panStart.current = { x: e.clientX, y: e.clientY };
    setViewport(v => ({ ...v, x: v.x + dx, y: v.y + dy }));
  }, []);

  const handlePointerUp = useCallback(() => {
    isPanning.current = false;
  }, []);

  const focusNode = useCallback((
    nodeX: number, nodeY: number, nodeWidth: number, nodeHeight: number,
    containerWidth: number, containerHeight: number,
  ) => {
    const zoom = viewport.zoom;
    const cx = containerWidth / 2 - (nodeX + nodeWidth / 2) * zoom;
    const cy = containerHeight / 2 - (nodeY + nodeHeight / 2) * zoom;
    setViewport(v => ({ ...v, x: cx, y: cy }));
  }, [viewport.zoom]);

  const viewBox = `${-viewport.x / viewport.zoom} ${-viewport.y / viewport.zoom} ${graphWidth / viewport.zoom} ${graphHeight / viewport.zoom}`;

  return {
    viewport,
    viewBox,
    fitToView,
    zoomTo,
    focusNode,
    handlers: {
      onWheel: handleWheel,
      onPointerDown: handlePointerDown,
      onPointerMove: handlePointerMove,
      onPointerUp: handlePointerUp,
    },
  };
}
```

**Tests (minimum 5):**
1. Initial viewport: x=0, y=0, zoom=1.
2. `fitToView` computes centered viewport with correct zoom.
3. `zoomTo` clamps between MIN_ZOOM and MAX_ZOOM.
4. `focusNode` centers viewport on given node coordinates.
5. Pointer events update viewport x/y (simulate pan).

**Commit:** `feat(dag): viewport hook with pan/zoom/fit`

---

## Task 8: `DagView.tsx` — main container

**Files:**
- Create: `frontend/src/components/Workflows/Runs/DagView/DagView.tsx`
- Create: `frontend/src/components/Workflows/Runs/DagView/index.ts` (barrel export)
- Test: `frontend/src/components/Workflows/Runs/DagView/__tests__/DagView.test.tsx`

```tsx
// DagView.tsx
import { useRef, useEffect, useMemo } from 'react';
import type { StepSpec, StepRunDetail } from '../../../../types';
import type { LiveEvent } from '../StepStatusPanel';
import { buildDagModel, computeFailurePath, edgeStatus, isEdgeOnFailurePath } from './dagHelpers';
import { useElkLayout } from './useElkLayout';
import { useDagViewport } from './useDagViewport';
import { DagNode } from './DagNode';
import { DagEdge } from './DagEdge';

interface DagViewProps {
  steps: StepSpec[];
  stepRuns: StepRunDetail[];
  liveEvents?: LiveEvent[];
  selectedNodeId?: string | null;
  onNodeClick?: (nodeId: string) => void;
}

export function DagView({ steps, stepRuns, liveEvents = [], selectedNodeId, onNodeClick }: DagViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  // Build status map from stepRuns + liveEvents (reuse StepStatusPanel's merge logic concept)
  const statusMap = useMemo(() => {
    const m = new Map<string, { status: any; duration_ms?: number; error?: any }>();
    for (const sr of stepRuns) {
      m.set(sr.step_id, { status: sr.status, duration_ms: sr.duration_ms, error: sr.error });
    }
    // Apply live event overrides
    for (const evt of liveEvents) {
      const sid = evt.data.step_id;
      if (!sid) continue;
      const cur = m.get(sid) ?? { status: 'pending' };
      if (evt.type === 'step.started') cur.status = 'running';
      else if (evt.type === 'step.completed') cur.status = evt.data.status ?? 'success';
      else if (evt.type === 'step.failed') { cur.status = 'failed'; cur.error = evt.data.error; }
      m.set(sid, cur);
    }
    return m;
  }, [stepRuns, liveEvents]);

  const dagModel = useMemo(() => buildDagModel(steps, statusMap), [steps, statusMap]);
  const { layout, loading, error } = useElkLayout(dagModel);
  const { viewport, fitToView, focusNode, handlers } = useDagViewport(
    layout?.width ?? 800,
    layout?.height ?? 600,
  );

  // Auto-fit on first layout
  useEffect(() => {
    if (layout && containerRef.current) {
      const { width, height } = containerRef.current.getBoundingClientRect();
      fitToView(width, height);
    }
  }, [layout]); // intentionally not including fitToView to avoid loop

  // Failure path
  const failurePath = useMemo(() => {
    if (!layout) return { highlighted: new Set<string>(), dimmed: new Set<string>() };
    return computeFailurePath(dagModel);
  }, [dagModel, layout]);

  const hasFailure = failurePath.highlighted.size > 0;

  // Show all toggle
  const [showAll, setShowAll] = useState(false);

  if (loading) {
    return <div className="p-6 text-wr-text-secondary">Computing layout...</div>;
  }
  if (error || !layout) {
    return <div className="p-6 text-red-400">Layout error: {error?.message}</div>;
  }

  // Build node status lookup for edge coloring
  const nodeStatusMap = new Map(layout.nodes.map(n => [n.id, n.status]));

  return (
    <div
      ref={containerRef}
      className="relative w-full bg-wr-bg rounded-lg border border-wr-border overflow-hidden"
      style={{ height: 500 }}
      data-testid="dag-view-container"
    >
      {/* Controls */}
      <div className="absolute top-2 right-2 z-10 flex gap-1">
        <button
          className="px-2 py-1 text-xs rounded bg-wr-surface border border-wr-border text-wr-text hover:bg-wr-surface-2"
          onClick={() => {
            if (containerRef.current) {
              const r = containerRef.current.getBoundingClientRect();
              fitToView(r.width, r.height);
            }
          }}
          data-testid="dag-fit-btn"
        >
          Fit
        </button>
        {hasFailure && (
          <button
            className="px-2 py-1 text-xs rounded bg-wr-surface border border-wr-border text-wr-text hover:bg-wr-surface-2"
            onClick={() => setShowAll(v => !v)}
            data-testid="dag-show-all-btn"
          >
            {showAll ? 'Show failure path' : 'Show all'}
          </button>
        )}
      </div>

      {/* SVG canvas */}
      <svg
        width="100%"
        height="100%"
        {...handlers}
        style={{ touchAction: 'none' }}
      >
        <defs>
          <marker
            id="arrowhead"
            markerWidth={10} markerHeight={7}
            refX={10} refY={3.5}
            orient="auto"
          >
            <polygon points="0 0, 10 3.5, 0 7" fill="#737373" />
          </marker>
        </defs>

        <g transform={`translate(${viewport.x}, ${viewport.y}) scale(${viewport.zoom})`}>
          {/* Edges */}
          {layout.edges.map(e => {
            const srcStatus = nodeStatusMap.get(e.source) ?? 'pending';
            const onFP = isEdgeOnFailurePath(e, failurePath.highlighted);
            const isDimmed = hasFailure && !showAll && !onFP;
            return (
              <DagEdge
                key={`${e.source}-${e.target}`}
                edge={e}
                edgeStatus={edgeStatus(srcStatus)}
                dimmed={isDimmed}
                onFailurePath={onFP && !showAll}
              />
            );
          })}

          {/* Nodes */}
          {layout.nodes.map(n => {
            const isDimmed = hasFailure && !showAll && failurePath.dimmed.has(n.id);
            const isHighlighted = hasFailure && !showAll && failurePath.highlighted.has(n.id);
            return (
              <DagNode
                key={n.id}
                node={n}
                dimmed={isDimmed}
                highlighted={isHighlighted}
                selected={n.id === selectedNodeId}
                onClick={onNodeClick}
              />
            );
          })}
        </g>
      </svg>
    </div>
  );
}
```

`index.ts`:
```ts
export { DagView } from './DagView';
```

**Tests (minimum 5):**
1. Renders `dag-view-container` with SVG.
2. Renders one `dag-node-*` testid per step.
3. Renders edge elements between dependent steps.
4. Loading state shows "Computing layout..." text.
5. Fit button present and clickable.

Mock `useElkLayout` to return pre-computed positions (avoid actual elkjs in component tests).

**Commit:** `feat(dag): main DAG view container composing all primitives`

---

## Task 9: RunDetailPage toggle + view persistence

**Files:**
- Modify: `frontend/src/components/Workflows/Runs/RunDetailPage.tsx`
- Test: `frontend/src/components/Workflows/Runs/__tests__/RunDetailPage.toggle.test.tsx`

Changes:
1. Add `viewMode` state: `'cards' | 'graph'`. Initialize from `localStorage.getItem('wf-run-view-mode') ?? 'cards'`.
2. On toggle change, persist to localStorage.
3. Add toggle button group in header: `[Cards] [Graph]`.
4. When `viewMode === 'graph'`: render `<DagView>` above + card list below (cards remain for scroll-to targeting).
5. When `viewMode === 'cards'`: render card list only (current behavior).
6. Need the workflow's step definitions (StepSpec[]) for the DAG. Fetch via `getVersion(run.workflow_version_id)` — but `workflow_version_id` doesn't include `workflow_id`. We need to resolve this. Options:
   - Add `workflow_id` to `RunDetail` type if backend provides it. Check `getRun` response.
   - Or store `workflowId` in URL params / pass from navigation context.
   - Simplest: add route param — the run route is `/workflows/runs/:runId`. Modify to `/workflows/:workflowId/runs/:runId` so we have both. Then fetch version.

**Implementation decision:** Check what the backend `GET /runs/:runId` returns. If it includes `workflow_id` in the response, use that. If not, adjust the route to include `workflowId`.

Check: `backend/src/api/routes_workflows.py` for the run GET response shape. Read `RunDetail` type in frontend. The `workflow_version_id` field exists — we can use the backend's version lookup endpoint to get the DAG. But we need to map `workflow_version_id` to `(workflow_id, version)`. The simplest approach: extend the run route to include `workflowId` in the URL path, since the "Run" button on WorkflowBuilderPage already knows `workflowId`.

Update router: change `runs/:runId` to `:workflowId/runs/:runId` or pass `workflowId` via navigation state.

Actually, check current navigation from WorkflowBuilderPage → RunDetailPage. It navigates to `/workflows/runs/${run.id}`. The `workflowId` is available at that point. Simplest fix: pass `workflowId` as a query param or route state.

For now: use React Router's `useLocation().state` to pass `workflowId` from WorkflowBuilderPage. If state is missing (direct URL access), show cards-only mode with a message "Graph view requires workflow context".

**Tests (minimum 5):**
1. Default: cards view rendered, no DagView.
2. Toggle to Graph: DagView rendered.
3. Toggle persists to localStorage.
4. Page load with localStorage `'graph'` → Graph view rendered.
5. Cards still rendered below DagView in graph mode (for bidirectional highlighting).

**Commit:** `feat(dag): run detail page toggle (cards/graph) with localStorage persistence`

---

## Task 10: Bidirectional node ↔ card highlighting

**Files:**
- Modify: `frontend/src/components/Workflows/Runs/StepStatusPanel.tsx` — accept `highlightedStepId` + `onCardClick` props
- Modify: `frontend/src/components/Workflows/Runs/RunDetailPage.tsx` — wire bidirectional highlighting
- Test: `frontend/src/components/Workflows/Runs/__tests__/interaction.test.tsx`

StepStatusPanel changes:
```tsx
interface StepStatusPanelProps {
  stepRuns: StepRunDetail[];
  liveEvents?: LiveEvent[];
  highlightedStepId?: string | null;
  onCardClick?: (stepId: string) => void;
}
```

Each StepCard gets:
- Highlight ring when `step.step_id === highlightedStepId` (accent border `border-wr-accent`)
- `onClick` → `onCardClick(step.step_id)`
- `data-testid={`step-card-${step.step_id}`}` for scroll targeting
- `ref` for scroll-into-view when highlighted changes

RunDetailPage wiring:
- `highlightedNodeId` state
- DagView `onNodeClick` → sets `highlightedNodeId`, scrolls to card via `ref.scrollIntoView()`
- StepStatusPanel `onCardClick` → sets `highlightedNodeId`, calls `focusNode` on DagView viewport (pass via ref/callback)

**Tests (minimum 4):**
1. Click DagNode → corresponding StepCard gets highlight class.
2. Click StepCard → corresponding DagNode gets selected styling.
3. Click DagNode → StepCard scrolls into view.
4. Clicking another node/card clears previous highlight.

**Commit:** `feat(dag): bidirectional node-card highlighting`

---

## Task 11: CSS animations for flow particles

**Files:**
- Modify: `frontend/src/index.css` — add `dag-flow` keyframe + `dag-flow-particle` class
- Test: `frontend/src/components/Workflows/Runs/DagView/__tests__/DagEdge.test.tsx` (extend)

Add to `frontend/src/index.css` (after existing animation definitions):
```css
@keyframes dag-flow {
  to { stroke-dashoffset: -24; }
}
.dag-flow-particle {
  animation: dag-flow 0.8s linear infinite;
}
```

Verify DagEdge already references `dag-flow-particle` class (done in Task 6).

**Additional tests:**
1. Active edge renders element with `dag-flow-particle` class.
2. Non-active edge does NOT render flow particle element.

**Commit:** `feat(dag): flow particle CSS animation`

---

## Task 12: Integration smoke + edge cases

**Files:**
- Test: `frontend/src/components/Workflows/Runs/DagView/__tests__/integration.test.tsx`

Integration tests that exercise the full stack (mock elkjs):
1. DagView with 3-step chain: renders 3 nodes, 2 edges.
2. DagView with parallel steps (A→C, B→C): renders fan-in correctly.
3. Live event updates: SSE `step.started` → node color changes to amber.
4. Live event: `step.failed` → failure path auto-highlights (upstream + downstream dimmed).
5. "Show all" button appears on failure → click restores full graph.
6. Empty steps array → renders empty state message.
7. Single-step workflow → renders one node, no edges.

**Commit:** `test(dag): integration tests for DagView`

---

## Task 13: Final verification + non-impact + PR

**Files:**
- Create: `backend/tests/test_phase4_non_impact.py`

```python
from __future__ import annotations
import subprocess

def test_backend_non_impact():
    """Phase 4 is purely frontend — no backend changes."""
    result = subprocess.run(
        ["git", "diff", "main..HEAD", "--name-only", "--", "backend/"],
        capture_output=True, text=True,
    )
    changed = [f for f in result.stdout.strip().splitlines() if f]
    allowed = {"backend/tests/test_phase4_non_impact.py"}
    unexpected = [f for f in changed if f not in allowed]
    assert not unexpected, f"Unexpected backend changes: {unexpected}"

def test_investigation_ui_non_impact():
    result = subprocess.run(
        ["git", "diff", "main..HEAD", "--name-only", "--",
         "frontend/src/components/Investigation/"],
        capture_output=True, text=True,
    )
    changed = [f for f in result.stdout.strip().splitlines() if f]
    assert not changed, f"Investigation UI changed: {changed}"
```

**Run full suites:**
```bash
cd frontend && npm run test -- --run
python3 -m pytest backend/tests/test_phase4_non_impact.py -v --timeout=30
```

**PR:**
- Title: `feat(dag): phase 4 — canvas replay (read-only DAG view)`
- Body: summary, exit criteria citations, test plan.

**Commit:** `test(dag): phase 4 non-impact snapshot`

---

## Exit criteria checklist (copy to PR body)

- [ ] Toggle switches between card list and DAG graph on RunDetailPage
- [ ] DAG renders all steps as nodes with correct status colors (live-updating via SSE)
- [ ] Edges show progressive coloring + flow particles for active runs
- [ ] Failure path auto-highlights on failed steps (upstream + downstream + dim)
- [ ] Pan/zoom works (wheel zoom, drag pan, fit-to-view button)
- [ ] Bidirectional highlighting: click node → highlight card, click card → highlight node
- [ ] Layout stable — status updates never trigger re-layout
- [ ] Toggle preference persisted in localStorage
- [ ] No backend changes (except non-impact test file)
- [ ] Vitest green; no regressions in Phase 1/2/3 tests
- [ ] Non-impact: backend untouched, Investigation UI untouched
