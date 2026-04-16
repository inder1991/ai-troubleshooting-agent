# Phase 4: Canvas Replay (Read-Only DAG) — Design

**Goal:** Add a visual DAG view to RunDetailPage as a toggle alongside the existing card list. This is a **debugging surface** — clarity over aesthetics, signal over animation, speed over completeness.

**Architecture:** elkjs for deterministic DAG layout + hand-built SVG rendering + full pan/zoom. Purely frontend — no backend changes.

**Tech Stack:** elkjs (WASM), SVG, existing `useRunEvents` hook, `wr-*` Tailwind tokens.

---

## 1. Non-goals

- No authoring/editing (Phase 5+)
- No drag/drop, no inline config
- No split view (deferred — validate graph usefulness first; toggle-only for Phase 4)
- No full visual canvas for workflow building (post-Phase 6 per phase sequencing)

## 2. Data Model

Pure domain types, no UI leakage:

```ts
interface DagNode {
  id: string;            // step_id — globally stable across retries/replays
  agent: string;
  agentVersion: number;
  status: StepRunStatus; // pending | running | success | failed | skipped | cancelled
  duration_ms?: number;
  error?: { type?: string; message?: string };
}

interface DagEdge {
  source: string;  // step_id of upstream dependency
  target: string;  // step_id of downstream consumer
}

interface DagModel {
  nodes: DagNode[];
  edges: DagEdge[];
}
```

## 3. Dependency Extraction

