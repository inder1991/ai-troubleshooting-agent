# Topology Editor: Comprehensive UX Overhaul Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix systemic UX issues in the network topology editor — broken interface placement, unselectable edges, inconsistent handles, missing feedback, and add text annotations.

**Architecture:** React + TypeScript + ReactFlow. All changes are in `frontend/src/components/topology/` and `frontend/src/index.css`.

**Tech Stack:** React 18, TypeScript, ReactFlow, Tailwind CSS

---

## Phase 1 — Core UX (sequential, each builds on previous)

### Task 1: Interface Nodes — Fix Placement & Add Resize

**Files:**
- Modify: `frontend/src/components/topology/InterfaceNode.tsx`
- Modify: `frontend/src/components/topology/TopologyEditorView.tsx`

**Problems:**
- `handleAddInterface` hardcodes ALL interfaces to spawn right of device with `sourceHandle:'left' → targetHandle:'right'` — all edges converge on ONE handle
- No `NodeResizeControl` on InterfaceNode — user can't shrink/expand
- No `w-full h-full` — layout breaks if resize is added
- Interfaces stack in a single column

**Step 1: Fix InterfaceNode.tsx**

Add `NodeResizeControl` with `minWidth={60}, minHeight={28}`:
```tsx
import { NodeResizeControl } from '@xyflow/react';

// Inside component:
<NodeResizeControl
  minWidth={60}
  minHeight={28}
  style={{ background: 'transparent', border: 'none' }}
>
  <div style={{ width: 8, height: 8, background: '#07b6d5', borderRadius: 2 }} />
</NodeResizeControl>
```

Add `w-full h-full` on inner container. Make compact by default — show only `eth0 [OUT]` inline, expand to show IP/parent on resize.

**Step 2: Fix handleAddInterface in TopologyEditorView.tsx**

Distribute interfaces around 4 cardinal positions of the parent device:
- 1st interface → **top** (sourceHandle: 'bottom' → targetHandle: 'top'), position: (x, y - 100)
- 2nd interface → **right** (sourceHandle: 'left' → targetHandle: 'right'), position: (x + 200, y)
- 3rd interface → **bottom** (sourceHandle: 'top' → targetHandle: 'bottom'), position: (x, y + 100)
- 4th interface → **left** (sourceHandle: 'right' → targetHandle: 'left'), position: (x - 200, y)
- 5th+ → cycle back with offset

Auto-assign role based on position order: outside, inside, management, sync.

**Step 3: Verify**

Run: `cd frontend && npx tsc --noEmit`

**Step 4: Commit**

```bash
git add frontend/src/components/topology/InterfaceNode.tsx frontend/src/components/topology/TopologyEditorView.tsx
git commit -m "fix(topology): distribute interfaces around device cardinal positions and add resize"
```

---

### Task 2: Edge Selection, Hover & Deletion

**Files:**
- Modify: `frontend/src/components/topology/LabeledEdge.tsx`
- Modify: `frontend/src/components/topology/TopologyEditorView.tsx`
- Modify: `frontend/src/index.css`

**Problems:**
- Edges aren't individually clickable for selection
- No hover state on edges
- Edge label at 7px is barely readable

**Step 1: Fix LabeledEdge.tsx**

Add invisible fat interaction path behind visible path:
```tsx
{/* Invisible fat path for click targeting */}
<path
  d={edgePath}
  fill="none"
  stroke="transparent"
  strokeWidth={15}
  className="react-flow__edge-interaction"
/>
{/* Visible path */}
<path
  d={edgePath}
  fill="none"
  stroke={style?.stroke || '#3a5a60'}
  strokeWidth={style?.strokeWidth || 1.5}
  className="react-flow__edge-path"
/>
```

Increase label font to 9px, increase label padding, add stronger background contrast (`#0f2023` bg with 95% opacity).

**Step 2: Add CSS hover transitions to index.css**

```css
.react-flow__edge-path {
  transition: stroke-width 0.2s ease, filter 0.2s ease;
}
.react-flow__edge:hover .react-flow__edge-path {
  stroke-width: 3;
  filter: drop-shadow(0 0 3px rgba(7, 182, 213, 0.3));
}
.react-flow__edge.selected .react-flow__edge-path {
  stroke: #07b6d5;
  stroke-width: 2.5;
}
```

**Step 3: Add onEdgeClick handler in TopologyEditorView.tsx**

