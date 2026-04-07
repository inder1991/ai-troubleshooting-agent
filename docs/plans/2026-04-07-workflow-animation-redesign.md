# Workflow Animation Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Redesign the "How It Works" animation from vertical cyan-on-dark to horizontal amber flow with camera pan, tiered node hierarchy, spotlight panel, dramatic finale, and reduced-motion accessibility.

**Architecture:** Config-driven animation engine stays intact — we update interfaces to carry tier/outputLabel metadata, rewrite node coordinates to horizontal columns, add a camera pan system and spotlight panel to WorkflowAnimation, rewrite AnimationNode for three-tier sizing with pure SVG ducks (no foreignObject), and update all colors from cyan to amber.

**Tech Stack:** React 18, TypeScript, Framer Motion 11, Tailwind CSS, pure SVG

---

### Task 1: Update WorkflowConfig interfaces and color constants

**Files:**
- Modify: `frontend/src/components/HowItWorks/workflowConfigs.ts:1-34`

**Step 1: Update the TypeScript interfaces**

Add `tier` and `outputLabels` to `WorkflowNode`, `accentColor` to `WorkflowEdge`, and `phaseColumn` to `WorkflowPhase`. Also add a color constants object.

Replace the entire interfaces block (lines 1-34) with:

```typescript
import type { DuckVariant } from './DuckAvatar';

// ─── Design System Colors ───
export const WF_COLORS = {
  // Backgrounds
  pageBg: '#1a1814',
  panelBg: '#161310',
  cardBg: '#252118',
  border: '#3d3528',
  // Accents
  amber: '#e09f3e',
  green: '#10b981',
  // Node status
  activeFill: '#2a2010',
  activeStroke: '#e09f3e',
  completeFill: '#0c2d1f',
  completeStroke: '#10b981',
  pendingFill: '#252118',
  pendingStroke: '#3d3528',
  // Text
  mutedText: '#8a7e6b',
  labelText: '#e2e8f0',
  dimText: '#5a5347',
  // Agent edge colors
  agentRed: '#ef4444',
  agentBlue: '#38bdf8',
  agentOrange: '#f59e0b',
  agentPurple: '#a78bfa',
  agentEmerald: '#10b981',
} as const;

export type NodeTier = 'landmark' | 'agent' | 'pipeline';

export interface WorkflowNode {
  id: string;
  label: string;
  duck: DuckVariant;
  x: number;
  y: number;
  tier: NodeTier;
  subtitle?: string;
  badge?: string;
  accentColor?: string; // left accent bar color for agent tier
  outputLabels?: string[]; // shown in finale for report nodes
}

export interface WorkflowEdge {
  from: string;
  to: string;
  color?: string; // defaults to WF_COLORS.amber
}

export interface WorkflowPhase {
  name: string;
  description: string;
  startTime: number;
  duration: number;
  activateNodes: string[];
  activateEdges: [string, string][];
  parallel?: boolean;
  phaseColumn?: number; // x-position for phase divider label
}

export interface WorkflowConfig {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  phases: WorkflowPhase[];
  totalDuration: number;
  viewBoxWidth: number;   // total horizontal canvas width
  viewBoxHeight: number;  // canvas height
}
```

**Step 2: Run type check to verify interfaces compile**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -40`
Expected: Errors in downstream files (AnimationNode, WorkflowAnimation) about missing `tier` — this is expected since configs haven't been updated yet.

**Step 3: Commit**

```bash
git add frontend/src/components/HowItWorks/workflowConfigs.ts
git commit -m "feat(workflow): update config interfaces with tier, outputLabels, horizontal viewBox"
```

---

### Task 2: Rewrite cluster and app configs with horizontal layout

**Files:**
- Modify: `frontend/src/components/HowItWorks/workflowConfigs.ts:65-261`

**Step 1: Replace clusterConfig with horizontal layout**

Replace everything from `// ─── Layout constants ───` to the end of `clusterConfig` (lines 36-150) with:

```typescript
// ─── Horizontal Layout Constants ───
// Cluster: 5 columns across ~2400px width, ~600px height
// App: 7 columns across ~1800px width, ~500px height

// ═══════════════════════════════════════════════════════════════
// CLUSTER DIAGNOSTICS (35 seconds)
// Columns: Pre-flight(x=200) → Agents(x=700) → Intelligence(x=1200) → Synthesis(x=1700) → Report(x=2200)
// ═══════════════════════════════════════════════════════════════

export const clusterConfig: WorkflowConfig = {
  totalDuration: 35,
  viewBoxWidth: 2400,
  viewBoxHeight: 600,
  nodes: [
    // Col 1: Pre-flight (x=200, spread vertically)
    { id: 'form',     label: 'Mission Deployed', duck: 'supervisor', x: 200, y: 80,  tier: 'landmark', subtitle: 'Form submitted' },
    { id: 'rbac',     label: 'RBAC Check',       duck: 'rbac',       x: 200, y: 160, tier: 'pipeline', subtitle: 'Checking permissions...' },
    { id: 'topo',     label: 'Topology Scan',    duck: 'network',    x: 200, y: 240, tier: 'pipeline', subtitle: 'Mapping cluster...' },
    { id: 'alerts',   label: 'Alert Correlation', duck: 'metrics',   x: 200, y: 320, tier: 'pipeline', subtitle: 'Grouping alerts...' },
    { id: 'firewall', label: 'Causal Firewall',  duck: 'critic',     x: 200, y: 400, tier: 'pipeline', subtitle: 'Pruning links...' },
    { id: 'dispatch', label: 'Dispatch Router',  duck: 'supervisor', x: 200, y: 480, tier: 'pipeline', subtitle: 'Routing to agents...' },

    // Col 2: Domain agents (x=700, fan-out vertically)
    { id: 'ctrl',    label: 'Control Plane',  duck: 'ctrl_plane', x: 700, y: 80,  tier: 'agent', accentColor: '#ef4444', subtitle: 'Analyzing operators...', badge: '4 anomalies' },
    { id: 'compute', label: 'Compute',        duck: 'compute',    x: 700, y: 180, tier: 'agent', accentColor: '#38bdf8', subtitle: 'Checking nodes...',       badge: '6 anomalies' },
    { id: 'net',     label: 'Network',        duck: 'network',    x: 700, y: 280, tier: 'agent', accentColor: '#f59e0b', subtitle: 'DNS & ingress...',        badge: '5 anomalies' },
    { id: 'stor',    label: 'Storage',        duck: 'storage',    x: 700, y: 380, tier: 'agent', accentColor: '#a78bfa', subtitle: 'PVC health...',           badge: '3 anomalies' },
    { id: 'rbac_a',  label: 'RBAC',           duck: 'rbac',       x: 700, y: 480, tier: 'agent', accentColor: '#10b981', subtitle: 'Security audit...',       badge: '2 anomalies' },

    // Col 3: Intelligence pipeline (x=1200, vertical stack)
    { id: 'signal',  label: 'Signal Normalizer',  duck: 'generic', x: 1200, y: 80,  tier: 'pipeline', subtitle: 'Extracting signals...' },
    { id: 'pattern', label: 'Pattern Matcher',     duck: 'generic', x: 1200, y: 170, tier: 'pipeline', subtitle: 'Matching failure patterns...' },
    { id: 'temporal',label: 'Temporal Analyzer',   duck: 'generic', x: 1200, y: 260, tier: 'pipeline', subtitle: 'Restart velocity...' },
    { id: 'graph',   label: 'Evidence Graph',      duck: 'generic', x: 1200, y: 350, tier: 'pipeline', subtitle: 'Building causal graph...' },
    { id: 'hypo',    label: 'Hypothesis Engine',   duck: 'generic', x: 1200, y: 440, tier: 'pipeline', subtitle: 'Ranking root causes...' },
    { id: 'critic',  label: 'Critic Validator',    duck: 'critic',  x: 1200, y: 530, tier: 'pipeline', subtitle: '6-layer validation...' },

    // Col 4: Synthesis (x=1700)
    { id: 'synth',    label: 'Synthesize',        duck: 'supervisor', x: 1700, y: 200, tier: 'pipeline', subtitle: 'Building diagnosis...' },
    { id: 'solution', label: 'Solution Validator', duck: 'critic',    x: 1700, y: 340, tier: 'pipeline', subtitle: 'Validating remediation...' },
    { id: 'impact',   label: 'Impact Analysis',   duck: 'generic',   x: 1700, y: 480, tier: 'pipeline', subtitle: 'Blast radius...' },

    // Col 5: Report (x=2200)
    { id: 'report', label: 'Health Report', duck: 'supervisor', x: 2200, y: 300, tier: 'landmark', badge: 'Diagnosis Complete', outputLabels: ['Causal Chains', 'Blast Radius', 'Remediation Steps'] },
  ],

  edges: [
    // Pre-flight vertical chain
    { from: 'form', to: 'rbac' },
    { from: 'rbac', to: 'topo' },
    { from: 'topo', to: 'alerts' },
    { from: 'alerts', to: 'firewall' },
    { from: 'firewall', to: 'dispatch' },
    // Fan-out (dispatch → agents, horizontal)
    { from: 'dispatch', to: 'ctrl',    color: '#ef4444' },
    { from: 'dispatch', to: 'compute', color: '#38bdf8' },
    { from: 'dispatch', to: 'net',     color: '#f59e0b' },
    { from: 'dispatch', to: 'stor',    color: '#a78bfa' },
    { from: 'dispatch', to: 'rbac_a',  color: '#10b981' },
    // Fan-in (agents → signal, horizontal)
    { from: 'ctrl',    to: 'signal', color: '#ef4444' },
    { from: 'compute', to: 'signal', color: '#38bdf8' },
    { from: 'net',     to: 'signal', color: '#f59e0b' },
    { from: 'stor',    to: 'signal', color: '#a78bfa' },
    { from: 'rbac_a',  to: 'signal', color: '#10b981' },
    // Intelligence vertical chain
    { from: 'signal', to: 'pattern' },
    { from: 'pattern', to: 'temporal' },
    { from: 'temporal', to: 'graph' },
    { from: 'graph', to: 'hypo' },
    { from: 'hypo', to: 'critic' },
    // Synthesis
    { from: 'critic', to: 'synth' },
    { from: 'synth', to: 'solution' },
    { from: 'solution', to: 'impact' },
    { from: 'impact', to: 'report' },
  ],

  phases: [
    {
      name: 'Pre-flight',
      description: 'Checking permissions, mapping topology, correlating alerts',
      startTime: 0, duration: 5,
      activateNodes: ['form', 'rbac', 'topo', 'alerts', 'firewall', 'dispatch'],
      activateEdges: [['form','rbac'], ['rbac','topo'], ['topo','alerts'], ['alerts','firewall'], ['firewall','dispatch']],
      phaseColumn: 200,
    },
    {
      name: 'Domain Agents',
      description: '5 specialized agents analyze the cluster in parallel',
      startTime: 5, duration: 10,
      activateNodes: ['ctrl', 'compute', 'net', 'stor', 'rbac_a'],
      activateEdges: [['dispatch','ctrl'], ['dispatch','compute'], ['dispatch','net'], ['dispatch','stor'], ['dispatch','rbac_a']],
      parallel: true,
      phaseColumn: 700,
    },
    {
      name: 'Intelligence',
      description: 'Normalizing signals, matching patterns, building evidence graph',
      startTime: 15, duration: 10,
      activateNodes: ['signal', 'pattern', 'temporal', 'graph', 'hypo', 'critic'],
      activateEdges: [['ctrl','signal'], ['compute','signal'], ['net','signal'], ['stor','signal'], ['rbac_a','signal'],
                      ['signal','pattern'], ['pattern','temporal'], ['temporal','graph'], ['graph','hypo'], ['hypo','critic']],
      phaseColumn: 1200,
    },
    {
      name: 'Synthesis',
      description: 'Generating root cause analysis, remediation plan, and health report',
      startTime: 25, duration: 7,
      activateNodes: ['synth', 'solution', 'impact', 'report'],
      activateEdges: [['critic','synth'], ['synth','solution'], ['solution','impact'], ['impact','report']],
      phaseColumn: 1700,
    },
    {
      name: 'Diagnosis Complete',
      description: 'Causal chains, blast radius, and remediation steps ready',
      startTime: 32, duration: 3,
      activateNodes: [],
      activateEdges: [],
      phaseColumn: 2200,
    },
  ],
};
```

