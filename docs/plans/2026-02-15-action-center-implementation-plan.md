# Action Center UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the blank landing state with a capability-first Action Center, move the session form from sidebar to center, and replace the tab layout with a split Chat + Results Panel that reveals progressively.

**Architecture:** The center area transitions through 3 states: Action Center (home) → Capability Form → Active Session (chat left + results right). The sidebar remains for session history. A multi-step progress bar replaces the status bar. Existing dashboard/activity components are recomposed into a scrollable right panel.

**Tech Stack:** React 18, TypeScript, Tailwind CSS, lucide-react icons

**Design Doc:** `docs/plans/2026-02-15-action-center-ui-design.md`

---

## Phase 1: Types & API Foundation

### Task 1: Add capability types and form models

**Files:**
- Modify: `frontend/src/types/index.ts`

**Step 1: Add the new types at the bottom of the V4 Types section**

```typescript
// ===== Action Center Types =====

export type CapabilityType =
  | 'troubleshoot_app'
  | 'pr_review'
  | 'github_issue_fix'
  | 'cluster_diagnostics';

export interface CapabilityConfig {
  id: CapabilityType;
  label: string;
  subtitle: string;
  icon: string; // lucide icon name
  color: string; // tailwind color class
}

export interface TroubleshootAppForm {
  capability: 'troubleshoot_app';
  service_name: string;
  time_window: string;
  trace_id?: string;
  namespace?: string;
  elk_index?: string;
  repo_url?: string;
}

export interface PRReviewForm {
  capability: 'pr_review';
  repo_url: string;
  pr_number: string;
  focus_areas?: string[];
}

export interface GithubIssueFixForm {
  capability: 'github_issue_fix';
  repo_url: string;
  issue_number: string;
  target_branch?: string;
}

export interface ClusterDiagnosticsForm {
  capability: 'cluster_diagnostics';
  cluster_url: string;
  namespace?: string;
  symptoms?: string;
  auth_token?: string;
}

export type CapabilityFormData =
  | TroubleshootAppForm
  | PRReviewForm
  | GithubIssueFixForm
  | ClusterDiagnosticsForm;

// Extend V4Session to include capability type
export interface V4SessionExtended extends V4Session {
  capability: CapabilityType;
}
```

**Step 2: Run build to verify types compile**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat: add capability types and form models for Action Center"
```

---

## Phase 2: Action Center Component

### Task 2: Create ActionCenter component

**Files:**
- Create: `frontend/src/components/ActionCenter/ActionCenter.tsx`
- Create: `frontend/src/components/ActionCenter/CapabilityCard.tsx`

**Step 1: Create CapabilityCard.tsx**

```tsx
// frontend/src/components/ActionCenter/CapabilityCard.tsx
import React from 'react';
import { Search, FileText, Bug, Container } from 'lucide-react';
import type { CapabilityType } from '../../types';

interface CapabilityCardProps {
  id: CapabilityType;
  label: string;
  subtitle: string;
  icon: string;
  color: string;
  onClick: (id: CapabilityType) => void;
}

const iconMap: Record<string, React.FC<{ className?: string }>> = {
  search: Search,
  'file-text': FileText,
  bug: Bug,
  container: Container,
};

const CapabilityCard: React.FC<CapabilityCardProps> = ({
  id,
  label,
  subtitle,
  icon,
  color,
  onClick,
}) => {
  const Icon = iconMap[icon] || Search;

  return (
    <button
      onClick={() => onClick(id)}
      className={`group relative flex flex-col items-center justify-center p-8 rounded-xl border border-gray-700 bg-gray-900/50 hover:bg-gray-800/80 hover:border-gray-500 transition-all duration-200 text-center`}
    >
      <div className={`w-14 h-14 rounded-xl ${color} flex items-center justify-center mb-4 group-hover:scale-110 transition-transform`}>
        <Icon className="w-7 h-7 text-white" />
      </div>
      <h3 className="text-lg font-semibold text-white mb-1">{label}</h3>
      <p className="text-sm text-gray-400 leading-snug">{subtitle}</p>
    </button>
  );
};

export default CapabilityCard;
```

**Step 2: Create ActionCenter.tsx**

```tsx
// frontend/src/components/ActionCenter/ActionCenter.tsx
import React from 'react';
import type { CapabilityType, V4Session } from '../../types';
import CapabilityCard from './CapabilityCard';

const capabilities = [
  {
    id: 'troubleshoot_app' as CapabilityType,
    label: 'Troubleshoot Application',
    subtitle: 'Diagnose production incidents with AI agents',
    icon: 'search',
    color: 'bg-blue-600',
  },
  {
    id: 'pr_review' as CapabilityType,
    label: 'PR Review',
    subtitle: 'AI-powered code review for pull requests',
    icon: 'file-text',
    color: 'bg-purple-600',
  },
  {
    id: 'github_issue_fix' as CapabilityType,
    label: 'GitHub Issue Fix',
    subtitle: 'Analyze and fix GitHub issues automatically',
    icon: 'bug',
    color: 'bg-orange-600',
  },
  {
    id: 'cluster_diagnostics' as CapabilityType,
    label: 'Cluster Diagnostics',
    subtitle: 'OpenShift & Kubernetes health analysis',
    icon: 'container',
    color: 'bg-teal-600',
  },
];

interface ActionCenterProps {
  onSelectCapability: (capability: CapabilityType) => void;
  recentSessions: V4Session[];
  onResumeSession: (session: V4Session) => void;
}