Add `selectedEdgeId` state. On edge click, set it and pass to DevicePropertyPanel.

**Step 4: Verify**

Run: `cd frontend && npx tsc --noEmit`

**Step 5: Commit**

```bash
git add frontend/src/components/topology/LabeledEdge.tsx frontend/src/components/topology/TopologyEditorView.tsx frontend/src/index.css
git commit -m "fix(topology): add edge hover states, fat click target, and selection handling"
```

---

### Task 3: Handle Type Standardization

**Files:**
- Modify: `frontend/src/components/topology/DeviceNode.tsx`
- Modify: `frontend/src/components/topology/InterfaceNode.tsx`
- Modify: `frontend/src/components/topology/VPCNode.tsx`
- Modify: `frontend/src/components/topology/SubnetGroupNode.tsx`
- Modify: `frontend/src/components/topology/HAGroupNode.tsx`
- Modify: `frontend/src/components/topology/AZNode.tsx`
- Modify: `frontend/src/components/topology/ASGNode.tsx`
- Modify: `frontend/src/components/topology/ComplianceZoneNode.tsx`

**Problem:** All handles are `type="source"` — no target handles. No directionality hints.

**Fix:** Standardize across ALL node components:
- Top handle: `type="target"`, id="top"
- Left handle: `type="target"`, id="left"
- Bottom handle: `type="source"`, id="bottom"
- Right handle: `type="source"`, id="right"

This creates natural flow: connections go top→bottom or left→right. Keep `ConnectionMode.Loose` so users aren't blocked.

**Step 1:** Read each node component, change handle types
**Step 2:** Verify: `cd frontend && npx tsc --noEmit`
**Step 3:** Commit: `git commit -m "fix(topology): standardize handle types — top/left=target, bottom/right=source"`

---

## Phase 2 — Workflow & Features (parallel)

### Task 4: Auto-Save Property Panel

**Files:**
- Modify: `frontend/src/components/topology/DevicePropertyPanel.tsx`

**Problem:** User must click "Apply Changes" button after every edit — not discoverable.

**Fix:**
- Replace manual "Apply Changes" with auto-save: call `onNodeUpdate` on each input `onChange` (debounced 300ms)
- Remove the Apply button entirely
- Show subtle "Saved" indicator (fade-in/fade-out text) after auto-save triggers
- Keep validation inline — red borders still block bad values

**Step 1:** Read DevicePropertyPanel.tsx
**Step 2:** Add debounce utility (300ms), wire each input onChange to auto-save
**Step 3:** Remove Apply button, add "Saved" indicator
**Step 4:** Verify: `cd frontend && npx tsc --noEmit`
**Step 5:** Commit: `git commit -m "fix(topology): auto-save property panel on change with debounce"`

---

### Task 5: Toast Notification System

**Files:**
- Create: `frontend/src/components/topology/ToastNotification.tsx`
- Modify: `frontend/src/components/topology/TopologyEditorView.tsx`

**Fix:**
- Create `ToastNotification.tsx` — positioned bottom-center, auto-dismiss 3s
- States: success (green border), error (red border), info (cyan border)
- Wire into: handleSave (success/fail), handlePromote (success/fail), handleLoad, handleIPAMImported

```tsx
interface ToastProps {
  message: string;
  type: 'success' | 'error' | 'info';
  onDismiss: () => void;
}
```

**Step 1:** Create ToastNotification.tsx
**Step 2:** Add toast state management to TopologyEditorView
**Step 3:** Wire toasts into save, promote, load, IPAM import handlers
**Step 4:** Verify: `cd frontend && npx tsc --noEmit`
**Step 5:** Commit: `git commit -m "feat(topology): add toast notification system for action feedback"`

---

### Task 6: Edge Type Editing in Property Panel

**Files:**
- Modify: `frontend/src/components/topology/DevicePropertyPanel.tsx`
- Modify: `frontend/src/components/topology/TopologyEditorView.tsx`

**Problem:** Edge label is read-only. No UI to change edge type.

**Fix:**
- When an edge is selected, show edge properties section in DevicePropertyPanel:
  - Edge Type dropdown: connected_to, routes_to, load_balances, tunnel_to, nacl_guards, vpc_contains, attached_to
  - Source/Target display (read-only)
  - Delete Edge button
- Pass `selectedEdge`, `onEdgeUpdate`, `onEdgeDelete` props to panel