**Step 2: Replace appConfig with horizontal layout**

Replace the app config section (lines 152-261) with:

```typescript
// ═══════════════════════════════════════════════════════════════
// APP DIAGNOSTICS (40 seconds)
// Columns: Form(x=150) → Log(x=400) → Metrics+K8s(x=650) → Code(x=900)
//          → Change(x=1150) → Critic(x=1400) → Synth+Report(x=1650)
// ═══════════════════════════════════════════════════════════════

export const appConfig: WorkflowConfig = {
  totalDuration: 40,
  viewBoxWidth: 1800,
  viewBoxHeight: 500,
  nodes: [
    // Col 1: Form + Supervisor (x=150)
    { id: 'form',       label: 'Mission Deployed',  duck: 'supervisor', x: 150, y: 180, tier: 'landmark', subtitle: 'Form submitted' },
    { id: 'supervisor', label: 'Supervisor',         duck: 'supervisor', x: 150, y: 320, tier: 'agent', accentColor: '#e09f3e', subtitle: 'Orchestrating...' },

    // Col 2: Log (x=400)
    { id: 'log', label: 'Log Agent', duck: 'log', x: 400, y: 250, tier: 'agent', accentColor: '#fbbf24', subtitle: 'Scanning error patterns...', badge: '3 patterns' },

    // Col 3: Metrics + K8s (x=650, fan-out vertically)
    { id: 'metrics', label: 'Metrics Agent', duck: 'metrics', x: 650, y: 160, tier: 'agent', accentColor: '#10b981', subtitle: 'Querying Prometheus...', badge: '5 anomalies' },
    { id: 'k8s',     label: 'K8s Agent',     duck: 'k8s',     x: 650, y: 340, tier: 'agent', accentColor: '#f59e0b', subtitle: 'Checking pod health...', badge: '2 issues' },

    // Col 4: Code (x=900)
    { id: 'code', label: 'Code Agent', duck: 'code', x: 900, y: 250, tier: 'agent', accentColor: '#60a5fa', subtitle: 'Tracing to source code...', badge: '4 files' },

    // Col 5: Change (x=1150)
    { id: 'change', label: 'Change Agent', duck: 'change', x: 1150, y: 250, tier: 'agent', accentColor: '#c084fc', subtitle: 'Correlating deployments...', badge: '1 commit' },

    // Col 6: Critic (x=1400)
    { id: 'critic', label: 'Critic Agent', duck: 'critic', x: 1400, y: 250, tier: 'agent', accentColor: '#f87171', subtitle: 'Cross-validating findings...' },

    // Col 7: Synthesis + Report (x=1650)
    { id: 'impact', label: 'Impact Analysis', duck: 'generic',    x: 1650, y: 140, tier: 'pipeline', subtitle: 'Blast radius estimation...' },
    { id: 'synth',  label: 'Synthesis',       duck: 'supervisor', x: 1650, y: 250, tier: 'pipeline', subtitle: 'Building final report...' },
    { id: 'report', label: 'Diagnosis Report', duck: 'supervisor', x: 1650, y: 380, tier: 'landmark', badge: 'Diagnosis Complete', outputLabels: ['Root Cause', 'Blast Radius', 'Remediation', 'Past Incidents'] },
  ],

  edges: [
    { from: 'form', to: 'supervisor' },
    { from: 'supervisor', to: 'log' },
    { from: 'log', to: 'metrics', color: '#10b981' },
    { from: 'log', to: 'k8s',     color: '#f59e0b' },
    { from: 'metrics', to: 'code', color: '#10b981' },
    { from: 'k8s',     to: 'code', color: '#f59e0b' },
    { from: 'code', to: 'change' },
    { from: 'change', to: 'critic' },
    { from: 'critic', to: 'impact' },
    { from: 'impact', to: 'synth' },
    { from: 'synth', to: 'report' },
  ],

  phases: [
    {
      name: 'Dispatch',
      description: 'Supervisor receives the mission and plans agent execution',
      startTime: 0, duration: 3,
      activateNodes: ['form', 'supervisor'],
      activateEdges: [['form', 'supervisor']],
      phaseColumn: 150,
    },
    {
      name: 'Log Analysis',
      description: 'Scanning logs for error patterns and reconstructing service flow',
      startTime: 3, duration: 6,
      activateNodes: ['log'],
      activateEdges: [['supervisor', 'log']],
      phaseColumn: 400,
    },
    {
      name: 'Parallel Analysis',
      description: 'Metrics and K8s agents analyze simultaneously',
      startTime: 9, duration: 8,
      activateNodes: ['metrics', 'k8s'],
      activateEdges: [['log', 'metrics'], ['log', 'k8s']],
      parallel: true,
      phaseColumn: 650,
    },
    {
      name: 'Code Analysis',
      description: 'Tracing stack frames to source code',
      startTime: 17, duration: 6,
      activateNodes: ['code'],
      activateEdges: [['metrics', 'code'], ['k8s', 'code']],
      phaseColumn: 900,
    },
    {
      name: 'Change Correlation',
      description: 'Correlating recent deployments with the incident',
      startTime: 23, duration: 5,
      activateNodes: ['change'],
      activateEdges: [['code', 'change']],
      phaseColumn: 1150,
    },
    {
      name: 'Validation',
      description: 'Cross-validating all findings for contradictions',
      startTime: 28, duration: 5,
      activateNodes: ['critic'],
      activateEdges: [['change', 'critic']],
      phaseColumn: 1400,
    },
    {
      name: 'Synthesis & Output',
      description: 'Estimating blast radius and generating final diagnosis',
      startTime: 33, duration: 5,
      activateNodes: ['impact', 'synth', 'report'],
      activateEdges: [['critic', 'impact'], ['impact', 'synth'], ['synth', 'report']],
      phaseColumn: 1650,
    },
    {
      name: 'Diagnosis Complete',
      description: 'Root cause, blast radius, and remediation ready',
      startTime: 38, duration: 2,
      activateNodes: [],
      activateEdges: [],
    },
  ],
};
```