const ActionCenter: React.FC<ActionCenterProps> = ({
  onSelectCapability,
  recentSessions,
  onResumeSession,
}) => {
  const recents = recentSessions.slice(0, 5);

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-8">
      {/* Title */}
      <h1 className="text-3xl font-bold text-white mb-2">
        AI SRE Platform
      </h1>
      <p className="text-gray-400 mb-10">What would you like to do?</p>

      {/* Capability cards - 2x2 grid */}
      <div className="grid grid-cols-2 gap-4 max-w-2xl w-full mb-12">
        {capabilities.map((cap) => (
          <CapabilityCard
            key={cap.id}
            {...cap}
            onClick={onSelectCapability}
          />
        ))}
      </div>

      {/* Recent sessions */}
      {recents.length > 0 && (
        <div className="max-w-2xl w-full">
          <h2 className="text-sm font-medium text-gray-500 uppercase tracking-wide mb-3">
            Recent Activity
          </h2>
          <div className="space-y-1">
            {recents.map((session) => (
              <button
                key={session.session_id}
                onClick={() => onResumeSession(session)}
                className="w-full flex items-center justify-between px-4 py-3 rounded-lg hover:bg-gray-800/50 transition-colors group"
              >
                <div className="flex items-center gap-3">
                  <span className={`w-2 h-2 rounded-full ${
                    session.status === 'complete' ? 'bg-green-500' :
                    session.status === 'initial' ? 'bg-gray-500' :
                    'bg-blue-500 animate-pulse'
                  }`} />
                  <span className="text-sm text-white">{session.service_name}</span>
                  <span className="text-xs text-gray-500">
                    {new Date(session.created_at).toLocaleDateString([], {
                      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
                    })}
                  </span>
                </div>
                <span className="text-xs text-gray-600 group-hover:text-gray-400 transition-colors">
                  Resume →
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default ActionCenter;
```

**Step 3: Verify build**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/components/ActionCenter/
git commit -m "feat: create Action Center with capability cards and recent sessions"
```

---

### Task 3: Create CapabilityForm component

**Files:**
- Create: `frontend/src/components/ActionCenter/CapabilityForm.tsx`
- Create: `frontend/src/components/ActionCenter/forms/TroubleshootAppFields.tsx`
- Create: `frontend/src/components/ActionCenter/forms/PRReviewFields.tsx`
- Create: `frontend/src/components/ActionCenter/forms/GithubIssueFixFields.tsx`
- Create: `frontend/src/components/ActionCenter/forms/ClusterDiagnosticsFields.tsx`

**Step 1: Create TroubleshootAppFields.tsx**

```tsx
// frontend/src/components/ActionCenter/forms/TroubleshootAppFields.tsx
import React from 'react';
import type { TroubleshootAppForm } from '../../../types';

interface Props {
  data: TroubleshootAppForm;
  onChange: (data: TroubleshootAppForm) => void;
}

const TroubleshootAppFields: React.FC<Props> = ({ data, onChange }) => {
  const update = (field: Partial<TroubleshootAppForm>) =>
    onChange({ ...data, ...field });

  return (
    <>
      <div>
        <label className="block text-sm text-gray-300 mb-1.5">Service Name *</label>
        <input
          type="text"
          value={data.service_name}
          onChange={(e) => update({ service_name: e.target.value })}
          className="w-full px-4 py-2.5 bg-gray-800 border border-gray-600 rounded-lg text-white text-sm focus:border-blue-500 focus:outline-none"
          placeholder="e.g. order-service"
          required
        />
      </div>
      <div>
        <label className="block text-sm text-gray-300 mb-1.5">Time Window *</label>
        <select
          value={data.time_window}
          onChange={(e) => update({ time_window: e.target.value })}
          className="w-full px-4 py-2.5 bg-gray-800 border border-gray-600 rounded-lg text-white text-sm focus:border-blue-500 focus:outline-none"
        >
          <option value="15m">Last 15 minutes</option>
          <option value="30m">Last 30 minutes</option>
          <option value="1h">Last 1 hour</option>
          <option value="3h">Last 3 hours</option>
          <option value="6h">Last 6 hours</option>
          <option value="24h">Last 24 hours</option>
        </select>
      </div>
      <div>
        <label className="block text-sm text-gray-300 mb-1.5">Trace ID</label>
        <input
          type="text"
          value={data.trace_id || ''}
          onChange={(e) => update({ trace_id: e.target.value || undefined })}
          className="w-full px-4 py-2.5 bg-gray-800 border border-gray-600 rounded-lg text-white text-sm focus:border-blue-500 focus:outline-none"
          placeholder="Optional — for trace-level analysis"
        />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm text-gray-300 mb-1.5">Namespace</label>
          <input
            type="text"
            value={data.namespace || ''}
            onChange={(e) => update({ namespace: e.target.value || undefined })}
            className="w-full px-4 py-2.5 bg-gray-800 border border-gray-600 rounded-lg text-white text-sm focus:border-blue-500 focus:outline-none"
            placeholder="production"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-300 mb-1.5">ELK Index</label>
          <input
            type="text"
            value={data.elk_index || ''}
            onChange={(e) => update({ elk_index: e.target.value || undefined })}
            className="w-full px-4 py-2.5 bg-gray-800 border border-gray-600 rounded-lg text-white text-sm focus:border-blue-500 focus:outline-none"
            placeholder="app-logs-*"
          />
        </div>
      </div>
      <div>
        <label className="block text-sm text-gray-300 mb-1.5">Repository URL</label>
        <input
          type="text"
          value={data.repo_url || ''}
          onChange={(e) => update({ repo_url: e.target.value || undefined })}
          className="w-full px-4 py-2.5 bg-gray-800 border border-gray-600 rounded-lg text-white text-sm focus:border-blue-500 focus:outline-none"
          placeholder="https://github.com/org/repo"
        />
      </div>
    </>
  );
};

export default TroubleshootAppFields;
```

**Step 2: Create PRReviewFields.tsx**

```tsx
// frontend/src/components/ActionCenter/forms/PRReviewFields.tsx
import React from 'react';
import type { PRReviewForm } from '../../../types';

interface Props {
  data: PRReviewForm;
  onChange: (data: PRReviewForm) => void;
}

const focusOptions = ['security', 'performance', 'correctness', 'style'] as const;

const PRReviewFields: React.FC<Props> = ({ data, onChange }) => {
  const update = (field: Partial<PRReviewForm>) =>
    onChange({ ...data, ...field });

  const toggleFocus = (area: string) => {
    const current = data.focus_areas || [];
    const updated = current.includes(area)
      ? current.filter((a) => a !== area)
      : [...current, area];
    update({ focus_areas: updated.length > 0 ? updated : undefined });
  };

  return (
    <>
      <div>
        <label className="block text-sm text-gray-300 mb-1.5">Repository URL *</label>
        <input
          type="text"
          value={data.repo_url}
          onChange={(e) => update({ repo_url: e.target.value })}
          className="w-full px-4 py-2.5 bg-gray-800 border border-gray-600 rounded-lg text-white text-sm focus:border-blue-500 focus:outline-none"
          placeholder="https://github.com/org/repo"
          required
        />
      </div>
      <div>
        <label className="block text-sm text-gray-300 mb-1.5">PR Number or URL *</label>
        <input
          type="text"
          value={data.pr_number}
          onChange={(e) => update({ pr_number: e.target.value })}
          className="w-full px-4 py-2.5 bg-gray-800 border border-gray-600 rounded-lg text-white text-sm focus:border-blue-500 focus:outline-none"
          placeholder="142 or https://github.com/org/repo/pull/142"
          required
        />
      </div>
      <div>
        <label className="block text-sm text-gray-300 mb-1.5">Focus Areas</label>
        <div className="flex flex-wrap gap-2">
          {focusOptions.map((area) => (
            <button
              key={area}
              type="button"
              onClick={() => toggleFocus(area)}
              className={`px-3 py-1.5 rounded-lg text-sm capitalize transition-colors ${
                (data.focus_areas || []).includes(area)
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-800 text-gray-400 border border-gray-600 hover:border-gray-400'
              }`}
            >
              {area}
            </button>
          ))}
        </div>
      </div>
    </>
  );
};

export default PRReviewFields;
```

**Step 3: Create GithubIssueFixFields.tsx**

```tsx
// frontend/src/components/ActionCenter/forms/GithubIssueFixFields.tsx
import React from 'react';
import type { GithubIssueFixForm } from '../../../types';

interface Props {
  data: GithubIssueFixForm;
  onChange: (data: GithubIssueFixForm) => void;
}

const GithubIssueFixFields: React.FC<Props> = ({ data, onChange }) => {
  const update = (field: Partial<GithubIssueFixForm>) =>
    onChange({ ...data, ...field });

  return (
    <>
      <div>
        <label className="block text-sm text-gray-300 mb-1.5">Repository URL *</label>
        <input
          type="text"
          value={data.repo_url}
          onChange={(e) => update({ repo_url: e.target.value })}
          className="w-full px-4 py-2.5 bg-gray-800 border border-gray-600 rounded-lg text-white text-sm focus:border-blue-500 focus:outline-none"
          placeholder="https://github.com/org/repo"
          required
        />
      </div>
      <div>
        <label className="block text-sm text-gray-300 mb-1.5">Issue Number or URL *</label>
        <input
          type="text"
          value={data.issue_number}
          onChange={(e) => update({ issue_number: e.target.value })}
          className="w-full px-4 py-2.5 bg-gray-800 border border-gray-600 rounded-lg text-white text-sm focus:border-blue-500 focus:outline-none"
          placeholder="87 or https://github.com/org/repo/issues/87"
          required
        />
      </div>
      <div>
        <label className="block text-sm text-gray-300 mb-1.5">Target Branch</label>
        <input
          type="text"
          value={data.target_branch || ''}
          onChange={(e) => update({ target_branch: e.target.value || undefined })}
          className="w-full px-4 py-2.5 bg-gray-800 border border-gray-600 rounded-lg text-white text-sm focus:border-blue-500 focus:outline-none"
          placeholder="main"
        />
      </div>
    </>
  );
};

export default GithubIssueFixFields;
```

**Step 4: Create ClusterDiagnosticsFields.tsx**

```tsx
// frontend/src/components/ActionCenter/forms/ClusterDiagnosticsFields.tsx
import React from 'react';
import type { ClusterDiagnosticsForm } from '../../../types';

interface Props {
  data: ClusterDiagnosticsForm;
  onChange: (data: ClusterDiagnosticsForm) => void;
}

const ClusterDiagnosticsFields: React.FC<Props> = ({ data, onChange }) => {
  const update = (field: Partial<ClusterDiagnosticsForm>) =>
    onChange({ ...data, ...field });

  return (
    <>
      <div>
        <label className="block text-sm text-gray-300 mb-1.5">Cluster URL *</label>
        <input
          type="text"
          value={data.cluster_url}
          onChange={(e) => update({ cluster_url: e.target.value })}
          className="w-full px-4 py-2.5 bg-gray-800 border border-gray-600 rounded-lg text-white text-sm focus:border-blue-500 focus:outline-none"
          placeholder="https://api.cluster.example.com:6443"
          required
        />
      </div>
      <div>
        <label className="block text-sm text-gray-300 mb-1.5">Auth Token *</label>
        <input
          type="password"
          value={data.auth_token || ''}
          onChange={(e) => update({ auth_token: e.target.value || undefined })}
          className="w-full px-4 py-2.5 bg-gray-800 border border-gray-600 rounded-lg text-white text-sm focus:border-blue-500 focus:outline-none"
          placeholder="Bearer token or service account token"
          required
        />
      </div>
      <div>
        <label className="block text-sm text-gray-300 mb-1.5">Namespace</label>
        <input
          type="text"
          value={data.namespace || ''}
          onChange={(e) => update({ namespace: e.target.value || undefined })}
          className="w-full px-4 py-2.5 bg-gray-800 border border-gray-600 rounded-lg text-white text-sm focus:border-blue-500 focus:outline-none"
          placeholder="All namespaces (leave blank) or specific namespace"
        />
      </div>
      <div>
        <label className="block text-sm text-gray-300 mb-1.5">Symptoms / Description</label>
        <textarea
          value={data.symptoms || ''}
          onChange={(e) => update({ symptoms: e.target.value || undefined })}
          rows={3}
          className="w-full px-4 py-2.5 bg-gray-800 border border-gray-600 rounded-lg text-white text-sm focus:border-blue-500 focus:outline-none resize-none"
          placeholder="Describe what you're observing — pods crashing, high latency, etc."
        />
      </div>
    </>
  );
};

export default ClusterDiagnosticsFields;
```

**Step 5: Create CapabilityForm.tsx (the container that renders the right fields)**

```tsx
// frontend/src/components/ActionCenter/CapabilityForm.tsx
import React, { useState } from 'react';
import { ArrowLeft } from 'lucide-react';
import type {
  CapabilityType,
  CapabilityFormData,
  TroubleshootAppForm,
  PRReviewForm,
  GithubIssueFixForm,
  ClusterDiagnosticsForm,
} from '../../types';
import TroubleshootAppFields from './forms/TroubleshootAppFields';
import PRReviewFields from './forms/PRReviewFields';
import GithubIssueFixFields from './forms/GithubIssueFixFields';
import ClusterDiagnosticsFields from './forms/ClusterDiagnosticsFields';

const capabilityLabels: Record<CapabilityType, string> = {
  troubleshoot_app: 'Troubleshoot Application',
  pr_review: 'PR Review',
  github_issue_fix: 'GitHub Issue Fix',
  cluster_diagnostics: 'Cluster Diagnostics',
};

const defaultFormData: Record<CapabilityType, CapabilityFormData> = {
  troubleshoot_app: {
    capability: 'troubleshoot_app',
    service_name: '',
    time_window: '1h',
  },
  pr_review: {
    capability: 'pr_review',
    repo_url: '',
    pr_number: '',
  },
  github_issue_fix: {
    capability: 'github_issue_fix',
    repo_url: '',
    issue_number: '',
  },
  cluster_diagnostics: {
    capability: 'cluster_diagnostics',
    cluster_url: '',
  },
};

interface CapabilityFormProps {
  capability: CapabilityType;
  onBack: () => void;
  onSubmit: (data: CapabilityFormData) => void;
  loading: boolean;
}

const CapabilityForm: React.FC<CapabilityFormProps> = ({
  capability,
  onBack,
  onSubmit,
  loading,
}) => {
  const [formData, setFormData] = useState<CapabilityFormData>(
    defaultFormData[capability]
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(formData);
  };

  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="max-w-lg w-full">
        {/* Back button */}
        <button
          onClick={onBack}
          className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors mb-6"
        >
          <ArrowLeft className="w-4 h-4" />
          <span className="text-sm">Back</span>
        </button>

        {/* Form title */}
        <h2 className="text-2xl font-bold text-white mb-8">
          {capabilityLabels[capability]}
        </h2>

        <form onSubmit={handleSubmit} className="space-y-5">
          {capability === 'troubleshoot_app' && (
            <TroubleshootAppFields
              data={formData as TroubleshootAppForm}
              onChange={(d) => setFormData(d)}
            />
          )}
          {capability === 'pr_review' && (
            <PRReviewFields
              data={formData as PRReviewForm}
              onChange={(d) => setFormData(d)}
            />
          )}
          {capability === 'github_issue_fix' && (
            <GithubIssueFixFields
              data={formData as GithubIssueFixForm}
              onChange={(d) => setFormData(d)}
            />
          )}
          {capability === 'cluster_diagnostics' && (
            <ClusterDiagnosticsFields
              data={formData as ClusterDiagnosticsForm}
              onChange={(d) => setFormData(d)}
            />
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full mt-6 px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-colors"
          >
            {loading ? 'Starting...' : 'Start Analysis'}
          </button>
        </form>
      </div>
    </div>
  );
};

export default CapabilityForm;
```

**Step 6: Verify build**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 7: Commit**

```bash
git add frontend/src/components/ActionCenter/
git commit -m "feat: create CapabilityForm with per-capability field components"
```

---

## Phase 3: Results Panel & Progress Bar

### Task 4: Create ResultsPanel component

**Files:**
- Create: `frontend/src/components/ResultsPanel.tsx`

**Step 1: Create ResultsPanel.tsx**

This component replaces DashboardTab + ActivityLogTab as a scrollable right panel with stacked cards.

```tsx
// frontend/src/components/ResultsPanel.tsx
import React, { useEffect, useState, useCallback } from 'react';
import type { V4Findings, V4SessionStatus, TaskEvent, TokenUsage } from '../types';
import { getFindings, getSessionStatus, getEvents } from '../services/api';
import ErrorPatternsCard from './Dashboard/ErrorPatternsCard';
import MetricsChartCard from './Dashboard/MetricsChartCard';
import K8sStatusCard from './Dashboard/K8sStatusCard';
import TraceCard from './Dashboard/TraceCard';
import CodeImpactCard from './Dashboard/CodeImpactCard';
import DiagnosisSummaryCard from './Dashboard/DiagnosisSummaryCard';
import TokenSummary from './ActivityLog/TokenSummary';

interface ResultsPanelProps {
  sessionId: string;
  taskEvents: TaskEvent[];
}

const ResultsPanel: React.FC<ResultsPanelProps> = ({ sessionId, taskEvents }) => {
  const [findings, setFindings] = useState<V4Findings | null>(null);
  const [status, setStatus] = useState<V4SessionStatus | null>(null);
  const [tokenUsage, setTokenUsage] = useState<TokenUsage[]>([]);

  const fetchData = useCallback(async () => {
    try {
      const [f, s] = await Promise.all([
        getFindings(sessionId),
        getSessionStatus(sessionId),
      ]);
      setFindings(f);
      setStatus(s);
      setTokenUsage(s.token_usage);
    } catch {
      // Silent retry on next interval
    }
  }, [sessionId]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const hasResults = findings && (
    findings.error_patterns.length > 0 ||
    findings.metric_anomalies.length > 0 ||
    findings.pod_statuses.length > 0 ||
    findings.trace_spans.length > 0 ||
    findings.impacted_files.length > 0 ||
    findings.findings.length > 0
  );

  return (
    <div className="h-full overflow-y-auto border-l border-gray-700 bg-gray-950">
      {!hasResults ? (
        <div className="flex items-center justify-center h-full text-gray-500">
          <div className="text-center px-6">
            <div className="w-8 h-8 border-2 border-gray-600 border-t-blue-500 rounded-full animate-spin mx-auto mb-3" />
            <p className="text-sm">Waiting for results...</p>
            <p className="text-xs text-gray-600 mt-1">Cards will appear as agents complete.</p>
          </div>
        </div>
      ) : (
        <div className="p-4 space-y-4">
          {/* Diagnosis Summary (always first if available) */}
          {findings && status && findings.findings.length > 0 && (
            <DiagnosisSummaryCard
              confidence={status.confidence}
              findings={findings.findings}
              criticVerdicts={findings.critic_verdicts}
              breadcrumbs={status.breadcrumbs}
            />
          )}

          {findings && findings.error_patterns.length > 0 && (
            <ErrorPatternsCard patterns={findings.error_patterns} />
          )}

          {findings && findings.metric_anomalies.length > 0 && (
            <MetricsChartCard anomalies={findings.metric_anomalies} />
          )}

          {findings && (findings.pod_statuses.length > 0 || findings.k8s_events.length > 0) && (
            <K8sStatusCard pods={findings.pod_statuses} events={findings.k8s_events} />
          )}

          {findings && findings.trace_spans.length > 0 && (
            <TraceCard spans={findings.trace_spans} />
          )}

          {findings && findings.impacted_files.length > 0 && (
            <CodeImpactCard impacts={findings.impacted_files} />
          )}

          {/* Activity log (compact) */}
          {taskEvents.length > 0 && (
            <div className="rounded-lg border border-gray-700 bg-gray-900/50 p-4">
              <h3 className="text-sm font-semibold text-white mb-3">Activity Log</h3>
              <div className="space-y-1 max-h-48 overflow-y-auto">
                {taskEvents.slice(-20).map((event, i) => (
                  <div key={`${event.timestamp}-${i}`} className="flex items-center gap-2 text-xs">
                    <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                      event.event_type === 'success' ? 'bg-green-500' :
                      event.event_type === 'error' ? 'bg-red-500' :
                      event.event_type === 'warning' ? 'bg-orange-500' :
                      event.event_type === 'started' ? 'bg-blue-500' :
                      'bg-gray-500'
                    }`} />
                    <span className="text-gray-500 font-mono whitespace-nowrap">
                      {new Date(event.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                    </span>
                    <span className="text-blue-400 whitespace-nowrap">{event.agent}</span>
                    <span className="text-gray-400 truncate">{event.message}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Token summary */}
          {tokenUsage.length > 0 && (
            <div className="rounded-lg border border-gray-700 bg-gray-900/50 p-4">
              <TokenSummary tokenUsage={tokenUsage} />
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default ResultsPanel;
```

**Step 2: Verify build**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/ResultsPanel.tsx
git commit -m "feat: create ResultsPanel with scrollable stacked cards"
```

---

### Task 5: Create ProgressBar component

**Files:**
- Create: `frontend/src/components/ProgressBar.tsx`

**Step 1: Create ProgressBar.tsx**

```tsx
// frontend/src/components/ProgressBar.tsx
import React from 'react';
import type { DiagnosticPhase, TokenUsage } from '../types';

interface ProgressBarProps {
  phase: DiagnosticPhase | null;
  confidence: number;
  tokenUsage: TokenUsage[];
  wsConnected: boolean;
}

interface Step {
  id: string;
  label: string;
  phases: DiagnosticPhase[];
}

const steps: Step[] = [
  { id: 'logs', label: 'Logs', phases: ['collecting_context', 'logs_analyzed'] },
  { id: 'metrics', label: 'Metrics', phases: ['metrics_analyzed'] },
  { id: 'k8s', label: 'K8s', phases: ['k8s_analyzed'] },
  { id: 'tracing', label: 'Tracing', phases: ['tracing_analyzed'] },
  { id: 'code', label: 'Code', phases: ['code_analyzed'] },
  { id: 'done', label: 'Done', phases: ['validating', 'diagnosis_complete', 'complete'] },
];

const getStepStatus = (
  step: Step,
  currentPhase: DiagnosticPhase | null,
  allPhases: DiagnosticPhase[]
): 'complete' | 'active' | 'pending' => {
  if (!currentPhase) return 'pending';

  const phaseOrder: DiagnosticPhase[] = [
    'initial', 'collecting_context', 'logs_analyzed', 'metrics_analyzed',
    'k8s_analyzed', 'tracing_analyzed', 'code_analyzed',
    'validating', 're_investigating', 'diagnosis_complete', 'fix_in_progress', 'complete',
  ];

  const currentIdx = phaseOrder.indexOf(currentPhase);
  const stepMaxPhaseIdx = Math.max(...step.phases.map((p) => phaseOrder.indexOf(p)));
  const stepMinPhaseIdx = Math.min(...step.phases.map((p) => phaseOrder.indexOf(p)));

  if (currentIdx > stepMaxPhaseIdx) return 'complete';
  if (currentIdx >= stepMinPhaseIdx && currentIdx <= stepMaxPhaseIdx) return 'active';
  return 'pending';
};

const ProgressBar: React.FC<ProgressBarProps> = ({
  phase,
  confidence,
  tokenUsage,
  wsConnected,
}) => {
  const totalTokens = tokenUsage.reduce((sum, t) => sum + t.total_tokens, 0);
  const confidencePercent = Math.round(confidence * 100);

  return (
    <div className="h-10 bg-gray-900 border-t border-gray-700 flex items-center px-4 gap-4">
      {/* Connection indicator */}
      <div className="flex items-center gap-1.5">
        <span className={`w-1.5 h-1.5 rounded-full ${wsConnected ? 'bg-green-500' : 'bg-red-500'}`} />
      </div>

      {/* Step progress */}
      {phase && phase !== 'initial' && (
        <div className="flex items-center gap-1 flex-1">
          {steps.map((step, i) => {
            const status = getStepStatus(step, phase, []);
            return (
              <React.Fragment key={step.id}>
                {/* Dot */}
                <div className="flex items-center gap-1">
                  <span className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${
                    status === 'complete' ? 'bg-green-500' :
                    status === 'active' ? 'bg-blue-500 animate-pulse' :
                    'bg-gray-600'
                  }`} />
                  <span className={`text-xs whitespace-nowrap ${
                    status === 'complete' ? 'text-green-400' :
                    status === 'active' ? 'text-blue-400 font-medium' :
                    'text-gray-500'
                  }`}>
                    {step.label}
                  </span>
                </div>
                {/* Connector line */}
                {i < steps.length - 1 && (
                  <div className={`flex-1 h-px min-w-4 ${
                    status === 'complete' ? 'bg-green-500' : 'bg-gray-700'
                  }`} />
                )}
              </React.Fragment>
            );
          })}
        </div>
      )}

      {/* Spacer when no progress */}
      {(!phase || phase === 'initial') && <div className="flex-1" />}

      {/* Right side stats */}
      <div className="flex items-center gap-4 text-xs">
        {confidencePercent > 0 && (
          <span className={`font-medium ${
            confidencePercent >= 80 ? 'text-green-400' :
            confidencePercent >= 50 ? 'text-yellow-400' :
            'text-red-400'
          }`}>
            {confidencePercent}%
          </span>
        )}
        {totalTokens > 0 && (
          <span className="text-gray-500 font-mono">
            {totalTokens.toLocaleString()} tokens
          </span>
        )}
      </div>
    </div>
  );
};

