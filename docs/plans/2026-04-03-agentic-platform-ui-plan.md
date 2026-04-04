# Agentic Platform UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the three Platform UI views (Agent Catalog, Workflow Builder, Workflow Runs) against the existing backend API — no backend changes required.

**Architecture:** Three new views added under a "Platform" nav group in SidebarNav. Agent Catalog uses the existing `GET /api/v4/agents` and `GET /api/v4/agents/{id}/executions` endpoints. Workflow Builder is pure frontend (YAML textarea + ReactFlow DAG preview, saves to localStorage). Workflow Runs reframes the existing sessions API (`GET /api/v4/sessions`, `GET /api/v4/session/{id}/status`) as workflow run history.

**Tech Stack:** React + TypeScript + Tailwind, ReactFlow (already installed) for DAG preview, react-syntax-highlighter (already installed) for YAML display. No new dependencies.

---

## Task 1: Add Platform nav group and route wiring

**Files:**
- Modify: `frontend/src/components/Layout/SidebarNav.tsx`
- Modify: `frontend/src/App.tsx`

**Step 1: Add Platform NavView types to SidebarNav**

In `frontend/src/components/Layout/SidebarNav.tsx`, find the `NavView` type on line 4 and add the three new views:

```typescript
export type NavView = 'home' | 'sessions' | 'app-diagnostics' | 'cluster-diagnostics'
  | /* existing views */ 'agent-catalog' | 'workflow-builder' | 'workflow-runs';
```

Then add a new nav group to the `navItems` array after the `agent-matrix` link:

```typescript
{
  kind: 'group', group: 'Platform', icon: 'hub',
  children: [
    { id: 'agent-catalog', label: 'Agent Catalog', icon: 'smart_toy', badge: 'NEW' },
    { id: 'workflow-builder', label: 'Workflow Builder', icon: 'account_tree', badge: 'NEW' },
    { id: 'workflow-runs', label: 'Workflow Runs', icon: 'play_circle', badge: 'NEW' },
  ],
},
```

**Step 2: Run TypeScript check — expect NavView errors in App.tsx**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "NavView\|agent-catalog\|workflow"
```

Expected: errors saying `'agent-catalog'` not assignable to NavView in App.tsx (because App.tsx switch cases don't have the new views yet).

**Step 3: Wire routes in App.tsx**

Add imports at the top of `frontend/src/App.tsx` (after existing imports):

```typescript
import AgentCatalogView from './components/Platform/AgentCatalog/AgentCatalogView';
import WorkflowBuilderView from './components/Platform/WorkflowBuilder/WorkflowBuilderView';
import WorkflowRunsView from './components/Platform/WorkflowRuns/WorkflowRunsView';
```

Find the main view switch/conditional in App.tsx (where `AgentMatrixView` is rendered, around line 760) and add:

```typescript
{currentView === 'agent-catalog' && <AgentCatalogView />}
{currentView === 'workflow-builder' && <WorkflowBuilderView />}
{currentView === 'workflow-runs' && <WorkflowRunsView />}
```

**Step 4: Create stub components so TypeScript resolves**

Create `frontend/src/components/Platform/AgentCatalog/AgentCatalogView.tsx`:
```typescript
import React from 'react';
const AgentCatalogView: React.FC = () => <div>Agent Catalog — coming soon</div>;
export default AgentCatalogView;
```

Create `frontend/src/components/Platform/WorkflowBuilder/WorkflowBuilderView.tsx`:
```typescript
import React from 'react';
const WorkflowBuilderView: React.FC = () => <div>Workflow Builder — coming soon</div>;
export default WorkflowBuilderView;
```

Create `frontend/src/components/Platform/WorkflowRuns/WorkflowRunsView.tsx`:
```typescript
import React from 'react';
const WorkflowRunsView: React.FC = () => <div>Workflow Runs — coming soon</div>;
export default WorkflowRunsView;
```

**Step 5: Check TypeScript resolves**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -E "Platform|agent-catalog|workflow-builder|workflow-runs"
```

Expected: no errors for the new files.

**Step 6: Commit**

```bash
git add frontend/src/components/Layout/SidebarNav.tsx \
        frontend/src/App.tsx \
        frontend/src/components/Platform/
git commit -m "feat(platform): add Platform nav group and stub routes"
```

---

## Task 2: Agent Catalog — list view

**Files:**
- Create: `frontend/src/components/Platform/AgentCatalog/AgentCatalogView.tsx`
- Create: `frontend/src/components/Platform/AgentCatalog/AgentCatalogCard.tsx`
- Create: `frontend/src/components/Platform/AgentCatalog/useAgentCatalog.ts`

**Step 1: Create the data hook**

Create `frontend/src/components/Platform/AgentCatalog/useAgentCatalog.ts`:

```typescript
import { useState, useEffect, useCallback } from 'react';
import { API_BASE_URL } from '../../../services/api';

export interface CatalogAgent {
  id: string;
  name: string;
  workflow: string;
  role: string;
  description: string;
  status: 'active' | 'degraded' | 'offline';
  degraded_tools: string[];
  tools: string[];
  timeout_s: number;
  llm_config?: { model?: string };
}

export function useAgentCatalog() {
  const [agents, setAgents] = useState<CatalogAgent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    try {
      setLoading(true);
      const res = await window.fetch(`${API_BASE_URL}/api/v4/agents`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setAgents(data.agents || []);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetch(); }, [fetch]);

  return { agents, loading, error, refresh: fetch };
}
```

**Step 2: Create AgentCatalogCard**

Create `frontend/src/components/Platform/AgentCatalog/AgentCatalogCard.tsx`:

```typescript
import React from 'react';
import type { CatalogAgent } from './useAgentCatalog';

const STATUS_COLOR: Record<string, string> = {
  active: '#22c55e',
  degraded: '#f59e0b',
  offline: '#ef4444',
};

const ROLE_COLOR: Record<string, string> = {
  orchestrator: '#07b6d5',
  analysis: '#a855f7',
  validation: '#22c55e',
  'fix-generation': '#e09f3e',
};

interface Props {
  agent: CatalogAgent;
  selected: boolean;
  onClick: () => void;
}

const AgentCatalogCard: React.FC<Props> = ({ agent, selected, onClick }) => (
  <div
    onClick={onClick}
    style={{
      background: selected ? 'rgba(7,182,213,0.08)' : 'rgba(255,255,255,0.02)',
      border: `1px solid ${selected ? '#07b6d5' : '#1e2a2e'}`,
      borderRadius: 8, padding: '12px 14px', cursor: 'pointer',
      transition: 'border-color 0.15s',
    }}
  >
    <div className="flex items-start justify-between gap-2">
      <div className="flex items-center gap-2 min-w-0">
        <span
          className="material-symbols-outlined flex-shrink-0"
          style={{ fontSize: 16, color: ROLE_COLOR[agent.role] || '#64748b' }}
        >
          smart_toy
        </span>
        <span className="text-xs font-mono font-semibold truncate" style={{ color: '#e8e0d4' }}>
          {agent.name}
        </span>
      </div>
      <span
        className="w-2 h-2 rounded-full flex-shrink-0 mt-1"
        style={{ background: STATUS_COLOR[agent.status] }}
        title={agent.status}
      />
    </div>

    <div className="mt-1 text-[10px] font-mono truncate" style={{ color: '#64748b' }}>
      {agent.id}
    </div>

    <div className="mt-2 flex items-center gap-2 flex-wrap">
      <span
        className="text-[9px] font-mono px-1.5 py-0.5 rounded"
        style={{
          background: `${ROLE_COLOR[agent.role] || '#64748b'}20`,
          color: ROLE_COLOR[agent.role] || '#64748b',
          border: `1px solid ${ROLE_COLOR[agent.role] || '#64748b'}40`,
        }}
      >
        {agent.role}
      </span>
      <span className="text-[9px] font-mono" style={{ color: '#3d4a50' }}>
        {agent.workflow}
      </span>
    </div>

    {agent.tools.length > 0 && (
      <div className="mt-2 text-[9px] font-mono" style={{ color: '#4a5568' }}>
        {agent.tools.length} tool{agent.tools.length !== 1 ? 's' : ''}
        {agent.timeout_s && ` · ${agent.timeout_s}s timeout`}
      </div>
    )}
  </div>
);

export default AgentCatalogCard;
```

**Step 3: Build AgentCatalogView with search + filter**

Replace the stub in `frontend/src/components/Platform/AgentCatalog/AgentCatalogView.tsx`:

```typescript
import React, { useState, useMemo } from 'react';
import { useAgentCatalog } from './useAgentCatalog';
import AgentCatalogCard from './AgentCatalogCard';
import AgentDetailPanel from './AgentDetailPanel';
import type { CatalogAgent } from './useAgentCatalog';

const WORKFLOWS = ['all', 'app_diagnostics', 'cluster_diagnostics', 'network', 'database'];

const AgentCatalogView: React.FC = () => {
  const { agents, loading, error, refresh } = useAgentCatalog();
  const [search, setSearch] = useState('');
  const [workflowFilter, setWorkflowFilter] = useState('all');
  const [selected, setSelected] = useState<CatalogAgent | null>(null);

  const filtered = useMemo(() => agents.filter(a => {
    const matchesSearch = !search ||
      a.name.toLowerCase().includes(search.toLowerCase()) ||
      a.id.toLowerCase().includes(search.toLowerCase());
    const matchesWorkflow = workflowFilter === 'all' || a.workflow === workflowFilter;
    return matchesSearch && matchesWorkflow;
  }), [agents, search, workflowFilter]);

  return (
    <div className="flex h-full" style={{ background: '#0a1214' }}>
      {/* Left: catalog list */}
      <div className="flex flex-col" style={{ width: selected ? 360 : '100%', borderRight: '1px solid #1e2a2e', transition: 'width 0.2s' }}>
        {/* Header */}
        <div className="px-5 pt-5 pb-3 border-b" style={{ borderColor: '#1e2a2e' }}>
          <div className="flex items-center justify-between mb-3">
            <div>
              <h1 className="text-base font-mono font-bold" style={{ color: '#e8e0d4' }}>Agent Catalog</h1>
              <p className="text-xs font-mono mt-0.5" style={{ color: '#64748b' }}>
                {agents.length} agents · {agents.filter(a => a.status === 'active').length} active
              </p>
            </div>
            <button onClick={refresh} className="p-1.5 rounded" style={{ color: '#64748b' }}>
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>refresh</span>
            </button>
          </div>

          {/* Search */}
          <div className="relative mb-2">
            <span className="material-symbols-outlined absolute left-2 top-1/2 -translate-y-1/2 text-sm" style={{ color: '#64748b', fontSize: 15 }}>search</span>
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search agents..."
              className="w-full pl-8 pr-3 py-1.5 rounded text-xs font-mono outline-none"
              style={{ background: '#0f1e22', border: '1px solid #1e2a2e', color: '#e8e0d4' }}
            />
          </div>

          {/* Workflow filter pills */}
          <div className="flex gap-1 flex-wrap">
            {WORKFLOWS.map(w => (
              <button
                key={w}
                onClick={() => setWorkflowFilter(w)}
                className="px-2 py-0.5 rounded text-[9px] font-mono transition-colors"
                style={{
                  background: workflowFilter === w ? 'rgba(7,182,213,0.15)' : 'transparent',
                  border: `1px solid ${workflowFilter === w ? '#07b6d5' : '#1e2a2e'}`,
                  color: workflowFilter === w ? '#07b6d5' : '#64748b',
                }}
              >
                {w === 'all' ? 'All' : w.replace('_', ' ')}
              </button>
            ))}
          </div>
        </div>

        {/* Grid */}
        <div className="flex-1 overflow-auto p-4">
          {loading && (
            <div className="flex items-center justify-center h-32 text-xs font-mono" style={{ color: '#64748b' }}>
              Loading agents...
            </div>
          )}
          {error && (
            <div className="flex items-center justify-center h-32 text-xs font-mono" style={{ color: '#ef4444' }}>
              {error}
            </div>
          )}
          {!loading && !error && (
            <div className="grid gap-2" style={{ gridTemplateColumns: selected ? '1fr' : 'repeat(auto-fill, minmax(220px, 1fr))' }}>
              {filtered.map(agent => (
                <AgentCatalogCard
                  key={agent.id}
                  agent={agent}
                  selected={selected?.id === agent.id}
                  onClick={() => setSelected(selected?.id === agent.id ? null : agent)}
                />
              ))}
            </div>
          )}
          {!loading && !error && filtered.length === 0 && (
            <div className="text-xs font-mono text-center py-12" style={{ color: '#64748b' }}>
              No agents match your filter.
            </div>
          )}
        </div>
      </div>

      {/* Right: detail panel */}
      {selected && (
        <div className="flex-1 overflow-hidden">
          <AgentDetailPanel agent={selected} onClose={() => setSelected(null)} />
        </div>
      )}
    </div>
  );
};

export default AgentCatalogView;
```