**Step 3: Run type check**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -40`
Expected: Errors in AnimationNode about missing `tier` prop — expected, will fix in Task 3.

**Step 4: Commit**

```bash
git add frontend/src/components/HowItWorks/workflowConfigs.ts
git commit -m "feat(workflow): horizontal layout configs with tier metadata and output labels"
```

---

### Task 3: Rewrite AnimationNode with three-tier sizing and pure SVG ducks

**Files:**
- Modify: `frontend/src/components/HowItWorks/AnimationNode.tsx`

**Step 1: Rewrite the entire AnimationNode component**

Replace the entire file content with:

```tsx
import React from 'react';
import { motion } from 'framer-motion';
import type { DuckVariant, DuckState } from './DuckAvatar';
import { DuckSVGContent } from './DuckAvatar';
import type { NodeTier } from './workflowConfigs';
import { WF_COLORS } from './workflowConfigs';

export type NodeStatus = 'pending' | 'active' | 'complete';

interface AnimationNodeProps {
  id: string;
  label: string;
  duck: DuckVariant;
  x: number;
  y: number;
  tier: NodeTier;
  status: NodeStatus;
  progress?: number;
  subtitle?: string;
  badge?: string;
  accentColor?: string;
  dimmed?: boolean; // for finale dimming
}

// Tier-based dimensions
const TIER_SIZES = {
  landmark: { width: 180, height: 64, radius: 12, fontSize: 13, duckSize: 32, strokeWidth: 2 },
  agent:    { width: 150, height: 56, radius: 10, fontSize: 11, duckSize: 28, strokeWidth: 1.5 },
  pipeline: { width: 130, height: 44, radius: 8,  fontSize: 10, duckSize: 0,  strokeWidth: 1 },
};

const STATUS_COLORS = {
  pending:  { fill: WF_COLORS.pendingFill, stroke: WF_COLORS.pendingStroke, glow: 'none' },
  active:   { fill: WF_COLORS.activeFill,  stroke: WF_COLORS.activeStroke,  glow: WF_COLORS.amber },
  complete: { fill: WF_COLORS.completeFill, stroke: WF_COLORS.completeStroke, glow: WF_COLORS.green },
};

const RING_RADIUS = 14;

const AnimationNode: React.FC<AnimationNodeProps> = ({
  id, label, duck, x, y, tier, status, progress = 0, subtitle, badge, accentColor, dimmed,
}) => {
  const colors = STATUS_COLORS[status];
  const size = TIER_SIZES[tier];
  const duckState: DuckState = status === 'active' ? 'working' : status === 'complete' ? 'done' : 'idle';
  const showDuck = tier !== 'pipeline';

  const circumference = 2 * Math.PI * RING_RADIUS;
  const dashOffset = circumference * (1 - progress);

  const halfW = size.width / 2;
  const halfH = size.height / 2;

  return (
    <motion.g
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: dimmed ? 0.4 : 1, scale: 1 }}
      transition={{ type: 'spring', stiffness: 200, damping: 20 }}
    >
      {/* Glow */}
      {status !== 'pending' && !dimmed && (
        <motion.ellipse
          cx={x}
          cy={y}
          rx={halfW + 8}
          ry={halfH + 8}
          fill={colors.glow}
          initial={{ opacity: 0 }}
          animate={{ opacity: [0.05, 0.15, 0.05] }}
          transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
        />
      )}

      {/* Node background */}
      <motion.rect
        x={x - halfW}
        y={y - halfH}
        width={size.width}
        height={size.height}
        rx={size.radius}
        fill={colors.fill}
        stroke={colors.stroke}
        strokeWidth={size.strokeWidth}
        animate={{ stroke: colors.stroke, fill: colors.fill }}
        transition={{ duration: 0.5 }}
      />

      {/* Left accent bar for agent tier */}
      {tier === 'agent' && accentColor && (
        <rect
          x={x - halfW}
          y={y - halfH + 4}
          width={4}
          height={size.height - 8}
          rx={2}
          fill={accentColor}
        />
      )}

      {/* Duck avatar — pure SVG, no foreignObject */}
      {showDuck && (
        <g transform={`translate(${x - halfW + 10}, ${y - size.duckSize / 2}) scale(${size.duckSize / 24})`}>
          <DuckSVGContent variant={duck} state={duckState} />
        </g>
      )}

      {/* Label */}
      <text
        x={showDuck ? x + (tier === 'landmark' ? 12 : 8) : x}
        y={subtitle && status === 'active' ? y - 3 : y + 1}
        textAnchor="middle"
        fill={status === 'pending' ? WF_COLORS.dimText : WF_COLORS.labelText}
        fontSize={size.fontSize}
        fontWeight="600"
        fontFamily="DM Sans, Inter, system-ui, sans-serif"
      >
        {label}
      </text>

      {/* Subtitle */}
      {subtitle && status === 'active' && (
        <motion.text
          x={showDuck ? x + (tier === 'landmark' ? 12 : 8) : x}
          y={y + 10}
          textAnchor="middle"
          fill={WF_COLORS.mutedText}
          fontSize="8"
          fontFamily="Inter, system-ui, sans-serif"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
        >
          {subtitle}
        </motion.text>
      )}

      {/* Badge */}
      {badge && status === 'complete' && (
        <motion.g
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ type: 'spring', stiffness: 300, delay: 0.2 }}
        >
          <rect
            x={x + halfW - 40}
            y={y + halfH - 6}
            width={36}
            height={14}
            rx={7}
            fill="#059669"
          />
          <text
            x={x + halfW - 22}
            y={y + halfH + 4}
            textAnchor="middle"
            fill="white"
            fontSize="7"
            fontWeight="600"
          >
            {badge}
          </text>
        </motion.g>
      )}

      {/* Progress ring (active agents/landmarks only) */}
      {status === 'active' && progress > 0 && tier !== 'pipeline' && (
        <g transform={`translate(${x + halfW - 20}, ${y})`}>
          <circle r={RING_RADIUS} fill="none" stroke={WF_COLORS.pendingStroke} strokeWidth="2" />
          <motion.circle
            r={RING_RADIUS}
            fill="none"
            stroke={WF_COLORS.amber}
            strokeWidth="2"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            strokeLinecap="round"
            transform="rotate(-90)"
            animate={{ strokeDashoffset: dashOffset }}
            transition={{ duration: 0.3 }}
          />
        </g>
      )}

      {/* Burst effect for report/final nodes */}
      {status === 'complete' && id.includes('report') && (
        <motion.circle
          key={`${id}-burst`}
          cx={x}
          cy={y}
          r={halfW}
          fill="none"
          stroke={WF_COLORS.amber}
          strokeWidth={2}
          initial={{ r: 10, opacity: 0.8 }}
          animate={{ r: halfW * 2, opacity: 0 }}
          transition={{ duration: 1.5, ease: 'easeOut' }}
        />
      )}
    </motion.g>
  );
};