export default ProgressBar;
```

**Step 2: Verify build**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/ProgressBar.tsx
git commit -m "feat: create multi-step ProgressBar with phase tracking"
```

---

## Phase 4: Update Sidebar & Wire Everything Together

### Task 6: Update SessionSidebar to remove the form

**Files:**
- Modify: `frontend/src/components/SessionSidebar.tsx`

The form is moving to the center area (CapabilityForm). The sidebar now just shows session list with a "New Session" button that navigates to the Action Center.

**Step 1: Rewrite SessionSidebar.tsx**

Replace the entire component. The new version:
- Removes the embedded form
- Adds a "New Session" button that calls `onNewSession()` (navigates parent to action center)
- Groups sessions — still shows service name, phase badge, confidence
- Keeps `onSelectSession` for clicking existing sessions

```tsx
// frontend/src/components/SessionSidebar.tsx
import React, { useEffect } from 'react';
import type { V4Session, DiagnosticPhase } from '../types';
import { listSessionsV4 } from '../services/api';

interface SessionSidebarProps {
  activeSessionId: string | null;
  onSelectSession: (session: V4Session) => void;
  onNewSession: () => void;
  sessions: V4Session[];
  onSessionsChange: (sessions: V4Session[]) => void;
}

const phaseColors: Record<DiagnosticPhase, string> = {
  initial: 'bg-gray-500',
  collecting_context: 'bg-blue-500',
  logs_analyzed: 'bg-blue-400',
  metrics_analyzed: 'bg-blue-400',
  k8s_analyzed: 'bg-blue-400',
  tracing_analyzed: 'bg-blue-400',
  code_analyzed: 'bg-blue-400',
  validating: 'bg-yellow-500',
  re_investigating: 'bg-orange-500',
  diagnosis_complete: 'bg-green-500',
  fix_in_progress: 'bg-purple-500',
  complete: 'bg-green-600',
};

const phaseLabel = (phase: DiagnosticPhase): string =>
  phase.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

const SessionSidebar: React.FC<SessionSidebarProps> = ({
  activeSessionId,
  onSelectSession,
  onNewSession,
  sessions,
  onSessionsChange,
}) => {
  useEffect(() => {
    const loadSessions = async () => {
      try {
        const data = await listSessionsV4();
        onSessionsChange(data);
      } catch (err) {
        console.error('Failed to load sessions:', err);
      }
    };
    loadSessions();
  }, [onSessionsChange]);

  return (
    <div className="w-64 bg-gray-900 border-r border-gray-700 flex flex-col h-full">
      <div className="p-4 border-b border-gray-700">
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">
          Sessions
        </h2>
        <button
          onClick={onNewSession}
          className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors"
        >
          + New Session
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {sessions.length === 0 ? (
          <div className="p-4 text-center text-gray-500 text-sm">
            No sessions yet.
          </div>
        ) : (
          sessions.map((session) => (
            <button
              key={session.session_id}
              onClick={() => onSelectSession(session)}
              className={`w-full text-left px-4 py-3 border-b border-gray-800 hover:bg-gray-800 transition-colors ${
                activeSessionId === session.session_id
                  ? 'bg-gray-800 border-l-2 border-l-blue-500'
                  : ''
              }`}
            >
              <div className="font-medium text-white text-sm truncate">
                {session.service_name}
              </div>
              <div className="flex items-center gap-2 mt-1">
                <span
                  className={`inline-block w-2 h-2 rounded-full ${
                    phaseColors[session.status] || 'bg-gray-500'
                  }`}
                />
                <span className="text-xs text-gray-400">
                  {phaseLabel(session.status)}
                </span>
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );
};

export default SessionSidebar;
```

