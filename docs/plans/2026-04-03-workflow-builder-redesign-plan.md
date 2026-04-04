# Workflow Builder Enterprise Redesign — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Redesign the Workflow Builder into an enterprise-grade tool with three synchronized views (Canvas, List, Code) serving both engineers and non-engineers.

**Architecture:** A shared `useWorkflowState` hook drives all three views. The hook owns parsed state + YAML + dirty flag. Canvas and List views both consume the hook and render `StepConfigSidebar` when a step is selected. All edits re-serialize to YAML via `workflowSerializer.ts`.

**Tech Stack:** React 18, TypeScript, ReactFlow v11, Tailwind CSS, design tokens at `src/styles/tokens.ts`, Material Symbols icons, existing workflowParser.ts (to be extended).

**Design reference:** `docs/plans/2026-04-03-workflow-builder-redesign-design.md`

---

### Task 1: Extend workflowParser.ts — new step fields

**Files:**
- Modify: `frontend/src/components/Platform/WorkflowBuilder/workflowParser.ts`

**What to do:**

Extend `WorkflowStep` interface and `parseWorkflowYaml` to support new fields. All new fields are optional for backward compatibility.

**Step 1: Update the WorkflowStep interface**

Replace the existing interface (lines 1–7) with:

```ts
export interface WorkflowStep {
  id: string;
  label?: string;          // human-readable display name
  agent: string;
  depends_on: string[];
  condition?: string;
  gate?: string;
  timeout?: number;        // seconds
  retries?: number;        // 0–5
  retry_delay?: number;    // seconds
  human_gate?: boolean;    // true if gate === 'human_approval'
  skip_if?: string;        // expression string
  parameters?: Record<string, string>;  // custom agent parameters
}
```

Also extend `ParsedWorkflow`:
```ts
export interface ParsedWorkflow {
  id?: string;
  name?: string;
  version?: string;
  triggers?: string[];
  steps: WorkflowStep[];
  errors: string[];
  dirty?: boolean;
}
```

**Step 2: Add parsing for new fields inside the for loop in parseWorkflowYaml**

After the existing `conditionM` and `gateM` lines, add:

```ts
const labelM = block.match(/\s+label:\s*"?([^"\n]+)"?\s*$/m);
const timeoutM = block.match(/\s+timeout:\s*(\d+)/);
const retriesM = block.match(/\s+retries:\s*(\d+)/);
const retryDelayM = block.match(/\s+retry_delay:\s*(\d+)/);
const skipIfM = block.match(/\s+skip_if:\s*"?([^"\n]+)"?\s*$/m);

// Parse parameters block
const parameters: Record<string, string> = {};
const paramSection = block.match(/\s+parameters:\s*\n((?:\s+\w+:.+\n?)+)/);
if (paramSection) {
  const paramLines = paramSection[1].match(/\s+(\w+):\s*(.+)/g) || [];
  paramLines.forEach(line => {
    const [, k, v] = line.match(/\s+(\w+):\s*(.+)/) || [];
    if (k && v) parameters[k.trim()] = v.trim().replace(/^["']|["']$/g, '');
  });
}

const humanGate = gateM?.[1] === 'human_approval';
```

**Step 3: Update the steps.push call to include new fields**

```ts
steps.push({
  id: stepId,
  label: labelM?.[1]?.trim(),
  agent,
  depends_on,
  condition: conditionM?.[1],
  gate: gateM?.[1],
  timeout: timeoutM ? parseInt(timeoutM[1]) : undefined,
  retries: retriesM ? parseInt(retriesM[1]) : undefined,
  retry_delay: retryDelayM ? parseInt(retryDelayM[1]) : undefined,
  human_gate: humanGate || undefined,
  skip_if: skipIfM?.[1]?.trim(),
  parameters: Object.keys(parameters).length > 0 ? parameters : undefined,
});
```

Also add version/triggers parsing near the top of the function, after `nameMatch`:
```ts
const versionMatch = yaml.match(/^version:\s*"?([^"\n]+)"?/m);
const triggersMatch = yaml.match(/^trigger:\s*\[([^\]]+)\]/m);
const triggers = triggersMatch
  ? triggersMatch[1].split(',').map(t => t.trim())
  : [];
```

And update the return:
```ts
return {
  id: idMatch?.[1]?.trim(),
  name: nameMatch?.[1]?.trim(),
  version: versionMatch?.[1]?.trim(),
  triggers,
  steps,
  errors,
};
```

**Step 4: Verify TypeScript compiles**
```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors

**Step 5: Commit**
```bash
git add frontend/src/components/Platform/WorkflowBuilder/workflowParser.ts
git commit -m "feat(builder): extend WorkflowStep with label, timeout, retries, human_gate, parameters"
```

---

### Task 2: Create workflowSerializer.ts — state → YAML

**Files:**
- Create: `frontend/src/components/Platform/WorkflowBuilder/workflowSerializer.ts`

**What to do:**

Serialize a `ParsedWorkflow` back to YAML string. This is the write path: any visual edit calls `stateToYaml` and updates the YAML textarea.

**Step 1: Create the file**

```ts
import type { ParsedWorkflow, WorkflowStep } from './workflowParser';

function indent(n: number): string { return '  '.repeat(n); }

function stepToYaml(step: WorkflowStep): string {
  const lines: string[] = [];
  lines.push(`${indent(1)}- id: ${step.id}`);
  if (step.label) lines.push(`${indent(2)}label: "${step.label}"`);
  lines.push(`${indent(2)}agent: ${step.agent}`);

  if (step.depends_on.length === 0) {
    lines.push(`${indent(2)}depends_on: []`);
  } else {
    lines.push(`${indent(2)}depends_on: [${step.depends_on.join(', ')}]`);
  }

  if (step.timeout !== undefined) lines.push(`${indent(2)}timeout: ${step.timeout}`);
  if (step.retries !== undefined) lines.push(`${indent(2)}retries: ${step.retries}`);
  if (step.retry_delay !== undefined) lines.push(`${indent(2)}retry_delay: ${step.retry_delay}`);
  if (step.human_gate) {
    lines.push(`${indent(2)}gate: human_approval`);
    lines.push(`${indent(2)}gate_timeout: 30m`);
  }
  if (step.condition) lines.push(`${indent(2)}condition: "${step.condition}"`);
  if (step.skip_if) lines.push(`${indent(2)}skip_if: "${step.skip_if}"`);
  if (step.parameters && Object.keys(step.parameters).length > 0) {
    lines.push(`${indent(2)}parameters:`);
    Object.entries(step.parameters).forEach(([k, v]) => {
      lines.push(`${indent(3)}${k}: "${v}"`);
    });
  }
  return lines.join('\n');
}

export function stateToYaml(workflow: ParsedWorkflow): string {
  const lines: string[] = [];
  if (workflow.id) lines.push(`id: ${workflow.id}`);
  if (workflow.name) lines.push(`name: ${workflow.name}`);
  if (workflow.version) lines.push(`version: "${workflow.version}"`);
  if (workflow.triggers && workflow.triggers.length > 0) {
    lines.push(`trigger: [${workflow.triggers.join(', ')}]`);
  }
  lines.push('');
  lines.push('steps:');
  workflow.steps.forEach(step => {
    lines.push(stepToYaml(step));
  });
  return lines.join('\n') + '\n';
}
```

**Step 2: Verify TypeScript compiles**
```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors

**Step 3: Commit**
```bash
git add frontend/src/components/Platform/WorkflowBuilder/workflowSerializer.ts
git commit -m "feat(builder): add workflowSerializer — stateToYaml for visual → YAML sync"
```

---

### Task 3: Create useWorkflowState.ts — shared state hook

**Files:**
- Create: `frontend/src/components/Platform/WorkflowBuilder/useWorkflowState.ts`

**What to do:**

Central hook that owns all workflow state. Both Canvas and List views import this — they never manage their own workflow state.

**Step 1: Create the file**

