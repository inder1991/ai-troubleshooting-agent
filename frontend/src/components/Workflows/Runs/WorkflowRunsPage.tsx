import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { getRecentRuns, addRecentRun, updateRunStatus } from './recentRuns';
import type { RecentRunEntry } from './recentRuns';
import { getRun } from '../../../services/runs';
import { createRun } from '../../../services/runs';
import { listWorkflows, listVersions, getVersion } from '../../../services/workflows';
import { InputsForm } from './InputsForm';
import type { RunStatus, WorkflowSummary, VersionSummary, WorkflowVersionDetail } from '../../../types';

const STATUS_CLASSES: Record<RunStatus, string> = {
  running: 'bg-amber-500 animate-pulse',
  pending: 'bg-neutral-500',
  cancelling: 'bg-slate-400',
  cancelled: 'bg-slate-500',
  succeeded: 'bg-emerald-500',
  failed: 'bg-red-500',
};

const VISIBLE_REFRESH = 10;

/** Format a date string as relative time (e.g. "2 min ago"). */
function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

type NewRunStep = 'closed' | 'select' | 'inputs';

export function WorkflowRunsPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const filterWorkflowId = searchParams.get('workflow_id');

  const [runs, setRuns] = useState<RecentRunEntry[]>([]);

  // New-run wizard state
  const [newRunStep, setNewRunStep] = useState<NewRunStep>('closed');
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([]);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState('');
  const [versions, setVersions] = useState<VersionSummary[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null);
  const [versionDetail, setVersionDetail] = useState<WorkflowVersionDetail | null>(null);
  const [loadingVersionDetail, setLoadingVersionDetail] = useState(false);

  // Load recent runs from localStorage on mount
  useEffect(() => {
    setRuns(getRecentRuns());
  }, []);

  // Refresh status for the first N visible runs
  useEffect(() => {
    const toRefresh = runs.slice(0, VISIBLE_REFRESH);
    if (toRefresh.length === 0) return;

    let cancelled = false;

    async function refresh() {
      for (const entry of toRefresh) {
        if (cancelled) return;
        try {
          const detail = await getRun(entry.runId);
          if (cancelled) return;
          if (detail.status !== entry.status) {
            updateRunStatus(entry.runId, detail.status);
            setRuns((prev) =>
              prev.map((r) =>
                r.runId === entry.runId ? { ...r, status: detail.status } : r,
              ),
            );
          }
        } catch {
          // silently ignore — run may have been deleted
        }
      }
    }

    refresh();
    return () => { cancelled = true; };
    // Only run once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Filter by workflow_id query param
  const filteredRuns = useMemo(() => {
    if (!filterWorkflowId) return runs;
    return runs.filter((r) => r.workflowId === filterWorkflowId);
  }, [runs, filterWorkflowId]);

  // New run: open wizard
  const handleNewRun = useCallback(async () => {
    setNewRunStep('select');
    try {
      const wfs = await listWorkflows();
      setWorkflows(wfs);
    } catch {
      // ignore
    }
  }, []);

  // New run: select workflow
  const handleWorkflowChange = useCallback(async (wfId: string) => {
    setSelectedWorkflowId(wfId);
    setSelectedVersion(null);
    setVersionDetail(null);
    setVersions([]);
    if (!wfId) return;
    try {
      const vs = await listVersions(wfId);
      setVersions(vs);
    } catch {
      // ignore
    }
  }, []);

  // New run: select version -> load detail
  const handleVersionChange = useCallback(
    async (v: number) => {
      setSelectedVersion(v);
      setVersionDetail(null);
      if (!selectedWorkflowId) return;
      setLoadingVersionDetail(true);
      try {
        const detail = await getVersion(selectedWorkflowId, v);
        setVersionDetail(detail);
        setNewRunStep('inputs');
      } catch {
        // ignore
      } finally {
        setLoadingVersionDetail(false);
      }
    },
    [selectedWorkflowId],
  );

  // New run: submit
  const handleSubmit = useCallback(
    async (inputs: Record<string, unknown>, opts: { idempotency_key?: string }) => {
      if (!selectedWorkflowId || !versionDetail) return;
      try {
        const run = await createRun(selectedWorkflowId, {
          inputs,
          idempotency_key: opts.idempotency_key,
        });
        const wf = workflows.find((w) => w.id === selectedWorkflowId);
        addRecentRun({
          runId: run.id,
          workflowId: selectedWorkflowId,
          workflowName: wf?.name,
          status: run.status,
          startedAt: run.started_at ?? new Date().toISOString(),
        });
        setNewRunStep('closed');
        navigate(`/workflows/runs/${run.id}`);
      } catch {
        // ignore
      }
    },
    [selectedWorkflowId, versionDetail, workflows, navigate],
  );

  const handleCancelNewRun = useCallback(() => {
    setNewRunStep('closed');
    setSelectedWorkflowId('');
    setSelectedVersion(null);
    setVersionDetail(null);
    setVersions([]);
    setWorkflows([]);
  }, []);

  return (
    <div className="p-6 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-wr-text">Workflow Runs</h1>
        <button
          onClick={handleNewRun}
          className="rounded-md bg-wr-accent px-3 py-1.5 text-sm font-medium text-wr-on-accent hover:bg-wr-accent-hover"
        >
          New run
        </button>
      </div>

      {/* New run wizard — step 1: select workflow + version */}
      {newRunStep === 'select' && (
        <div className="rounded-lg border border-wr-border bg-wr-surface p-4 space-y-3">
          <h2 className="text-sm font-medium text-wr-text">Start a new run</h2>

          <div>
            <label htmlFor="wf-select" className="block text-xs font-medium text-wr-text-muted mb-1">
              Workflow
            </label>
            <select
              id="wf-select"
              aria-label="Workflow"
              value={selectedWorkflowId}
              onChange={(e) => handleWorkflowChange(e.target.value)}
              className="w-full rounded-md border border-wr-border bg-wr-bg px-2 py-1.5 text-sm text-wr-text"
            >
              <option value="">Select a workflow...</option>
              {workflows.map((wf) => (
                <option key={wf.id} value={wf.id}>
                  {wf.name}
                </option>
              ))}
            </select>
          </div>

          {versions.length > 0 && (
            <div>
              <label htmlFor="ver-select" className="block text-xs font-medium text-wr-text-muted mb-1">
                Version
              </label>
              <select
                id="ver-select"
                aria-label="Version"
                value={selectedVersion ?? ''}
                onChange={(e) => handleVersionChange(Number(e.target.value))}
                className="w-full rounded-md border border-wr-border bg-wr-bg px-2 py-1.5 text-sm text-wr-text"
              >
                <option value="">Select a version...</option>
                {versions.map((v) => (
                  <option key={v.version} value={v.version}>
                    v{v.version}
                  </option>
                ))}
              </select>
            </div>
          )}

          {loadingVersionDetail && (
            <div className="text-xs text-wr-text-secondary">Loading version...</div>
          )}

          <div className="flex justify-end">
            <button
              onClick={handleCancelNewRun}
              className="rounded-md border border-wr-border bg-wr-surface px-3 py-1.5 text-sm text-wr-text hover:bg-wr-elevated"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* New run wizard — step 2: inputs form */}
      {newRunStep === 'inputs' && versionDetail && (
        <InputsForm
          schema={versionDetail.dag.inputs_schema}
          onSubmit={handleSubmit}
          onCancel={handleCancelNewRun}
        />
      )}

      {/* Runs list */}
      {filteredRuns.length === 0 ? (
        <div className="text-center py-12 text-wr-text-muted text-sm">
          No recent runs. Start one with the button above.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-wr-border text-left text-xs font-medium text-wr-text-muted">
                <th className="py-2 pr-4">Run ID</th>
                <th className="py-2 pr-4">Workflow</th>
                <th className="py-2 pr-4">Status</th>
                <th className="py-2 pr-4">Started</th>
                <th className="py-2">Action</th>
              </tr>
            </thead>
            <tbody>
              {filteredRuns.map((entry) => (
                <tr
                  key={entry.runId}
                  className="border-b border-wr-border/50 hover:bg-wr-elevated/30"
                >
                  <td className="py-2 pr-4 font-mono text-xs text-wr-text">
                    {entry.runId}
                  </td>
                  <td className="py-2 pr-4 text-wr-text">
                    {entry.workflowName ?? entry.workflowId}
                  </td>
                  <td className="py-2 pr-4">
                    <span
                      data-testid="run-status-badge"
                      className={`inline-block px-2 py-0.5 rounded text-xs font-semibold text-white ${STATUS_CLASSES[entry.status] ?? 'bg-neutral-500'}`}
                    >
                      {entry.status}
                    </span>
                  </td>
                  <td className="py-2 pr-4 text-xs text-wr-text-muted">
                    {relativeTime(entry.startedAt)}
                  </td>
                  <td className="py-2">
                    <Link
                      to={`/workflows/runs/${entry.runId}`}
                      className="rounded px-2 py-1 text-xs font-medium text-wr-accent hover:underline"
                    >
                      View
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Footer note */}
      <p className="text-xs text-wr-text-muted pt-2">
        Showing runs from this browser only. A global run history will be available in a future release.
      </p>
    </div>
  );
}

export default WorkflowRunsPage;