**Step 4: Create stub AgentDetailPanel so it compiles**

Create `frontend/src/components/Platform/AgentCatalog/AgentDetailPanel.tsx`:

```typescript
import React from 'react';
import type { CatalogAgent } from './useAgentCatalog';

interface Props { agent: CatalogAgent; onClose: () => void; }

const AgentDetailPanel: React.FC<Props> = ({ agent, onClose }) => (
  <div className="h-full flex flex-col" style={{ background: '#0c1a1f' }}>
    <div className="flex items-center justify-between px-5 py-4 border-b" style={{ borderColor: '#1e2a2e' }}>
      <span className="text-sm font-mono font-bold" style={{ color: '#e8e0d4' }}>{agent.name}</span>
      <button onClick={onClose}><span className="material-symbols-outlined" style={{ fontSize: 18, color: '#64748b' }}>close</span></button>
    </div>
    <div className="p-5 text-xs font-mono" style={{ color: '#64748b' }}>Detail panel — Task 3</div>
  </div>
);

export default AgentDetailPanel;
```

**Step 5: Check TypeScript**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "Platform/AgentCatalog"
```

Expected: no errors.

**Step 6: Commit**

```bash
git add frontend/src/components/Platform/AgentCatalog/
git commit -m "feat(platform): agent catalog list view with search and workflow filter"
```

---

## Task 3: Agent Catalog — detail panel

**Files:**
- Modify: `frontend/src/components/Platform/AgentCatalog/AgentDetailPanel.tsx`

**Step 1: Fetch agent executions**

Replace `AgentDetailPanel.tsx` with the full implementation:

```typescript
import React, { useState, useEffect } from 'react';
import { API_BASE_URL } from '../../../services/api';
import type { CatalogAgent } from './useAgentCatalog';

interface Execution {
  execution_id: string;
  status: string;
  started_at: string;
  duration_ms?: number;
  findings_count?: number;
}

interface Props { agent: CatalogAgent; onClose: () => void; }

const STATUS_COLOR: Record<string, string> = {
  completed: '#22c55e', failed: '#ef4444', timed_out: '#f59e0b', running: '#07b6d5',
};

const copyYaml = (agent: CatalogAgent) => {
  const yaml = `- id: ${agent.id}\n  agent: ${agent.id}\n  input:\n    # fill required fields\n`;
  navigator.clipboard.writeText(yaml);
};