**Step 2: Verify build (will have errors until App.tsx is updated — that's expected)**

**Step 3: Commit**

```bash
git add frontend/src/components/SessionSidebar.tsx
git commit -m "refactor: simplify SessionSidebar, move form to Action Center"
```

---

### Task 7: Rewrite App.tsx with layout state machine

**Files:**
- Modify: `frontend/src/App.tsx`

This is the main integration task. App.tsx now manages 3 layout states:
1. `home` — shows ActionCenter
2. `form` — shows CapabilityForm for the selected capability
3. `session` — shows Chat (center) + ResultsPanel (right) + ProgressBar (bottom)

**Step 1: Rewrite App.tsx**

```tsx
// frontend/src/App.tsx
import React, { useState, useCallback } from 'react';
import type {
  V4Session,
  ChatMessage,
  TaskEvent,
  DiagnosticPhase,
  TokenUsage,
  CapabilityType,
  CapabilityFormData,
} from './types';
import { useWebSocketV4 } from './hooks/useWebSocket';
import { getSessionStatus, startSessionV4 } from './services/api';
import SessionSidebar from './components/SessionSidebar';
import ActionCenter from './components/ActionCenter/ActionCenter';
import CapabilityForm from './components/ActionCenter/CapabilityForm';
import ChatTab from './components/Chat/ChatTab';
import ResultsPanel from './components/ResultsPanel';
import ProgressBar from './components/ProgressBar';

type ViewState =
  | { view: 'home' }
  | { view: 'form'; capability: CapabilityType }
  | { view: 'session' };

function App() {
  // Navigation state
  const [viewState, setViewState] = useState<ViewState>({ view: 'home' });
  const [formLoading, setFormLoading] = useState(false);

  // Session state
  const [sessions, setSessions] = useState<V4Session[]>([]);
  const [activeSession, setActiveSession] = useState<V4Session | null>(null);
  const [chatMessages, setChatMessages] = useState<Record<string, ChatMessage[]>>({});
  const [taskEvents, setTaskEvents] = useState<Record<string, TaskEvent[]>>({});
  const [wsConnected, setWsConnected] = useState(false);
  const [currentPhase, setCurrentPhase] = useState<DiagnosticPhase | null>(null);
  const [confidence, setConfidence] = useState(0);
  const [tokenUsage, setTokenUsage] = useState<TokenUsage[]>([]);

  const activeSessionId = activeSession?.session_id ?? null;

  // --- Status refresh ---
  const refreshStatus = useCallback(async (sessionId: string) => {
    try {
      const status = await getSessionStatus(sessionId);
      setCurrentPhase(status.phase);
      setConfidence(status.confidence);
      setTokenUsage(status.token_usage);
    } catch {
      // Silent
    }
  }, []);

  // --- WebSocket handlers ---
  const handleTaskEvent = useCallback(
    (event: TaskEvent) => {
      const sid = event.session_id || activeSessionId;
      if (!sid) return;
      setTaskEvents((prev) => ({
        ...prev,
        [sid]: [...(prev[sid] || []), event],
      }));
      if (event.event_type === 'success' || event.event_type === 'error') {
        refreshStatus(sid);
      }
    },
    [activeSessionId, refreshStatus]
  );

  const handleChatResponse = useCallback(
    (message: ChatMessage) => {
      if (!activeSessionId) return;
      setChatMessages((prev) => ({
        ...prev,
        [activeSessionId]: [...(prev[activeSessionId] || []), message],
      }));
    },
    [activeSessionId]
  );

  useWebSocketV4(activeSessionId, {
    onTaskEvent: handleTaskEvent,
    onChatResponse: handleChatResponse,
    onConnect: useCallback(() => setWsConnected(true), []),
    onDisconnect: useCallback(() => setWsConnected(false), []),
  });

  // --- Navigation handlers ---
  const handleSelectCapability = useCallback((capability: CapabilityType) => {
    setViewState({ view: 'form', capability });
  }, []);

  const handleBackToHome = useCallback(() => {
    setViewState({ view: 'home' });
  }, []);

  const handleNewSession = useCallback(() => {
    setActiveSession(null);
    setViewState({ view: 'home' });
  }, []);

  const handleFormSubmit = useCallback(
    async (data: CapabilityFormData) => {
      setFormLoading(true);
      try {
        // For now, only troubleshoot_app calls the v4 API.
        // Other capabilities will be wired as their backends are built.
        if (data.capability === 'troubleshoot_app') {
          const session = await startSessionV4({
            service_name: data.service_name,
            time_window: data.time_window,
            trace_id: data.trace_id,
            namespace: data.namespace,
            repo_url: data.repo_url,
          });
          setSessions((prev) => [session, ...prev]);
          setActiveSession(session);
          setCurrentPhase(session.status);
          setConfidence(session.confidence);
          setViewState({ view: 'session' });
        } else {
          // Placeholder: show session view with a coming-soon state
          // The form data is available for when backends are built
          setViewState({ view: 'session' });
        }
      } catch (err) {
        console.error('Failed to start session:', err);
      } finally {
        setFormLoading(false);
      }
    },
    []
  );

  const handleSelectSession = useCallback(
    (session: V4Session) => {
      setActiveSession(session);
      setCurrentPhase(session.status);
      setConfidence(session.confidence);
      refreshStatus(session.session_id);
      setViewState({ view: 'session' });
    },
    [refreshStatus]
  );

  const handleNewChatMessage = useCallback(
    (message: ChatMessage) => {
      if (!activeSessionId) return;
      setChatMessages((prev) => ({
        ...prev,
        [activeSessionId]: [...(prev[activeSessionId] || []), message],
      }));
    },
    [activeSessionId]
  );

  // --- Derived data ---
  const currentChatMessages = activeSessionId ? chatMessages[activeSessionId] || [] : [];
  const currentTaskEvents = activeSessionId ? taskEvents[activeSessionId] || [] : [];

  // --- Render ---
  return (
    <div className="flex h-screen bg-gray-950 text-white">
      {/* Sidebar */}
      <SessionSidebar
        activeSessionId={activeSessionId}
        onSelectSession={handleSelectSession}
        onNewSession={handleNewSession}
        sessions={sessions}
        onSessionsChange={setSessions}
      />

      {/* Main content area */}
      <div className="flex-1 flex flex-col min-w-0">
        {viewState.view === 'home' && (
          <ActionCenter
            onSelectCapability={handleSelectCapability}
            recentSessions={sessions}
            onResumeSession={handleSelectSession}
          />
        )}

        {viewState.view === 'form' && (
          <CapabilityForm
            capability={viewState.capability}
            onBack={handleBackToHome}
            onSubmit={handleFormSubmit}
            loading={formLoading}
          />
        )}

        {viewState.view === 'session' && activeSession && (
          <>
            {/* Header */}
            <div className="h-12 bg-gray-900 border-b border-gray-700 flex items-center px-4">
              <h1 className="text-sm font-semibold text-white">
                {activeSession.service_name}
              </h1>
              <span className="ml-3 text-xs text-gray-500 font-mono">
                {activeSession.session_id.substring(0, 8)}...
              </span>
            </div>

            {/* Chat (center) + Results (right) */}
            <div className="flex-1 flex overflow-hidden">
              {/* Chat panel */}
              <div className="flex-1 min-w-0">
                <ChatTab
                  sessionId={activeSession.session_id}
                  messages={currentChatMessages}
                  onNewMessage={handleNewChatMessage}
                />
              </div>

              {/* Results panel (right) */}
              <div className="w-96 flex-shrink-0">
                <ResultsPanel
                  sessionId={activeSession.session_id}
                  taskEvents={currentTaskEvents}
                />
              </div>
            </div>

            {/* Progress bar (replaces status bar) */}
            <ProgressBar
              phase={currentPhase}
              confidence={confidence}
              tokenUsage={tokenUsage}
              wsConnected={wsConnected}
            />
          </>
        )}

        {/* Edge case: session view but no active session (shouldn't happen) */}
        {viewState.view === 'session' && !activeSession && (
          <ActionCenter
            onSelectCapability={handleSelectCapability}
            recentSessions={sessions}
            onResumeSession={handleSelectSession}
          />
        )}
      </div>
    </div>
  );
}

export default App;
```

**Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

**Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: rewrite App with Action Center, capability forms, and split layout"
```

---

## Phase 5: Keyboard Shortcuts

### Task 8: Add keyboard shortcuts

**Files:**
- Create: `frontend/src/hooks/useKeyboardShortcuts.ts`
- Modify: `frontend/src/App.tsx` (add the hook call)

**Step 1: Create useKeyboardShortcuts.ts**

```tsx
// frontend/src/hooks/useKeyboardShortcuts.ts
import { useEffect } from 'react';
import type { CapabilityType } from '../types';

interface ShortcutHandlers {
  onNewSession: () => void;
  onSelectCapability: (capability: CapabilityType) => void;
  onEscape: () => void;
}

const capabilityKeys: Record<string, CapabilityType> = {
  '1': 'troubleshoot_app',
  '2': 'pr_review',
  '3': 'github_issue_fix',
  '4': 'cluster_diagnostics',
};

export const useKeyboardShortcuts = (handlers: ShortcutHandlers) => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger when typing in inputs
      const target = e.target as HTMLElement;
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT') {
        if (e.key === 'Escape') {
          handlers.onEscape();
        }
        return;
      }

      // Ctrl+N or Cmd+N — New session
      if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
        e.preventDefault();
        handlers.onNewSession();
        return;
      }

      // Ctrl+1/2/3/4 — Quick-pick capability
      if ((e.ctrlKey || e.metaKey) && capabilityKeys[e.key]) {
        e.preventDefault();
        handlers.onSelectCapability(capabilityKeys[e.key]);
        return;
      }

      // Escape — Back to home
      if (e.key === 'Escape') {
        handlers.onEscape();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handlers]);
};
```

**Step 2: Add the hook to App.tsx**

Add after the existing hooks in App.tsx:

```tsx
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts';

