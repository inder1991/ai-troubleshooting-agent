import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { WorkflowSummary } from '../../../types';
import { listWorkflows, createWorkflow } from '../../../services/workflows';

export function WorkflowListPage() {
  const navigate = useNavigate();

  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Create form state
  const [showCreate, setShowCreate] = useState(false);
  const [createName, setCreateName] = useState('');
  const [createDesc, setCreateDesc] = useState('');
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        setLoading(true);
        const wfs = await listWorkflows();
        if (!cancelled) setWorkflows(wfs);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load workflows');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleCreate = useCallback(async () => {
    if (!createName.trim() || creating) return;
    setCreating(true);
    try {
      const wf = await createWorkflow({
        name: createName.trim(),
        description: createDesc.trim(),
      });
      navigate(`/workflows/${wf.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create workflow');
      setCreating(false);
    }
  }, [createName, createDesc, creating, navigate]);

  // ---- Render ----

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-wr-text-muted">
        Loading workflows...
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center text-wr-status-error">
        {error}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-display font-semibold text-wr-text">
          Workflows
        </h1>
        <button
          type="button"
          data-testid="create-workflow-btn"
          onClick={() => setShowCreate((o) => !o)}
          className="rounded-md border border-wr-border bg-wr-accent px-4 py-2 text-sm text-wr-on-accent hover:bg-wr-accent-hover"
        >
          Create workflow
        </button>
      </div>

      {/* Create form (collapsible) */}
      {showCreate && (
        <div className="mb-6 rounded-md border border-wr-border bg-wr-surface p-4">
          <div className="space-y-3">
            <div>
              <label
                htmlFor="wf-create-name"
                className="block text-sm font-medium text-wr-text mb-1"
              >
                Name
              </label>
              <input
                id="wf-create-name"
                data-testid="wf-name-input"
                type="text"
                value={createName}
                onChange={(e) => setCreateName(e.target.value)}
                className="w-full rounded-md border border-wr-border bg-wr-bg px-3 py-2 text-sm text-wr-text focus:outline focus:outline-2 focus:outline-wr-accent"
                placeholder="Workflow name"
              />
            </div>
            <div>
              <label
                htmlFor="wf-create-desc"
                className="block text-sm font-medium text-wr-text mb-1"
              >
                Description (optional)
              </label>
              <input
                id="wf-create-desc"
                type="text"
                value={createDesc}
                onChange={(e) => setCreateDesc(e.target.value)}
                className="w-full rounded-md border border-wr-border bg-wr-bg px-3 py-2 text-sm text-wr-text focus:outline focus:outline-2 focus:outline-wr-accent"
                placeholder="Optional description"
              />
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                data-testid="wf-create-submit"
                onClick={handleCreate}
                disabled={!createName.trim() || creating}
                className="rounded-md border border-wr-border bg-wr-accent px-4 py-1.5 text-sm text-wr-on-accent hover:bg-wr-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
              >
                Create
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowCreate(false);
                  setCreateName('');
                  setCreateDesc('');
                }}
                className="rounded-md border border-wr-border bg-wr-surface px-4 py-1.5 text-sm text-wr-text hover:bg-wr-elevated"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Workflow list */}
      {workflows.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-wr-text-muted">
          <p className="text-lg">No workflows yet</p>
          <p className="mt-1 text-sm">Create your first workflow to get started.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {workflows.map((wf) => (
            <button
              key={wf.id}
              type="button"
              onClick={() => navigate(`/workflows/${wf.id}`)}
              className="flex w-full items-center gap-4 rounded-md border border-wr-border bg-wr-surface px-4 py-3 text-left hover:bg-wr-elevated transition-colors"
            >
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-wr-text">
                  {wf.name}
                </div>
                {wf.description && (
                  <div className="mt-0.5 text-xs text-wr-text-muted truncate">
                    {wf.description}
                  </div>
                )}
              </div>
              <div className="shrink-0 text-xs text-wr-text-muted">
                {new Date(wf.created_at).toLocaleDateString()}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default WorkflowListPage;