```ts
import { useState, useCallback, useMemo } from 'react';
import { parseWorkflowYaml } from './workflowParser';
import { stateToYaml } from './workflowSerializer';
import type { ParsedWorkflow, WorkflowStep } from './workflowParser';

const LS_KEY = 'platform_workflow_builder_yaml';

export function useWorkflowState(initialYaml: string) {
  const [yaml, setYamlRaw] = useState(initialYaml);
  const [dirty, setDirty] = useState(false);

  const parsed = useMemo(() => parseWorkflowYaml(yaml), [yaml]);

  // Update YAML directly (from Code view)
  const setYaml = useCallback((newYaml: string) => {
    setYamlRaw(newYaml);
    setDirty(true);
  }, []);

  // Derive new YAML from a mutated ParsedWorkflow, update state
  const applyState = useCallback((next: ParsedWorkflow) => {
    const newYaml = stateToYaml(next);
    setYamlRaw(newYaml);
    setDirty(true);
  }, []);

  const updateWorkflowMeta = useCallback((fields: Partial<Pick<ParsedWorkflow, 'id' | 'name'>>) => {
    applyState({ ...parsed, ...fields });
  }, [parsed, applyState]);

  const addStep = useCallback((agent: string) => {
    const id = `step_${Date.now()}`;
    const newStep: WorkflowStep = {
      id,
      agent,
      depends_on: [],
      label: agent.replace(/_agent$/, '').replace(/_/g, ' '),
    };
    applyState({ ...parsed, steps: [...parsed.steps, newStep] });
    return id;
  }, [parsed, applyState]);

  const updateStep = useCallback((stepId: string, fields: Partial<WorkflowStep>) => {
    const steps = parsed.steps.map(s =>
      s.id === stepId ? { ...s, ...fields } : s
    );
    applyState({ ...parsed, steps });
  }, [parsed, applyState]);

  const removeStep = useCallback((stepId: string) => {
    const steps = parsed.steps
      .filter(s => s.id !== stepId)
      .map(s => ({
        ...s,
        depends_on: s.depends_on.filter(d => d !== stepId),
      }));
    applyState({ ...parsed, steps });
  }, [parsed, applyState]);

  const moveStep = useCallback((fromIndex: number, toIndex: number) => {
    const steps = [...parsed.steps];
    const [moved] = steps.splice(fromIndex, 1);
    steps.splice(toIndex, 0, moved);
    applyState({ ...parsed, steps });
  }, [parsed, applyState]);

  const save = useCallback(() => {
    localStorage.setItem(LS_KEY, yaml);
    setDirty(false);
    return { id: parsed.id, name: parsed.name, yaml };
  }, [yaml, parsed]);

  return {
    yaml,
    parsed,
    dirty,
    setYaml,
    updateWorkflowMeta,
    addStep,
    updateStep,
    removeStep,
    moveStep,
    save,
  };
}
```

**Step 2: Verify TypeScript compiles**
```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors

**Step 3: Commit**
```bash
git add frontend/src/components/Platform/WorkflowBuilder/useWorkflowState.ts
git commit -m "feat(builder): useWorkflowState — shared hook driving Canvas/List/Code views"
```

---

### Task 4: Create AgentPickerModal.tsx

**Files:**
- Create: `frontend/src/components/Platform/WorkflowBuilder/AgentPickerModal.tsx`

**What to do:**

A modal dialog for selecting an agent. Triggered from `+ Add Step` and from the agent dropdown in `StepConfigSidebar`. Replaces `AgentBrowserPanel` for the primary pick interaction.

**Step 1: Create the file**

```tsx
import React, { useState, useEffect, useRef } from 'react';
import { API_BASE_URL } from '../../../services/api';
import { t } from '../../../styles/tokens';

interface AgentSummary {
  id: string;
  name: string;
  workflow: string;
  status: 'active' | 'degraded' | 'offline';
}

const WORKFLOW_LABELS: Record<string, string> = {
  app_diagnostics: 'App',
  cluster_diagnostics: 'Cluster',
  network_diagnostics: 'Network',
  database_diagnostics: 'Database',
};

const STATUS_COLOR: Record<string, string> = {
  active: t.green,
  degraded: t.amber,
  offline: t.red,
};

interface Props {
  onSelect: (agentId: string) => void;
  onClose: () => void;
}