export default AnimationNode;
```

**Step 2: Run type check**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -40`
Expected: Error about `DuckSVGContent` not exported from DuckAvatar — will fix in Task 4.

**Step 3: Commit**

```bash
git add frontend/src/components/HowItWorks/AnimationNode.tsx
git commit -m "feat(workflow): three-tier AnimationNode with pure SVG ducks and amber palette"
```

---

### Task 4: Add DuckSVGContent export to DuckAvatar

**Files:**
- Modify: `frontend/src/components/HowItWorks/DuckAvatar.tsx`

The existing `DuckAvatar` wraps everything in `<motion.svg>` which breaks inside SVG (foreignObject was the workaround). We need a `DuckSVGContent` that renders the raw SVG `<g>` elements without any `<svg>` wrapper, for direct embedding inside parent SVG.

**Step 1: Add the DuckSVGContent component**

After the `DuckAvatar` component (before `export default`), add:

```tsx
/**
 * Pure SVG content — no <svg> wrapper.
 * Renders in a 24x24 coordinate system.
 * Parent must provide `transform` for positioning and scaling.
 */
export const DuckSVGContent: React.FC<{ variant: DuckVariant; state: DuckState }> = ({ variant, state }) => {
  const bodyFill = state === 'done' ? '#10b981' : state === 'working' ? '#fbbf24' : '#475569';
  const bodyStroke = state === 'done' ? '#059669' : state === 'working' ? '#d97706' : '#334155';

  return (
    <g>
      <path d={DUCK_BODY} fill={bodyFill} stroke={bodyStroke} strokeWidth="0.5" />
      <path d={DUCK_BEAK} fill="#f59e0b" />
      <circle cx={DUCK_EYE.cx} cy={DUCK_EYE.cy} r={DUCK_EYE.r} fill="white" />
      <Accessory variant={variant} />
      {state === 'done' && (
        <g>
          <circle cx="19" cy="16" r="3.5" fill="#059669" />
          <path d="M17.5 16l1 1 2-2.5" stroke="white" strokeWidth="1" fill="none" strokeLinecap="round" />
        </g>
      )}
    </g>
  );
};
```

**Step 2: Also update Accessory supervisor color from cyan to amber**

In the `Accessory` function, find the `case 'supervisor':` block (lines 36-45) and replace all `#07b6d5` with `#e09f3e`:

```tsx
    case 'supervisor':
      return (
        <g stroke="#e09f3e" strokeWidth="1" fill="none">
          <path d="M8 5.5 Q8 2 12 2 Q16 2 16 5.5" />
          <circle cx="7.5" cy="5.5" r="1.2" fill="#e09f3e" />
          <circle cx="16.5" cy="5.5" r="1.2" fill="#e09f3e" />
          <line x1="7.5" y1="6.7" x2="7.5" y2="8.5" />
          <circle cx="7.5" cy="9" r="0.6" fill="#e09f3e" />
        </g>
      );
```

Also update the `case 'network':` antenna color from `#07b6d5` to `#e09f3e` (lines 74-79):

```tsx
    case 'network':
      return (
        <g stroke="#e09f3e" strokeWidth="0.8">
          <line x1="12" y1="4" x2="12" y2="0.5" />
          <circle cx="12" cy="0" r="1" fill="#e09f3e" />
          <path d="M9.5 1.5 Q12 -0.5 14.5 1.5" fill="none" strokeWidth="0.6" opacity="0.5" />
          <path d="M8 2.5 Q12 -1.5 16 2.5" fill="none" strokeWidth="0.5" opacity="0.3" />
        </g>
      );
```

**Step 3: Run type check**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -40`
Expected: May still have errors from WorkflowAnimation not passing `tier` — expected.

**Step 4: Commit**

```bash
git add frontend/src/components/HowItWorks/DuckAvatar.tsx
git commit -m "feat(workflow): add DuckSVGContent for pure SVG embedding, update colors to amber"
```

---

### Task 5: Update AnimationEdge for horizontal flow and amber colors

**Files:**
- Modify: `frontend/src/components/HowItWorks/AnimationEdge.tsx`

The current edge code assumes vertical flow (source bottom → target top). For horizontal layout, edges can go either horizontally (left→right) or vertically (within the same column). We need smart bezier curves that detect the dominant direction.

**Step 1: Rewrite AnimationEdge**

Replace the entire file with:

```tsx
import React, { useId } from 'react';
import { motion } from 'framer-motion';
import { WF_COLORS } from './workflowConfigs';

export type EdgeStatus = 'pending' | 'active' | 'complete';

interface AnimationEdgeProps {
  fromX: number;
  fromY: number;
  toX: number;
  toY: number;
  status: EdgeStatus;
  color?: string;
  fromWidth?: number;
  fromHeight?: number;
  toWidth?: number;
  toHeight?: number;
}

const AnimationEdge: React.FC<AnimationEdgeProps> = ({
  fromX, fromY, toX, toY, status,
  color = WF_COLORS.amber,
  fromWidth = 140, fromHeight = 52,
  toWidth = 140, toHeight = 52,
}) => {
  const id = useId();

  // Determine if edge is primarily horizontal or vertical
  const dx = Math.abs(toX - fromX);
  const dy = Math.abs(toY - fromY);
  const horizontal = dx > dy;

  let pathD: string;

  if (horizontal) {
    // Horizontal: exit right side of source, enter left side of target
    const startX = fromX + fromWidth / 2;
    const startY = fromY;
    const endX = toX - toWidth / 2;
    const endY = toY;
    const cpOffset = (endX - startX) * 0.4;
    pathD = `M ${startX} ${startY} C ${startX + cpOffset} ${startY}, ${endX - cpOffset} ${endY}, ${endX} ${endY}`;
  } else {
    // Vertical: exit bottom of source, enter top of target
    const startX = fromX;
    const startY = fromY + fromHeight / 2;
    const endX = toX;
    const endY = toY - toHeight / 2;
    const cpOffset = (endY - startY) * 0.4;
    pathD = `M ${startX} ${startY} C ${startX} ${startY + cpOffset}, ${endX} ${endY - cpOffset}, ${endX} ${endY}`;
  }

  const strokeColor = status === 'pending' ? WF_COLORS.pendingStroke : color;
  const strokeOpacity = status === 'pending' ? 0.3 : 0.6;

  return (
    <g>
      <path
        d={pathD}
        fill="none"
        stroke={strokeColor}
        strokeWidth={1.5}
        strokeOpacity={strokeOpacity}
      />

      {status === 'active' && (
        <>
          <motion.circle
            r={3}
            fill={color}
            filter={`url(#particle-glow-${id})`}
            initial={{ offsetDistance: '0%' }}
            animate={{ offsetDistance: '100%' }}
            transition={{ duration: 1.2, repeat: Infinity, ease: 'linear' }}
            style={{ offsetPath: `path("${pathD}")` }}
          />
          <motion.circle
            r={2}
            fill={color}
            opacity={0.5}
            initial={{ offsetDistance: '0%' }}
            animate={{ offsetDistance: '100%' }}
            transition={{ duration: 1.2, repeat: Infinity, ease: 'linear', delay: 0.2 }}
            style={{ offsetPath: `path("${pathD}")` }}
          />
          <defs>
            <filter id={`particle-glow-${id}`} x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur in="SourceGraphic" stdDeviation="2" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
        </>
      )}

      {status === 'complete' && (
        <motion.path
          d={pathD}
          fill="none"
          stroke={color}
          strokeWidth={3}
          initial={{ pathLength: 0, opacity: 0.8 }}
          animate={{ pathLength: 1, opacity: 0 }}
          transition={{ duration: 0.8, ease: 'easeOut' }}
        />
      )}
    </g>
  );
};

