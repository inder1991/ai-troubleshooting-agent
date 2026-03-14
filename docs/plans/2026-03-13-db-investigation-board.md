# Database Investigation Board — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the basic DatabaseWarRoom with an Investigation Board layout featuring 6 always-visible instrument panels, a narrative case file, and a spatial map with replication topology + health gauges.

**Architecture:** Rewrite `DatabaseWarRoom.tsx` as a 3-column CSS grid (3-5-4). Center column becomes a 3x2 instrument grid wiring the existing db-viz components (QueryFlamechart, ExplainPlanTree, IndexUsageMatrix, TableBloatHeatmap, ConnectionPoolGauge, SlowQueryTimeline). Left column becomes agent-grouped case file. Right column becomes replication topology + health gauges + agent status. A dynamic root cause strip at the bottom of the center column appears when the synthesizer delivers its verdict.

**Tech Stack:** React, TypeScript, Tailwind CSS, Framer Motion (for panel state transitions)

---

## Task 1: Create InstrumentPanel wrapper component

**Files:**
- Create: `frontend/src/components/Investigation/db-board/InstrumentPanel.tsx`

**Step 1: Create the panel wrapper**

This is a reusable wrapper for each of the 6 instrument panels. It handles 3 visual states: dormant, scanning, lit.

```tsx
import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';

export type PanelState = 'dormant' | 'scanning' | 'lit';

interface InstrumentPanelProps {
  title: string;
  icon: string;
  agentName: string;
  state: PanelState;
  children: React.ReactNode;
  onExpand?: () => void;
}

const stateStyles: Record<PanelState, string> = {
  dormant: 'border-duck-border/40 bg-duck-card/10 opacity-50',
  scanning: 'border-amber-500/40 bg-duck-card/20 animate-border-pulse-amber',
  lit: 'border-duck-border bg-duck-card/30',
};

const InstrumentPanel: React.FC<InstrumentPanelProps> = ({
  title,
  icon,
  agentName,
  state,
  children,
  onExpand,
}) => {
  return (
    <div
      className={`relative rounded-lg border p-3 transition-all duration-500 overflow-hidden ${stateStyles[state]}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-sm text-duck-muted" aria-hidden="true">
            {icon}
          </span>
          <span className="text-[11px] font-display font-bold text-slate-300">{title}</span>
        </div>
        <div className="flex items-center gap-2">
          {state === 'scanning' && (
            <span className="text-[9px] text-amber-400 animate-pulse">{agentName}</span>
          )}
          {state === 'lit' && onExpand && (
            <button
              onClick={onExpand}
              className="text-duck-muted hover:text-white transition-colors"
              aria-label={`Expand ${title}`}
            >
              <span className="material-symbols-outlined text-sm">open_in_full</span>
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      <AnimatePresence mode="wait">
        {state === 'dormant' && (
          <motion.div
            key="dormant"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex items-center justify-center h-24 text-[10px] text-slate-600 italic"
          >
            Waiting for {agentName}...
          </motion.div>
        )}
        {state === 'scanning' && (
          <motion.div
            key="scanning"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex items-center justify-center h-24"
          >
            <div className="flex items-center gap-2 text-[10px] text-amber-400">
              <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span>
              Analyzing...
            </div>
          </motion.div>
        )}
        {state === 'lit' && (
          <motion.div
            key="lit"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
          >
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default InstrumentPanel;
```

**Step 2: Commit**
```bash
git add frontend/src/components/Investigation/db-board/InstrumentPanel.tsx
git commit -m "feat(db-board): add InstrumentPanel wrapper with dormant/scanning/lit states"
```

---

## Task 2: Create CaseFile component (left column)

**Files:**
- Create: `frontend/src/components/Investigation/db-board/CaseFile.tsx`

**Step 1: Create the agent-grouped case file**

Groups events by agent with collapsible sections showing investigation narrative.

```tsx
import React, { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { TaskEvent } from '../../../types';

const DB_AGENTS = [
  { id: 'query_analyst', label: 'Query Analyst', icon: 'query_stats', color: 'text-amber-400' },
  { id: 'health_analyst', label: 'Health Analyst', icon: 'monitor_heart', color: 'text-emerald-400' },
  { id: 'schema_analyst', label: 'Schema Analyst', icon: 'schema', color: 'text-violet-400' },
  { id: 'synthesizer', label: 'Synthesizer', icon: 'hub', color: 'text-duck-accent' },
];

type AgentState = 'pending' | 'scanning' | 'complete' | 'error';

interface CaseFileProps {
  serviceName: string;
  sessionId: string;
  events: TaskEvent[];
  elapsedSec: number;
}

const stateIcon: Record<AgentState, { icon: string; class: string }> = {
  pending: { icon: 'radio_button_unchecked', class: 'text-slate-600' },
  scanning: { icon: 'pending', class: 'text-amber-400 animate-spin' },
  complete: { icon: 'check_circle', class: 'text-emerald-400' },
  error: { icon: 'error', class: 'text-red-400' },
};

function deriveAgentState(agentEvents: TaskEvent[]): AgentState {
  if (agentEvents.length === 0) return 'pending';
  const last = agentEvents[agentEvents.length - 1];
  if (last.event_type === 'success') return 'complete';
  if (last.event_type === 'error') return 'error';
  return 'scanning';
}

function formatElapsed(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}m ${s}s`;
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

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Case header */}
      <div className="px-4 pt-4 pb-3 border-b border-duck-border shrink-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="material-symbols-outlined text-violet-400 text-lg" aria-hidden="true">folder_open</span>
          <h2 className="text-sm font-display font-bold text-white">Case File</h2>
        </div>
        <p className="text-[11px] text-slate-300 font-mono">{serviceName}</p>
        <div className="flex items-center gap-3 mt-1.5">
          <span className="text-[10px] text-slate-500">Session {sessionId.slice(0, 8)}</span>
          <span className="text-[10px] text-amber-400 font-mono">{formatElapsed(elapsedSec)}</span>
        </div>
      </div>

      {/* Agent sections */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2 custom-scrollbar">
        {agentGroups.map((agent) => {
          const isCollapsed = collapsed[agent.id] ?? false;
          const si = stateIcon[agent.state];
          return (
            <div key={agent.id} className="border border-duck-border/50 rounded-lg overflow-hidden">
              {/* Agent header */}
              <button
                onClick={() => toggle(agent.id)}
                className="w-full flex items-center gap-2 px-3 py-2 hover:bg-duck-surface/50 transition-colors text-left"
              >
                <span className={`material-symbols-outlined text-sm ${si.class}`}>{si.icon}</span>
                <span className={`text-[11px] font-bold ${agent.color}`}>{agent.label}</span>
                <span className="ml-auto text-[9px] text-slate-600">
                  {agent.events.length > 0 ? `${agent.events.length} events` : ''}
                </span>
                <span
                  className={`material-symbols-outlined text-xs text-slate-600 transition-transform ${isCollapsed ? '' : 'rotate-90'}`}
                >
                  chevron_right
                </span>
              </button>

              {/* Agent findings */}
              <AnimatePresence>
                {!isCollapsed && agent.events.length > 0 && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    className="border-t border-duck-border/30"
                  >
                    <div className="px-3 py-2 space-y-1.5">
                      {agent.events.slice(-8).map((ev, i) => (
                        <div key={i} className="flex items-start gap-2">
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
git commit -m "feat(db-board): add CaseFile component with agent-grouped narrative"
```

---

## Task 3: Create RootCauseStrip component

**Files:**
- Create: `frontend/src/components/Investigation/db-board/RootCauseStrip.tsx`

**Step 1: Create the dynamic root cause verdict strip**

Appears when synthesizer delivers findings. Shows verdict, confidence, severity, recommendation.

```tsx
import React from 'react';
import { motion } from 'framer-motion';

interface RootCauseStripProps {
  verdict: string | null;
  confidence: number;
  severity?: 'critical' | 'high' | 'medium' | 'low';
  recommendation?: string;
  litPanels?: string[]; // panel titles that contributed evidence
}

const severityStyles: Record<string, string> = {
  critical: 'bg-red-500/10 text-red-400 border-red-500/30',
  high: 'bg-orange-500/10 text-orange-400 border-orange-500/30',
  medium: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
  low: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
};

const RootCauseStrip: React.FC<RootCauseStripProps> = ({
  verdict,
  confidence,
  severity = 'medium',
  recommendation,
  litPanels,
}) => {
  if (!verdict) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
      className="border border-duck-accent/30 bg-duck-accent/5 rounded-lg p-3 mt-2"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="material-symbols-outlined text-duck-accent text-sm">target</span>
            <span className="text-[11px] font-display font-bold text-duck-accent">Root Cause</span>
            {severity && (
              <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border ${severityStyles[severity]}`}>
                {severity.toUpperCase()}
              </span>
            )}
          </div>
          <p className="text-[11px] text-slate-200 leading-relaxed">{verdict}</p>
          {recommendation && (
            <p className="text-[10px] text-slate-400 mt-1.5 italic">{recommendation}</p>
          )}
          {litPanels && litPanels.length > 0 && (
            <div className="flex items-center gap-1.5 mt-2">
              <span className="text-[9px] text-slate-500">Evidence from:</span>
              {litPanels.map((p) => (
                <span key={p} className="text-[9px] px-1.5 py-0.5 rounded bg-duck-accent/10 text-duck-accent border border-duck-accent/20">
                  {p}
                </span>
              ))}
            </div>
          )}
        </div>
        {/* Confidence arc */}
        <div className="shrink-0 flex flex-col items-center">
          <svg width="48" height="48" viewBox="0 0 48 48">
            <circle cx="24" cy="24" r="20" fill="none" stroke="#3d3528" strokeWidth="3" />
            <circle
              cx="24" cy="24" r="20" fill="none"
              stroke="#e09f3e"
              strokeWidth="3"
              strokeDasharray={`${(confidence / 100) * 125.6} 125.6`}
              strokeLinecap="round"
              transform="rotate(-90 24 24)"
            />
            <text x="24" y="26" textAnchor="middle" fill="#e8e0d4" fontSize="11" fontFamily="DM Sans" fontWeight="700">
              {confidence}%
            </text>
          </svg>
        </div>
      </div>
    </motion.div>
  );
};