const AgentPickerModal: React.FC<Props> = ({ onSelect, onClose }) => {
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    searchRef.current?.focus();
    window.fetch(`${API_BASE_URL}/api/v4/agents`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data?.agents) {
          setAgents(data.agents.map((a: any) => ({
            id: a.id,
            name: a.name || a.id,
            workflow: a.workflow || 'app_diagnostics',
            status: a.status || 'active',
          })));
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  const filtered = agents.filter(a =>
    search === '' ||
    a.id.toLowerCase().includes(search.toLowerCase()) ||
    a.name.toLowerCase().includes(search.toLowerCase())
  );

  const groups: Record<string, AgentSummary[]> = {};
  filtered.forEach(a => {
    const g = WORKFLOW_LABELS[a.workflow] || a.workflow;
    groups[g] = groups[g] || [];
    groups[g].push(a);
  });

  return (
    // Backdrop
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.6)' }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        className="flex flex-col rounded-lg overflow-hidden"
        style={{
          width: 400,
          maxHeight: 480,
          background: t.bgSurface,
          border: `1px solid ${t.borderDefault}`,
          boxShadow: '0 24px 48px rgba(0,0,0,0.5)',
        }}
        role="dialog"
        aria-modal="true"
        aria-label="Choose an agent"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b flex-shrink-0"
          style={{ borderColor: t.borderDefault }}>
          <span className="text-sm font-display font-semibold" style={{ color: t.textPrimary }}>Choose an Agent</span>
          <button onClick={onClose} aria-label="Close agent picker">
            <span className="material-symbols-outlined" style={{ fontSize: 18, color: t.textMuted }}>close</span>
          </button>
        </div>

        {/* Search */}
        <div className="px-4 py-2 border-b flex-shrink-0" style={{ borderColor: t.borderDefault }}>
          <div className="flex items-center gap-2" style={{
            background: t.bgDeep,
            border: `1px solid ${t.borderDefault}`,
            borderRadius: 6,
            padding: '6px 10px',
          }}>
            <span className="material-symbols-outlined" style={{ fontSize: 14, color: t.textFaint }}>search</span>
            <input
              ref={searchRef}
              type="text"
              placeholder="Search agents..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="flex-1 text-xs font-sans bg-transparent outline-none"
              style={{ color: t.textPrimary }}
              aria-label="Search agents"
            />
          </div>
        </div>

        {/* List */}
        <div className="flex-1 overflow-auto">
          {loading && (
            <div className="flex items-center justify-center h-16 text-xs font-sans" style={{ color: t.textMuted }}>
              Loading agents...
            </div>
          )}
          {!loading && filtered.length === 0 && (
            <div className="flex items-center justify-center h-16 text-xs font-sans" style={{ color: t.textMuted }}>
              No agents found
            </div>
          )}
          {Object.entries(groups).map(([groupLabel, groupAgents]) => (
            <div key={groupLabel}>
              <div className="px-4 py-1.5 text-[10px] font-sans uppercase tracking-widest sticky top-0"
                style={{ color: t.textFaint, background: t.bgSurface, borderBottom: `1px solid ${t.bgTrack}` }}>
                {groupLabel}
              </div>
              {groupAgents.map(agent => (
                <button
                  key={agent.id}
                  onClick={() => { onSelect(agent.id); onClose(); }}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-left"
                  style={{
                    borderBottom: `1px solid ${t.borderFaint}`,
                    opacity: agent.status === 'offline' ? 0.45 : 1,
                  }}
                  disabled={agent.status === 'offline'}
                >
                  <div className="w-2 h-2 rounded-full flex-shrink-0"
                    style={{ background: STATUS_COLOR[agent.status] || t.textFaint }} />
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-sans truncate" style={{ color: t.textPrimary }}>{agent.name}</div>
                    <div className="text-[10px] font-mono truncate mt-0.5" style={{ color: t.textMuted }}>{agent.id}</div>
                  </div>
                  {agent.status === 'offline' && (
                    <span className="text-[10px] font-sans flex-shrink-0" style={{ color: t.textFaint }}>offline</span>
                  )}
                </button>
              ))}
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t flex justify-end flex-shrink-0" style={{ borderColor: t.borderDefault }}>
          <button
            onClick={onClose}
            className="text-xs font-sans px-3 py-1.5 rounded"
            style={{ color: t.textMuted, border: `1px solid ${t.borderDefault}` }}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
};

export default AgentPickerModal;
```

**Step 2: Verify TypeScript compiles**
```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors

**Step 3: Commit**
```bash
git add frontend/src/components/Platform/WorkflowBuilder/AgentPickerModal.tsx
git commit -m "feat(builder): AgentPickerModal — searchable agent selector with status indicators"
```

---

### Task 5: Create StepConfigSidebar.tsx

**Files:**
- Create: `frontend/src/components/Platform/WorkflowBuilder/StepConfigSidebar.tsx`

**What to do:**

The shared config panel used in both Canvas and List views. Receives the selected step and dispatches updates via the `updateStep` and `removeStep` callbacks from `useWorkflowState`.

**Step 1: Create the file**

```tsx
import React, { useState } from 'react';
import type { WorkflowStep, ParsedWorkflow } from './workflowParser';
import AgentPickerModal from './AgentPickerModal';
import { t } from '../../../styles/tokens';

interface Props {
  step: WorkflowStep;
  allSteps: ParsedWorkflow['steps'];
  onUpdate: (stepId: string, fields: Partial<WorkflowStep>) => void;
  onRemove: (stepId: string) => void;
  onClose: () => void;
}

const RETRY_MAX = 5;

const StepConfigSidebar: React.FC<Props> = ({ step, allSteps, onUpdate, onRemove, onClose }) => {
  const [showAgentPicker, setShowAgentPicker] = useState(false);
  const [newParamKey, setNewParamKey] = useState('');
  const [newParamVal, setNewParamVal] = useState('');
  const [confirmDelete, setConfirmDelete] = useState(false);

  const otherSteps = allSteps.filter(s => s.id !== step.id);

  const field = (label: string, children: React.ReactNode) => (
    <div className="mb-4">
      <label className="block text-[10px] font-sans uppercase tracking-widest mb-1.5" style={{ color: t.textFaint }}>
        {label}
      </label>
      {children}
    </div>
  );

  const inputClass = "w-full text-xs font-sans px-3 py-2 rounded outline-none";
  const inputStyle = { background: t.bgDeep, border: `1px solid ${t.borderDefault}`, color: t.textPrimary };

  const sectionLabel = (text: string) => (
    <div className="text-[10px] font-sans uppercase tracking-widest mb-3 mt-5 pb-1"
      style={{ color: t.textFaint, borderBottom: `1px solid ${t.borderSubtle}` }}>
      {text}
    </div>
  );

  return (
    <>
      {showAgentPicker && (
        <AgentPickerModal
          onSelect={agentId => onUpdate(step.id, { agent: agentId })}
          onClose={() => setShowAgentPicker(false)}
        />
      )}

      <div className="flex flex-col h-full" style={{ background: t.bgSurface, borderLeft: `1px solid ${t.borderDefault}`, width: 320 }}>
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b flex-shrink-0"
          style={{ borderColor: t.borderDefault }}>
          <span className="text-sm font-display font-semibold" style={{ color: t.textPrimary }}>Step Config</span>
          <button onClick={onClose} aria-label="Close config panel">
            <span className="material-symbols-outlined" style={{ fontSize: 18, color: t.textMuted }}>close</span>
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-auto px-4 py-4">
          {/* Basic */}
          {field('Label',
            <input
              className={inputClass}
              style={inputStyle}
              value={step.label || ''}
              onChange={e => onUpdate(step.id, { label: e.target.value })}
              placeholder="Human-readable step name"
            />
          )}

          {field('Agent',
            <button
              onClick={() => setShowAgentPicker(true)}
              className="w-full flex items-center justify-between px-3 py-2 rounded text-xs font-mono text-left"
              style={{ background: t.bgDeep, border: `1px solid ${t.borderDefault}`, color: step.agent ? t.textPrimary : t.textFaint }}
            >
              <span>{step.agent || 'Select agent...'}</span>
              <span className="material-symbols-outlined" style={{ fontSize: 14, color: t.textFaint }}>unfold_more</span>
            </button>
          )}

          {/* Dependencies */}
          {sectionLabel('Dependencies')}
          <div className="flex flex-wrap gap-1.5 mb-2">
            {step.depends_on.map(depId => {
              const depStep = allSteps.find(s => s.id === depId);
              return (
                <div key={depId} className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-sans"
                  style={{ background: t.bgTrack, border: `1px solid ${t.borderDefault}`, color: t.textPrimary }}>
                  {depStep?.label || depId}
                  <button onClick={() => onUpdate(step.id, {
                    depends_on: step.depends_on.filter(d => d !== depId)
                  })} aria-label={`Remove dependency ${depId}`}>
                    <span className="material-symbols-outlined" style={{ fontSize: 12, color: t.textMuted }}>close</span>
                  </button>
                </div>
              );
            })}
          </div>
          <select
            className="w-full text-xs font-sans px-3 py-2 rounded outline-none"
            style={{ background: t.bgDeep, border: `1px solid ${t.borderDefault}`, color: t.textMuted }}
            value=""
            onChange={e => {
              if (e.target.value && !step.depends_on.includes(e.target.value)) {
                onUpdate(step.id, { depends_on: [...step.depends_on, e.target.value] });
              }
            }}
          >
            <option value="">+ Add dependency</option>
            {otherSteps.filter(s => !step.depends_on.includes(s.id)).map(s => (
              <option key={s.id} value={s.id}>{s.label || s.id}</option>
            ))}
          </select>

          {/* Execution */}
          {sectionLabel('Execution')}
          <div className="grid grid-cols-2 gap-3 mb-4">
            <div>
              <label className="block text-[10px] font-sans mb-1" style={{ color: t.textFaint }}>Timeout (s)</label>
              <input
                type="number"
                className={inputClass}
                style={inputStyle}
                value={step.timeout ?? ''}
                placeholder="300"
                min={0}
                onChange={e => onUpdate(step.id, { timeout: e.target.value ? parseInt(e.target.value) : undefined })}
              />
            </div>
            <div>
              <label className="block text-[10px] font-sans mb-1" style={{ color: t.textFaint }}>Retry delay (s)</label>
              <input
                type="number"
                className={inputClass}
                style={inputStyle}
                value={step.retry_delay ?? ''}
                placeholder="30"
                min={0}
                onChange={e => onUpdate(step.id, { retry_delay: e.target.value ? parseInt(e.target.value) : undefined })}
              />
            </div>
          </div>

          <div className="mb-4">
            <label className="block text-[10px] font-sans mb-2" style={{ color: t.textFaint }}>
              Retries: {step.retries ?? 0}
            </label>
            <div className="flex gap-1">
              {Array.from({ length: RETRY_MAX }).map((_, i) => (
                <button
                  key={i}
                  onClick={() => onUpdate(step.id, { retries: i + 1 === step.retries ? 0 : i + 1 })}
                  aria-label={`Set ${i + 1} retries`}
                  className="w-7 h-7 rounded text-[10px] font-mono"
                  style={{
                    background: (step.retries ?? 0) > i ? t.cyanBg : t.bgDeep,
                    border: `1px solid ${(step.retries ?? 0) > i ? t.cyanBorder : t.borderDefault}`,
                    color: (step.retries ?? 0) > i ? t.cyan : t.textFaint,
                  }}
                >
                  {i + 1}
                </button>
              ))}
            </div>
          </div>

          {/* Control Flow */}
          {sectionLabel('Control Flow')}

          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="text-xs font-sans" style={{ color: t.textPrimary }}>Human Gate</div>
              <div className="text-[10px] font-sans mt-0.5" style={{ color: t.textFaint }}>Pause for approval before continuing</div>
            </div>
            <button
              onClick={() => onUpdate(step.id, { human_gate: !step.human_gate })}
              aria-label={`${step.human_gate ? 'Disable' : 'Enable'} human gate`}
              aria-pressed={!!step.human_gate}
              className="w-10 h-5 rounded-full relative flex-shrink-0 transition-colors"
              style={{ background: step.human_gate ? t.amber : t.bgTrack }}
            >
              <span className="absolute top-0.5 w-4 h-4 rounded-full transition-transform"
                style={{
                  background: t.textPrimary,
                  transform: step.human_gate ? 'translateX(22px)' : 'translateX(2px)',
                }} />
            </button>
          </div>

          <div className="mb-4">
            <label className="block text-[10px] font-sans mb-1.5" style={{ color: t.textFaint }}>Skip if</label>
            <input
              className={inputClass}
              style={inputStyle}
              value={step.skip_if || ''}
              onChange={e => onUpdate(step.id, { skip_if: e.target.value || undefined })}
              placeholder="e.g. prev.confidence > 0.9"
            />
          </div>

          {/* Agent Parameters */}
          {sectionLabel('Agent Parameters')}
          {Object.entries(step.parameters || {}).map(([k, v]) => (
            <div key={k} className="flex items-center gap-2 mb-2">
              <input
                className="flex-1 text-[10px] font-mono px-2 py-1.5 rounded outline-none"
                style={{ background: t.bgDeep, border: `1px solid ${t.borderDefault}`, color: t.textPrimary }}
                value={k}
                readOnly
              />
              <input
                className="flex-1 text-[10px] font-mono px-2 py-1.5 rounded outline-none"
                style={{ background: t.bgDeep, border: `1px solid ${t.borderDefault}`, color: t.textPrimary }}
                value={v}
                onChange={e => {
                  const params = { ...(step.parameters || {}), [k]: e.target.value };
                  onUpdate(step.id, { parameters: params });
                }}
              />
              <button
                onClick={() => {
                  const params = { ...(step.parameters || {}) };
                  delete params[k];
                  onUpdate(step.id, { parameters: Object.keys(params).length ? params : undefined });
                }}
                aria-label={`Remove parameter ${k}`}
              >
                <span className="material-symbols-outlined" style={{ fontSize: 14, color: t.textMuted }}>close</span>
              </button>
            </div>
          ))}
          <div className="flex items-center gap-2 mb-1">
            <input
              className="flex-1 text-[10px] font-mono px-2 py-1.5 rounded outline-none"
              style={{ background: t.bgDeep, border: `1px solid ${t.borderDefault}`, color: t.textPrimary }}
              placeholder="key"
              value={newParamKey}
              onChange={e => setNewParamKey(e.target.value)}
            />
            <input
              className="flex-1 text-[10px] font-mono px-2 py-1.5 rounded outline-none"
              style={{ background: t.bgDeep, border: `1px solid ${t.borderDefault}`, color: t.textPrimary }}
              placeholder="value"
              value={newParamVal}
              onChange={e => setNewParamVal(e.target.value)}
            />
            <button
              onClick={() => {
                if (!newParamKey.trim()) return;
                onUpdate(step.id, { parameters: { ...(step.parameters || {}), [newParamKey.trim()]: newParamVal } });
                setNewParamKey(''); setNewParamVal('');
              }}
              aria-label="Add parameter"
            >
              <span className="material-symbols-outlined" style={{ fontSize: 16, color: t.cyan }}>add_circle</span>
            </button>
          </div>

          {/* Delete */}
          <div className="mt-6 pt-4" style={{ borderTop: `1px solid ${t.borderSubtle}` }}>
            {confirmDelete ? (
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-sans" style={{ color: t.textMuted }}>Remove this step?</span>
                <button
                  onClick={() => onRemove(step.id)}
                  className="px-2.5 py-1 rounded text-[10px] font-sans"
                  style={{ background: t.redBg, border: `1px solid ${t.redBorder}`, color: t.red }}
                >Yes, remove</button>
                <button
                  onClick={() => setConfirmDelete(false)}
                  className="text-[10px] font-sans"
                  style={{ color: t.textMuted }}
                >Cancel</button>
              </div>
            ) : (
              <button
                onClick={() => setConfirmDelete(true)}
                className="flex items-center gap-1.5 text-xs font-sans"
                style={{ color: t.red }}
              >
                <span className="material-symbols-outlined" style={{ fontSize: 14 }}>delete</span>
                Delete Step
              </button>
            )}
          </div>
        </div>
      </div>
    </>
  );
};

export default StepConfigSidebar;
```

**Step 2: Verify TypeScript compiles**
```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors

**Step 3: Commit**
```bash
git add frontend/src/components/Platform/WorkflowBuilder/StepConfigSidebar.tsx
git commit -m "feat(builder): StepConfigSidebar — full step configuration panel shared by Canvas and List"
```

---

### Task 6: Create WorkflowCanvas.tsx

**Files:**
- Create: `frontend/src/components/Platform/WorkflowBuilder/WorkflowCanvas.tsx`

**What to do:**

Interactive ReactFlow canvas. Nodes are clickable (to select for config), draggable (to reposition), and show human-readable labels. Add Step and Auto-layout buttons in the canvas toolbar. Renders `StepConfigSidebar` when a step is selected.

**Step 1: Create the file**

```tsx
import React, { useMemo, useState, useCallback } from 'react';
import ReactFlow, {
  Background, Controls, MarkerType, useNodesState, useEdgesState,
  addEdge, Panel,
} from 'reactflow';
import type { Node, Edge, Connection } from 'reactflow';
import 'reactflow/dist/style.css';
import type { ParsedWorkflow, WorkflowStep } from './workflowParser';
import StepConfigSidebar from './StepConfigSidebar';
import AgentPickerModal from './AgentPickerModal';
import { t } from '../../../styles/tokens';

const NODE_W = 200;
const NODE_H = 70;

const AGENT_ICONS: Record<string, string> = {
  log_analysis_agent: 'description',
  metrics_agent: 'monitoring',
  k8s_agent: 'cloud',
  tracing_agent: 'timeline',
  code_navigator_agent: 'code',
  change_agent: 'edit_note',
  critic_agent: 'rate_review',
  fix_generator: 'build',
  db_agent: 'database',
  network_analysis_agent: 'hub',
};

function getIcon(agentId: string): string {
  return AGENT_ICONS[agentId] || 'smart_toy';
}

function buildNodes(steps: WorkflowStep[], selectedId: string | null): Node[] {
  const depth: Record<string, number> = {};
  const getDepth = (id: string): number => {
    if (depth[id] !== undefined) return depth[id];
    const step = steps.find(s => s.id === id);
    if (!step || step.depends_on.length === 0) return (depth[id] = 0);
    return (depth[id] = Math.max(...step.depends_on.map(d => getDepth(d) + 1)));
  };
  steps.forEach(s => getDepth(s.id));

  const layers: Record<number, string[]> = {};
  steps.forEach(s => {
    const d = depth[s.id] || 0;
    layers[d] = layers[d] || [];
    layers[d].push(s.id);
  });

  return steps.map(step => {
    const layer = depth[step.id] || 0;
    const siblings = layers[layer];
    const siblingIdx = siblings.indexOf(step.id);
    const x = layer * (NODE_W + 80);
    const y = siblingIdx * (NODE_H + 32) - ((siblings.length - 1) * (NODE_H + 32)) / 2 + 240;
    const isSelected = step.id === selectedId;
    const isGate = !!step.human_gate || step.gate === 'human_approval';

    return {
      id: step.id,
      position: { x, y },
      data: { step },
      style: {
        background: isGate ? t.amberBg : t.cyanBg,
        border: `1px solid ${isSelected ? t.cyan : isGate ? t.amberBorder : t.cyanBorder}`,
        borderRadius: 8,
        width: NODE_W,
        padding: 0,
        boxShadow: isSelected ? `0 0 0 2px ${t.cyan}40` : 'none',
      },
    };
  });
}

function buildEdges(steps: WorkflowStep[]): Edge[] {
  const edges: Edge[] = [];
  steps.forEach(step => {
    step.depends_on.forEach(dep => {
      edges.push({
        id: `${dep}-${step.id}`,
        source: dep,
        target: step.id,
        type: 'smoothstep',
        style: { stroke: `${t.cyan}50`, strokeWidth: 1.5 },
        markerEnd: { type: MarkerType.ArrowClosed, color: `${t.cyan}50`, width: 14, height: 14 },
      });
    });
  });
  return edges;
}

// Custom node renderer
const WorkflowNode: React.FC<{ data: { step: WorkflowStep } }> = ({ data: { step } }) => {
  const isGate = !!step.human_gate || step.gate === 'human_approval';
  const displayLabel = step.label || step.id.replace(/_/g, ' ');
  return (
    <div className="flex flex-col" style={{ padding: '10px 14px', width: NODE_W }}>
      <div className="flex items-center gap-2 mb-1">
        <span className="material-symbols-outlined flex-shrink-0" style={{ fontSize: 14, color: isGate ? t.amber : t.cyan }}>
          {isGate ? 'pause_circle' : getIcon(step.agent)}
        </span>
        <span className="text-xs font-display font-semibold truncate" style={{ color: t.textPrimary }}>
          {displayLabel}
        </span>
      </div>
      <div className="text-[10px] font-mono truncate" style={{ color: t.textMuted }}>{step.agent}</div>
      {isGate && (
        <div className="text-[9px] font-sans mt-1 uppercase tracking-widest" style={{ color: t.amber }}>
          ⏸ Human Gate
        </div>
      )}
    </div>
  );
};

const nodeTypes = { default: WorkflowNode };

interface Props {
  parsed: ParsedWorkflow;
  onUpdate: (stepId: string, fields: Partial<WorkflowStep>) => void;
  onAdd: (agent: string) => string;
  onRemove: (stepId: string) => void;
}

const WorkflowCanvas: React.FC<Props> = ({ parsed, onUpdate, onAdd, onRemove }) => {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showPicker, setShowPicker] = useState(false);

  const initialNodes = useMemo(() => buildNodes(parsed.steps, selectedId), [parsed.steps, selectedId]);
  const initialEdges = useMemo(() => buildEdges(parsed.steps), [parsed.steps]);

  const [nodes, , onNodesChange] = useNodesState(initialNodes);
  const [edges, , onEdgesChange] = useEdgesState(initialEdges);

  const selectedStep = parsed.steps.find(s => s.id === selectedId) || null;

  const handleNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedId(prev => prev === node.id ? null : node.id);
  }, []);

  const handlePaneClick = useCallback(() => {
    setSelectedId(null);
  }, []);

  const handleAddStep = (agentId: string) => {
    const newId = onAdd(agentId);
    setSelectedId(newId);
    setShowPicker(false);
  };

  if (parsed.steps.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4" style={{ background: t.bgDeep }}>
        <span className="material-symbols-outlined" style={{ fontSize: 40, color: t.borderDefault }}>account_tree</span>
        <div className="text-sm font-sans" style={{ color: t.textMuted }}>No steps yet</div>
        <button
          onClick={() => setShowPicker(true)}
          className="flex items-center gap-2 px-4 py-2 rounded text-xs font-sans"
          style={{ background: t.cyanBg, border: `1px solid ${t.cyanBorder}`, color: t.cyan }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: 14 }}>add</span>
          Add First Step
        </button>
        {showPicker && <AgentPickerModal onSelect={handleAddStep} onClose={() => setShowPicker(false)} />}
      </div>
    );
  }

  return (
    <div className="flex h-full" style={{ background: t.bgDeep }}>
      {showPicker && <AgentPickerModal onSelect={handleAddStep} onClose={() => setShowPicker(false)} />}

      <div className="flex-1">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={handleNodeClick}
          onPaneClick={handlePaneClick}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.3 }}
          nodesDraggable
          nodesConnectable={false}
          elementsSelectable
        >
          <Background color={t.borderSubtle} gap={24} size={1} />
          <Controls showInteractive={false} style={{ background: t.bgSurface, border: `1px solid ${t.borderDefault}` }} />
          <Panel position="top-left">
            <div className="flex items-center gap-2 p-2">
              <button
                onClick={() => setShowPicker(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-sans"
                style={{ background: t.bgSurface, border: `1px solid ${t.borderDefault}`, color: t.textPrimary }}
              >
                <span className="material-symbols-outlined" style={{ fontSize: 13 }}>add</span>
                Add Step
              </button>
            </div>
          </Panel>
        </ReactFlow>
      </div>

      {selectedStep && (
        <StepConfigSidebar
          step={selectedStep}
          allSteps={parsed.steps}
          onUpdate={onUpdate}
          onRemove={(id) => { onRemove(id); setSelectedId(null); }}
          onClose={() => setSelectedId(null)}
        />
      )}
    </div>
  );
};