export default AnimationEdge;
```

**Step 2: Run type check**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -40`

**Step 3: Commit**

```bash
git add frontend/src/components/HowItWorks/AnimationEdge.tsx
git commit -m "feat(workflow): horizontal/vertical smart bezier edges with amber default"
```

---

### Task 6: Create SpotlightPanel component

**Files:**
- Create: `frontend/src/components/HowItWorks/SpotlightPanel.tsx`

**Step 1: Create the SpotlightPanel**

```tsx
import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { DuckVariant, DuckState } from './DuckAvatar';
import { DuckSVGContent } from './DuckAvatar';
import { WF_COLORS } from './workflowConfigs';

interface SpotlightPanelProps {
  activeAgent: {
    duck: DuckVariant;
    name: string;
    subtitle: string;
    state: DuckState;
    progress: number; // 0-1
  } | null;
  isComplete: boolean;
}

const RING_R = 16;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_R;

const SpotlightPanel: React.FC<SpotlightPanelProps> = ({ activeAgent, isComplete }) => {
  // Determine what to show
  const duck: DuckVariant = isComplete
    ? 'supervisor'
    : activeAgent?.duck ?? 'supervisor';
  const name = isComplete
    ? 'Supervisor'
    : activeAgent?.name ?? 'Supervisor';
  const subtitle = isComplete
    ? 'Diagnosis Complete'
    : activeAgent?.subtitle ?? 'Processing...';
  const duckState: DuckState = isComplete
    ? 'done'
    : activeAgent?.state ?? 'working';
  const progress = isComplete ? 1 : (activeAgent?.progress ?? 0);

  const dashOffset = RING_CIRCUMFERENCE * (1 - progress);

  return (
    <div
      className="w-[200px] shrink-0 flex flex-col items-center justify-center gap-4 border-r"
      style={{
        backgroundColor: WF_COLORS.panelBg,
        borderColor: WF_COLORS.border,
      }}
    >
      {/* Large duck avatar */}
      <AnimatePresence mode="wait">
        <motion.div
          key={duck}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.3, ease: 'easeOut' }}
        >
          <svg width={80} height={80} viewBox="0 0 24 24" style={{ overflow: 'visible' }}>
            <DuckSVGContent variant={duck} state={duckState} />
          </svg>
        </motion.div>
      </AnimatePresence>

      {/* Progress ring */}
      <svg width={36} height={36} viewBox="-18 -18 36 36">
        <circle r={RING_R} fill="none" stroke={WF_COLORS.border} strokeWidth="2.5" />
        <circle
          r={RING_R}
          fill="none"
          stroke={isComplete ? WF_COLORS.green : WF_COLORS.amber}
          strokeWidth="2.5"
          strokeDasharray={RING_CIRCUMFERENCE}
          strokeDashoffset={dashOffset}
          strokeLinecap="round"
          transform="rotate(-90)"
          style={{ transition: 'stroke-dashoffset 0.3s ease' }}
        />
        {isComplete && (
          <text
            textAnchor="middle"
            dominantBaseline="central"
            fill={WF_COLORS.green}
            fontSize="12"
            fontFamily="DM Sans, system-ui"
          >
            ✓
          </text>
        )}
      </svg>

      {/* Role name */}
      <AnimatePresence mode="wait">
        <motion.div
          key={name}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.3 }}
          className="text-center px-3"
        >
          <div
            className="text-sm font-bold"
            style={{ color: WF_COLORS.labelText, fontFamily: 'DM Sans, Inter, system-ui, sans-serif' }}
          >
            {name}
          </div>
          <div
            className="text-[11px] mt-1"
            style={{ color: WF_COLORS.mutedText, fontFamily: 'Inter, system-ui, sans-serif' }}
          >
            {subtitle}
          </div>
        </motion.div>
      </AnimatePresence>
    </div>
  );
};

export default SpotlightPanel;
```

**Step 2: Run type check**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -40`

**Step 3: Commit**

```bash
git add frontend/src/components/HowItWorks/SpotlightPanel.tsx
git commit -m "feat(workflow): add SpotlightPanel with large duck avatar and progress ring"
```

---

### Task 7: Rewrite WorkflowAnimation with camera pan, phase dividers, and finale

**Files:**
- Modify: `frontend/src/components/HowItWorks/WorkflowAnimation.tsx`

This is the biggest change. The new WorkflowAnimation adds:
1. Camera pan system (translateX following active phase)
2. Phase divider labels
3. Finale sequence (sequential dimming + output labels)
4. SpotlightPanel integration
5. Reduced-motion static view
6. Dispatch pulse effect
7. Pass tier/accentColor to AnimationNode

**Step 1: Rewrite the entire WorkflowAnimation component**

Replace the entire file with:

```tsx
import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import type { WorkflowConfig, WorkflowNode } from './workflowConfigs';
import { WF_COLORS } from './workflowConfigs';
import type { NodeStatus } from './AnimationNode';
import type { EdgeStatus } from './AnimationEdge';
import AnimationNode from './AnimationNode';
import AnimationEdge from './AnimationEdge';
import PlaybackBar from './PlaybackBar';
import SpotlightPanel from './SpotlightPanel';

// Tier-based dimensions for edge connection points
const TIER_DIMS: Record<string, { width: number; height: number }> = {
  landmark: { width: 180, height: 64 },
  agent:    { width: 150, height: 56 },
  pipeline: { width: 130, height: 44 },
};

interface WorkflowAnimationProps {
  config: WorkflowConfig;
}

