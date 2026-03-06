# Phase 2: War Room Enhancement — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Solve the "Wall of Text" problem in the Investigation view. Implement progressive disclosure, causal tree grouping with visual tethers, enhanced recommendation blocks, and loading polish.

**Architecture:** Enhance existing Investigation components (CausalTreeCard, AgentFindingCard, RecommendationCard, EvidenceFindings) rather than replacing them. Add 1 new component (EvidenceStackGroup). All changes scoped to `frontend/src/components/Investigation/` and `frontend/src/index.css`.

**Tech Stack:** React 18, TypeScript, Tailwind CSS, Material Symbols Outlined icons. No new dependencies.

**IMPORTANT:** Do NOT modify any files outside the Investigation directory or index.css. Shared components from Phase 1 (`SparklineWidget`, `StatusBadge`, `SkeletonLoader`) are imported from `../shared`.

---

## Existing Code Context

**Key types (in `frontend/src/types/index.ts`):**
- `CausalTree` (line 1155): `{ id, root_cause: Finding, severity, blast_radius, cascading_symptoms: Finding[], correlated_signals: CorrelatedSignalGroup[], operational_recommendations: OperationalRecommendation[], triage_status, resource_refs }`
- `Finding` (line 236): `{ finding_id, agent_name, category, summary, title, description, severity, confidence_score, confidence, evidence, suggested_fix?, resource_refs? }`
- `OperationalRecommendation` (line 1140): `{ id, title, urgency, category, commands: CommandStep[], rollback_commands, risk_level, prerequisites, expected_outcome, resource_refs }`
- `CommandStep` (line 1130): `{ order, description, command, command_type, is_dry_run, dry_run_command, validation_command }`
- `CausalRole` (line 1096): `'root_cause' | 'cascading_symptom' | 'correlated' | 'informational'`
- `ErrorPattern` (line 93): has `causal_role?: 'root_cause' | 'cascading_failure' | 'correlated_anomaly'`

**Key existing components:**
- `CausalTreeCard.tsx`: Already shows root cause + cascading + correlated + recommendations. We enhance it.
- `CausalForestView.tsx`: Renders list of CausalTreeCards. We replace its child with EvidenceStackGroup.
- `AgentFindingCard.tsx`: Simple wrapper (agent badge + title + children). We add optional progressive disclosure.
- `RecommendationCard.tsx`: Already has dry-run toggle, command blocks, rollback. We enhance terminal styling.
- `CausalRoleBadge.tsx`: Badge for root_cause/cascading_failure/correlated_anomaly. Already complete.
- `EvidenceFindings.tsx`: 1150+ line center column. We add skeleton loading and use EvidenceStackGroup.

**CSS classes already available (in `frontend/src/index.css`):**
- `.card-border-L/M/K/C/D` — agent left borders
- `.animate-pulse-red` — red glow pulse
- `.finding-glow-red` / `.finding-glow-amber` — inset glow animations
- `.animate-border-pulse-amber` / `.animate-border-pulse-green` — border pulse

---

## Task 1: EvidenceStackGroup — Causal Tree with Visual Tethers

**Files:**
- Create: `frontend/src/components/Investigation/cards/EvidenceStackGroup.tsx`

**What it does:** Wraps a `CausalTree` object and renders it as a visually grouped hierarchy — root cause card at top (always visible, red-tinted), cascading symptoms and correlated signals indented below with dashed SVG tether lines. Toggle button to show/hide child findings.

**Step 1: Create the component**

