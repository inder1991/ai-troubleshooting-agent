# Database Investigation Board v2 — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the basic DatabaseWarRoom with an Investigation Board that avoids AI slop anti-patterns: no identical card grids, no card-in-card nesting, no hero metric templates, variable panel sizing by importance.

**Architecture:** Rewrite `DatabaseWarRoom.tsx` as a 3-column CSS grid (3-5-4). Center column uses asymmetric CSS grid with variable-sized zones — Query Performance dominates (largest), Schema Drift is compact (single row). Visualizations render directly without card wrappers. Health metrics are a single inline strip, not a gauge grid. Root Cause verdict takes over center column when synthesizer delivers. Left column is agent-grouped case file. Right column is replication topology + health strip + agent status.

**Tech Stack:** React, TypeScript, Tailwind CSS, Framer Motion (for panel state transitions)

**Anti-pattern compliance:**
- No identical card grid (panels vary in size and visual weight)
- No card-in-card nesting (viz components render without wrappers when lit)
- No hero metric template (health is a compact strip, not gauge grid)
- Varied spacing (tight within sections, generous between zones)
- Root cause dominates when present (not tucked at bottom)

---

## Task 1: Create PanelZone component (replaces InstrumentPanel)

**Files:**
- Create: `frontend/src/components/Investigation/db-board/PanelZone.tsx`

**Step 1: Create the zone component**

Unlike the old InstrumentPanel card wrapper, PanelZone is minimal — it handles the dormant/scanning/lit state transitions but does NOT wrap content in a bordered card. When lit, the child visualization IS the content with no extra container.

```tsx
import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';

export type PanelState = 'dormant' | 'scanning' | 'lit';

interface PanelZoneProps {
  title: string;
  icon: string;
  agentName: string;
  state: PanelState;
  children: React.ReactNode;
  className?: string;
}

const PanelZone: React.FC<PanelZoneProps> = ({
  title,
  icon,
  agentName,
  state,
  children,
  className = '',
}) => {
  return (
    <div className={`flex flex-col min-h-0 ${className}`}>
      {/* Zone label — always visible, minimal */}
      <div className="flex items-center gap-1.5 mb-1.5">
        <span
          className={`material-symbols-outlined text-[14px] ${
            state === 'lit' ? 'text-duck-accent' : 'text-slate-600'
          }`}
          aria-hidden="true"
        >
          {icon}
        </span>
        <span
          className={`text-[10px] font-display font-bold ${
            state === 'lit' ? 'text-slate-300' : 'text-slate-600'
          }`}
        >
          {title}
        </span>
        {state === 'scanning' && (
          <span className="text-[9px] text-amber-400 ml-auto flex items-center gap-1">
            <span className="material-symbols-outlined text-[12px] animate-spin">progress_activity</span>
            {agentName}
          </span>
        )}
      </div>

      {/* Content area — no card wrapper */}
      <AnimatePresence mode="wait">
        {state === 'dormant' && (
          <motion.div
            key="dormant"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex-1 flex items-center justify-center border border-dashed border-duck-border/30 rounded-lg"
          >
            <span className="text-[10px] text-slate-700 italic">
              Waiting for {agentName}
            </span>
          </motion.div>
        )}
        {state === 'scanning' && (
          <motion.div
            key="scanning"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex-1 flex items-center justify-center border border-amber-500/20 rounded-lg bg-amber-500/[0.02]"
          >
            <span className="text-[10px] text-amber-400/60">Analyzing...</span>
          </motion.div>
        )}
        {state === 'lit' && (
          <motion.div
            key="lit"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            className="flex-1 min-h-0 overflow-hidden"
          >
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default PanelZone;
```

**Step 2: Commit**
```bash
git add frontend/src/components/Investigation/db-board/PanelZone.tsx
git commit -m "feat(db-board): add PanelZone with dormant/scanning/lit states — no card wrapper"
```

---

## Task 2: Create CaseFile component (left column)

**Files:**
- Create: `frontend/src/components/Investigation/db-board/CaseFile.tsx`