const WorkflowAnimation: React.FC<WorkflowAnimationProps> = ({ config }) => {
  const [elapsed, setElapsed] = useState(0);
  const [isPlaying, setIsPlaying] = useState(true);
  const rafRef = useRef<number | null>(null);
  const lastTickRef = useRef<number | null>(null);
  const doneRef = useRef(false);
  const prefersReducedMotion = useReducedMotion();

  // ─── Animation loop ───
  useEffect(() => {
    if (!isPlaying || prefersReducedMotion) {
      lastTickRef.current = null;
      return;
    }

    const tick = (timestamp: number) => {
      if (lastTickRef.current === null) {
        lastTickRef.current = timestamp;
      }
      const delta = (timestamp - lastTickRef.current) / 1000;
      lastTickRef.current = timestamp;

      setElapsed((prev) => {
        const next = prev + delta;
        if (next >= config.totalDuration) {
          doneRef.current = true;
          setIsPlaying(false);
          return config.totalDuration;
        }
        return next;
      });

      if (!doneRef.current) {
        rafRef.current = requestAnimationFrame(tick);
      }
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [isPlaying, config.totalDuration, prefersReducedMotion]);

  // If reduced motion, jump to end
  useEffect(() => {
    if (prefersReducedMotion) {
      setElapsed(config.totalDuration);
      setIsPlaying(false);
      doneRef.current = true;
    }
  }, [prefersReducedMotion, config.totalDuration]);

  const handlePlayPause = useCallback(() => {
    if (elapsed >= config.totalDuration) {
      setElapsed(0);
      doneRef.current = false;
      setIsPlaying(true);
    } else {
      setIsPlaying((p) => !p);
    }
  }, [elapsed, config.totalDuration]);

  const handleReset = useCallback(() => {
    setElapsed(0);
    setIsPlaying(false);
    lastTickRef.current = null;
    doneRef.current = false;
  }, []);

  const handleSeek = useCallback((time: number) => {
    setElapsed(Math.max(0, Math.min(time, config.totalDuration)));
    lastTickRef.current = null;
  }, [config.totalDuration]);

  // ─── Current phase ───
  const currentPhase = useMemo(() => {
    for (let i = config.phases.length - 1; i >= 0; i--) {
      if (elapsed >= config.phases[i].startTime) return config.phases[i];
    }
    return config.phases[0];
  }, [elapsed, config.phases]);

  // ─── Node statuses ───
  const nodeStatuses = useMemo(() => {
    const statuses: Record<string, { status: NodeStatus; progress: number }> = {};
    for (const node of config.nodes) {
      statuses[node.id] = { status: 'pending', progress: 0 };
    }

    for (const phase of config.phases) {
      const phaseStart = phase.startTime;
      const phaseEnd = phase.startTime + phase.duration;
      if (elapsed < phaseStart) continue;

      const phasePct = Math.min((elapsed - phaseStart) / phase.duration, 1);

      if (phase.parallel) {
        for (const nodeId of phase.activateNodes) {
          statuses[nodeId] = elapsed >= phaseEnd
            ? { status: 'complete', progress: 1 }
            : { status: 'active', progress: phasePct };
        }
      } else {
        const nodeCount = phase.activateNodes.length;
        if (nodeCount === 0) continue;
        const perNode = phase.duration / nodeCount;
        for (let i = 0; i < nodeCount; i++) {
          const nodeStart = phaseStart + i * perNode;
          const nodeEnd = nodeStart + perNode;
          const nodeId = phase.activateNodes[i];
          if (elapsed >= nodeEnd) {
            statuses[nodeId] = { status: 'complete', progress: 1 };
          } else if (elapsed >= nodeStart) {
            statuses[nodeId] = { status: 'active', progress: (elapsed - nodeStart) / perNode };
          }
        }
      }
    }
    return statuses;
  }, [elapsed, config]);

  // ─── Edge statuses ───
  const edgeStatuses = useMemo(() => {
    const statuses: Record<string, EdgeStatus> = {};
    for (const edge of config.edges) {
      statuses[`${edge.from}->${edge.to}`] = 'pending';
    }

    for (const phase of config.phases) {
      if (elapsed < phase.startTime) continue;
      const phaseEnd = phase.startTime + phase.duration;
      const edgeCount = phase.activateEdges.length;
      if (edgeCount === 0) continue;

      if (phase.parallel) {
        for (const [from, to] of phase.activateEdges) {
          statuses[`${from}->${to}`] = elapsed >= phaseEnd ? 'complete' : 'active';
        }
      } else {
        const perEdge = phase.duration / edgeCount;
        for (let i = 0; i < edgeCount; i++) {
          const [from, to] = phase.activateEdges[i];
          const edgeStart = phase.startTime + i * perEdge;
          const edgeEnd = edgeStart + perEdge;
          if (elapsed >= edgeEnd) {
            statuses[`${from}->${to}`] = 'complete';
          } else if (elapsed >= edgeStart) {
            statuses[`${from}->${to}`] = 'active';
          }
        }
      }
    }
    return statuses;
  }, [elapsed, config]);

  // ─── Node position lookup ───
  const nodeMap = useMemo(() => {
    const map: Record<string, WorkflowNode> = {};
    for (const n of config.nodes) map[n.id] = n;
    return map;
  }, [config.nodes]);

  // ─── Camera position ───
  // Camera centers on the active phase column, showing ~500px window
  const VIEWPORT_WIDTH = 500;
  const cameraX = useMemo(() => {
    const col = currentPhase.phaseColumn;
    if (col === undefined) return 0;
    // Center viewport on phase column
    return Math.max(0, Math.min(col - VIEWPORT_WIDTH / 2, config.viewBoxWidth - VIEWPORT_WIDTH));
  }, [currentPhase, config.viewBoxWidth]);

  // ─── Active agent for spotlight ───
  const activeAgent = useMemo(() => {
    // Find the currently active node that's an agent or landmark
    for (const node of config.nodes) {
      const ns = nodeStatuses[node.id];
      if (ns?.status === 'active' && (node.tier === 'agent' || node.tier === 'landmark')) {
        return {
          duck: node.duck,
          name: node.label,
          subtitle: node.subtitle ?? 'Processing...',
          state: 'working' as const,
          progress: ns.progress,
        };
      }
    }
    return null;
  }, [nodeStatuses, config.nodes]);

  // ─── Finale state ───
  const isFinale = elapsed >= config.totalDuration;
  const finaleProgress = useMemo(() => {
    const lastPhase = config.phases[config.phases.length - 1];
    if (!lastPhase || elapsed < lastPhase.startTime) return 0;
    return Math.min((elapsed - lastPhase.startTime) / lastPhase.duration, 1);
  }, [elapsed, config.phases]);

  // How many nodes should be dimmed (left-to-right sequential dimming during finale)
  const dimmedCount = useMemo(() => {
    if (!isFinale) return 0;
    return config.nodes.length; // All dimmed except report
  }, [isFinale, config.nodes.length]);

  // ─── Dispatch pulse: detect when dispatch/supervisor activates agents ───
  const showDispatchPulse = useMemo(() => {
    // Find the "Domain Agents" or "Parallel Analysis" phase
    const fanPhase = config.phases.find(p => p.parallel && p.activateNodes.length > 2);
    if (!fanPhase) return null;
    const pulseStart = fanPhase.startTime;
    if (elapsed >= pulseStart && elapsed < pulseStart + 0.8) {
      // Find the dispatch/source node
      const sourceEdge = fanPhase.activateEdges[0];
      if (!sourceEdge) return null;
      const sourceNode = nodeMap[sourceEdge[0]];
      if (!sourceNode) return null;
      return { x: sourceNode.x, y: sourceNode.y, progress: (elapsed - pulseStart) / 0.8 };
    }
    return null;
  }, [elapsed, config.phases, nodeMap]);

  // ─── Phase divider positions ───
  const phaseDividers = useMemo(() => {
    const dividers: { x: number; label: string }[] = [];
    const seen = new Set<number>();
    for (const phase of config.phases) {
      if (phase.phaseColumn && !seen.has(phase.phaseColumn)) {
        seen.add(phase.phaseColumn);
        dividers.push({ x: phase.phaseColumn, label: phase.name.toUpperCase() });
      }
    }
    // Add divider lines between columns (midpoints)
    return dividers;
  }, [config.phases]);

  // SVG viewBox
  const viewBox = `0 0 ${config.viewBoxWidth} ${config.viewBoxHeight}`;

  // ─── Reduced motion: static view ───
  if (prefersReducedMotion) {
    return (
      <div className="flex h-full">
        <div className="flex-1 overflow-auto p-4" style={{ backgroundColor: WF_COLORS.pageBg }}>
          <svg
            width="100%"
            height="100%"
            viewBox={viewBox}
            preserveAspectRatio="xMidYMid meet"
          >
            {/* Phase labels */}
            {phaseDividers.map((d) => (
              <text
                key={d.x}
                x={d.x}
                y={20}
                textAnchor="middle"
                fill={WF_COLORS.mutedText}
                fontSize="9"
                fontWeight="700"
                fontFamily="DM Sans, system-ui"
                letterSpacing="0.1em"
              >
                {d.label}
              </text>
            ))}

            {/* All edges in complete state */}
            {config.edges.map((edge) => {
              const from = nodeMap[edge.from];
              const to = nodeMap[edge.to];
              if (!from || !to) return null;
              const fromDims = TIER_DIMS[from.tier];
              const toDims = TIER_DIMS[to.tier];
              return (
                <AnimationEdge
                  key={`${edge.from}->${edge.to}`}
                  fromX={from.x} fromY={from.y}
                  toX={to.x} toY={to.y}
                  status="complete"
                  color={edge.color ?? WF_COLORS.amber}
                  fromWidth={fromDims.width} fromHeight={fromDims.height}
                  toWidth={toDims.width} toHeight={toDims.height}
                />
              );
            })}

            {/* All nodes in complete state */}
            {config.nodes.map((node) => (
              <AnimationNode
                key={node.id}
                id={node.id}
                label={node.label}
                duck={node.duck}
                x={node.x} y={node.y}
                tier={node.tier}
                status="complete"
                progress={1}
                subtitle={node.subtitle}
                badge={node.badge}
                accentColor={node.accentColor}
              />
            ))}

            {/* Output labels for report nodes */}
            {config.nodes
              .filter(n => n.outputLabels)
              .map(n => n.outputLabels!.map((label, i) => (
                <text
                  key={`${n.id}-out-${i}`}
                  x={n.x}
                  y={n.y + 50 + i * 18}
                  textAnchor="middle"
                  fill={WF_COLORS.amber}
                  fontSize="10"
                  fontWeight="600"
                  fontFamily="DM Sans, system-ui"
                >
                  {label}
                </text>
              )))}
          </svg>
        </div>
      </div>
    );
  }

  // ─── Animated view ───
  return (
    <div className="flex h-full">
      {/* Spotlight panel */}
      <SpotlightPanel activeAgent={activeAgent} isComplete={isFinale} />

      {/* SVG Canvas with camera pan */}
      <div className="flex-1 flex flex-col overflow-hidden" style={{ backgroundColor: WF_COLORS.pageBg }}>
        <div className="flex-1 overflow-hidden relative">
          <motion.div
            className="h-full"
            animate={{ x: -cameraX }}
            transition={{ type: 'tween', duration: 0.8, ease: [0.25, 0.1, 0.25, 1] }}
            style={{ width: config.viewBoxWidth }}
          >
            <svg
              width={config.viewBoxWidth}
              height="100%"
              viewBox={viewBox}
              preserveAspectRatio="xMidYMid meet"
              className="h-full"
            >
              {/* Glow filter */}
              <defs>
                <filter id="node-glow" x="-50%" y="-50%" width="200%" height="200%">
                  <feGaussianBlur in="SourceAlpha" stdDeviation="4" result="blur" />
                  <feFlood floodColor={WF_COLORS.amber} floodOpacity="0.3" result="color" />
                  <feComposite in="color" in2="blur" operator="in" result="glow" />
                  <feMerge>
                    <feMergeNode in="glow" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
              </defs>

              {/* Phase divider lines and labels */}
              {phaseDividers.map((d, i) => {
                // Draw dashed line between phases (at midpoint between this and next column)
                const nextX = phaseDividers[i + 1]?.x;
                const dividerX = nextX ? (d.x + nextX) / 2 : undefined;
                return (
                  <g key={d.x}>
                    {/* Phase label */}
                    <text
                      x={d.x}
                      y={25}
                      textAnchor="middle"
                      fill={WF_COLORS.mutedText}
                      fontSize="9"
                      fontWeight="700"
                      fontFamily="DM Sans, system-ui"
                      letterSpacing="0.1em"
                      opacity={0.6}
                    >
                      {d.label}
                    </text>
                    {/* Vertical dashed divider */}
                    {dividerX && (
                      <line
                        x1={dividerX}
                        y1={35}
                        x2={dividerX}
                        y2={config.viewBoxHeight - 10}
                        stroke={WF_COLORS.border}
                        strokeWidth={1}
                        strokeDasharray="4 4"
                        opacity={0.4}
                      />
                    )}
                  </g>
                );
              })}

              {/* Dispatch pulse effect */}
              {showDispatchPulse && (
                <motion.circle
                  cx={showDispatchPulse.x}
                  cy={showDispatchPulse.y}
                  fill="none"
                  stroke={WF_COLORS.amber}
                  strokeWidth={2}
                  initial={{ r: 10, opacity: 0.8 }}
                  animate={{ r: 120, opacity: 0 }}
                  transition={{ duration: 0.8, ease: 'easeOut' }}
                />
              )}

              {/* Edges */}
              {config.edges.map((edge) => {
                const from = nodeMap[edge.from];
                const to = nodeMap[edge.to];
                if (!from || !to) return null;
                const key = `${edge.from}->${edge.to}`;
                const fromDims = TIER_DIMS[from.tier];
                const toDims = TIER_DIMS[to.tier];
                return (
                  <AnimationEdge
                    key={key}
                    fromX={from.x} fromY={from.y}
                    toX={to.x} toY={to.y}
                    status={edgeStatuses[key] || 'pending'}
                    color={edge.color}
                    fromWidth={fromDims.width} fromHeight={fromDims.height}
                    toWidth={toDims.width} toHeight={toDims.height}
                  />
                );
              })}

              {/* Nodes */}
              {config.nodes.map((node) => {
                const ns = nodeStatuses[node.id] || { status: 'pending' as const, progress: 0 };
                const isDimmed = isFinale && !node.id.includes('report');
                return (
                  <AnimationNode
                    key={node.id}
                    id={node.id}
                    label={node.label}
                    duck={node.duck}
                    x={node.x} y={node.y}
                    tier={node.tier}
                    status={ns.status}
                    progress={ns.progress}
                    subtitle={node.subtitle}
                    badge={node.badge}
                    accentColor={node.accentColor}
                    dimmed={isDimmed}
                  />
                );
              })}

              {/* Finale: output labels */}
              {isFinale && config.nodes
                .filter(n => n.outputLabels)
                .map(n => n.outputLabels!.map((label, i) => (
                  <motion.text
                    key={`${n.id}-out-${i}`}
                    x={n.x}
                    y={n.y + 55 + i * 20}
                    textAnchor="middle"
                    fill={WF_COLORS.amber}
                    fontSize="10"
                    fontWeight="600"
                    fontFamily="DM Sans, system-ui"
                    initial={{ opacity: 0, y: n.y + 60 + i * 20 }}
                    animate={{ opacity: 1, y: n.y + 55 + i * 20 }}
                    transition={{ type: 'spring', stiffness: 200, delay: 0.3 + i * 0.15 }}
                  >
                    {label}
                  </motion.text>
                )))}

              {/* Finale: "Diagnosis Complete" label */}
              {isFinale && (() => {
                const reportNode = config.nodes.find(n => n.id.includes('report'));
                if (!reportNode || !reportNode.outputLabels) return null;
                const yOffset = reportNode.y + 55 + reportNode.outputLabels.length * 20 + 15;
                return (
                  <motion.text
                    x={reportNode.x}
                    y={yOffset}
                    textAnchor="middle"
                    fill={WF_COLORS.amber}
                    fontSize="12"
                    fontWeight="700"
                    fontFamily="DM Sans, system-ui"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 1.0 }}
                  >
                    Diagnosis Complete
                  </motion.text>
                );
              })()}
            </svg>
          </motion.div>
        </div>

        {/* Playback bar */}
        <PlaybackBar
          isPlaying={isPlaying}
          elapsed={elapsed}
          totalDuration={config.totalDuration}
          phaseName={currentPhase.name}
          phaseDescription={currentPhase.description}
          onPlayPause={handlePlayPause}
          onReset={handleReset}
          onSeek={handleSeek}
        />
      </div>
    </div>
  );
};