```tsx
// frontend/src/components/Investigation/cards/EvidenceStackGroup.tsx
import React, { useState, useCallback } from 'react';
import type { CausalTree, Finding, TriageStatus, CorrelatedSignalGroup } from '../../../types';
import { updateTriageStatus } from '../../../services/api';
import { parseResourceEntities } from '../../../utils/parseResourceEntities';
import { useTelescopeContext } from '../../../contexts/TelescopeContext';
import CausalRoleBadge from './CausalRoleBadge';
import RecommendationCard from './RecommendationCard';

interface EvidenceStackGroupProps {
  tree: CausalTree;
  sessionId: string;
  onTriageUpdate?: (treeId: string, status: TriageStatus) => void;
}

const TRIAGE_SEQUENCE: TriageStatus[] = ['untriaged', 'acknowledged', 'mitigated', 'resolved'];
const TRIAGE_STYLES: Record<TriageStatus, string> = {
  untriaged: 'text-red-400 bg-red-950/30',
  acknowledged: 'text-amber-400 bg-amber-950/30',
  mitigated: 'text-cyan-400 bg-cyan-950/30',
  resolved: 'text-emerald-400 bg-emerald-950/30',
};

const EvidenceStackGroup: React.FC<EvidenceStackGroupProps> = ({ tree, sessionId, onTriageUpdate }) => {
  const [showImpact, setShowImpact] = useState(true);
  const [triage, setTriage] = useState<TriageStatus>(tree.triage_status);
  const { openTelescope } = useTelescopeContext();

  const handleEntityClick = useCallback((kind: string, name: string, namespace: string | null) => {
    openTelescope({ kind, name, namespace: namespace || 'default' });
  }, [openTelescope]);

  const cycleTriage = useCallback(async () => {
    const currentIdx = TRIAGE_SEQUENCE.indexOf(triage);
    const nextStatus = TRIAGE_SEQUENCE[(currentIdx + 1) % TRIAGE_SEQUENCE.length];
    setTriage(nextStatus);
    onTriageUpdate?.(tree.id, nextStatus);
    try {
      await updateTriageStatus(sessionId, tree.id, nextStatus);
    } catch { /* optimistic update */ }
  }, [triage, tree.id, sessionId, onTriageUpdate]);

  const childCount = tree.cascading_symptoms.length + tree.correlated_signals.length;
  const blastCount = tree.blast_radius
    ? (tree.blast_radius.upstream_affected?.length || 0) + (tree.blast_radius.downstream_affected?.length || 0)
    : 0;

  return (
    <div className="space-y-0">
      {/* ── Root Cause Card (always visible) ── */}
      <div
        className="relative rounded-lg overflow-hidden border border-[#ef4444]/40 bg-[#ef4444]/5"
        style={{ boxShadow: '0 0 15px rgba(239,68,68,0.1)' }}
      >
        {/* Pulsing left border */}
        <div className="absolute left-0 top-0 bottom-0 w-1 bg-[#ef4444] animate-pulse" />

        <div className="pl-4 pr-3 py-3 space-y-2">
          {/* Header row */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 flex-1 min-w-0">
              <CausalRoleBadge role="root_cause" />
              <span className="text-[11px] font-medium text-slate-200 truncate">
                {parseResourceEntities(tree.root_cause.title || tree.root_cause.summary, handleEntityClick)}
              </span>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {blastCount > 0 && (
                <span className="text-[9px] text-amber-400 bg-amber-950/30 px-1.5 py-0.5 rounded font-mono">
                  {blastCount} affected
                </span>
              )}
              <button
                onClick={(e) => { e.stopPropagation(); cycleTriage(); }}
                className={`text-[9px] font-bold px-2 py-0.5 rounded uppercase tracking-wider ${TRIAGE_STYLES[triage]}`}
              >
                {triage.replace('_', ' ')}
              </button>
            </div>
          </div>

          {/* Description */}
          <div className="text-[10px] text-slate-400 leading-relaxed">
            {parseResourceEntities(tree.root_cause.description || tree.root_cause.summary, handleEntityClick)}
          </div>

          {/* Resource refs as clickable pills */}
          {tree.root_cause.resource_refs && tree.root_cause.resource_refs.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {tree.root_cause.resource_refs.map((ref, i) => (
                <button
                  key={i}
                  onClick={() => handleEntityClick(ref.kind, ref.name, ref.namespace ?? null)}
                  className="text-[9px] px-2 py-0.5 rounded-full bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 hover:bg-cyan-500/20 transition-colors"
                >
                  {ref.kind}/{ref.name}
                </button>
              ))}
            </div>
          )}

          {/* Operational Recommendations (inside root cause card) */}
          {tree.operational_recommendations.length > 0 && (
            <div className="space-y-2 pt-1 border-t border-slate-800/40">
              <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">Recommendations</span>
              {tree.operational_recommendations.map(rec => (
                <RecommendationCard key={rec.id} recommendation={rec} />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Impact Toggle ── */}
      {childCount > 0 && (
        <div className="flex items-center pl-4 py-1">
          {/* Vertical tether line */}
          <div className="w-px h-4 border-l border-dashed border-slate-700/60 ml-1" />
          <button
            onClick={() => setShowImpact(!showImpact)}
            className="ml-3 text-[9px] font-bold text-slate-500 hover:text-slate-300 uppercase tracking-wider transition-colors flex items-center gap-1"
          >
            <span className="material-symbols-outlined text-[14px]" style={{ fontFamily: 'Material Symbols Outlined' }}>
              {showImpact ? 'expand_less' : 'expand_more'}
            </span>
            {showImpact ? 'HIDE IMPACT' : `SHOW IMPACT (${childCount})`}
          </button>
        </div>
      )}

      {/* ── Cascading Symptoms + Correlated Signals ── */}
      {showImpact && childCount > 0 && (
        <div className="relative pl-8">
          {/* Vertical tether line */}
          <div className="absolute left-[9px] top-0 bottom-2 border-l border-dashed border-slate-700/40" />

          {/* Cascading symptoms */}
          {tree.cascading_symptoms.map((symptom, i) => (
            <div key={symptom.finding_id || i} className="relative mb-2">
              {/* Horizontal elbow connector */}
              <div className="absolute -left-[23px] top-4 w-[23px] border-t border-dashed border-slate-700/40" />

              <div className="rounded-lg border border-[#224349] bg-slate-900/30 px-3 py-2.5 space-y-1">
                <div className="flex items-center gap-2">
                  <CausalRoleBadge role="cascading_failure" />
                  <span className="text-[10px] text-slate-300 truncate">
                    {parseResourceEntities(symptom.title || symptom.summary, handleEntityClick)}
                  </span>
                </div>
                {symptom.description && symptom.description !== symptom.summary && (
                  <div className="text-[9px] text-slate-500 pl-1">
                    {parseResourceEntities(symptom.description, handleEntityClick)}
                  </div>
                )}
              </div>
            </div>
          ))}

          {/* Correlated signals */}
          {tree.correlated_signals.map((sig, i) => (
            <div key={sig.group_name || i} className="relative mb-2 opacity-70">
              {/* Horizontal elbow connector */}
              <div className="absolute -left-[23px] top-4 w-[23px] border-t border-dashed border-cyan-500/20" />

              <div className="rounded-lg border border-cyan-500/20 bg-slate-900/20 px-3 py-2.5">
                <div className="flex items-center gap-2">
                  <CausalRoleBadge role="correlated_anomaly" />
                  <span className="text-[10px] text-slate-400">
                    <span className="text-cyan-400">{sig.group_name}</span>
                    {sig.narrative && `: ${sig.narrative}`}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default EvidenceStackGroup;
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Commit**

```bash
git add frontend/src/components/Investigation/cards/EvidenceStackGroup.tsx
git commit -m "feat(warroom): add EvidenceStackGroup — causal tree with visual tethers"
```

---

## Task 2: Wire EvidenceStackGroup into CausalForestView

**Files:**
- Modify: `frontend/src/components/Investigation/CausalForestView.tsx`

**Step 1: Replace CausalTreeCard with EvidenceStackGroup**

Replace the entire contents of `CausalForestView.tsx`:

```tsx
import React from 'react';
import type { CausalTree, TriageStatus } from '../../types';
import EvidenceStackGroup from './cards/EvidenceStackGroup';