const AgentDetailPanel: React.FC<Props> = ({ agent, onClose }) => {
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    window.fetch(`${API_BASE_URL}/api/v4/agents/${agent.id}/executions`)
      .then(r => r.ok ? r.json() : { executions: [] })
      .then(d => setExecutions(d.executions || []))
      .catch(() => {});
  }, [agent.id]);

  const handleCopy = () => {
    copyYaml(agent);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="h-full flex flex-col overflow-hidden" style={{ background: '#0c1a1f' }}>
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b flex-shrink-0" style={{ borderColor: '#1e2a2e' }}>
        <div>
          <div className="text-sm font-mono font-bold" style={{ color: '#e8e0d4' }}>{agent.name}</div>
          <div className="text-[10px] font-mono mt-0.5" style={{ color: '#64748b' }}>{agent.id}</div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleCopy}
            className="flex items-center gap-1 px-2.5 py-1 rounded text-[10px] font-mono"
            style={{ border: '1px solid #1e2a2e', color: copied ? '#22c55e' : '#64748b', background: 'transparent' }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 13 }}>{copied ? 'check' : 'content_copy'}</span>
            {copied ? 'Copied!' : 'Copy YAML'}
          </button>
          <button onClick={onClose}>
            <span className="material-symbols-outlined" style={{ fontSize: 18, color: '#64748b' }}>close</span>
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-auto px-5 py-4 space-y-5">
        {/* Description */}
        <div>
          <div className="text-[10px] font-mono uppercase tracking-widest mb-1" style={{ color: '#3d4a50' }}>Description</div>
          <div className="text-xs font-mono" style={{ color: '#9a9080' }}>{agent.description || '—'}</div>
        </div>

        {/* Meta */}
        <div className="grid grid-cols-2 gap-3">
          {[
            { label: 'Workflow', value: agent.workflow },
            { label: 'Role', value: agent.role },
            { label: 'Timeout', value: agent.timeout_s ? `${agent.timeout_s}s` : '—' },
            { label: 'Model', value: agent.llm_config?.model || 'default' },
          ].map(({ label, value }) => (
            <div key={label} className="rounded p-2.5" style={{ background: '#0a1214', border: '1px solid #1a2428' }}>
              <div className="text-[9px] font-mono uppercase tracking-widest mb-1" style={{ color: '#3d4a50' }}>{label}</div>
              <div className="text-xs font-mono truncate" style={{ color: '#e8e0d4' }}>{value}</div>
            </div>
          ))}
        </div>

        {/* Tools */}
        <div>
          <div className="text-[10px] font-mono uppercase tracking-widest mb-2" style={{ color: '#3d4a50' }}>Tools</div>
          {agent.tools.length === 0 ? (
            <div className="text-xs font-mono" style={{ color: '#3d4a50' }}>No tools defined</div>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {agent.tools.map(t => (
                <span
                  key={t}
                  className="px-2 py-0.5 rounded text-[10px] font-mono"
                  style={{ background: 'rgba(7,182,213,0.08)', border: '1px solid rgba(7,182,213,0.2)', color: '#07b6d5' }}
                >
                  {t}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Standalone invocation — disabled */}
        <div className="rounded p-3" style={{ background: '#0a1214', border: '1px solid #1a2428' }}>
          <div className="flex items-center gap-2 mb-1">
            <span className="material-symbols-outlined" style={{ fontSize: 14, color: '#3d4a50' }}>play_circle</span>
            <span className="text-xs font-mono font-semibold" style={{ color: '#3d4a50' }}>Try it</span>
            <span className="text-[9px] font-mono px-1.5 py-0.5 rounded" style={{ background: '#1a2428', color: '#4a5568' }}>COMING SOON</span>
          </div>
          <div className="text-[10px] font-mono" style={{ color: '#3d4a50' }}>
            Standalone agent invocation available after platform backend ships.
          </div>
        </div>

        {/* Recent executions */}
        <div>
          <div className="text-[10px] font-mono uppercase tracking-widest mb-2" style={{ color: '#3d4a50' }}>Recent Executions</div>
          {executions.length === 0 ? (
            <div className="text-xs font-mono" style={{ color: '#3d4a50' }}>No recent executions</div>
          ) : (
            <div className="space-y-1.5">
              {executions.slice(0, 5).map(ex => (
                <div
                  key={ex.execution_id}
                  className="flex items-center justify-between text-[10px] font-mono rounded px-2.5 py-2"
                  style={{ background: '#0a1214', border: '1px solid #1a2428' }}
                >
                  <span style={{ color: STATUS_COLOR[ex.status] || '#64748b' }}>● {ex.status}</span>
                  <span style={{ color: '#4a5568' }}>{ex.duration_ms ? `${(ex.duration_ms / 1000).toFixed(1)}s` : '—'}</span>
                  <span style={{ color: '#3d4a50' }}>{ex.started_at ? new Date(ex.started_at).toLocaleTimeString() : '—'}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default AgentDetailPanel;
```

**Step 2: Check TypeScript**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "AgentDetailPanel"
```

Expected: no errors.

**Step 3: Commit**

```bash
git add frontend/src/components/Platform/AgentCatalog/AgentDetailPanel.tsx
git commit -m "feat(platform): agent detail panel with tools, executions, copy YAML"
```

---

## Task 4: Workflow Builder — YAML editor + DAG preview

**Files:**
- Create: `frontend/src/components/Platform/WorkflowBuilder/workflowParser.ts`
- Create: `frontend/src/components/Platform/WorkflowBuilder/WorkflowDagPreview.tsx`
- Create: `frontend/src/components/Platform/WorkflowBuilder/WorkflowValidation.tsx`
- Modify: `frontend/src/components/Platform/WorkflowBuilder/WorkflowBuilderView.tsx`

**Step 1: Write the workflow YAML parser (no external lib)**

Create `frontend/src/components/Platform/WorkflowBuilder/workflowParser.ts`:

```typescript
export interface WorkflowStep {
  id: string;
  agent: string;
  depends_on: string[];
  condition?: string;
  gate?: string;
}

export interface ParsedWorkflow {
  id?: string;
  name?: string;
  steps: WorkflowStep[];
  errors: string[];
}

export function parseWorkflowYaml(yaml: string): ParsedWorkflow {
  const errors: string[] = [];
  const steps: WorkflowStep[] = [];

  // Extract top-level id and name
  const idMatch = yaml.match(/^id:\s*(.+)$/m);
  const nameMatch = yaml.match(/^name:\s*(.+)$/m);

  // Find all step blocks (lines under "steps:")
  const stepsSection = yaml.split(/^steps:\s*$/m)[1] || '';
  const stepBlocks = stepsSection.split(/(?=\n\s{2}-\s)/);

  for (const block of stepBlocks) {
    const idM = block.match(/[-\s]+id:\s*(\S+)/);
    const agentM = block.match(/\s+agent:\s*(\S+)/);
    if (!idM) continue;

    const stepId = idM[1];
    const agent = agentM ? agentM[1] : '';

    if (!agent) errors.push(`Step '${stepId}': missing agent field`);

    // Parse depends_on
    const depends_on: string[] = [];
    const depsMatch = block.match(/depends_on:\s*\[([^\]]*)\]/);
    if (depsMatch) {
      depsMatch[1].split(',').forEach(d => {
        const trimmed = d.trim().replace(/['"]/g, '');
        if (trimmed) depends_on.push(trimmed);
      });
    } else {
      // Multi-line depends_on
      const multiLine = block.match(/depends_on:\s*\n((?:\s+-\s+\S+\n?)+)/);
      if (multiLine) {
        multiLine[1].match(/\S+/g)?.forEach(d => depends_on.push(d.replace('-', '').trim()));
      }
    }

    const conditionM = block.match(/condition:\s*"(.+)"/);
    const gateM = block.match(/gate:\s*(\S+)/);

    steps.push({
      id: stepId,
      agent,
      depends_on,
      condition: conditionM?.[1],
      gate: gateM?.[1],
    });
  }

  // Validate: check depends_on references exist
  const stepIds = new Set(steps.map(s => s.id));
  steps.forEach(step => {
    step.depends_on.forEach(dep => {
      if (!stepIds.has(dep)) {
        errors.push(`Step '${step.id}': depends_on '${dep}' not found`);
      }
    });
  });

  // Detect cycles via DFS
  const visited = new Set<string>();
  const inStack = new Set<string>();
  const hasCycle = (id: string): boolean => {
    if (inStack.has(id)) return true;
    if (visited.has(id)) return false;
    visited.add(id); inStack.add(id);
    const step = steps.find(s => s.id === id);
    for (const dep of step?.depends_on || []) {
      if (hasCycle(dep)) return true;
    }
    inStack.delete(id);
    return false;
  };
  steps.forEach(s => { if (hasCycle(s.id)) errors.push(`Cycle detected involving step '${s.id}'`); });

  return { id: idMatch?.[1], name: nameMatch?.[1], steps, errors };
}

export const APP_DIAGNOSTICS_TEMPLATE = `id: app_diagnostics
name: Application Diagnostics
version: "3.0"
trigger: [api, event]

triggers:
  inputs:
    - name: service_name
      label: "Service Name"
      type: string
      required: true
    - name: time_window
      type: select
      options: ["15m", "1h", "6h", "24h"]
      default: "1h"

steps:
  - id: logs
    agent: log_analysis_agent
    depends_on: []
    input:
      service_name: "{{ trigger.service_name }}"
      time_window: "{{ trigger.time_window }}"

  - id: metrics
    agent: metrics_agent
    depends_on: []
    input:
      service_name: "{{ trigger.service_name }}"

  - id: k8s
    agent: k8s_agent
    depends_on: []
    input:
      namespace: "{{ trigger.namespace | default('default') }}"

  - id: critic
    agent: critic_agent
    depends_on: [logs, metrics, k8s]
    condition: "{{ steps.logs.output.confidence < 0.7 }}"

  - id: fix
    agent: fix_generator
    depends_on: [critic]
    gate: human_approval
    gate_timeout: 30m
`;
```

**Step 2: Build DAG preview with ReactFlow**

Create `frontend/src/components/Platform/WorkflowBuilder/WorkflowDagPreview.tsx`:

```typescript
import React, { useMemo } from 'react';
import ReactFlow, { Background, Controls, type Node, type Edge } from 'reactflow';
import 'reactflow/dist/style.css';
import type { ParsedWorkflow } from './workflowParser';

const NODE_W = 160;
const NODE_H = 48;

const GATE_COLOR: Record<string, string> = {
  human_approval: '#f59e0b',
};

interface Props { workflow: ParsedWorkflow; }

export const WorkflowDagPreview: React.FC<Props> = ({ workflow }) => {
  const { nodes, edges } = useMemo(() => {
    const steps = workflow.steps;
    if (steps.length === 0) return { nodes: [], edges: [] };

    // Simple layered layout — compute depth of each step
    const depth: Record<string, number> = {};
    const getDepth = (id: string): number => {
      if (depth[id] !== undefined) return depth[id];
      const step = steps.find(s => s.id === id);
      if (!step || step.depends_on.length === 0) return (depth[id] = 0);
      return (depth[id] = Math.max(...step.depends_on.map(d => getDepth(d) + 1)));
    };
    steps.forEach(s => getDepth(s.id));

    // Group steps by depth layer
    const layers: Record<number, string[]> = {};
    steps.forEach(s => {
      const d = depth[s.id] || 0;
      layers[d] = layers[d] || [];
      layers[d].push(s.id);
    });

    const nodes: Node[] = steps.map(step => {
      const layer = depth[step.id] || 0;
      const siblings = layers[layer];
      const siblingIdx = siblings.indexOf(step.id);
      const x = layer * (NODE_W + 60);
      const y = siblingIdx * (NODE_H + 20) - ((siblings.length - 1) * (NODE_H + 20)) / 2 + 200;

      return {
        id: step.id,
        position: { x, y },
        data: { label: step.id, agent: step.agent, gate: step.gate, condition: step.condition },
        style: {
          background: step.gate ? 'rgba(245,158,11,0.12)' : 'rgba(7,182,213,0.08)',
          border: `1px solid ${step.gate ? '#f59e0b' : '#07b6d5'}40`,
          borderRadius: 6, padding: '6px 10px', fontSize: 10, fontFamily: 'monospace',
          color: '#e8e0d4', width: NODE_W,
        },
      };
    });

    const edges: Edge[] = [];
    steps.forEach(step => {
      step.depends_on.forEach(dep => {
        edges.push({
          id: `${dep}-${step.id}`,
          source: dep,
          target: step.id,
          style: { stroke: '#1e2a2e', strokeWidth: 1.5 },
          animated: false,
        });
      });
    });

    return { nodes, edges };
  }, [workflow]);

  if (workflow.steps.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-xs font-mono" style={{ color: '#3d4a50', background: '#080f12' }}>
        No steps defined yet
      </div>
    );
  }

  return (
    <div style={{ width: '100%', height: '100%', background: '#080f12' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
      >
        <Background color="#1e2a2e" gap={20} />
        <Controls showInteractive={false} style={{ background: '#0c1a1f', border: '1px solid #1e2a2e' }} />
      </ReactFlow>
    </div>
  );
};

export default WorkflowDagPreview;
```

**Step 3: Build WorkflowBuilderView**

Replace stub in `frontend/src/components/Platform/WorkflowBuilder/WorkflowBuilderView.tsx`:

```typescript
import React, { useState, useMemo, useEffect } from 'react';
import { parseWorkflowYaml, APP_DIAGNOSTICS_TEMPLATE } from './workflowParser';
import WorkflowDagPreview from './WorkflowDagPreview';

const LS_KEY = 'platform_workflow_builder_yaml';

const WorkflowBuilderView: React.FC = () => {
  const [yaml, setYaml] = useState<string>(() =>
    localStorage.getItem(LS_KEY) || APP_DIAGNOSTICS_TEMPLATE
  );
  const [saved, setSaved] = useState(false);

  const parsed = useMemo(() => parseWorkflowYaml(yaml), [yaml]);

  const handleSave = () => {
    localStorage.setItem(LS_KEY, yaml);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="flex flex-col h-full" style={{ background: '#0a1214' }}>
      {/* Toolbar */}
      <div className="flex items-center justify-between px-5 py-3 border-b flex-shrink-0" style={{ borderColor: '#1e2a2e' }}>
        <div>
          <h1 className="text-base font-mono font-bold" style={{ color: '#e8e0d4' }}>
            {parsed.name || 'Untitled Workflow'}
          </h1>
          {parsed.id && (
            <div className="text-[10px] font-mono mt-0.5" style={{ color: '#64748b' }}>id: {parsed.id}</div>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* Validation badge */}
          {parsed.errors.length > 0 ? (
            <span className="flex items-center gap-1 text-[10px] font-mono px-2 py-1 rounded"
              style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', color: '#ef4444' }}>
              <span className="material-symbols-outlined" style={{ fontSize: 12 }}>error</span>
              {parsed.errors.length} error{parsed.errors.length !== 1 ? 's' : ''}
            </span>
          ) : (
            <span className="flex items-center gap-1 text-[10px] font-mono px-2 py-1 rounded"
              style={{ background: 'rgba(34,197,94,0.1)', border: '1px solid rgba(34,197,94,0.3)', color: '#22c55e' }}>
              <span className="material-symbols-outlined" style={{ fontSize: 12 }}>check_circle</span>
              Valid
            </span>
          )}

          <button onClick={handleSave}
            className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-mono"
            style={{ background: 'rgba(7,182,213,0.1)', border: '1px solid rgba(7,182,213,0.3)', color: saved ? '#22c55e' : '#07b6d5' }}>
            <span className="material-symbols-outlined" style={{ fontSize: 13 }}>{saved ? 'check' : 'save'}</span>
            {saved ? 'Saved' : 'Save'}
          </button>

          <button
            disabled
            className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-mono cursor-not-allowed"
            style={{ background: 'transparent', border: '1px solid #1e2a2e', color: '#3d4a50' }}
            title="Workflow execution available after platform backend ships"
          >
            <span className="material-symbols-outlined" style={{ fontSize: 13 }}>play_circle</span>
            Run
          </button>
        </div>
      </div>

      {/* Main split */}
      <div className="flex flex-1 overflow-hidden">
        {/* YAML Editor */}
        <div className="flex flex-col border-r" style={{ width: '50%', borderColor: '#1e2a2e' }}>
          <div className="px-4 py-2 border-b flex-shrink-0 flex items-center gap-2" style={{ borderColor: '#1e2a2e' }}>
            <span className="text-[10px] font-mono uppercase tracking-widest" style={{ color: '#3d4a50' }}>Workflow YAML</span>
          </div>
          <textarea
            value={yaml}
            onChange={e => setYaml(e.target.value)}
            spellCheck={false}
            className="flex-1 resize-none outline-none p-4 text-xs font-mono"
            style={{
              background: '#080f12', color: '#e8e0d4', lineHeight: 1.6,
              tabSize: 2,
            }}
          />
          {/* Errors */}
          {parsed.errors.length > 0 && (
            <div className="border-t px-4 py-2 flex-shrink-0 space-y-1" style={{ borderColor: '#1e2a2e', background: '#0c1214' }}>
              {parsed.errors.map((e, i) => (
                <div key={i} className="flex items-start gap-1.5 text-[10px] font-mono" style={{ color: '#ef4444' }}>
                  <span className="material-symbols-outlined flex-shrink-0" style={{ fontSize: 12 }}>error</span>
                  {e}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* DAG Preview */}
        <div className="flex flex-col" style={{ width: '50%' }}>
          <div className="px-4 py-2 border-b flex-shrink-0 flex items-center justify-between" style={{ borderColor: '#1e2a2e' }}>
            <span className="text-[10px] font-mono uppercase tracking-widest" style={{ color: '#3d4a50' }}>DAG Preview</span>
            <span className="text-[10px] font-mono" style={{ color: '#3d4a50' }}>
              {parsed.steps.length} step{parsed.steps.length !== 1 ? 's' : ''}
            </span>
          </div>
          <div className="flex-1">
            <WorkflowDagPreview workflow={parsed} />
          </div>
        </div>
      </div>
    </div>
  );
};

export default WorkflowBuilderView;
```

**Step 4: Check TypeScript**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "Platform/WorkflowBuilder"
```

Expected: no errors.

**Step 5: Commit**

```bash
git add frontend/src/components/Platform/WorkflowBuilder/
git commit -m "feat(platform): workflow builder — YAML editor + ReactFlow DAG preview + live validation"
```

---

## Task 5: Workflow Runs — list view

**Files:**
- Create: `frontend/src/components/Platform/WorkflowRuns/useWorkflowRuns.ts`
- Create: `frontend/src/components/Platform/WorkflowRuns/WorkflowRunCard.tsx`
- Modify: `frontend/src/components/Platform/WorkflowRuns/WorkflowRunsView.tsx`

**Step 1: Create data hook — reframes sessions as runs**

Create `frontend/src/components/Platform/WorkflowRuns/useWorkflowRuns.ts`:

```typescript
import { useState, useEffect, useCallback } from 'react';
import { API_BASE_URL } from '../../../services/api';

export interface WorkflowRun {
  id: string;                     // session_id
  workflow_name: string;          // derived from session data
  service_name: string;
  status: 'running' | 'completed' | 'failed' | 'waiting_approval';
  confidence?: number;
  started_at: string;
  finished_at?: string;
  agents_completed: string[];
  agents_pending: string[];
  overall_confidence?: number;
}

function deriveStatus(session: any): WorkflowRun['status'] {
  if (session.phase === 'FIX_APPROVAL_PENDING') return 'waiting_approval';
  if (session.phase === 'DIAGNOSIS_COMPLETE') return 'completed';
  if (session.error) return 'failed';
  return 'running';
}

export function useWorkflowRuns() {
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [loading, setLoading] = useState(true);

  const fetch = useCallback(async () => {
    try {
      setLoading(true);
      const res = await window.fetch(`${API_BASE_URL}/api/v4/sessions`);
      if (!res.ok) return;
      const data = await res.json();
      const sessions = data.sessions || [];
      setRuns(sessions.map((s: any) => ({
        id: s.session_id || s.id,
        workflow_name: 'App Diagnostics',
        service_name: s.service_name || s.input?.service_name || 'Unknown service',
        status: deriveStatus(s),
        started_at: s.created_at || s.started_at || new Date().toISOString(),
        finished_at: s.finished_at,
        agents_completed: s.agents_completed || [],
        agents_pending: s.agents_pending || [],
        overall_confidence: s.overall_confidence,
      })));
    } catch {
      // API unavailable
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetch(); }, [fetch]);

  return { runs, loading, refresh: fetch };
}
```

**Step 2: Create WorkflowRunCard**

Create `frontend/src/components/Platform/WorkflowRuns/WorkflowRunCard.tsx`:

```typescript
import React from 'react';
import type { WorkflowRun } from './useWorkflowRuns';

const STATUS_CONFIG: Record<WorkflowRun['status'], { color: string; icon: string; label: string }> = {
  completed:        { color: '#22c55e', icon: 'check_circle', label: 'Completed' },
  failed:           { color: '#ef4444', icon: 'error',        label: 'Failed' },
  running:          { color: '#07b6d5', icon: 'progress_activity', label: 'Running' },
  waiting_approval: { color: '#f59e0b', icon: 'pending_actions', label: 'Awaiting Approval' },
};

function elapsed(start: string, end?: string) {
  const ms = new Date(end || Date.now()).getTime() - new Date(start).getTime();
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

interface Props { run: WorkflowRun; selected: boolean; onClick: () => void; }

const WorkflowRunCard: React.FC<Props> = ({ run, selected, onClick }) => {
  const cfg = STATUS_CONFIG[run.status];
  return (
    <div
      onClick={onClick}
      className="px-4 py-3 cursor-pointer border-b"
      style={{
        borderColor: '#1e2a2e',
        background: selected ? 'rgba(7,182,213,0.06)' : 'transparent',
        borderLeft: selected ? '2px solid #07b6d5' : '2px solid transparent',
      }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-xs font-mono font-semibold truncate" style={{ color: '#e8e0d4' }}>
            {run.workflow_name}
          </div>
          <div className="text-[10px] font-mono mt-0.5 truncate" style={{ color: '#64748b' }}>
            {run.service_name}
          </div>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          <span className="material-symbols-outlined" style={{ fontSize: 14, color: cfg.color }}>
            {cfg.icon}
          </span>
          <span className="text-[10px] font-mono" style={{ color: cfg.color }}>{cfg.label}</span>
        </div>
      </div>

      <div className="mt-2 flex items-center gap-3 text-[10px] font-mono" style={{ color: '#3d4a50' }}>
        <span>{new Date(run.started_at).toLocaleString()}</span>
        <span>·</span>
        <span>{elapsed(run.started_at, run.finished_at)}</span>
        {run.overall_confidence !== undefined && (
          <>
            <span>·</span>
            <span style={{ color: run.overall_confidence > 0.8 ? '#22c55e' : '#f59e0b' }}>
              {Math.round(run.overall_confidence * 100)}% conf
            </span>
          </>
        )}
      </div>

      {/* Agent completion bar */}
      {(run.agents_completed.length + run.agents_pending.length) > 0 && (
        <div className="mt-2 h-1 rounded-full overflow-hidden" style={{ background: '#1e2a2e' }}>
          <div
            className="h-full rounded-full"
            style={{
              width: `${(run.agents_completed.length / (run.agents_completed.length + run.agents_pending.length)) * 100}%`,
              background: cfg.color,
              transition: 'width 0.3s',
            }}
          />
        </div>
      )}
    </div>
  );
};

export default WorkflowRunCard;
```

**Step 3: Build WorkflowRunsView**

Replace stub in `frontend/src/components/Platform/WorkflowRuns/WorkflowRunsView.tsx`:

```typescript
import React, { useState } from 'react';
import { useWorkflowRuns } from './useWorkflowRuns';
import WorkflowRunCard from './WorkflowRunCard';
import WorkflowRunDetail from './WorkflowRunDetail';
import type { WorkflowRun } from './useWorkflowRuns';

const WorkflowRunsView: React.FC = () => {
  const { runs, loading, refresh } = useWorkflowRuns();
  const [selected, setSelected] = useState<WorkflowRun | null>(null);

  return (
    <div className="flex h-full" style={{ background: '#0a1214' }}>
      {/* Left: run list */}
      <div className="flex flex-col border-r" style={{ width: selected ? 320 : '100%', borderColor: '#1e2a2e', transition: 'width 0.2s' }}>
        <div className="flex items-center justify-between px-5 py-4 border-b flex-shrink-0" style={{ borderColor: '#1e2a2e' }}>
          <div>
            <h1 className="text-base font-mono font-bold" style={{ color: '#e8e0d4' }}>Workflow Runs</h1>
            <p className="text-xs font-mono mt-0.5" style={{ color: '#64748b' }}>
              {runs.length} run{runs.length !== 1 ? 's' : ''}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              disabled
              className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-mono cursor-not-allowed"
              style={{ border: '1px solid #1e2a2e', color: '#3d4a50', background: 'transparent' }}
              title="Workflow triggering available after platform backend ships"
            >
              <span className="material-symbols-outlined" style={{ fontSize: 13 }}>play_circle</span>
              New Run
            </button>
            <button onClick={refresh} style={{ color: '#64748b' }}>
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>refresh</span>
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-auto">
          {loading && (
            <div className="flex items-center justify-center h-32 text-xs font-mono" style={{ color: '#64748b' }}>Loading...</div>
          )}
          {!loading && runs.length === 0 && (
            <div className="flex flex-col items-center justify-center h-48 gap-3">
              <span className="material-symbols-outlined" style={{ fontSize: 36, color: '#1e2a2e' }}>play_circle</span>
              <div className="text-xs font-mono text-center" style={{ color: '#64748b' }}>
                No workflow runs yet.<br />
                <span style={{ color: '#3d4a50' }}>Start an investigation from App Diagnostics.</span>
              </div>
            </div>
          )}
          {!loading && runs.map(run => (
            <WorkflowRunCard
              key={run.id}
              run={run}
              selected={selected?.id === run.id}
              onClick={() => setSelected(selected?.id === run.id ? null : run)}
            />
          ))}
        </div>
      </div>

      {/* Right: detail */}
      {selected && (
        <div className="flex-1 overflow-hidden">
          <WorkflowRunDetail run={selected} onClose={() => setSelected(null)} />
        </div>
      )}
    </div>
  );
};

export default WorkflowRunsView;
```

**Step 4: Create stub WorkflowRunDetail**

Create `frontend/src/components/Platform/WorkflowRuns/WorkflowRunDetail.tsx`:

```typescript
import React from 'react';
import type { WorkflowRun } from './useWorkflowRuns';

interface Props { run: WorkflowRun; onClose: () => void; }
const WorkflowRunDetail: React.FC<Props> = ({ run, onClose }) => (
  <div className="h-full flex flex-col" style={{ background: '#0c1a1f' }}>
    <div className="flex items-center justify-between px-5 py-4 border-b" style={{ borderColor: '#1e2a2e' }}>
      <span className="text-sm font-mono font-bold" style={{ color: '#e8e0d4' }}>{run.service_name}</span>
      <button onClick={onClose}><span className="material-symbols-outlined" style={{ fontSize: 18, color: '#64748b' }}>close</span></button>
    </div>
    <div className="p-5 text-xs font-mono" style={{ color: '#64748b' }}>Run detail — Task 6</div>
  </div>
);
export default WorkflowRunDetail;
```

**Step 5: Check TypeScript**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "Platform/WorkflowRuns"
```

Expected: no errors.

**Step 6: Commit**

```bash
git add frontend/src/components/Platform/WorkflowRuns/
git commit -m "feat(platform): workflow runs list view reframing existing sessions API"
```

---

## Task 6: Workflow Runs — run detail with step breakdown + human gate

**Files:**
- Modify: `frontend/src/components/Platform/WorkflowRuns/WorkflowRunDetail.tsx`

**Step 1: Replace stub with full implementation**

Replace `WorkflowRunDetail.tsx`:

```typescript
import React, { useState, useEffect } from 'react';
import { API_BASE_URL } from '../../../services/api';
import type { WorkflowRun } from './useWorkflowRuns';

interface Step {
  id: string;
  status: 'completed' | 'running' | 'pending' | 'failed' | 'skipped';
  summary?: string;
  duration_s?: number;
}

const STATUS_CONFIG = {
  completed: { color: '#22c55e', icon: 'check_circle' },
  running:   { color: '#07b6d5', icon: 'progress_activity' },
  pending:   { color: '#3d4a50', icon: 'radio_button_unchecked' },
  failed:    { color: '#ef4444', icon: 'error' },
  skipped:   { color: '#4a5568', icon: 'remove_circle' },
};

const KNOWN_AGENTS = [
  'log_analysis_agent', 'metrics_agent', 'k8s_agent',
  'tracing_agent', 'code_navigator_agent', 'change_agent',
  'critic_agent', 'fix_generator',
];

function buildSteps(run: WorkflowRun): Step[] {
  return KNOWN_AGENTS.map(id => {
    const done = run.agents_completed.includes(id);
    const pending = run.agents_pending.includes(id);
    return {
      id,
      status: done ? 'completed' : pending ? 'running' : 'pending',
    };
  });
}

interface Props { run: WorkflowRun; onClose: () => void; }

const WorkflowRunDetail: React.FC<Props> = ({ run, onClose }) => {
  const [steps, setSteps] = useState<Step[]>(() => buildSteps(run));
  const [findings, setFindings] = useState<any[]>([]);
  const [approving, setApproving] = useState(false);

  useEffect(() => {
    setSteps(buildSteps(run));

    // Fetch session findings for step summaries
    window.fetch(`${API_BASE_URL}/api/v4/session/${run.id}/findings`)
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data?.findings) setFindings(data.findings); })
      .catch(() => {});
  }, [run]);

  const handleApprove = async () => {
    setApproving(true);
    try {
      await window.fetch(`${API_BASE_URL}/api/v4/session/${run.id}/fix/approve`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved: true }),
      });
    } catch { /* ignore */ }
    setApproving(false);
  };

  const handleReject = async () => {
    await window.fetch(`${API_BASE_URL}/api/v4/session/${run.id}/fix/approve`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approved: false }),
    });
  };

  return (
    <div className="h-full flex flex-col overflow-hidden" style={{ background: '#0c1a1f' }}>
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b flex-shrink-0" style={{ borderColor: '#1e2a2e' }}>
        <div>
          <div className="text-sm font-mono font-bold" style={{ color: '#e8e0d4' }}>{run.service_name}</div>
          <div className="text-[10px] font-mono mt-0.5" style={{ color: '#64748b' }}>
            {run.workflow_name} · {new Date(run.started_at).toLocaleString()}
          </div>
        </div>
        <button onClick={onClose}>
          <span className="material-symbols-outlined" style={{ fontSize: 18, color: '#64748b' }}>close</span>
        </button>
      </div>

      <div className="flex-1 overflow-auto px-5 py-4 space-y-4">
        {/* Steps */}
        <div>
          <div className="text-[10px] font-mono uppercase tracking-widest mb-3" style={{ color: '#3d4a50' }}>Steps</div>
          <div className="space-y-2">
            {steps.map((step, i) => {
              const cfg = STATUS_CONFIG[step.status];
              const finding = findings.find((f: any) =>
                f.source_agent === step.id || f.agent === step.id
              );
              return (
                <div
                  key={step.id}
                  className="flex items-start gap-3 rounded px-3 py-2.5"
                  style={{ background: '#0a1214', border: '1px solid #1a2428' }}
                >
                  <span className="material-symbols-outlined flex-shrink-0 mt-0.5" style={{ fontSize: 15, color: cfg.color }}>
                    {cfg.icon}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-[11px] font-mono" style={{ color: '#e8e0d4' }}>{step.id}</div>
                    {finding && (
                      <div className="text-[10px] font-mono mt-0.5 truncate" style={{ color: '#9a9080' }}>
                        {finding.summary || finding.title}
                      </div>
                    )}
                  </div>
                  <span className="text-[10px] font-mono flex-shrink-0" style={{ color: cfg.color }}>
                    {step.status}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Human gate — shown when waiting_approval */}
        {run.status === 'waiting_approval' && (
          <div className="rounded-lg p-4" style={{ background: 'rgba(245,158,11,0.06)', border: '1px solid rgba(245,158,11,0.3)' }}>
            <div className="flex items-center gap-2 mb-2">
              <span className="material-symbols-outlined" style={{ fontSize: 16, color: '#f59e0b' }}>pending_actions</span>
              <span className="text-xs font-mono font-semibold" style={{ color: '#f59e0b' }}>Awaiting Approval</span>
            </div>
            <div className="text-[11px] font-mono mb-3" style={{ color: '#9a9080' }}>
              fix_generator has proposed a fix. Review and approve to create a PR.
            </div>
            <div className="flex gap-2">
              <button
                onClick={handleApprove}
                disabled={approving}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-mono"
                style={{ background: 'rgba(34,197,94,0.1)', border: '1px solid rgba(34,197,94,0.4)', color: '#22c55e' }}
              >
                <span className="material-symbols-outlined" style={{ fontSize: 13 }}>check</span>
                {approving ? 'Approving...' : 'Approve & Create PR'}
              </button>
              <button
                onClick={handleReject}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-mono"
                style={{ background: 'transparent', border: '1px solid rgba(239,68,68,0.4)', color: '#ef4444' }}
              >
                <span className="material-symbols-outlined" style={{ fontSize: 13 }}>close</span>
                Reject
              </button>
            </div>
          </div>
        )}

        {/* Confidence */}
        {run.overall_confidence !== undefined && (
          <div className="rounded p-3" style={{ background: '#0a1214', border: '1px solid #1a2428' }}>
            <div className="text-[10px] font-mono uppercase tracking-widest mb-2" style={{ color: '#3d4a50' }}>Overall Confidence</div>
            <div className="flex items-center gap-3">
              <div className="flex-1 h-2 rounded-full overflow-hidden" style={{ background: '#1a2428' }}>
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${run.overall_confidence * 100}%`,
                    background: run.overall_confidence > 0.8 ? '#22c55e' : run.overall_confidence > 0.5 ? '#f59e0b' : '#ef4444',
                  }}
                />
              </div>
              <span className="text-sm font-mono font-bold" style={{ color: '#e8e0d4' }}>
                {Math.round(run.overall_confidence * 100)}%
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default WorkflowRunDetail;
```

**Step 2: Check TypeScript**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "Platform/WorkflowRuns"
```

Expected: no errors.

**Step 3: Final TypeScript check across all Platform files**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "Platform"
```

Expected: no errors.

**Step 4: Final commit**

```bash
git add frontend/src/components/Platform/WorkflowRuns/WorkflowRunDetail.tsx
git commit -m "feat(platform): workflow run detail with step breakdown and human gate approval"
```

---

## Done

All three Platform UI views are implemented:
- **Agent Catalog** — 25 agents, health status, search/filter, detail panel with tools + executions + copy YAML
- **Workflow Builder** — YAML editor + ReactFlow DAG preview + live validation + localStorage save
- **Workflow Runs** — session history reframed as runs, step breakdown, confidence bar, human gate inline approval

Next session (backend platform layer):
- `BaseAgent` SDK with `execute()` interface
- `AgentManifest` YAML loader with schema validation
- `ExecutionStore` SQLite schema
- `POST /api/v4/agents/{id}/run` standalone endpoint
- `WorkflowEngine` DAG executor