**Step 1: Create agent-grouped narrative case file**

Groups events by agent with collapsible sections. No card wrappers on individual entries — uses left-border color accent per agent instead.

```tsx
import React, { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { TaskEvent } from '../../../types';

const DB_AGENTS = [
  { id: 'query_analyst', label: 'Query Analyst', icon: 'query_stats', borderColor: 'border-l-amber-400' },
  { id: 'health_analyst', label: 'Health Analyst', icon: 'monitor_heart', borderColor: 'border-l-emerald-400' },
  { id: 'schema_analyst', label: 'Schema Analyst', icon: 'schema', borderColor: 'border-l-violet-400' },
  { id: 'synthesizer', label: 'Synthesizer', icon: 'hub', borderColor: 'border-l-duck-accent' },
];

type AgentState = 'pending' | 'scanning' | 'complete' | 'error';

interface CaseFileProps {
  serviceName: string;
  sessionId: string;
  events: TaskEvent[];
  elapsedSec: number;
}

const stateIcon: Record<AgentState, { icon: string; cls: string }> = {
  pending: { icon: 'radio_button_unchecked', cls: 'text-slate-600' },
  scanning: { icon: 'pending', cls: 'text-amber-400 animate-spin' },
  complete: { icon: 'check_circle', cls: 'text-emerald-400' },
  error: { icon: 'error', cls: 'text-red-400' },
};

function deriveAgentState(agentEvents: TaskEvent[]): AgentState {
  if (agentEvents.length === 0) return 'pending';
  const last = agentEvents[agentEvents.length - 1];
  if (last.event_type === 'success') return 'complete';
  if (last.event_type === 'error') return 'error';
  return 'scanning';
}

const CaseFile: React.FC<CaseFileProps> = ({ serviceName, sessionId, events, elapsedSec }) => {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const agentGroups = useMemo(() => {
    return DB_AGENTS.map((agent) => {
      const agentEvents = events.filter((e) => e.agent_name === agent.id);
      return { ...agent, events: agentEvents, state: deriveAgentState(agentEvents) };
    });
  }, [events]);

  const toggle = (id: string) => setCollapsed((prev) => ({ ...prev, [id]: !prev[id] }));

  const m = Math.floor(elapsedSec / 60);
  const s = elapsedSec % 60;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="px-4 pt-4 pb-3 border-b border-duck-border/50 shrink-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="material-symbols-outlined text-violet-400 text-lg" aria-hidden="true">folder_open</span>
          <h2 className="text-sm font-display font-bold text-white">Case File</h2>
        </div>
        <p className="text-[11px] text-slate-300 font-mono">{serviceName}</p>
        <div className="flex items-center gap-3 mt-1.5">
          <span className="text-[10px] text-slate-500 font-mono">{sessionId.slice(0, 8)}</span>
          <span className="text-[10px] text-amber-400 font-mono">{m}m {s}s</span>
        </div>
      </div>

      {/* Agent sections — no cards, just left-border accent */}
      <div className="flex-1 overflow-y-auto py-3 custom-scrollbar">
        {agentGroups.map((agent) => {
          const isCollapsed = collapsed[agent.id] ?? false;
          const si = stateIcon[agent.state];
          return (
            <div key={agent.id} className={`border-l-2 ${agent.borderColor} ml-4 mb-3`}>
              {/* Agent header */}
              <button
                onClick={() => toggle(agent.id)}
                className="w-full flex items-center gap-2 pl-3 pr-4 py-1.5 hover:bg-duck-surface/30 transition-colors text-left"
                aria-expanded={!isCollapsed}
              >
                <span className={`material-symbols-outlined text-[14px] ${si.cls}`}>{si.icon}</span>
                <span className="text-[11px] font-bold text-slate-300 flex-1">{agent.label}</span>
                {agent.events.length > 0 && (
                  <span className="text-[9px] text-slate-600">{agent.events.length}</span>
                )}
                <span
                  className={`material-symbols-outlined text-[12px] text-slate-600 transition-transform duration-200 ${isCollapsed ? '' : 'rotate-90'}`}
                >
                  chevron_right
                </span>
              </button>

              {/* Events */}
              <AnimatePresence>
                {!isCollapsed && agent.events.length > 0 && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.2 }}
                  >
                    <div className="pl-8 pr-4 pb-2 space-y-1">
                      {agent.events.slice(-8).map((ev, i) => (
                        <div key={i} className="flex items-start gap-1.5">
                          <span className={`w-1 h-1 rounded-full mt-1.5 shrink-0 ${
                            ev.event_type === 'error' ? 'bg-red-400' :
                            ev.event_type === 'finding' ? 'bg-amber-400' :
                            ev.event_type === 'success' ? 'bg-emerald-400' :
                            'bg-slate-600'
                          }`} />
                          <p className="text-[10px] text-slate-400 leading-relaxed">{ev.message}</p>
                        </div>
                      ))}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default CaseFile;
```