interface CausalForestViewProps {
  forest: CausalTree[];
  sessionId: string;
  onTriageUpdate?: (treeId: string, status: TriageStatus) => void;
}

const CausalForestView: React.FC<CausalForestViewProps> = ({ forest, sessionId, onTriageUpdate }) => {
  if (!forest.length) return null;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 px-4">
        <span className="material-symbols-outlined text-[16px] text-cyan-500" style={{ fontFamily: 'Material Symbols Outlined' }}>account_tree</span>
        <span className="text-[10px] font-black text-slate-300 tracking-[0.1em] uppercase">Causal Forest</span>
        <span className="text-[9px] text-slate-500 font-mono">{forest.length} root cause{forest.length !== 1 ? 's' : ''}</span>
      </div>
      {forest.map(tree => (
        <EvidenceStackGroup key={tree.id} tree={tree} sessionId={sessionId} onTriageUpdate={onTriageUpdate} />
      ))}
    </div>
  );
};

export default CausalForestView;
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Commit**

```bash
git add frontend/src/components/Investigation/CausalForestView.tsx
git commit -m "feat(warroom): wire EvidenceStackGroup into CausalForestView"
```

---

## Task 3: AgentFindingCard — Progressive Disclosure

**Files:**
- Modify: `frontend/src/components/Investigation/cards/AgentFindingCard.tsx`