export default WorkflowAnimation;
```

**Step 2: Run type check**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -40`
Expected: Should be clean or minimal issues.

**Step 3: Commit**

```bash
git add frontend/src/components/HowItWorks/WorkflowAnimation.tsx
git commit -m "feat(workflow): camera pan, phase dividers, spotlight integration, finale sequence, reduced-motion"
```

---

### Task 8: Update PlaybackBar colors to amber

**Files:**
- Modify: `frontend/src/components/HowItWorks/PlaybackBar.tsx`

**Step 1: Replace all cyan references with amber**

Update these specific values throughout the file:

| Old | New |
|-----|-----|
| `bg-[#0a1a1f]` | `bg-[#161310]` |
| `border-slate-800` | style `borderColor: '#3d3528'` |
| `text-[#07b6d5]` | `text-[#e09f3e]` |
| `bg-[#07b6d5]/10` | `bg-[#e09f3e]/10` |
| `border-[#07b6d5]/30` | `border-[#e09f3e]/30` |
| `bg-[#07b6d5]` | `bg-[#e09f3e]` |
| `shadow-[0_0_6px_#07b6d5]` | `shadow-[0_0_6px_#e09f3e]` |
| `border-[#0f2023]` | `border-[#1a1814]` |
| `hover:bg-[#07b6d5]/20` | `hover:bg-[#e09f3e]/20` |

Replace the entire file with:

