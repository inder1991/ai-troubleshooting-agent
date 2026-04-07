# Workflow Animation Redesign — Design

**Goal:** Redesign the "How It Works" animation to use horizontal flow with camera pan, warm amber color palette matching the app's design system, tiered node hierarchy, spotlight panel with large duck avatars, dramatic phase transitions, and cinematic finale.

**Context:** The initial implementation used cyan-on-dark colors, vertical layout, identical node sizing, and tiny duck avatars. The critique identified these as AI-aesthetic anti-patterns that clash with the app's warm command-center design system.

---

## 1. Layout & Camera System

**Horizontal flow, left-to-right**, with camera pan auto-scrolling to follow the active phase.

**Canvas structure:**
- Full viewport SVG with wide viewBox (~2400x600 for cluster, ~1800x500 for app)
- Only ~one phase width visible at a time (~500px window)
- Camera `transform: translateX()` animated via Framer Motion as phases progress
- Past phases slide off-screen left, faded to 20% opacity
- Future phases invisible until camera reaches them

**Spotlight panel (left side):**
- Fixed 200px-wide panel on the left, outside the scrolling SVG
- Large duck avatar (80px), role name, status text, progress ring
- Crossfade (300ms) between agents as active node changes
- When no agent active: supervisor duck with "Processing..."
- When complete: supervisor with "Diagnosis Complete" + checkmark
- Background: `#161310` with right border `#3d3528`

**Node layout (horizontal columns):**
- **Cluster:** Pre-flight (col 1, 6 nodes vertical) → Agents (col 2, 5 nodes vertical fan-out) → Intelligence (col 3, 6 nodes vertical) → Synthesis (col 4, 3 nodes) → Report (col 5)
- **App:** Form+Supervisor (col 1) → Log (col 2) → Metrics+K8s (col 3) → Code (col 4) → Change (col 5) → Critic (col 6) → Impact+Synth+Report (col 7)

**Playback bar:** Bottom, phase label syncs with camera position.

---

## 2. Color & Visual Identity

**Primary accent:** `#e09f3e` (app's warm amber). Replaces all `#07b6d5` cyan.

**Backgrounds:**
- Page: `#1a1814` (duck-bg)
- Header: `#161310` (duck-panel)
- Node pending fill: `#252118` (duck-card)
- Node pending stroke: `#3d3528` (duck-border)

**Node status colors:**
- Active: fill `#2a2010`, stroke `#e09f3e`, glow `#e09f3e`
- Complete: fill `#0c2d1f`, stroke `#10b981`, glow `#10b981`

**Edge colors:**
- Default pipeline: `#e09f3e` (amber)
- Fan-out agent edges: per-agent colors (red `#ef4444`, blue `#38bdf8`, orange `#f59e0b`, purple `#a78bfa`, emerald `#10b981`)

**Particles:** Match edge color.

**PlaybackBar & tabs:** All cyan → amber.

**Title:** "How It Works" — single color white, no partial-color accent.

**Typography:** SVG text uses `fontFamily: 'DM Sans, Inter, system-ui, sans-serif'`.

---

## 3. Node Hierarchy & Sizing

Three tiers for visual rhythm:

**Tier 1 — Landmark nodes (start & finish):**
- "Mission Deployed", "Health Report" / "Diagnosis Report"
- 180x64px, border-radius 12px, stroke 2px, label 13px
- Duck at 32px inside node

**Tier 2 — Agent nodes (named agents):**
- Control Plane, Compute, Network, Storage, RBAC, Log, Metrics, K8s, Code, Change, Critic
- 150x56px, border-radius 10px
- 4px colored left accent bar matching agent edge color (mirrors AgentFindingCard)
- Duck at 28px

**Tier 3 — Pipeline/utility nodes:**
- RBAC Check, Topology Scan, Alert Correlation, Causal Firewall, Dispatch Router, Signal Normalizer, Pattern Matcher, Temporal Analyzer, Evidence Graph, Hypothesis Engine, Solution Validator, Impact Analysis, Synthesis
- 130x44px, border-radius 8px
- No duck avatar — system steps
- Label 10px, muted styling

Visual pattern: **big start → small pipeline → prominent agents → small pipeline → big finish**.

---

## 4. Phase Transitions & Finale

**Phase dividers:**
- Vertical dashed lines between phase columns, `#3d3528` at 0.4 opacity
- Phase label text above columns: 9px uppercase `#8a7e6b`, tracking-widest (e.g. "PRE-FLIGHT", "DOMAIN AGENTS")

**Dispatch pulse:**
- When Dispatch Router activates: radial wave ring expands outward (amber, fades to 0)
- Then 5 fan-out edges animate with per-agent colors

**Convergence effect:**
- When fan-in edges converge on a target node: ring contracts inward (reverse of dispatch)
- Signals "data merging"

**Dramatic finale (last ~3 seconds):**
1. Nodes sequentially dim left-to-right (100ms stagger) — settled: opacity 0.4, no glow
2. Camera pans to final report node
3. Report node amber burst ring expanding outward
4. Output labels fade in with staggered spring animation:
   - Cluster: "Causal Chains", "Blast Radius", "Remediation Steps"
   - App: "Root Cause", "Blast Radius", "Remediation", "Past Incidents"
5. "Diagnosis Complete" label fades in below, DM Sans bold, amber

**Reduced motion (`prefers-reduced-motion`):**
- Static horizontal flowchart, all nodes in "complete" state
- Phase labels visible, output labels visible
- No animation, no particles, no camera pan
- Playback bar hidden — infographic view

---

## 5. Spotlight Panel

**Position:** Fixed left panel, 200px wide, full canvas height. SVG flowchart takes remaining space.

**Background:** `#161310` with right border `#3d3528`.

**Content (top to bottom):**
- Large duck avatar: 80px, pure SVG, centered
- Role name: 14px DM Sans bold, white
- Status line: 11px Inter, `#8a7e6b`
- Progress ring: 32px diameter, amber stroke

**Behavior:**
- Pipeline/utility nodes active → supervisor duck, "Processing..."
- Agent node activates → crossfade to that agent's duck + name + subtitle
- Complete → supervisor duck, "Diagnosis Complete" + checkmark
- Idle (before start / after reset) → supervisor duck, "Ready to diagnose"
- Crossfade: 300ms ease-out

---

## 6. Components (Updated)

| Component | Changes |
|-----------|---------|
| `HowItWorksView.tsx` | Amber palette, white title, updated tab styling |
| `WorkflowAnimation.tsx` | Horizontal viewBox, camera pan system, phase dividers, finale sequence, reduced-motion static view |
| `AnimationNode.tsx` | Three tiers (landmark/agent/pipeline), left accent bar for agents, variable sizing, no foreignObject |
| `AnimationEdge.tsx` | Amber default color, horizontal bezier curves |
| `DuckAvatar.tsx` | Pure SVG rendering (remove motion.svg wrapper for direct use), scalable |
| `PlaybackBar.tsx` | Amber accent, DM Sans font |
| `SpotlightPanel.tsx` | **NEW** — large duck, role name, status, progress ring |
| `workflowConfigs.ts` | Horizontal x/y coordinates, node tier metadata, output labels per workflow |

## What Does NOT Change

- No backend changes
- No changes to existing diagnostic workflows or war room UI
- No new npm dependencies
- Config-driven architecture preserved
- PlaybackBar UX (play/pause/reset/scrubber/seek) preserved