**What changes:** Add optional `collapsible` mode. When enabled, shows a scannable collapsed header (severity badge, title, agent badge, optional sparkline). Click expands to show children. Root cause cards get red tint + pulsing border. Backward-compatible — existing usage with `children` and no `collapsible` prop behaves identically.

**Step 1: Enhance the component**

Replace the entire contents of `AgentFindingCard.tsx`:

```tsx
import React, { memo, useState } from 'react';
import { SparklineWidget } from '../../shared';

type AgentCode = 'L' | 'M' | 'K' | 'C' | 'D';

const agentStyles: Record<AgentCode, { border: string; bg: string; label: string }> = {
  L: { border: 'card-border-L', bg: 'bg-red-500/10', label: 'Log Analyzer' },
  M: { border: 'card-border-M', bg: 'bg-cyan-500/10', label: 'Metric Scanner' },
  K: { border: 'card-border-K', bg: 'bg-orange-500/10', label: 'K8s Probe' },
  C: { border: 'card-border-C', bg: 'bg-emerald-500/10', label: 'Change Intel' },
  D: { border: 'card-border-D', bg: 'bg-blue-500/10', label: 'Code Navigator' },
};

const badgeColor: Record<AgentCode, string> = {
  L: 'bg-red-500 text-white',
  M: 'bg-cyan-500 text-white',
  K: 'bg-orange-500 text-white',
  C: 'bg-emerald-500 text-white',
  D: 'bg-blue-500 text-white',
};

interface AgentFindingCardProps {
  agent: AgentCode;
  title: string;
  children: React.ReactNode;
  /** Enable collapse/expand behavior */
  collapsible?: boolean;
  /** Start expanded (default true for non-collapsible, false for collapsible) */
  defaultExpanded?: boolean;
  /** Root cause variant — red tint, pulsing border, always starts expanded */
  isRootCause?: boolean;
  /** Optional sparkline data shown in collapsed header */
  sparklineData?: number[];
  /** Severity label shown as badge in collapsed header */
  severityLabel?: string;
}

const AgentFindingCard: React.FC<AgentFindingCardProps> = ({
  agent,
  title,
  children,
  collapsible = false,
  defaultExpanded,
  isRootCause = false,
  sparklineData,
  severityLabel,
}) => {
  const style = agentStyles[agent] || agentStyles.L;

  // Root cause always starts expanded; collapsible defaults to collapsed; non-collapsible always expanded
  const initialExpanded = isRootCause ? true : defaultExpanded ?? !collapsible;
  const [expanded, setExpanded] = useState(initialExpanded);

  const rootCauseClasses = isRootCause
    ? 'border-[#ef4444]/40 bg-[#ef4444]/5'
    : `${style.bg}`;

  const borderClass = isRootCause ? '' : style.border;

  return (
    <div
      className={`${borderClass} ${rootCauseClasses} rounded-lg overflow-hidden relative`}
      style={isRootCause ? { boxShadow: '0 0 15px rgba(239,68,68,0.1)' } : undefined}
    >
      {/* Pulsing left border for root cause */}
      {isRootCause && (
        <div className="absolute left-0 top-0 bottom-0 w-1 bg-[#ef4444] animate-pulse" />
      )}

      {/* Header — always visible */}
      <div
        className={`px-4 py-2.5 flex items-center gap-2 ${collapsible ? 'cursor-pointer select-none' : ''}`}
        onClick={collapsible ? () => setExpanded(!expanded) : undefined}
      >
        {/* Agent badge */}
        <span className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0 ${badgeColor[agent]}`}>
          {agent}
        </span>
        <span className="text-[10px] text-slate-500 uppercase tracking-wider shrink-0">{style.label}</span>

        {/* Severity label */}
        {severityLabel && (
          <span className={`text-[8px] font-bold px-1.5 py-0.5 rounded shrink-0 ${
            severityLabel === 'critical' ? 'text-red-400 bg-red-950/30 border border-red-500/40'
            : severityLabel === 'warn' ? 'text-amber-400 bg-amber-950/30 border border-amber-500/40'
            : 'text-slate-400 bg-slate-800/30 border border-slate-500/40'
          }`}>
            {severityLabel.toUpperCase()}
          </span>
        )}

        {/* Title */}
        <span className={`text-xs font-medium text-slate-200 ml-1 flex-1 ${collapsible && !expanded ? 'truncate' : ''}`}>
          {title}
        </span>

        {/* Inline sparkline in collapsed mode */}
        {collapsible && !expanded && sparklineData && sparklineData.length >= 2 && (
          <div className="w-16 shrink-0">
            <SparklineWidget data={sparklineData} height={16} strokeWidth={1.5} color={isRootCause ? 'red' : 'cyan'} />
          </div>
        )}

        {/* Expand chevron */}
        {collapsible && (
          <span
            className="material-symbols-outlined text-[16px] text-slate-500 shrink-0 transition-transform duration-200"
            style={{ fontFamily: 'Material Symbols Outlined', transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)' }}
          >
            expand_more
          </span>
        )}
      </div>

      {/* Body — children */}
      {expanded && (
        <div className="px-4 pb-3">
          {children}
        </div>
      )}
    </div>
  );
};