**Step 2: Commit**
```bash
git add frontend/src/components/Investigation/db-board/CaseFile.tsx
git commit -m "feat(db-board): add CaseFile with agent-grouped narrative, no card nesting"
```

---

## Task 3: Create RootCauseVerdict component

**Files:**
- Create: `frontend/src/components/Investigation/db-board/RootCauseVerdict.tsx`

**Step 1: Create the verdict component**

When the synthesizer delivers, this takes visual prominence — not a tiny strip, but a full-width takeover of the center column top area.

```tsx
import React from 'react';
import { motion } from 'framer-motion';

interface RootCauseVerdictProps {
  verdict: string | null;
  confidence: number;
  severity?: 'critical' | 'high' | 'medium' | 'low';
  recommendation?: string;
  contributingPanels?: string[];
}

const severityColor: Record<string, string> = {
  critical: 'border-red-500/40 text-red-400',
  high: 'border-orange-500/40 text-orange-400',
  medium: 'border-amber-500/40 text-amber-400',
  low: 'border-emerald-500/40 text-emerald-400',
};

const RootCauseVerdict: React.FC<RootCauseVerdictProps> = ({
  verdict,
  confidence,
  severity = 'medium',
  recommendation,
  contributingPanels,
}) => {
  if (!verdict) return null;

  const sev = severityColor[severity] || severityColor.medium;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      className={`border-l-3 ${sev.split(' ')[0]} bg-duck-surface/50 rounded-r-lg px-4 py-3 mb-4`}
    >
      {/* Verdict header with confidence */}
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-duck-accent text-lg">target</span>
          <span className="text-xs font-display font-bold text-white">Root Cause Identified</span>
          <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border ${sev}`}>
            {severity.toUpperCase()}
          </span>
        </div>
        <span className="text-sm font-display font-bold text-duck-accent">{confidence}%</span>
      </div>

      {/* Verdict text */}
      <p className="text-[12px] text-slate-200 leading-relaxed mb-2">{verdict}</p>

      {/* Recommendation */}
      {recommendation && (
        <p className="text-[11px] text-slate-400 italic border-t border-duck-border/30 pt-2 mt-2">
          {recommendation}
        </p>
      )}

      {/* Contributing panels */}
      {contributingPanels && contributingPanels.length > 0 && (
        <div className="flex items-center gap-1.5 mt-2">
          <span className="text-[9px] text-slate-500">Evidence:</span>
          {contributingPanels.map((p) => (
            <span key={p} className="text-[9px] px-1.5 py-0.5 rounded bg-duck-accent/10 text-duck-accent">
              {p}
            </span>
          ))}
        </div>
      )}
    </motion.div>
  );
};

export default RootCauseVerdict;
```

**Step 2: Commit**
```bash
git add frontend/src/components/Investigation/db-board/RootCauseVerdict.tsx
git commit -m "feat(db-board): add RootCauseVerdict with left-border severity, no card nesting"
```

---

## Task 4: Create HealthStrip component (replaces gauge grid)

**Files:**
- Create: `frontend/src/components/Investigation/db-board/HealthStrip.tsx`

**Step 1: Create compact inline health strip**

Instead of 4 identical arc gauges (hero metric anti-pattern), this is a single compact row of key/value pairs with color-coded status dots.

```tsx
import React from 'react';