export default WorkflowCanvas;
```

**Step 2: Verify TypeScript compiles**
```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors

**Step 3: Commit**
```bash
git add frontend/src/components/Platform/WorkflowBuilder/WorkflowCanvas.tsx
git commit -m "feat(builder): WorkflowCanvas — interactive ReactFlow canvas with step config sidebar"
```

---

### Task 7: Create WorkflowList.tsx

**Files:**
- Create: `frontend/src/components/Platform/WorkflowBuilder/WorkflowList.tsx`

**What to do:**

Ordered step list view. Supports HTML5 drag-and-drop for reordering. Click a step to open the config sidebar (same `StepConfigSidebar` as Canvas).

**Step 1: Create the file**

```tsx
import React, { useState, useRef } from 'react';
import type { ParsedWorkflow, WorkflowStep } from './workflowParser';
import StepConfigSidebar from './StepConfigSidebar';
import AgentPickerModal from './AgentPickerModal';
import { t } from '../../../styles/tokens';

const AGENT_ICONS: Record<string, string> = {
  log_analysis_agent: 'description', metrics_agent: 'monitoring',
  k8s_agent: 'cloud', tracing_agent: 'timeline',
  code_navigator_agent: 'code', change_agent: 'edit_note',
  critic_agent: 'rate_review', fix_generator: 'build',
  db_agent: 'database', network_analysis_agent: 'hub',
};

interface Props {
  parsed: ParsedWorkflow;
  onUpdate: (stepId: string, fields: Partial<WorkflowStep>) => void;
  onAdd: (agent: string) => string;
  onRemove: (stepId: string) => void;
  onMove: (fromIndex: number, toIndex: number) => void;
}

const WorkflowList: React.FC<Props> = ({ parsed, onUpdate, onAdd, onRemove, onMove }) => {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showPicker, setShowPicker] = useState(false);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);
  const dragIndex = useRef<number | null>(null);

  const selectedStep = parsed.steps.find(s => s.id === selectedId) || null;

  const handleAddStep = (agentId: string) => {
    const newId = onAdd(agentId);
    setSelectedId(newId);
    setShowPicker(false);
  };

  return (
    <div className="flex h-full" style={{ background: t.bgBase }}>
      {showPicker && <AgentPickerModal onSelect={handleAddStep} onClose={() => setShowPicker(false)} />}

      {/* Step list */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b flex-shrink-0"
          style={{ borderColor: t.borderDefault }}>
          <span className="text-[10px] font-sans uppercase tracking-widest" style={{ color: t.textFaint }}>
            {parsed.steps.length} step{parsed.steps.length !== 1 ? 's' : ''}
          </span>
          <button
            onClick={() => setShowPicker(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-sans"
            style={{ background: t.cyanBg, border: `1px solid ${t.cyanBorder}`, color: t.cyan }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 13 }}>add</span>
            Add Step
          </button>
        </div>

        <div className="flex-1 overflow-auto px-5 py-3">
          {parsed.steps.length === 0 && (
            <div className="flex flex-col items-center justify-center h-48 gap-4">
              <span className="material-symbols-outlined" style={{ fontSize: 36, color: t.borderDefault }}>format_list_bulleted</span>
              <p className="text-sm font-sans" style={{ color: t.textMuted }}>No steps yet</p>
              <button
                onClick={() => setShowPicker(true)}
                className="flex items-center gap-2 px-4 py-2 rounded text-xs font-sans"
                style={{ background: t.cyanBg, border: `1px solid ${t.cyanBorder}`, color: t.cyan }}
              >
                <span className="material-symbols-outlined" style={{ fontSize: 14 }}>add</span>
                Add First Step
              </button>
            </div>
          )}

          {parsed.steps.map((step, index) => {
            const isSelected = step.id === selectedId;
            const isGate = !!step.human_gate || step.gate === 'human_approval';
            const displayLabel = step.label || step.id.replace(/_/g, ' ');
            const icon = AGENT_ICONS[step.agent] || 'smart_toy';
            const depLabels = step.depends_on.map(depId => {
              const dep = parsed.steps.find(s => s.id === depId);
              return dep?.label || depId;
            });

            return (
              <div
                key={step.id}
                draggable
                onDragStart={() => { dragIndex.current = index; }}
                onDragOver={e => { e.preventDefault(); setDragOverIndex(index); }}
                onDragLeave={() => setDragOverIndex(null)}
                onDrop={() => {
                  if (dragIndex.current !== null && dragIndex.current !== index) {
                    onMove(dragIndex.current, index);
                  }
                  setDragOverIndex(null);
                  dragIndex.current = null;
                }}
                onClick={() => setSelectedId(isSelected ? null : step.id)}
                className="flex items-start gap-3 px-4 py-3 rounded-lg mb-2 cursor-pointer"
                style={{
                  background: isSelected ? t.cyanSelected : t.bgSurface,
                  border: `1px solid ${isSelected ? t.cyan : dragOverIndex === index ? t.cyanBorder : t.borderDefault}`,
                  borderLeft: isSelected ? `3px solid ${t.cyan}` : isGate ? `3px solid ${t.amber}` : `1px solid ${t.borderDefault}`,
                }}
                role="button"
                tabIndex={0}
                aria-selected={isSelected}
                onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelectedId(isSelected ? null : step.id); } }}
              >
                {/* Drag handle */}
                <span className="material-symbols-outlined flex-shrink-0 mt-0.5 cursor-grab"
                  style={{ fontSize: 16, color: t.textFaint }}>drag_indicator</span>

                {/* Step number */}
                <div className="w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5"
                  style={{ background: t.bgTrack, fontSize: 10, color: t.textMuted, fontFamily: 'monospace' }}>
                  {index + 1}
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="material-symbols-outlined" style={{ fontSize: 13, color: isGate ? t.amber : t.cyan }}>
                      {isGate ? 'pause_circle' : icon}
                    </span>
                    <span className="text-xs font-display font-semibold" style={{ color: t.textPrimary }}>{displayLabel}</span>
                    {isGate && (
                      <span className="text-[9px] font-sans px-1.5 py-0.5 rounded uppercase tracking-widest"
                        style={{ background: t.amberBg, border: `1px solid ${t.amberBorder}`, color: t.amber }}>
                        Gate
                      </span>
                    )}
                  </div>
                  <div className="text-[10px] font-mono" style={{ color: t.textMuted }}>{step.agent}</div>
                  {depLabels.length > 0 && (
                    <div className="text-[10px] font-sans mt-1" style={{ color: t.textFaint }}>
                      After: {depLabels.join(', ')}
                    </div>
                  )}
                </div>

                <span className="material-symbols-outlined flex-shrink-0 mt-1"
                  style={{ fontSize: 14, color: t.textFaint, opacity: isSelected ? 1 : 0.4 }}>
                  chevron_right
                </span>
              </div>
            );
          })}

          {parsed.steps.length > 0 && (
            <button
              onClick={() => setShowPicker(true)}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-lg mt-1 text-xs font-sans"
              style={{ border: `1px dashed ${t.borderDefault}`, color: t.textFaint }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 14 }}>add</span>
              Add Step
            </button>
          )}
        </div>
      </div>

      {/* Config sidebar */}
      {selectedStep && (
        <StepConfigSidebar
          step={selectedStep}
          allSteps={parsed.steps}
          onUpdate={onUpdate}
          onRemove={(id) => { onRemove(id); setSelectedId(null); }}
          onClose={() => setSelectedId(null)}
        />
      )}
    </div>
  );
};

export default WorkflowList;
```