export default memo(AgentFindingCard);
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Verify backward compatibility**

Existing usages in `EvidenceFindings.tsx` use `<AgentFindingCard agent="L" title="...">children</AgentFindingCard>` — these continue to work identically because `collapsible` defaults to `false` and children always render.

**Step 4: Commit**

```bash
git add frontend/src/components/Investigation/cards/AgentFindingCard.tsx
git commit -m "feat(warroom): add progressive disclosure to AgentFindingCard"
```

---

## Task 4: Enhance RecommendationCard Terminal Styling

**Files:**
- Modify: `frontend/src/components/Investigation/cards/RecommendationCard.tsx`

**What changes:** Darken terminal block background to `#050a0b`, add destructive warning badge next to risk level, improve validation command display with verified icon, make command text cyan.

**Step 1: Update the CommandBlock and header styling**

In `RecommendationCard.tsx`, make these targeted edits:

1. **Line 67** — Change terminal background from `bg-slate-950/60 border border-slate-800/50` to darker:
```tsx
// OLD:
<pre className="text-[10px] font-mono bg-slate-950/60 border border-slate-800/50 rounded px-3 py-2 text-slate-300 overflow-x-auto whitespace-pre-wrap">

// NEW:
<pre className="text-[10px] font-mono rounded px-3 py-2 overflow-x-auto whitespace-pre-wrap" style={{ backgroundColor: '#050a0b', border: '1px solid #1a2a2e', color: '#07b6d5' }}>
```

2. **Line 68** — Change prompt color:
```tsx
// OLD:
<span className="text-slate-600 mr-2">$</span>

// NEW:
<span className="text-slate-600 mr-2 select-none">$</span>
```