interface HealthStripProps {
  cacheHitRatio?: number;
  tps?: number;
  deadlocks?: number;
  uptimeSeconds?: number;
}

function formatUptime(sec: number): string {
  if (sec >= 86400) return `${Math.floor(sec / 86400)}d`;
  if (sec >= 3600) return `${Math.floor(sec / 3600)}h`;
  return `${Math.floor(sec / 60)}m`;
}

function statusDot(ok: boolean): string {
  return ok ? 'bg-emerald-400' : 'bg-red-400';
}

const HealthStrip: React.FC<HealthStripProps> = ({
  cacheHitRatio,
  tps,
  deadlocks,
  uptimeSeconds,
}) => {
  const items = [
    {
      label: 'Cache',
      value: cacheHitRatio != null ? `${(cacheHitRatio * 100).toFixed(1)}%` : '—',
      ok: (cacheHitRatio ?? 1) >= 0.9,
    },
    {
      label: 'TPS',
      value: tps != null ? (tps >= 1000 ? `${(tps / 1000).toFixed(1)}K` : String(Math.round(tps))) : '—',
      ok: true,
    },
    {
      label: 'Deadlocks',
      value: deadlocks != null ? String(deadlocks) : '—',
      ok: (deadlocks ?? 0) === 0,
    },
    {
      label: 'Uptime',
      value: uptimeSeconds != null ? formatUptime(uptimeSeconds) : '—',
      ok: (uptimeSeconds ?? 0) > 3600,
    },
  ];

  return (
    <div className="flex items-center gap-4 px-3 py-2 bg-duck-surface/30 rounded-lg">
      {items.map((item) => (
        <div key={item.label} className="flex items-center gap-1.5">
          <span className={`w-1.5 h-1.5 rounded-full ${statusDot(item.ok)}`} />
          <span className="text-[9px] text-slate-500">{item.label}</span>
          <span className="text-[10px] font-bold text-slate-300">{item.value}</span>
        </div>
      ))}
    </div>
  );
};

export default HealthStrip;
```

**Step 2: Commit**
```bash
git add frontend/src/components/Investigation/db-board/HealthStrip.tsx
git commit -m "feat(db-board): add HealthStrip — compact inline health metrics, no gauge grid"
```

---

## Task 5: Rewrite DatabaseWarRoom with asymmetric board layout

**Files:**
- Modify: `frontend/src/components/Investigation/DatabaseWarRoom.tsx` (full rewrite)

**Step 1: Rewrite with asymmetric center column**

The center column uses CSS grid with variable row/column spans:
- Query Performance: large (spans 2 cols, taller)
- Connection Pool: standard (1 col)
- Index Health: standard (1 col)
- Table Bloat: standard (1 col)
- Query Plan: standard (1 col)
- Schema Drift: compact (full width, single short row)

```tsx
import React, { useState, useMemo, useEffect, useRef } from 'react';
import type { V4Session, TaskEvent, DiagnosticPhase } from '../../types';

import PanelZone from './db-board/PanelZone';
import type { PanelState } from './db-board/PanelZone';
import CaseFile from './db-board/CaseFile';
import RootCauseVerdict from './db-board/RootCauseVerdict';
import HealthStrip from './db-board/HealthStrip';

import QueryFlamechart from './db-viz/QueryFlamechart';
import ExplainPlanTree from './db-viz/ExplainPlanTree';
import IndexUsageMatrix from './db-viz/IndexUsageMatrix';
import TableBloatHeatmap from './db-viz/TableBloatHeatmap';
import ConnectionPoolGauge from './db-viz/ConnectionPoolGauge';
import SlowQueryTimeline from './db-viz/SlowQueryTimeline';
import ReplicationTopologySVG from './db-viz/ReplicationTopologySVG';