export default RootCauseStrip;
```

**Step 2: Commit**
```bash
git add frontend/src/components/Investigation/db-board/RootCauseStrip.tsx
git commit -m "feat(db-board): add RootCauseStrip with confidence arc and evidence links"
```

---

## Task 4: Create DBHealthGauges component (right column)

**Files:**
- Create: `frontend/src/components/Investigation/db-board/DBHealthGauges.tsx`

**Step 1: Create the 4-gauge health panel**

Shows cache hit ratio, TPS, deadlocks, uptime as mini arc gauges.

```tsx
import React from 'react';

interface GaugeData {
  label: string;
  value: string;
  pct: number; // 0-100 for arc fill
  color: string;
}

interface DBHealthGaugesProps {
  cacheHitRatio?: number;
  tps?: number;
  deadlocks?: number;
  uptimeSeconds?: number;
}

function MiniGauge({ label, value, pct, color }: GaugeData) {
  const arc = (pct / 100) * 94.2; // circumference of r=15
  return (
    <div className="flex flex-col items-center gap-1">
      <svg width="40" height="40" viewBox="0 0 40 40">
        <circle cx="20" cy="20" r="15" fill="none" stroke="#3d3528" strokeWidth="2.5" />
        <circle
          cx="20" cy="20" r="15" fill="none"
          stroke={color}
          strokeWidth="2.5"
          strokeDasharray={`${arc} 94.2`}
          strokeLinecap="round"
          transform="rotate(-90 20 20)"
        />
        <text x="20" y="22" textAnchor="middle" fill="#e8e0d4" fontSize="9" fontWeight="700" fontFamily="DM Sans">
          {value}
        </text>
      </svg>
      <span className="text-[9px] text-slate-500">{label}</span>
    </div>
  );
}