3. **Lines 78-82** — Enhance validation command display:
```tsx
// OLD:
{step.validation_command && (
  <div className="text-[9px] text-slate-600 pl-2">
    Verify: <code className="text-slate-500">{step.validation_command}</code>
  </div>
)}

// NEW:
{step.validation_command && (
  <div className="flex items-center gap-1 text-[9px] text-slate-600 pl-2 cursor-pointer select-all" onClick={() => navigator.clipboard.writeText(step.validation_command!)}>
    <span className="material-symbols-outlined text-[12px] text-emerald-600" style={{ fontFamily: 'Material Symbols Outlined' }}>verified</span>
    <code className="text-slate-500 hover:text-slate-300 transition-colors">{step.validation_command}</code>
  </div>
)}
```

4. **Lines 109-111** — Add destructive warning badge next to risk label:
```tsx
// OLD:
<span className={`text-[8px] font-bold ${risk.className}`}>{risk.label}</span>

// NEW:
<span className={`text-[8px] font-bold px-1.5 py-0.5 rounded ${risk.className} ${rec.risk_level === 'destructive' ? 'bg-red-500/20 border border-red-500/30' : ''}`}>
  {risk.label}
</span>
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Commit**

```bash
git add frontend/src/components/Investigation/cards/RecommendationCard.tsx
git commit -m "feat(warroom): enhance RecommendationCard terminal styling and destructive badge"
```

---

## Task 5: Skeleton Loading State in EvidenceFindings

**Files:**
- Modify: `frontend/src/components/Investigation/EvidenceFindings.tsx`

**What changes:** When `findings` is null (initial load), show 3 shimmer skeleton cards instead of empty space. Uses `SkeletonLoader` from shared components.

**Step 1: Add import and skeleton rendering**

At top of `EvidenceFindings.tsx`, add to imports:
```tsx
import { SkeletonLoader } from '../shared';
```

Find the section where findings are checked (around line 250-260, the start of evidence rendering). Before the existing evidence sections, add an early return for the loading state:

```tsx
// After the BriefingHeader and before the main evidence sections
{!findings && (
  <div className="space-y-3 px-4 py-6">
    <SkeletonLoader variant="card" />
    <SkeletonLoader variant="card" />
    <SkeletonLoader variant="card" />
  </div>
)}
```

This should be placed inside the component's render, after the BriefingHeader block and before the `LogicVineContainer`. It renders only when `findings` is null.

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Commit**

```bash
git add frontend/src/components/Investigation/EvidenceFindings.tsx
git commit -m "feat(warroom): add skeleton loading cards while findings fetch"
```

---

## Task 6: Enable Collapsible Mode on Root Cause Pattern Cards

**Files:**
- Modify: `frontend/src/components/Investigation/EvidenceFindings.tsx`

**What changes:** Where root cause patterns are rendered with `<AgentFindingCard agent="L">`, add `collapsible isRootCause defaultExpanded` props to enable the new progressive disclosure for root cause findings. Similarly, add `collapsible` to cascading pattern cards and finding cards.

**Step 1: Find root cause pattern rendering**

Search for the section rendering root cause patterns (around lines 450-520 in EvidenceFindings.tsx). The patterns are rendered inside VineCard components with `<AgentFindingCard agent="L" title="...">`.

Add `collapsible isRootCause defaultExpanded` to root cause cards:
```tsx
<AgentFindingCard agent="L" title={pattern.pattern} collapsible isRootCause defaultExpanded>
```

Add `collapsible` to cascading symptom cards:
```tsx
<AgentFindingCard agent="L" title={pattern.pattern} collapsible>
```

Add `collapsible` to general finding cards (in the Findings section, around line 600):
```tsx
<AgentFindingCard agent={agentCode} title={finding.title} collapsible severityLabel={finding.severity}>
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Verify Vite build**

Run: `cd frontend && npx vite build`
Expected: Build succeeds

**Step 4: Commit**

```bash
git add frontend/src/components/Investigation/EvidenceFindings.tsx
git commit -m "feat(warroom): enable progressive disclosure on finding cards"
```

---

## Task 7: CSS Enhancements for War Room

**Files:**
- Modify: `frontend/src/index.css`