interface DatabaseWarRoomProps {
  session: V4Session;
  events: TaskEvent[];
  wsConnected: boolean;
  phase: DiagnosticPhase | null;
  confidence: number;
}

const DB_AGENTS = ['query_analyst', 'health_analyst', 'schema_analyst', 'synthesizer'];

function derivePanelState(events: TaskEvent[], agentName: string, dataKey: string): PanelState {
  const agentEvents = events.filter((e) => e.agent_name === agentName);
  if (agentEvents.length === 0) return 'dormant';
  const hasFinding = agentEvents.some((e) => e.event_type === 'finding' && e.details?.[dataKey]);
  if (hasFinding) return 'lit';
  const hasActivity = agentEvents.some((e) => ['started', 'progress'].includes(e.event_type));
  if (hasActivity) return 'scanning';
  return 'dormant';
}

function extractData<T>(events: TaskEvent[], agent: string, key: string): T | null {
  for (let i = events.length - 1; i >= 0; i--) {
    const ev = events[i];
    if (ev.agent_name === agent && ev.details?.[key]) return ev.details[key] as T;
  }
  return null;
}

const DatabaseWarRoom: React.FC<DatabaseWarRoomProps> = ({
  session, events, wsConnected, phase, confidence,
}) => {
  const [elapsedSec, setElapsedSec] = useState(0);
  const startRef = useRef(Date.now());
  useEffect(() => {
    const iv = setInterval(() => setElapsedSec(Math.floor((Date.now() - startRef.current) / 1000)), 1000);
    return () => clearInterval(iv);
  }, []);

  // Panel states
  const ps = useMemo(() => ({
    queries: derivePanelState(events, 'query_analyst', 'slow_queries'),
    connPool: derivePanelState(events, 'health_analyst', 'connections'),
    indexes: derivePanelState(events, 'schema_analyst', 'indexes'),
    bloat: derivePanelState(events, 'schema_analyst', 'table_bloat'),
    plan: derivePanelState(events, 'query_analyst', 'explain_plan'),
    schema: derivePanelState(events, 'schema_analyst', 'schema_changes'),
  }), [events]);

  // Data extraction
  const slowQueries = extractData<any[]>(events, 'query_analyst', 'slow_queries');
  const planSteps = extractData<any[]>(events, 'query_analyst', 'plan_steps');
  const explainPlan = extractData<any>(events, 'query_analyst', 'explain_plan');
  const connections = extractData<any>(events, 'health_analyst', 'connections');
  const indexes = extractData<any[]>(events, 'schema_analyst', 'indexes');
  const tableBloat = extractData<any[]>(events, 'schema_analyst', 'table_bloat');
  const replication = extractData<any>(events, 'health_analyst', 'replication');
  const performance = extractData<any>(events, 'health_analyst', 'performance');

  // Synthesizer verdict
  const synthEvent = useMemo(() => {
    for (let i = events.length - 1; i >= 0; i--) {
      if (events[i].agent_name === 'synthesizer' && events[i].event_type === 'success') return events[i];
    }
    return null;
  }, [events]);

  const litPanels = useMemo(() => {
    const out: string[] = [];
    if (ps.queries === 'lit') out.push('Queries');
    if (ps.connPool === 'lit') out.push('Connections');
    if (ps.indexes === 'lit') out.push('Indexes');
    if (ps.bloat === 'lit') out.push('Bloat');
    if (ps.plan === 'lit') out.push('Plan');
    return out;
  }, [ps]);

  return (
    <div className="flex flex-col h-full overflow-hidden bg-duck-bg">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-duck-border bg-duck-panel/50 shrink-0">
        <div className="flex items-center gap-3">
          <span className="material-symbols-outlined text-violet-400 text-xl">database</span>
          <div>
            <h1 className="text-sm font-display font-bold text-white">{session.service_name}</h1>
            <p className="text-[10px] text-slate-500">{phase || 'initializing'}</p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-[10px] font-mono text-amber-400">
            {Math.floor(elapsedSec / 60)}m {elapsedSec % 60}s
          </span>
          <div className="flex items-center gap-1.5">
            <span className={`w-1.5 h-1.5 rounded-full ${wsConnected ? 'bg-emerald-400' : 'bg-red-400'}`} />
            <span className={`text-[10px] font-bold uppercase ${wsConnected ? 'text-emerald-400' : 'text-red-400'}`}>
              {wsConnected ? 'LIVE' : 'OFFLINE'}
            </span>
          </div>
        </div>
      </div>

      {/* 3-column board */}
      <div className="grid grid-cols-12 flex-1 overflow-hidden">

        {/* LEFT: Case File */}
        <div className="col-span-3 border-r border-duck-border overflow-hidden">
          <CaseFile
            serviceName={session.service_name}
            sessionId={session.session_id}
            events={events}
            elapsedSec={elapsedSec}
          />
        </div>

        {/* CENTER: The Board — asymmetric grid */}
        <div className="col-span-5 overflow-y-auto p-4 custom-scrollbar">
          {/* Root Cause Verdict — takes top when present */}
          <RootCauseVerdict
            verdict={synthEvent?.message || null}
            confidence={confidence}
            severity={synthEvent?.details?.severity as any}
            recommendation={synthEvent?.details?.recommendation as string}
            contributingPanels={litPanels}
          />

          {/*
            Asymmetric grid:
            Row 1: Query Performance (wide) | Connection Pool (narrow)
            Row 2: Index Health | Table Bloat
            Row 3: Query Plan | (empty — plan can be tall)
            Row 4: Schema Drift (full width, compact)
          */}
          <div className="grid grid-cols-[2fr_1fr] gap-x-4 gap-y-5">
            {/* Query Performance — LARGE (spans left, taller min-height) */}
            <PanelZone
              title="Query Performance"
              icon="query_stats"
              agentName="query_analyst"
              state={ps.queries}
              className="min-h-[180px]"
            >
              <div className="space-y-3">
                {slowQueries && <SlowQueryTimeline queries={slowQueries} />}
                {planSteps && <QueryFlamechart planSteps={planSteps} />}
              </div>
            </PanelZone>

            {/* Connection Pool — standard */}
            <PanelZone
              title="Connections"
              icon="cable"
              agentName="health_analyst"
              state={ps.connPool}
              className="min-h-[180px]"
            >
              {connections && (
                <ConnectionPoolGauge
                  active={connections.active ?? 0}
                  idle={connections.idle ?? 0}
                  waiting={connections.waiting ?? 0}
                  max={connections.max_connections ?? connections.max ?? 100}
                />
              )}
            </PanelZone>

            {/* Index Health */}
            <PanelZone
              title="Index Health"
              icon="format_list_numbered"
              agentName="schema_analyst"
              state={ps.indexes}
            >
              {indexes && <IndexUsageMatrix indexes={indexes} />}
            </PanelZone>

            {/* Table Bloat */}
            <PanelZone
              title="Table Bloat"
              icon="grid_view"
              agentName="schema_analyst"
              state={ps.bloat}
            >
              {tableBloat && <TableBloatHeatmap tables={tableBloat} />}
            </PanelZone>

            {/* Query Plan — can be tall, takes left column */}
            <PanelZone
              title="Query Plan"
              icon="account_tree"
              agentName="query_analyst"
              state={ps.plan}
            >
              {explainPlan && <ExplainPlanTree plan={explainPlan} />}
            </PanelZone>

            {/* Empty right cell — intentional asymmetry */}
            <div />
          </div>

          {/* Schema Drift — full width, compact single row */}
          <div className="mt-5">
            <PanelZone
              title="Schema Drift"
              icon="difference"
              agentName="schema_analyst"
              state={ps.schema}
            >
              <p className="text-[10px] text-slate-500 italic">No schema changes detected</p>
            </PanelZone>
          </div>
        </div>

        {/* RIGHT: The Map */}
        <div className="col-span-4 border-l border-duck-border overflow-y-auto p-4 custom-scrollbar">
          {/* Replication Topology — top, largest element */}
          <div className="mb-5">
            <h3 className="text-[10px] font-display font-bold text-slate-500 mb-2">Replication</h3>
            {replication ? (
              <ReplicationTopologySVG
                primary={replication.primary || { host: session.service_name, lag_ms: 0 }}
                replicas={replication.replicas || []}
              />
            ) : (
              <div className="flex items-center justify-center h-28 border border-dashed border-duck-border/30 rounded-lg">
                <span className="text-[10px] text-slate-700 italic">Awaiting replication data</span>
              </div>
            )}
          </div>

          {/* Health Strip — compact inline, not gauge grid */}
          <div className="mb-5">
            <h3 className="text-[10px] font-display font-bold text-slate-500 mb-2">Health</h3>
            <HealthStrip
              cacheHitRatio={performance?.cache_hit_ratio}
              tps={performance?.transactions_per_sec}
              deadlocks={performance?.deadlocks}
              uptimeSeconds={performance?.uptime_seconds}
            />
          </div>

          {/* Agent Status — minimal, no cards */}
          <div>
            <h3 className="text-[10px] font-display font-bold text-slate-500 mb-2">Agents</h3>
            <div className="space-y-1">
              {DB_AGENTS.map((agent) => {
                const agentEvents = events.filter((e) => e.agent_name === agent);
                const last = agentEvents[agentEvents.length - 1];
                const status = last?.event_type || 'pending';
                return (
                  <div key={agent} className="flex items-center justify-between py-1 px-2">
                    <span className="text-[10px] text-slate-400">{agent.replace(/_/g, ' ')}</span>
                    <span className={`material-symbols-outlined text-[14px] ${
                      status === 'success' ? 'text-emerald-400' :
                      status === 'error' ? 'text-red-400' :
                      ['started', 'progress'].includes(status) ? 'text-amber-400 animate-spin' :
                      'text-slate-700'
                    }`}>
                      {status === 'success' ? 'check_circle' :
                       status === 'error' ? 'error' :
                       ['started', 'progress'].includes(status) ? 'progress_activity' :
                       'radio_button_unchecked'}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Completion summary */}
          {phase === 'complete' && synthEvent && (
            <div className="mt-5 border-t border-duck-border/50 pt-4">
              <div className="flex items-center gap-2 mb-1">
                <span className="material-symbols-outlined text-emerald-400 text-sm">check_circle</span>
                <span className="text-[11px] font-display font-bold text-emerald-400">Complete</span>
              </div>
              <p className="text-[10px] text-slate-300 leading-relaxed">{synthEvent.message}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default DatabaseWarRoom;
```

**Step 2: Verify TypeScript compiles**
```bash
cd frontend && npx tsc --noEmit
```
Expected: No errors

**Step 3: Commit**
```bash
git add frontend/src/components/Investigation/DatabaseWarRoom.tsx
git commit -m "feat(db-board): rewrite DatabaseWarRoom as Investigation Board with asymmetric layout"
```

---

## Task 6: Verify integration (no App.tsx changes needed)

**Step 1: Verify props unchanged**

The new DatabaseWarRoom accepts identical props to the old one:
```typescript
interface DatabaseWarRoomProps {
  session: V4Session;
  events: TaskEvent[];
  wsConnected: boolean;
  phase: DiagnosticPhase | null;
  confidence: number;
}
```

No changes needed in `App.tsx` — the import path and usage remain identical.

**Step 2: Run dev server**
```bash
cd frontend && npm run dev
```

Navigate to a database diagnostics session. Verify:
- 3-column layout renders (Case File | Board | Map)
- All 6 panel zones show "Waiting for..." in dormant state
- Replication area shows dashed placeholder
- Health strip shows "—" for all values
- Agent status shows all pending

**Step 3: Final commit**
```bash
git add -A
git commit -m "feat(db-board): Database Investigation Board complete — asymmetric panels, no AI slop"
```