**Shared domain utility** in `dagHelpers.ts` (NOT copied from StepList's UI helper). Extracts dependencies from:

- Input mapping refs (`{ref: {from: 'node', node_id}}`)
- Predicate/when refs (recursive AST walk)
- `fallback_step_id` references

Hardened with tests covering: fallback edges, conditional branching, nested predicates, self-referencing guards, missing refs.

## 4. Layout Engine

**elkjs** with layered algorithm (`elk.layered`). Deterministic — same graph structure always produces identical positions.

**Critical invariant:** layout is computed ONCE per DAG structure change (step IDs + dependency edges). Status updates (node colors, edge colors, animations) NEVER trigger re-layout. `useElkLayout` memoizes on a structural key derived from node IDs + edge pairs.

ELK options:
- `algorithm: 'layered'`
- `elk.direction: 'DOWN'` (top-to-bottom flow)
- `elk.layered.spacing.nodeNodeBetweenLayers: 60`
- `elk.layered.spacing.edgeNodeBetweenLayers: 30`
- `elk.edgeRouting: 'ORTHOGONAL'`
- Node size: fixed (e.g. 200×80), derived from medium-density content

## 5. Node Rendering (Medium Density)

Each node rectangle shows:
- Step ID (title, bold)
- Agent name @ version (subtitle, muted)
- Status badge (amber pulse = running, emerald = success, red = failed, gray = skipped, slate = cancelled, neutral = pending)
- Duration when complete (e.g. "2.3s")
- Error indicator (⚠) for failed nodes — visible without expanding

Click node → scrolls to and highlights the corresponding step card in the card list below.

## 6. Edge Rendering

Two visual layers:

1. **Progressive coloring:** edges start gray (pending). When upstream node completes → edge turns emerald. When upstream is running → amber. When upstream fails → red.

2. **Flow particles:** animated dots traveling along active edges via CSS `stroke-dashoffset` animation. Active = upstream node is `running`. Particles stop when upstream reaches a terminal status. Subtle, not distracting.

Edges drawn as orthogonal paths (ELK edge routing output).

## 7. Failure Path Highlighting

- **Auto-activates** when any step has status `failed`
- Highlights three things:
  1. Failed node(s) — red glow/border
  2. All transitive **upstream** dependencies (causal chain — "what fed into this failure?")
  3. All transitive **downstream** nodes affected (blast radius — "what got skipped/blocked?")
- Everything outside the failure path **dims** (opacity ~0.2)
- "Show all" button dismisses highlighting and restores full graph
- Multiple failures: highlights union of all failure paths

Failure path computation is a graph traversal utility in `dagHelpers.ts`, tested independently.

## 8. Pan/Zoom

Encapsulated in `useDagViewport` hook:

- **Zoom:** mouse wheel → scales SVG viewBox. Bounds: 0.25x – 3x.
- **Pan:** click-drag (pointer events) → translates viewBox origin.
- **Fit to view:** button resets viewBox to auto-fit entire graph with padding.
- **State:** `{ x, y, zoom }` managed in hook. Exposes `pan(dx, dy)`, `zoomTo(level)`, `fitToView(graphBounds)`, `focusNode(nodeId)`.
- `focusNode` animates viewport to center on a specific node (used for card→node highlighting).

## 9. Interaction Model (Read-Only)

**Bidirectional highlighting (ships in Phase 4, not deferred):**
- Click node in graph → scrolls to + highlights corresponding step card in list below
- Click card in list → highlights + focuses node in graph (when graph view active)
- Creates a two-way mental bridge between views

**No editing interactions:**
- No drag/drop
- No inline config
- No context menus
- Click is the only interaction (beyond pan/zoom)

## 10. Toggle UX

- Toggle button group on RunDetailPage header: `[Cards] [Graph]`
- Default: Cards
- Preference persisted in localStorage key `wf-run-view-mode`
- Both views share the same `useRunEvents` data source — no duplicate fetching
- Card list always renders below graph (even in graph mode) for bidirectional highlighting. Cards section can be collapsed but remains in DOM for scroll-to targeting.

## 11. Live Run Behavior

- SSE events from existing `useRunEvents` hook update `DagNode` statuses in real-time
- Graph re-renders on status changes: node badge color + edge color update
- **No layout recomputation** — only visual properties change
- Flow particles activate on edges leading to `running` nodes
- On terminal event → particles stop
- If any step fails → failure path auto-highlights

## 12. Component Structure

```
Workflows/Runs/
  DagView/
    DagView.tsx            — SVG container + pan/zoom controls + fit button
    DagNode.tsx            — node rectangle SVG renderer
    DagEdge.tsx            — edge path SVG renderer (progressive color + particles)
    useElkLayout.ts        — hook: DagModel → elkjs → positioned nodes/edges (memoized on structure)
    useDagViewport.ts      — hook: pan/zoom/fit state + focusNode
    dagHelpers.ts          — extractDeps, buildDagModel, computeFailurePath (shared domain logic)
    dagTypes.ts            — DagNode, DagEdge, DagModel, PositionedNode, PositionedEdge
    __tests__/
      dagHelpers.test.ts
      useElkLayout.test.ts
      DagView.test.tsx
      DagNode.test.tsx
      DagEdge.test.tsx
      interaction.test.tsx   — node↔card bidirectional highlighting
  RunDetailPage.tsx          — modified: add toggle, render DagView or StepStatusPanel
  StepStatusPanel.tsx        — modified: accept highlightedStepId prop for bidirectional highlighting
```

## 13. Testing Strategy

Priority order (interaction tests > computation tests > render tests):

1. **dagHelpers** — dependency extraction (fallback, branching, nested predicates), failure path computation (upstream + downstream, multiple failures, union)
2. **Interaction tests** — node click → correct card highlighted + scrolled, card click → correct node highlighted + focused in viewport
3. **useElkLayout** — mock ELK, verify memoization (same structure = no recompute), verify positioned output shape
4. **DagView/DagNode/DagEdge** — render with mock positioned data, verify SVG elements present, status colors correct
5. **RunDetailPage toggle** — switches views, localStorage persistence, shared data source
6. **No Playwright** — graph SVG interaction is unreliable in E2E; unit/integration tests cover the critical paths

## 14. Backend Changes

**None.** All data already available:
- `getVersion(wfId, v).dag` → step structure + dependencies
- `getRun(runId)` → step_runs with statuses
- `subscribeEvents(runId)` → live status updates

## 15. Performance Considerations

- elkjs layout is async (WASM) — show a brief loading indicator on first render
- Layout memoized — only recomputes if DAG structure changes (never during a run)
- SVG rendering uses `key` on nodes/edges for efficient React reconciliation
- Flow particle animation via CSS only (no JS animation loop)
- For very large graphs (50+ nodes): consider virtual viewport (only render visible nodes). Defer unless needed.

## 16. Deferred (Post-Phase 4)

- Split view (DAG left, step detail right) — validate toggle usefulness first
- Minimap for large graphs
- Time-scrubbing / replay slider (replay a completed run step by step)
- Virtual viewport for 50+ node graphs
- Backend-exposed DAG (currently derived client-side from step refs)
- Hypothesis flow / elimination path / causal chain overlays (Phase 5+ supervisor integration)

## 17. Exit Criteria

- [ ] Toggle switches between card list and DAG graph on RunDetailPage
- [ ] DAG renders all steps as nodes with correct status colors (live-updating via SSE)
- [ ] Edges show progressive coloring + flow particles for active runs
- [ ] Failure path auto-highlights on failed steps (upstream + downstream + dim)
- [ ] Pan/zoom works (wheel zoom, drag pan, fit-to-view button)
- [ ] Bidirectional highlighting: click node → highlight card, click card → highlight node
- [ ] Layout stable — status updates never trigger re-layout
- [ ] Toggle preference persisted in localStorage
- [ ] No backend changes
- [ ] Vitest green; no regressions in Phase 1/2/3 tests
- [ ] Non-impact: backend untouched, Investigation UI untouched