**What changes:** Add tether animation for the dashed connector lines, card entrance stagger animation, and edge hover styles for better visual polish.

**Step 1: Add new CSS animations**

Append to the existing animation section in `index.css` (after the existing `@keyframes` blocks, before the utility classes):

```css
/* ── War Room Phase 2: Visual tethers ── */
@keyframes tether-flow {
  0% { stroke-dashoffset: 12; }
  100% { stroke-dashoffset: 0; }
}
.tether-animate {
  animation: tether-flow 1.5s linear infinite;
}

/* Card entrance stagger */
@keyframes card-slide-in {
  0% { opacity: 0; transform: translateY(8px); }
  100% { opacity: 1; transform: translateY(0); }
}
.card-enter {
  animation: card-slide-in 0.3s ease-out forwards;
}
.card-enter-delay-1 { animation-delay: 0.05s; }
.card-enter-delay-2 { animation-delay: 0.1s; }
.card-enter-delay-3 { animation-delay: 0.15s; }

/* Root cause glow intensifier for EvidenceStackGroup */
.root-cause-glow {
  box-shadow: 0 0 15px rgba(239, 68, 68, 0.1), inset 0 1px 0 rgba(239, 68, 68, 0.05);
}
```

**Step 2: Commit**

```bash
git add frontend/src/index.css
git commit -m "feat(warroom): add CSS animations for tethers, card entrance, root cause glow"
```

---

## Task 8: Final Verification

**Step 1: TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 2: Vite production build**

Run: `cd frontend && npx vite build`
Expected: Build succeeds

**Step 3: File inventory check**

Verify these files exist and are non-empty:
- `frontend/src/components/Investigation/cards/EvidenceStackGroup.tsx` (NEW)
- `frontend/src/components/Investigation/cards/AgentFindingCard.tsx` (MODIFIED — progressive disclosure)
- `frontend/src/components/Investigation/cards/RecommendationCard.tsx` (MODIFIED — terminal styling)
- `frontend/src/components/Investigation/CausalForestView.tsx` (MODIFIED — uses EvidenceStackGroup)
- `frontend/src/components/Investigation/EvidenceFindings.tsx` (MODIFIED — skeletons + collapsible cards)
- `frontend/src/index.css` (MODIFIED — new animations)

---

## Execution Order

```
Task 1: EvidenceStackGroup component (new)
  ↓
Task 2: Wire into CausalForestView (depends on Task 1)
  ↓
Task 3: AgentFindingCard progressive disclosure (independent)
  ↓
Task 4: RecommendationCard terminal styling (independent)
  ↓
Task 5: Skeleton loading in EvidenceFindings (independent)
  ↓
Task 6: Enable collapsible mode in EvidenceFindings (depends on Task 3)
  ↓
Task 7: CSS animations (independent)
  ↓
Task 8: Final verification (depends on all)
```

Tasks 3, 4, 5, and 7 are independent of each other and can be parallelized.

---

## Verification Checklist

1. TypeScript: 0 errors on `npx tsc --noEmit`
2. Vite: Build succeeds on `npx vite build`
3. Visual: CausalForestView renders root cause with red tint, pulsing left border, resource tag pills
4. Visual: "SHOW IMPACT (N)" / "HIDE IMPACT" toggle works, dashed tether lines connect children
5. Visual: Cascading symptoms indented with horizontal elbow connectors
6. Visual: Correlated signals at 70% opacity with cyan border
7. Visual: AgentFindingCard with `collapsible` — click header to expand/collapse, chevron rotates
8. Visual: Root cause AgentFindingCard starts expanded with red styling
9. Visual: Collapsed AgentFindingCard shows truncated title + optional sparkline
10. Visual: RecommendationCard terminal blocks are dark (#050a0b) with cyan text
11. Visual: Destructive recommendations show red "DESTRUCTIVE" badge with background
12. Visual: Validation commands show green verified icon, cursor-pointer
13. Visual: EvidenceFindings shows 3 skeleton cards while findings is null
14. Visual: Cards animate in with slide-up on initial render