```tsx
import React from 'react';
import { WF_COLORS } from './workflowConfigs';

interface PlaybackBarProps {
  isPlaying: boolean;
  elapsed: number;
  totalDuration: number;
  phaseName: string;
  phaseDescription: string;
  onPlayPause: () => void;
  onReset: () => void;
  onSeek: (time: number) => void;
}

const formatTime = (s: number) => {
  const mins = Math.floor(s / 60);
  const secs = Math.floor(s % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
};

const PlaybackBar: React.FC<PlaybackBarProps> = ({
  isPlaying, elapsed, totalDuration, phaseName, phaseDescription,
  onPlayPause, onReset, onSeek,
}) => {
  const progress = totalDuration > 0 ? (elapsed / totalDuration) * 100 : 0;

  return (
    <div
      className="px-6 py-4 shrink-0 border-t"
      style={{ backgroundColor: WF_COLORS.panelBg, borderColor: WF_COLORS.border }}
    >
      {/* Phase info */}
      <div className="flex items-center gap-3 mb-3">
        <span
          className="text-[10px] uppercase tracking-widest font-bold"
          style={{ color: WF_COLORS.amber, fontFamily: 'DM Sans, system-ui' }}
        >
          {phaseName}
        </span>
        <span className="text-xs" style={{ color: WF_COLORS.mutedText }}>
          {phaseDescription}
        </span>
      </div>

      {/* Controls + timeline */}
      <div className="flex items-center gap-4">
        {/* Play/Pause */}
        <button
          onClick={onPlayPause}
          className="w-8 h-8 rounded-full bg-[#e09f3e]/10 border border-[#e09f3e]/30 flex items-center justify-center hover:bg-[#e09f3e]/20 transition-colors"
          aria-label={isPlaying ? 'Pause' : 'Play'}
        >
          <span className="material-symbols-outlined text-sm" style={{ color: WF_COLORS.amber }}>
            {isPlaying ? 'pause' : 'play_arrow'}
          </span>
        </button>

        {/* Reset */}
        <button
          onClick={onReset}
          className="w-8 h-8 rounded-full flex items-center justify-center hover:opacity-80 transition-opacity"
          style={{ backgroundColor: WF_COLORS.cardBg, border: `1px solid ${WF_COLORS.border}` }}
          aria-label="Reset"
        >
          <span className="material-symbols-outlined text-sm" style={{ color: WF_COLORS.mutedText }}>
            replay
          </span>
        </button>

        {/* Timeline scrubber */}
        <div
          className="flex-1 relative h-1.5 rounded-full cursor-pointer group"
          style={{ backgroundColor: WF_COLORS.cardBg }}
          onClick={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const pct = (e.clientX - rect.left) / rect.width;
            onSeek(pct * totalDuration);
          }}
        >
          <div
            className="absolute inset-y-0 left-0 rounded-full transition-all duration-100"
            style={{ width: `${progress}%`, backgroundColor: WF_COLORS.amber }}
          />
          <div
            className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
            style={{
              left: `${progress}%`,
              transform: 'translate(-50%, -50%)',
              backgroundColor: WF_COLORS.amber,
              border: `2px solid ${WF_COLORS.pageBg}`,
              boxShadow: `0 0 6px ${WF_COLORS.amber}`,
            }}
          />
        </div>

        {/* Time display */}
        <span
          className="text-xs font-mono w-20 text-right"
          style={{ color: WF_COLORS.mutedText }}
        >
          {formatTime(elapsed)} / {formatTime(totalDuration)}
        </span>
      </div>
    </div>
  );
};

export default PlaybackBar;
```

**Step 2: Run type check**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -40`

**Step 3: Commit**

```bash
git add frontend/src/components/HowItWorks/PlaybackBar.tsx
git commit -m "feat(workflow): PlaybackBar amber color palette and DM Sans font"
```

---

### Task 9: Update HowItWorksView with amber palette and layout

**Files:**
- Modify: `frontend/src/components/HowItWorks/HowItWorksView.tsx`

**Step 1: Rewrite HowItWorksView**

Replace the entire file with:

```tsx
import React, { useState } from 'react';
import WorkflowAnimation from './WorkflowAnimation';
import { clusterConfig, appConfig, WF_COLORS } from './workflowConfigs';

interface HowItWorksViewProps {
  onGoHome: () => void;
}

type Tab = 'cluster' | 'app';

const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: 'cluster', label: 'Cluster Diagnostics', icon: 'deployed_code' },
  { id: 'app',     label: 'App Diagnostics',     icon: 'bug_report' },
];

const HowItWorksView: React.FC<HowItWorksViewProps> = ({ onGoHome }) => {
  const [activeTab, setActiveTab] = useState<Tab>('cluster');

  return (
    <div className="flex flex-col h-full" style={{ backgroundColor: WF_COLORS.pageBg, color: WF_COLORS.labelText }}>
      {/* Header */}
      <header
        className="h-14 flex items-center justify-between px-6 shrink-0 border-b"
        style={{ backgroundColor: WF_COLORS.panelBg, borderColor: WF_COLORS.border }}
      >
        <div className="flex items-center gap-4">
          <button
            onClick={onGoHome}
            className="hover:opacity-80 transition-opacity"
            style={{ color: WF_COLORS.mutedText }}
            aria-label="Back to home"
          >
            <span className="material-symbols-outlined">arrow_back</span>
          </button>
          <h1
            className="text-xl font-bold text-white"
            style={{ fontFamily: 'DM Sans, Inter, system-ui, sans-serif' }}
          >
            How It Works
          </h1>
        </div>

        {/* Tabs */}
        <div
          className="flex gap-1 rounded-lg p-1 border"
          style={{ backgroundColor: WF_COLORS.pageBg, borderColor: WF_COLORS.border }}
        >
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-1.5 rounded-md text-xs font-bold transition-all`}
              style={activeTab === tab.id
                ? { backgroundColor: `${WF_COLORS.amber}15`, color: WF_COLORS.amber, border: `1px solid ${WF_COLORS.amber}4d` }
                : { color: WF_COLORS.mutedText, border: '1px solid transparent' }
              }
            >
              <span className="material-symbols-outlined text-sm">{tab.icon}</span>
              {tab.label}
            </button>
          ))}
        </div>

        <div className="w-24" />
      </header>

      {/* Animation canvas */}
      <div className="flex-1 overflow-hidden">
        {activeTab === 'cluster' && <WorkflowAnimation key="cluster" config={clusterConfig} />}
        {activeTab === 'app' && <WorkflowAnimation key="app" config={appConfig} />}
      </div>
    </div>
  );
};

export default HowItWorksView;
```

**Step 2: Run type check**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -40`

**Step 3: Commit**

```bash
git add frontend/src/components/HowItWorks/HowItWorksView.tsx
git commit -m "feat(workflow): HowItWorksView amber palette, white title, DM Sans"
```

---

### Task 10: Build verification and visual smoke test

**Files:**
- No new files

**Step 1: Run TypeScript type check**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -60`
Expected: Clean compilation (0 errors).

**Step 2: Run build**

Run: `cd frontend && npx vite build 2>&1 | tail -20`
Expected: Build succeeds.

**Step 3: Run dev server and verify**

Run: `cd frontend && npx vite --port 5174 &`

Open browser and verify:
- Navigate to How It Works page
- Cluster tab: horizontal flow, camera pans left to right
- Spotlight panel on left with large duck
- Nodes have three different sizes (landmark > agent > pipeline)
- Agent nodes have colored left accent bars
- All colors are amber (no cyan anywhere)
- Playback bar uses amber accent
- Phase labels visible above columns
- Finale: nodes dim, report node amber burst, output labels appear
- Tab switching: App tab works similarly
- Title says "How It Works" in white (no partial cyan)

**Step 4: Stop dev server**

**Step 5: Final commit if any fixes needed**

```bash
git add -u
git commit -m "fix(workflow): build verification fixes"
```

---

## Summary of Changes

| File | Action | Description |
|------|--------|-------------|
| `workflowConfigs.ts` | Rewrite | Interfaces + horizontal configs with tier, outputLabels, viewBox |
| `AnimationNode.tsx` | Rewrite | Three-tier sizing, pure SVG ducks, left accent bar, dimming |
| `DuckAvatar.tsx` | Modify | Add `DuckSVGContent` export, update colors to amber |
| `AnimationEdge.tsx` | Rewrite | Smart horizontal/vertical bezier curves, amber default |
| `SpotlightPanel.tsx` | Create | 200px left panel with large duck, progress ring, crossfade |
| `WorkflowAnimation.tsx` | Rewrite | Camera pan, phase dividers, dispatch pulse, finale, reduced-motion |
| `PlaybackBar.tsx` | Rewrite | Amber colors, DM Sans font, warm backgrounds |
| `HowItWorksView.tsx` | Rewrite | Amber palette, white title, warm backgrounds |