**Step 1:** Read DevicePropertyPanel.tsx, understand current props
**Step 2:** Add edge editing section (conditional on selectedEdge)
**Step 3:** Wire TopologyEditorView to pass edge data and handlers
**Step 4:** Verify: `cd frontend && npx tsc --noEmit`
**Step 5:** Commit: `git commit -m "feat(topology): add edge type editing in property panel"`

---

### Task 7: Text Annotation Blocks

**Files:**
- Create: `frontend/src/components/topology/TextAnnotationNode.tsx`
- Modify: `frontend/src/components/topology/NodePalette.tsx`
- Modify: `frontend/src/components/topology/TopologyEditorView.tsx`
- Modify: `frontend/src/components/topology/DevicePropertyPanel.tsx`

**Implementation:**
- New node type `text_annotation` — borderless text block on canvas
- Data: `{ text, fontSize, fontWeight, color, backgroundColor, borderStyle }`
- `NodeResizeControl` for resizing (minWidth=40, minHeight=20)
- 4 directional handles (hidden by default, shown on hover)
- Add "Annotations" category in NodePalette
- Register in nodeTypes, handle in onDrop
- Property panel: text textarea, font size, color picker, bg, border

**Step 1:** Create TextAnnotationNode.tsx
**Step 2:** Add to NodePalette, register in TopologyEditorView nodeTypes
**Step 3:** Handle in onDrop (not container, not device)
**Step 4:** Add property panel section for text_annotation
**Step 5:** Verify: `cd frontend && npx tsc --noEmit`
**Step 6:** Commit: `git commit -m "feat(topology): add text annotation blocks with resize and style options"`

---

## Phase 3 — Polish (parallel)

### Task 8: Container Label Z-Index Fix

**Files:**
- Modify: `frontend/src/components/topology/VPCNode.tsx`
- Modify: `frontend/src/components/topology/SubnetGroupNode.tsx`
- Modify: `frontend/src/components/topology/HAGroupNode.tsx`
- Modify: `frontend/src/components/topology/AZNode.tsx`
- Modify: `frontend/src/components/topology/ASGNode.tsx`
- Modify: `frontend/src/components/topology/ComplianceZoneNode.tsx`

**Fix:** Add `z-index: 10` and `pointer-events: none` to floating badge/label spans. Add `position: relative` to parent wrapper.

**Commit:** `git commit -m "fix(topology): fix container label z-index overlap"`

---

### Task 9: Handle Size Standardization

**Files:** All 8 node components

**Fix:** All handles: `!w-2.5 !h-2.5` (10px), border `#3a5a60`. Resize control: `8px x 8px` everywhere.

**Commit:** `git commit -m "fix(topology): standardize handle sizes and border colors across all nodes"`

---

### Task 10: Dark Theme CSS Overrides

**Files:** `frontend/src/index.css`

**Fix:**
```css
.react-flow__connection-path { stroke: #07b6d5; stroke-width: 2; }
.react-flow__controls button:hover { background: #1a3a40 !important; border-color: #07b6d5 !important; }
.react-flow__node.selected { filter: drop-shadow(0 0 4px rgba(7,182,213,0.4)); }
```

**Commit:** `git commit -m "fix(topology): add dark theme CSS overrides for connections, controls, selection"`

---

### Task 11: Firewall ClipPath Fix + Redundant Dimensions

**Files:**
- Modify: `frontend/src/components/topology/DeviceNode.tsx`
- Modify: All 6 container nodes

**Fix:**
- Increase padding inside clipPath to keep content safely inside polygon bounds
- Remove inline `minWidth/minHeight` from container div styles — let `NodeResizeControl` handle min bounds

**Commit:** `git commit -m "fix(topology): fix firewall clipPath padding and remove redundant dimension declarations"`

---

## Verification

1. `npx tsc --noEmit` — 0 TypeScript errors
2. Visual: Add firewall → add 4 interfaces → each radiates to a different side
3. Visual: Resize an interface node smaller → content collapses gracefully
4. Visual: Click an edge → edge highlights, side panel shows edge properties → change type → label updates
5. Visual: Hover over edge → stroke thickens, cursor changes
6. Visual: Edit device name in property panel → changes apply immediately without clicking Apply
7. Visual: Save with validation errors → toast shows error message
8. Visual: Draw connection → preview line is cyan, not gray
9. Visual: Nested containers → labels don't overlap
10. Visual: Drag "Text Note" from palette → type text → resize → connect to device
11. Visual: Select text annotation → property panel shows font size, color, border options
