import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { listRuns } from '../../../services/runs';
import { RunFilterBar } from './RunFilterBar';
import { createRun } from '../../../services/runs';
import { listWorkflows, listVersions, getVersion } from '../../../services/workflows';
import { InputsForm } from './InputsForm';
import type { RunListResponse, RunStatus, WorkflowSummary, VersionSummary, WorkflowVersionDetail } from '../../../types';

const STATUS_CLASSES: Record<RunStatus, string> = {
  running: 'bg-amber-500 animate-pulse',
  pending: 'bg-neutral-500',
  cancelling: 'bg-slate-400',
  cancelled: 'bg-slate-500',
  success: 'bg-emerald-500',
  failed: 'bg-red-500',
};

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

const LIMIT = 50;

export function WorkflowRunsPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  // Server-side run data
  const [runData, setRunData] = useState<RunListResponse | null>(null);
  const [loading, setLoading] = useState(true);

  // Filter state from URL params
  const statuses = searchParams.get('status')?.split(',').filter(Boolean) ?? [];
  const sortBy = (searchParams.get('sort') ?? 'started_at') as 'started_at' | 'duration';
  const sortOrder = (searchParams.get('order') ?? 'desc') as 'asc' | 'desc';
  const page = Number(searchParams.get('page') ?? '0');
  const workflowFilter = searchParams.get('workflow_id') ?? undefined;
  const fromDate = searchParams.get('from') ?? '';
  const toDate = searchParams.get('to') ?? '';

  // New-run wizard state
  const [newRunStep, setNewRunStep] = useState<NewRunStep>('closed');
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([]);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState('');
  const [versions, setVersions] = useState<VersionSummary[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null);
  const [versionDetail, setVersionDetail] = useState<WorkflowVersionDetail | null>(null);
  const [loadingVersionDetail, setLoadingVersionDetail] = useState(false);

  // Fetch runs when filters change
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listRuns({
      status: statuses.length > 0 ? statuses.join(',') : undefined,
      workflow_id: workflowFilter,
      from: fromDate || undefined,
      to: toDate || undefined,
      sort: sortBy,
      order: sortOrder,
      limit: LIMIT,
      offset: page * LIMIT,
    })
      .then((data) => { if (!cancelled) setRunData(data); })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams.toString()]);

  // Filter handlers
  const handleStatusToggle = useCallback((status: string) => {
    setSearchParams((prev) => {
      const current = prev.get('status')?.split(',').filter(Boolean) ?? [];
      const next = current.includes(status)
        ? current.filter((s) => s !== status)
        : [...current, status];
      const params = new URLSearchParams(prev);
      if (next.length > 0) params.set('status', next.join(','));
      else params.delete('status');
      params.delete('page');
      return params;
    });
  }, [setSearchParams]);

  const handleSortChange = useCallback((sort: 'started_at' | 'duration', order: 'asc' | 'desc') => {
    setSearchParams((prev) => {
      const params = new URLSearchParams(prev);
      params.set('sort', sort);
      params.set('order', order);
      params.delete('page');
      return params;
    });
  }, [setSearchParams]);

  const handleDateChange = useCallback((from: string, to: string) => {
    setSearchParams((prev) => {
      const params = new URLSearchParams(prev);
      if (from) params.set('from', from);
      else params.delete('from');
      if (to) params.set('to', to);
      else params.delete('to');
      params.delete('page');
      return params;
    });
  }, [setSearchParams]);

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

  // New run: submit — after creation, refresh the run list
  const handleSubmit = useCallback(
    async (inputs: Record<string, unknown>, opts: { idempotency_key?: string }) => {
      if (!selectedWorkflowId || !versionDetail) return;
      try {
        const run = await createRun(selectedWorkflowId, {
          inputs,
          idempotency_key: opts.idempotency_key,
        });
        setNewRunStep('closed');
        navigate(`/workflows/runs/${run.id}`, { state: { workflowId: selectedWorkflowId } });
      } catch {
        // ignore
      }
    },
    [selectedWorkflowId, versionDetail, navigate],
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

      {/* Filter bar */}
      <RunFilterBar
        statuses={statuses}
        onStatusToggle={handleStatusToggle}
        sortBy={sortBy}
        sortOrder={sortOrder}
        onSortChange={handleSortChange}
        fromDate={fromDate}
        toDate={toDate}
        onDateChange={handleDateChange}
      />

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
      {loading ? (
        <div className="text-center py-12 text-wr-text-muted text-sm">Loading runs...</div>
      ) : !runData || runData.runs.length === 0 ? (
        <div className="text-center py-12 text-wr-text-muted text-sm">
          No runs found. Start one with the button above.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-wr-border text-left text-xs font-medium text-wr-text-muted">
                <th className="py-2 pr-4">Run ID</th>
                <th className="py-2 pr-4">Status</th>
                <th className="py-2 pr-4">Started</th>
                <th className="py-2">Action</th>
              </tr>
            </thead>
            <tbody>
              {runData.runs.map((run) => (
                <tr
                  key={run.id}
                  className="border-b border-wr-border/50 hover:bg-wr-elevated/30"
                >
                  <td className="py-2 pr-4 font-mono text-xs text-wr-text">
                    {run.id}
                  </td>
                  <td className="py-2 pr-4">
                    <span
                      data-testid="run-status-badge"
                      className={`inline-block px-2 py-0.5 rounded text-xs font-semibold text-white ${STATUS_CLASSES[run.status] ?? 'bg-neutral-500'}`}
                    >
                      {run.status}
                    </span>
                  </td>
                  <td className="py-2 pr-4 text-xs text-wr-text-muted">
                    {run.started_at ? relativeTime(run.started_at) : '--'}
                  </td>
                  <td className="py-2">
                    <Link
                      to={`/workflows/runs/${run.id}`}
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

      {/* Pagination */}
      {runData && runData.total > LIMIT && (
        <div className="flex items-center justify-between">
          <span className="text-xs text-wr-text-muted">
            {runData.offset + 1}&ndash;{Math.min(runData.offset + LIMIT, runData.total)} of {runData.total}
          </span>
          <div className="flex gap-2">
            <button disabled={page === 0}
              onClick={() => setSearchParams((p) => { const params = new URLSearchParams(p); params.set('page', String(page - 1)); return params; })}
              className="rounded px-2 py-1 text-xs text-wr-text border border-wr-border hover:bg-wr-elevated disabled:opacity-40">
              Previous
            </button>
            <button disabled={runData.offset + LIMIT >= runData.total}
              onClick={() => setSearchParams((p) => { const params = new URLSearchParams(p); params.set('page', String(page + 1)); return params; })}
              className="rounded px-2 py-1 text-xs text-wr-text border border-wr-border hover:bg-wr-elevated disabled:opacity-40">
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default WorkflowRunsPage;