// Inside App(), after the WebSocket hook:
useKeyboardShortcuts({
  onNewSession: handleNewSession,
  onSelectCapability: handleSelectCapability,
  onEscape: handleBackToHome,
});
```

**Step 3: Verify build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

**Step 4: Commit**

```bash
git add frontend/src/hooks/useKeyboardShortcuts.ts frontend/src/App.tsx
git commit -m "feat: add keyboard shortcuts (Ctrl+N, Ctrl+1-4, Esc)"
```

---

## Phase 6: Cleanup

### Task 9: Remove unused TabLayout and StatusBar imports

**Files:**
- Modify: `frontend/src/App.tsx` — remove unused imports for TabLayout, StatusBar, DashboardTab, ActivityLogTab
- Keep: `frontend/src/components/TabLayout.tsx` — file preserved (not deleted) in case needed
- Keep: `frontend/src/components/StatusBar.tsx` — file preserved (not deleted) in case needed

**Step 1: Verify App.tsx no longer imports TabLayout, StatusBar, DashboardTab, or ActivityLogTab**

Check that these imports are not present in the final App.tsx. If they are, remove them.

**Step 2: Final build verification**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no warnings about unused imports

**Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "chore: remove unused TabLayout and StatusBar imports"
```

---

## Summary

| Task | Component | Files |
|------|-----------|-------|
| 1 | Capability types | `types/index.ts` |
| 2 | ActionCenter + CapabilityCard | `ActionCenter/ActionCenter.tsx`, `ActionCenter/CapabilityCard.tsx` |
| 3 | CapabilityForm + 4 field components | `ActionCenter/CapabilityForm.tsx`, `forms/*.tsx` |
| 4 | ResultsPanel | `ResultsPanel.tsx` |
| 5 | ProgressBar | `ProgressBar.tsx` |
| 6 | SessionSidebar simplification | `SessionSidebar.tsx` |
| 7 | App.tsx rewrite (main integration) | `App.tsx` |
| 8 | Keyboard shortcuts | `hooks/useKeyboardShortcuts.ts`, `App.tsx` |
| 9 | Cleanup unused imports | `App.tsx` |

**New files:** 10
**Modified files:** 3
**Total tasks:** 9