**Step 2: Verify TypeScript compiles**
```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors

**Step 3: Commit**
```bash
git add frontend/src/components/Platform/WorkflowBuilder/WorkflowList.tsx
git commit -m "feat(builder): WorkflowList — drag-to-reorder step list with config sidebar"
```

---

### Task 8: Create WorkflowCodeView.tsx

**Files:**
- Create: `frontend/src/components/Platform/WorkflowBuilder/WorkflowCodeView.tsx`

**What to do:**

Improved YAML editor with line numbers, sync indicator, format button, copy button, and inline error panel.

**Step 1: Create the file**

```tsx
import React, { useRef, useCallback } from 'react';
import { t } from '../../../styles/tokens';

interface Props {
  yaml: string;
  errors: string[];
  dirty: boolean;
  onChange: (yaml: string) => void;
}

const WorkflowCodeView: React.FC<Props> = ({ yaml, errors, dirty, onChange }) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleCopy = () => {
    navigator.clipboard.writeText(yaml).catch(() => {});
  };

  const handleFormat = () => {
    // Normalize indentation: ensure 2-space indent
    const formatted = yaml
      .split('\n')
      .map(line => {
        // Replace leading tabs with 2 spaces
        return line.replace(/^\t+/, match => '  '.repeat(match.length));
      })
      .join('\n');
    onChange(formatted);
  };

  const lineCount = yaml.split('\n').length;

  return (
    <div className="flex flex-col h-full" style={{ background: t.bgDeep }}>
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 border-b flex-shrink-0"
        style={{ borderColor: t.borderDefault, background: t.bgSurface }}>
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-1.5 rounded-full"
            style={{ background: dirty ? t.amber : t.green }} />
          <span className="text-[10px] font-sans" style={{ color: dirty ? t.amber : t.green }}>
            {dirty ? 'Unsaved changes' : 'Synced'}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleFormat}
            className="flex items-center gap-1 text-[10px] font-sans px-2 py-1 rounded"
            style={{ border: `1px solid ${t.borderDefault}`, color: t.textMuted }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 11 }}>format_align_left</span>
            Format
          </button>
          <button
            onClick={handleCopy}
            className="flex items-center gap-1 text-[10px] font-sans px-2 py-1 rounded"
            style={{ border: `1px solid ${t.borderDefault}`, color: t.textMuted }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 11 }}>content_copy</span>
            Copy
          </button>
        </div>
      </div>

      {/* Editor with line numbers */}
      <div className="flex flex-1 overflow-hidden font-mono text-xs">
        {/* Line numbers */}
        <div
          className="flex flex-col items-end px-3 pt-4 select-none flex-shrink-0 overflow-hidden"
          style={{
            background: t.bgSurface,
            borderRight: `1px solid ${t.borderSubtle}`,
            color: t.textFaint,
            minWidth: 44,
            lineHeight: '1.6',
            fontSize: 11,
          }}
          aria-hidden="true"
        >
          {Array.from({ length: lineCount }, (_, i) => (
            <div key={i} style={{ lineHeight: '1.6' }}>{i + 1}</div>
          ))}
        </div>

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          value={yaml}
          onChange={e => onChange(e.target.value)}
          spellCheck={false}
          aria-label="Workflow YAML editor"
          className="flex-1 resize-none p-4 text-xs font-mono"
          style={{
            background: t.bgDeep,
            color: t.textPrimary,
            lineHeight: 1.6,
            outline: 'none',
            border: 'none',
          }}
          onFocus={e => { e.currentTarget.style.boxShadow = `0 0 0 1px ${t.cyan}40 inset`; }}
          onBlur={e => { e.currentTarget.style.boxShadow = 'none'; }}
        />
      </div>

      {/* Error panel */}
      {errors.length > 0 && (
        <div className="border-t flex-shrink-0" style={{ borderColor: t.borderDefault, background: t.bgSurface }}>
          {errors.map((err, i) => (
            <div key={i} className="flex items-start gap-2 px-4 py-2"
              style={{ borderBottom: i < errors.length - 1 ? `1px solid ${t.borderSubtle}` : 'none' }}>
              <span className="material-symbols-outlined flex-shrink-0 mt-0.5" style={{ fontSize: 13, color: t.red }}>error</span>
              <span className="text-[10px] font-sans" style={{ color: t.red }}>{err}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default WorkflowCodeView;
```

**Step 2: Verify TypeScript compiles**
```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors

**Step 3: Commit**
```bash
git add frontend/src/components/Platform/WorkflowBuilder/WorkflowCodeView.tsx
git commit -m "feat(builder): WorkflowCodeView — line numbers, sync indicator, format/copy buttons"
```

---

### Task 9: Redesign WorkflowLibraryView.tsx

**Files:**
- Modify: `frontend/src/components/Platform/WorkflowBuilder/WorkflowLibraryView.tsx`

**What to do:**

Full rewrite of the library landing page. App Diagnostics becomes the hero card (full width, recommended badge). Other templates are compact rows. Saved workflows show last-modified timestamp. Search filters both sections.

**Step 1: Rewrite the file completely**

```tsx
import React, { useState, useEffect, useMemo } from 'react';
import { WORKFLOW_TEMPLATES } from './workflowParser';
import type { WorkflowTemplate } from './workflowParser';
import { t } from '../../../styles/tokens';

const LS_SAVED_KEY = 'platform_saved_workflows';

interface SavedWorkflow { id: string; name: string; yaml: string; savedAt: string; }

function loadSaved(): SavedWorkflow[] {
  try { return JSON.parse(localStorage.getItem(LS_SAVED_KEY) || '[]'); } catch { return []; }
}

interface Props { onOpen: (yaml: string) => void; onNew: () => void; }

const WorkflowLibraryView: React.FC<Props> = ({ onOpen, onNew }) => {
  const [saved, setSaved] = useState<SavedWorkflow[]>([]);
  const [search, setSearch] = useState('');

  useEffect(() => { setSaved(loadSaved()); }, []);

  const handleDelete = (id: string) => {
    const updated = saved.filter(w => w.id !== id);
    setSaved(updated);
    localStorage.setItem(LS_SAVED_KEY, JSON.stringify(updated));
  };

  const heroTemplate = WORKFLOW_TEMPLATES[0]; // App Diagnostics
  const otherTemplates = WORKFLOW_TEMPLATES.slice(1);

  const filteredOthers = useMemo(() =>
    search ? otherTemplates.filter(t =>
      t.name.toLowerCase().includes(search.toLowerCase()) ||
      t.description.toLowerCase().includes(search.toLowerCase())
    ) : otherTemplates,
    [search, otherTemplates]
  );

  const filteredSaved = useMemo(() =>
    search ? saved.filter(w => w.name.toLowerCase().includes(search.toLowerCase())) : saved,
    [search, saved]
  );

  const heroVisible = !search || heroTemplate.name.toLowerCase().includes(search.toLowerCase());

  return (
    <div className="flex flex-col h-full overflow-auto" style={{ background: t.bgBase }}>
      {/* Header */}
      <div className="flex items-center justify-between px-8 pt-8 pb-5 flex-shrink-0">
        <div>
          <h1 className="text-2xl font-display font-bold" style={{ color: t.textPrimary }}>Workflows</h1>
          <p className="text-sm font-sans mt-1" style={{ color: t.textMuted }}>
            Build, configure, and run diagnostic workflows.
          </p>
        </div>
        <button
          onClick={onNew}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-sans"
          style={{ background: t.cyanBg, border: `1px solid ${t.cyanBorder}`, color: t.cyan }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: 16 }}>add</span>
          New Workflow
        </button>
      </div>

      {/* Search */}
      <div className="px-8 pb-5">
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg"
          style={{ background: t.bgSurface, border: `1px solid ${t.borderDefault}`, maxWidth: 480 }}>
          <span className="material-symbols-outlined" style={{ fontSize: 16, color: t.textFaint }}>search</span>
          <input
            type="text"
            placeholder="Search workflows..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="flex-1 text-sm font-sans bg-transparent outline-none"
            style={{ color: t.textPrimary }}
            aria-label="Search workflows"
          />
          {search && (
            <button onClick={() => setSearch('')} aria-label="Clear search">
              <span className="material-symbols-outlined" style={{ fontSize: 14, color: t.textFaint }}>close</span>
            </button>
          )}
        </div>
      </div>

      <div className="flex-1 px-8 pb-8 space-y-8">
        {/* Hero card — App Diagnostics */}
        {heroVisible && (
          <section>
            <h2 className="text-xs font-sans uppercase tracking-widest mb-3" style={{ color: t.textFaint }}>
              Recommended
            </h2>
            <HeroCard template={heroTemplate} onOpen={() => onOpen(heroTemplate.yaml)} />
          </section>
        )}

        {/* Other templates */}
        {filteredOthers.length > 0 && (
          <section>
            <h2 className="text-xs font-sans uppercase tracking-widest mb-3" style={{ color: t.textFaint }}>
              Templates
            </h2>
            <div className="space-y-px rounded-lg overflow-hidden" style={{ border: `1px solid ${t.borderDefault}`, maxWidth: 820 }}>
              {filteredOthers.map((template, i) => (
                <TemplateRow
                  key={template.id}
                  template={template}
                  onOpen={() => onOpen(template.yaml)}
                  isLast={i === filteredOthers.length - 1}
                />
              ))}
            </div>
          </section>
        )}

        {/* Saved workflows */}
        {filteredSaved.length > 0 && (
          <section>
            <h2 className="text-xs font-sans uppercase tracking-widest mb-3" style={{ color: t.textFaint }}>
              My Workflows
            </h2>
            <div className="space-y-px rounded-lg overflow-hidden" style={{ border: `1px solid ${t.borderDefault}`, maxWidth: 820 }}>
              {filteredSaved.map((workflow, i) => (
                <SavedRow
                  key={workflow.id}
                  workflow={workflow}
                  onOpen={() => onOpen(workflow.yaml)}
                  onDelete={() => handleDelete(workflow.id)}
                  isLast={i === filteredSaved.length - 1}
                />
              ))}
            </div>
          </section>
        )}

        {/* No results */}
        {search && !heroVisible && filteredOthers.length === 0 && filteredSaved.length === 0 && (
          <div className="flex flex-col items-center justify-center h-32 gap-2">
            <span className="text-sm font-sans" style={{ color: t.textMuted }}>No workflows match "{search}"</span>
            <button onClick={() => setSearch('')} className="text-xs font-sans" style={{ color: t.cyan }}>
              Clear search
            </button>
          </div>
        )}

        {/* Empty saved state */}
        {!search && saved.length === 0 && (
          <p className="text-xs font-sans" style={{ color: t.textFaint }}>
            No saved workflows yet — open a template and click Save.
          </p>
        )}
      </div>
    </div>
  );
};

// Hero card — full width, recommended badge
const HeroCard: React.FC<{ template: WorkflowTemplate; onOpen: () => void }> = ({ template, onOpen }) => {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      onClick={onOpen}
      className="w-full text-left rounded-lg p-6"
      style={{
        background: t.bgSurface,
        border: `1px solid ${hovered ? t.cyanBorder : t.borderDefault}`,
        maxWidth: 820,
        transition: 'border-color 0.15s',
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0"
            style={{ background: t.cyanBg, border: `1px solid ${t.cyanBorder}` }}>
            <span className="material-symbols-outlined" style={{ fontSize: 20, color: t.cyan }}>{template.icon}</span>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-base font-display font-bold" style={{ color: t.textPrimary }}>{template.name}</span>
              <span className="text-[10px] font-sans px-2 py-0.5 rounded-full uppercase tracking-widest"
                style={{ background: t.cyanBg, border: `1px solid ${t.cyanBorder}`, color: t.cyan }}>
                Recommended
              </span>
            </div>
            <span className="text-[10px] font-mono" style={{ color: t.textMuted }}>{template.stepCount} steps</span>
          </div>
        </div>
        <span className="material-symbols-outlined transition-opacity"
          style={{ fontSize: 20, color: t.cyan, opacity: hovered ? 1 : 0.3 }}>
          arrow_forward
        </span>
      </div>
      <p className="text-sm font-sans leading-relaxed" style={{ color: t.textMuted }}>{template.description}</p>
    </button>
  );
};

// Compact template row
const TemplateRow: React.FC<{ template: WorkflowTemplate; onOpen: () => void; isLast: boolean }> = ({ template, onOpen, isLast }) => {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      onClick={onOpen}
      className="w-full text-left flex items-center gap-4 px-5 py-4"
      style={{
        background: hovered ? t.cyanSelected : t.bgSurface,
        borderBottom: isLast ? 'none' : `1px solid ${t.borderSubtle}`,
        transition: 'background 0.1s',
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <span className="material-symbols-outlined flex-shrink-0" style={{ fontSize: 18, color: t.textFaint }}>{template.icon}</span>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-display font-semibold" style={{ color: t.textPrimary }}>{template.name}</div>
        <div className="text-xs font-sans mt-0.5 truncate" style={{ color: t.textMuted }}>{template.description}</div>
      </div>
      <span className="text-[10px] font-mono flex-shrink-0" style={{ color: t.textFaint }}>{template.stepCount} steps</span>
      <span className="material-symbols-outlined flex-shrink-0" style={{ fontSize: 16, color: t.cyan, opacity: hovered ? 1 : 0.3 }}>
        arrow_forward
      </span>
    </button>
  );
};

// Saved workflow row
const SavedRow: React.FC<{ workflow: SavedWorkflow; onOpen: () => void; onDelete: () => void; isLast: boolean }> = ({ workflow, onOpen, onDelete, isLast }) => {
  const [hovered, setHovered] = useState(false);
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen(); } }}
      className="flex items-center gap-4 px-5 py-4 cursor-pointer"
      style={{
        background: hovered ? t.cyanSelected : t.bgSurface,
        borderBottom: isLast ? 'none' : `1px solid ${t.borderSubtle}`,
        transition: 'background 0.1s',
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <span className="material-symbols-outlined flex-shrink-0" style={{ fontSize: 18, color: t.textFaint }}>description</span>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-display font-medium truncate" style={{ color: t.textPrimary }}>{workflow.name}</div>
        <div className="text-[10px] font-sans mt-0.5" style={{ color: t.textMuted }}>
          Modified {new Date(workflow.savedAt).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
        </div>
      </div>
      <button
        onClick={e => { e.stopPropagation(); onDelete(); }}
        className="p-1.5 rounded transition-opacity"
        aria-label={`Delete ${workflow.name}`}
        style={{ color: t.red, opacity: hovered ? 1 : 0 }}
      >
        <span className="material-symbols-outlined" style={{ fontSize: 16 }}>delete</span>
      </button>
      <span className="material-symbols-outlined flex-shrink-0" style={{ fontSize: 16, color: t.cyan, opacity: hovered ? 1 : 0.3 }}>
        arrow_forward
      </span>
    </div>
  );
};

export default WorkflowLibraryView;
```

**Step 2: Verify TypeScript compiles**
```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors

**Step 3: Commit**
```bash
git add frontend/src/components/Platform/WorkflowBuilder/WorkflowLibraryView.tsx
git commit -m "feat(builder): WorkflowLibraryView — hero card, search, compact template rows"
```

---

### Task 10: Rewrite WorkflowBuilderView.tsx — wire everything together

**Files:**
- Modify: `frontend/src/components/Platform/WorkflowBuilder/WorkflowBuilderView.tsx`

**What to do:**

The top-level orchestrator. Owns view state (library/editor), view type (canvas/list/code), inline name editing, and wires `useWorkflowState` into all three views.

**Step 1: Rewrite the file completely**

```tsx
import React, { useState, useRef, useEffect } from 'react';
import { APP_DIAGNOSTICS_TEMPLATE } from './workflowParser';
import { useWorkflowState } from './useWorkflowState';
import WorkflowLibraryView from './WorkflowLibraryView';
import WorkflowCanvas from './WorkflowCanvas';
import WorkflowList from './WorkflowList';
import WorkflowCodeView from './WorkflowCodeView';
import { t } from '../../../styles/tokens';

const LS_KEY = 'platform_workflow_builder_yaml';
const LS_SAVED_KEY = 'platform_saved_workflows';

const BLANK_TEMPLATE = `id: new_workflow
name: New Workflow
version: "1.0"
trigger: [api]

steps:
`;

type ViewMode = 'canvas' | 'list' | 'code';

const WorkflowBuilderView: React.FC = () => {
  const [mode, setMode] = useState<'library' | 'editor'>('library');
  const [viewMode, setViewMode] = useState<ViewMode>('list');
  const [editingName, setEditingName] = useState(false);
  const [savedSuccess, setSavedSuccess] = useState(false);
  const nameInputRef = useRef<HTMLInputElement>(null);

  const initialYaml = localStorage.getItem(LS_KEY) || APP_DIAGNOSTICS_TEMPLATE;
  const {
    yaml, parsed, dirty,
    setYaml, updateWorkflowMeta,
    addStep, updateStep, removeStep, moveStep,
    save,
  } = useWorkflowState(initialYaml);

  useEffect(() => {
    if (editingName) nameInputRef.current?.focus();
  }, [editingName]);

  const openWorkflow = (workflowYaml: string) => {
    setYaml(workflowYaml);
    localStorage.setItem(LS_KEY, workflowYaml);
    setMode('editor');
  };

  const handleSave = () => {
    const { id, name, yaml: savedYaml } = save();
    // Persist to saved workflows list
    try {
      const existing = JSON.parse(localStorage.getItem(LS_SAVED_KEY) || '[]');
      const filtered = existing.filter((w: any) => w.id !== (id || 'untitled'));
      const updated = [{
        id: id || `workflow_${Date.now()}`,
        name: name || 'Untitled Workflow',
        yaml: savedYaml,
        savedAt: new Date().toISOString(),
      }, ...filtered];
      localStorage.setItem(LS_SAVED_KEY, JSON.stringify(updated));
    } catch { /* noop */ }
    setSavedSuccess(true);
    setTimeout(() => setSavedSuccess(false), 2000);
  };

  if (mode === 'library') {
    return (
      <WorkflowLibraryView
        onOpen={openWorkflow}
        onNew={() => openWorkflow(BLANK_TEMPLATE)}
      />
    );
  }

  const hasErrors = parsed.errors.length > 0;

  return (
    <div className="flex flex-col h-full" style={{ background: t.bgBase }}>
      {/* Toolbar */}
      <div className="flex items-center gap-4 px-4 py-3 border-b flex-shrink-0"
        style={{ borderColor: t.borderDefault, background: t.bgSurface }}>

        {/* Left: back + name */}
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <button
            onClick={() => setMode('library')}
            className="flex items-center gap-1 text-xs font-sans flex-shrink-0"
            style={{ color: t.textMuted }}
            onMouseEnter={e => (e.currentTarget.style.color = t.textPrimary)}
            onMouseLeave={e => (e.currentTarget.style.color = t.textMuted)}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 14 }}>arrow_back</span>
            Workflows
          </button>

          <span style={{ color: t.borderDefault, flexShrink: 0 }}>·</span>

          <div className="min-w-0">
            {editingName ? (
              <input
                ref={nameInputRef}
                defaultValue={parsed.name || ''}
                className="text-sm font-display font-semibold px-1 rounded outline-none"
                style={{
                  background: t.bgDeep,
                  border: `1px solid ${t.cyanBorder}`,
                  color: t.textPrimary,
                  minWidth: 160,
                }}
                onBlur={e => {
                  updateWorkflowMeta({ name: e.target.value });
                  setEditingName(false);
                }}
                onKeyDown={e => {
                  if (e.key === 'Enter') { (e.target as HTMLInputElement).blur(); }
                  if (e.key === 'Escape') setEditingName(false);
                }}
              />
            ) : (
              <button
                onClick={() => setEditingName(true)}
                className="flex items-center gap-1.5 group"
                title="Click to rename"
              >
                <span className="text-sm font-display font-semibold truncate" style={{ color: t.textPrimary }}>
                  {parsed.name || 'Untitled Workflow'}
                </span>
                <span className="material-symbols-outlined opacity-0 group-hover:opacity-100 transition-opacity"
                  style={{ fontSize: 13, color: t.textFaint }}>edit</span>
              </button>
            )}
            {parsed.id && (
              <div className="text-[10px] font-mono" style={{ color: t.textFaint }}>{parsed.id}</div>
            )}
          </div>
        </div>

        {/* Center: view switcher */}
        <div className="flex items-center rounded overflow-hidden flex-shrink-0"
          style={{ border: `1px solid ${t.borderDefault}`, background: t.bgDeep }}>
          {(['canvas', 'list', 'code'] as ViewMode[]).map(v => (
            <button
              key={v}
              onClick={() => setViewMode(v)}
              className="px-3 py-1.5 text-xs font-sans capitalize"
              aria-pressed={viewMode === v}
              style={{
                background: viewMode === v ? t.cyanBg : 'transparent',
                color: viewMode === v ? t.cyan : t.textMuted,
                borderRight: v !== 'code' ? `1px solid ${t.borderDefault}` : 'none',
              }}
            >
              {v === 'canvas' && <span className="material-symbols-outlined mr-1" style={{ fontSize: 11, verticalAlign: 'middle' }}>account_tree</span>}
              {v === 'list' && <span className="material-symbols-outlined mr-1" style={{ fontSize: 11, verticalAlign: 'middle' }}>format_list_bulleted</span>}
              {v === 'code' && <span className="material-symbols-outlined mr-1" style={{ fontSize: 11, verticalAlign: 'middle' }}>code</span>}
              {v}
            </button>
          ))}
        </div>

        {/* Right: status + actions */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <span
            className="flex items-center gap-1 text-[10px] font-sans px-2 py-1 rounded"
            style={{
              background: hasErrors ? t.redBg : t.greenBg,
              border: `1px solid ${hasErrors ? t.redBorder : t.greenBorder}`,
              color: hasErrors ? t.red : t.green,
            }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 11 }}>
              {hasErrors ? 'error' : 'check_circle'}
            </span>
            {hasErrors ? `${parsed.errors.length} error${parsed.errors.length !== 1 ? 's' : ''}` : 'Valid'}
          </span>

          <button
            onClick={handleSave}
            className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-sans"
            style={{
              background: savedSuccess ? t.greenBg : 'transparent',
              border: `1px solid ${savedSuccess ? t.greenBorder : t.borderDefault}`,
              color: savedSuccess ? t.green : t.textMuted,
            }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 13 }}>
              {savedSuccess ? 'check' : 'save'}
            </span>
            {savedSuccess ? 'Saved' : 'Save'}
          </button>

          <button
            className="flex items-center gap-1.5 px-4 py-1.5 rounded text-xs font-sans font-semibold"
            style={{ background: t.cyan, color: '#0a1214' }}
            onClick={() => {/* Navigate to runs — wired by parent via onNavigate if needed */}}
            title="Run this workflow"
          >
            <span className="material-symbols-outlined" style={{ fontSize: 14 }}>play_arrow</span>
            Run
          </button>
        </div>
      </div>

      {/* View area */}
      <div className="flex-1 overflow-hidden">
        {viewMode === 'canvas' && (
          <WorkflowCanvas
            parsed={parsed}
            onUpdate={updateStep}
            onAdd={addStep}
            onRemove={removeStep}
          />
        )}
        {viewMode === 'list' && (
          <WorkflowList
            parsed={parsed}
            onUpdate={updateStep}
            onAdd={addStep}
            onRemove={removeStep}
            onMove={moveStep}
          />
        )}
        {viewMode === 'code' && (
          <WorkflowCodeView
            yaml={yaml}
            errors={parsed.errors}
            dirty={dirty}
            onChange={setYaml}
          />
        )}
      </div>
    </div>
  );
};

export default WorkflowBuilderView;
```

**Step 2: Remove now-unused files** (replaced by new components):
```bash
rm frontend/src/components/Platform/WorkflowBuilder/WorkflowDagPreview.tsx
rm frontend/src/components/Platform/WorkflowBuilder/AgentBrowserPanel.tsx
```

**Step 3: Verify TypeScript compiles**
```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors. If there are import errors from files that imported `WorkflowDagPreview` or `AgentBrowserPanel`, fix those imports.

**Step 4: Run the dev server and manually verify:**
- Library page shows hero card + template rows + search
- Opening a template switches to editor mode
- Canvas view shows interactive nodes; clicking a node opens config sidebar
- List view shows step cards; clicking a step opens config sidebar; drag handle reorders
- Code view shows line numbers, sync indicator, format button
- Adding a step opens the agent picker modal
- Config sidebar: all fields update and reflect in the other views
- Save button persists to localStorage

**Step 5: Commit**
```bash
git add frontend/src/components/Platform/WorkflowBuilder/
git commit -m "feat(builder): enterprise workflow builder — canvas + list + code views with step config sidebar"
```