function formatUptime(sec: number): string {
  if (sec >= 86400) return `${Math.floor(sec / 86400)}d`;
  if (sec >= 3600) return `${Math.floor(sec / 3600)}h`;
  return `${Math.floor(sec / 60)}m`;
}

const DBHealthGauges: React.FC<DBHealthGaugesProps> = ({
  cacheHitRatio,
  tps,
  deadlocks,
  uptimeSeconds,
}) => {
  const gauges: GaugeData[] = [
    {
      label: 'Cache Hit',
      value: cacheHitRatio != null ? `${(cacheHitRatio * 100).toFixed(0)}%` : '—',
      pct: cacheHitRatio != null ? cacheHitRatio * 100 : 0,
      color: (cacheHitRatio ?? 1) >= 0.95 ? '#10b981' : (cacheHitRatio ?? 1) >= 0.8 ? '#f59e0b' : '#ef4444',
    },
    {
      label: 'TPS',
      value: tps != null ? (tps >= 1000 ? `${(tps / 1000).toFixed(1)}K` : String(Math.round(tps))) : '—',
      pct: tps != null ? Math.min((tps / 5000) * 100, 100) : 0,
      color: '#e09f3e',
    },
    {
      label: 'Deadlocks',
      value: deadlocks != null ? String(deadlocks) : '—',
      pct: deadlocks != null ? Math.min(deadlocks * 20, 100) : 0,
      color: (deadlocks ?? 0) === 0 ? '#10b981' : '#ef4444',
    },
    {
      label: 'Uptime',
      value: uptimeSeconds != null ? formatUptime(uptimeSeconds) : '—',
      pct: uptimeSeconds != null ? Math.min((uptimeSeconds / 604800) * 100, 100) : 0,
      color: '#10b981',
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-3">
      {gauges.map((g) => (
        <MiniGauge key={g.label} {...g} />
      ))}
    </div>
  );
};

export default DBHealthGauges;
```

**Step 2: Commit**
```bash
git add frontend/src/components/Investigation/db-board/DBHealthGauges.tsx
git commit -m "feat(db-board): add DBHealthGauges with 4 mini arc gauges"
```

---

## Task 5: Rewrite DatabaseWarRoom with Investigation Board layout

**Files:**
- Modify: `frontend/src/components/Investigation/DatabaseWarRoom.tsx` (full rewrite)

**Step 1: Rewrite the component**

This is the main orchestrator. It wires the 6 instrument panels, case file, map column, and root cause strip together. Derives panel states from event stream.

```tsx
import React, { useState, useMemo, useEffect, useRef } from 'react';
import type { V4Session, TaskEvent, DiagnosticPhase } from '../../types';

// Board components
import InstrumentPanel from './db-board/InstrumentPanel';
import type { PanelState } from './db-board/InstrumentPanel';
import CaseFile from './db-board/CaseFile';
import RootCauseStrip from './db-board/RootCauseStrip';
import DBHealthGauges from './db-board/DBHealthGauges';

// Existing db-viz components
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

// Derive panel state from events for a given agent
function derivePanelState(events: TaskEvent[], agentName: string, dataKey: string): PanelState {
  const agentEvents = events.filter((e) => e.agent_name === agentName);
  if (agentEvents.length === 0) return 'dormant';
  const hasFinding = agentEvents.some((e) => e.event_type === 'finding' && e.details?.[dataKey]);
  if (hasFinding) return 'lit';
  const hasActivity = agentEvents.some((e) => ['started', 'progress'].includes(e.event_type));
  if (hasActivity) return 'scanning';
  return 'dormant';
}

// Extract structured data from events
function extractFromEvents<T>(events: TaskEvent[], agentName: string, key: string): T | null {
  for (let i = events.length - 1; i >= 0; i--) {
    const ev = events[i];
    if (ev.agent_name === agentName && ev.details?.[key]) {
      return ev.details[key] as T;
    }
  }
  return null;
}

const DatabaseWarRoom: React.FC<DatabaseWarRoomProps> = ({
  session,
  events,
  wsConnected,
  phase,
  confidence,
}) => {
  // Elapsed time counter
  const [elapsedSec, setElapsedSec] = useState(0);
  const startRef = useRef(Date.now());
  useEffect(() => {
    const iv = setInterval(() => setElapsedSec(Math.floor((Date.now() - startRef.current) / 1000)), 1000);
    return () => clearInterval(iv);
  }, []);

  // Derive panel states
  const panelStates = useMemo(() => ({
    queries: derivePanelState(events, 'query_analyst', 'slow_queries'),
    connPool: derivePanelState(events, 'health_analyst', 'connections'),
    indexes: derivePanelState(events, 'schema_analyst', 'indexes'),
    bloat: derivePanelState(events, 'schema_analyst', 'table_bloat'),
    explainPlan: derivePanelState(events, 'query_analyst', 'explain_plan'),
    schemaDrift: derivePanelState(events, 'schema_analyst', 'schema_changes'),
  }), [events]);

  // Extract data for lit panels
  const slowQueries = extractFromEvents<any[]>(events, 'query_analyst', 'slow_queries');
  const planSteps = extractFromEvents<any[]>(events, 'query_analyst', 'plan_steps');
  const explainPlan = extractFromEvents<any>(events, 'query_analyst', 'explain_plan');
  const connections = extractFromEvents<any>(events, 'health_analyst', 'connections');
  const indexes = extractFromEvents<any[]>(events, 'schema_analyst', 'indexes');
  const tableBloat = extractFromEvents<any[]>(events, 'schema_analyst', 'table_bloat');
  const replication = extractFromEvents<any>(events, 'health_analyst', 'replication');
  const performance = extractFromEvents<any>(events, 'health_analyst', 'performance');

  // Synthesizer verdict
  const synthEvent = useMemo(() => {
    for (let i = events.length - 1; i >= 0; i--) {
      if (events[i].agent_name === 'synthesizer' && events[i].event_type === 'success') {
        return events[i];
      }
    }
    return null;
  }, [events]);

  const litPanelNames = useMemo(() => {
    const names: string[] = [];
    if (panelStates.queries === 'lit') names.push('Queries');
    if (panelStates.connPool === 'lit') names.push('Connections');
    if (panelStates.indexes === 'lit') names.push('Indexes');
    if (panelStates.bloat === 'lit') names.push('Bloat');
    if (panelStates.explainPlan === 'lit') names.push('Plan');
    return names;
  }, [panelStates]);

  return (
    <div className="flex flex-col h-full overflow-hidden bg-duck-bg">
      {/* Header Bar */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-duck-border bg-duck-card/30 shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-violet-500/10 border border-violet-500/20">
            <span className="material-symbols-outlined text-violet-400 text-lg">database</span>
          </div>
          <div>
            <h1 className="text-sm font-display font-bold text-white">{session.service_name}</h1>
            <p className="text-[10px] text-slate-500">
              Investigation Board — {phase || 'initializing'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[10px] font-mono text-amber-400">{elapsedSec > 0 ? `${Math.floor(elapsedSec / 60)}m ${elapsedSec % 60}s` : '0s'}</span>
          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold ${
            wsConnected ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'
          }`}>
            <span className={`w-1.5 h-1.5 rounded-full ${wsConnected ? 'bg-emerald-400' : 'bg-red-400'}`} />
            {wsConnected ? 'LIVE' : 'OFFLINE'}
          </span>
        </div>
      </div>

      {/* Three-column Investigation Board */}
      <div className="grid grid-cols-12 flex-1 overflow-hidden">

        {/* LEFT: Case File (col-3) */}
        <div className="col-span-3 border-r border-duck-border overflow-hidden">
          <CaseFile
            serviceName={session.service_name}
            sessionId={session.session_id}
            events={events}
            elapsedSec={elapsedSec}
          />
        </div>

        {/* CENTER: The Board — 6 Instrument Panels (col-5) */}
        <div className="col-span-5 overflow-y-auto p-3 custom-scrollbar">
          <div className="grid grid-cols-2 gap-3">
            {/* Row 1 */}
            <InstrumentPanel
              title="Query Performance"
              icon="query_stats"
              agentName="query_analyst"
              state={panelStates.queries}
            >
              {slowQueries && <SlowQueryTimeline queries={slowQueries} />}
              {planSteps && <QueryFlamechart planSteps={planSteps} />}
            </InstrumentPanel>

            <InstrumentPanel
              title="Connection Pool"
              icon="cable"
              agentName="health_analyst"
              state={panelStates.connPool}
            >
              {connections && (
                <ConnectionPoolGauge
                  active={connections.active ?? 0}
                  idle={connections.idle ?? 0}
                  waiting={connections.waiting ?? 0}
                  max={connections.max_connections ?? connections.max ?? 100}
                />
              )}
            </InstrumentPanel>

            {/* Row 2 */}
            <InstrumentPanel
              title="Index Health"
              icon="format_list_numbered"
              agentName="schema_analyst"
              state={panelStates.indexes}
            >
              {indexes && <IndexUsageMatrix indexes={indexes} />}
            </InstrumentPanel>

            <InstrumentPanel
              title="Table Bloat"
              icon="grid_view"
              agentName="schema_analyst"
              state={panelStates.bloat}
            >
              {tableBloat && <TableBloatHeatmap tables={tableBloat} />}
            </InstrumentPanel>

            {/* Row 3 */}
            <InstrumentPanel
              title="Query Plan"
              icon="account_tree"
              agentName="query_analyst"
              state={panelStates.explainPlan}
            >
              {explainPlan && <ExplainPlanTree plan={explainPlan} />}
            </InstrumentPanel>

            <InstrumentPanel
              title="Schema Drift"
              icon="difference"
              agentName="schema_analyst"
              state={panelStates.schemaDrift}
            >
              <div className="text-[10px] text-slate-400 italic">
                No schema changes detected
              </div>
            </InstrumentPanel>
          </div>

          {/* Root Cause Strip */}
          <RootCauseStrip
            verdict={synthEvent?.message || null}
            confidence={confidence}
            severity={synthEvent?.details?.severity as any}
            recommendation={synthEvent?.details?.recommendation as string}
            litPanels={litPanelNames}
          />
        </div>

        {/* RIGHT: The Map (col-4) */}
        <div className="col-span-4 border-l border-duck-border overflow-y-auto p-4 space-y-4 custom-scrollbar">
          {/* Replication Topology */}
          <div>
            <h3 className="text-[11px] font-display font-bold text-slate-400 mb-2">Replication Topology</h3>
            {replication ? (
              <ReplicationTopologySVG
                primary={replication.primary || { host: session.service_name, lag_ms: 0 }}
                replicas={replication.replicas || []}
              />
            ) : (
              <div className="flex items-center justify-center h-24 border border-duck-border/30 rounded-lg">
                <span className="text-[10px] text-slate-600 italic">Awaiting replication data...</span>
              </div>
            )}
          </div>

          {/* Health Gauges */}
          <div>
            <h3 className="text-[11px] font-display font-bold text-slate-400 mb-2">Health Gauges</h3>
            <DBHealthGauges
              cacheHitRatio={performance?.cache_hit_ratio}
              tps={performance?.transactions_per_sec}
              deadlocks={performance?.deadlocks}
              uptimeSeconds={performance?.uptime_seconds}
            />
          </div>

          {/* Agent Status (compact) */}
          <div>
            <h3 className="text-[11px] font-display font-bold text-slate-400 mb-2">Agent Status</h3>
            <div className="space-y-1.5">
              {DB_AGENTS.map((agent) => {
                const agentEvents = events.filter((e) => e.agent_name === agent);
                const lastEvent = agentEvents[agentEvents.length - 1];
                const status = lastEvent?.event_type || 'pending';
                return (
                  <div key={agent} className="flex items-center justify-between px-2.5 py-1.5 bg-duck-card/20 rounded">
                    <span className="text-[10px] text-slate-400">{agent.replace(/_/g, ' ')}</span>
                    <span className={`material-symbols-outlined text-sm ${
                      status === 'success' ? 'text-emerald-400' :
                      status === 'error' ? 'text-red-400' :
                      ['started', 'progress'].includes(status) ? 'text-amber-400 animate-spin' :
                      'text-slate-600'
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

          {/* Investigation Summary (when complete) */}
          {phase === 'complete' && synthEvent && (
            <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-lg p-3">
              <div className="flex items-center gap-2 mb-1">
                <span className="material-symbols-outlined text-emerald-400 text-sm">check_circle</span>
                <span className="text-[11px] font-display font-bold text-emerald-400">Investigation Complete</span>
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
git commit -m "feat(db-board): rewrite DatabaseWarRoom as Investigation Board with 6 instrument panels"
```

---

## Task 6: Verify integration in App.tsx

**Files:**
- Read: `frontend/src/App.tsx` (lines 669-690 — the DatabaseWarRoom render)

**Step 1: Verify props are unchanged**

The new DatabaseWarRoom accepts the same props as the old one:
- `session: V4Session`
- `events: TaskEvent[]`
- `wsConnected: boolean`
- `phase: DiagnosticPhase | null`
- `confidence: number`

No changes needed in App.tsx — the import and usage remain identical.

**Step 2: Run dev server and verify no crashes**
```bash
cd frontend && npm run dev
```
Navigate to Database Diagnostics → start a session → verify the 3-column board renders with dormant panels.

**Step 3: Commit (if any fixes needed)**
```bash
git commit -m "fix(db-board): integration fixes for Investigation Board"
```
