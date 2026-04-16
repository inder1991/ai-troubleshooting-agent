import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { RunStatus, WorkflowSummary } from '../../../types';
import { listWorkflows, createWorkflow, deleteWorkflow, duplicateWorkflow, updateWorkflow } from '../../../services/workflows';
import { ConfirmDeleteDialog } from '../Shared/ConfirmDeleteDialog';

const STATUS_DOT_CLASSES: Record<RunStatus, string> = {
  running: 'bg-amber-500',
  pending: 'bg-neutral-500',
  cancelling: 'bg-slate-400',
  cancelled: 'bg-slate-500',
  success: 'bg-emerald-500',
  failed: 'bg-red-500',
};

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

  // Three-dot menu / actions state
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [deleteTarget, setDeleteTarget] = useState<WorkflowSummary | null>(null);
  const [deleting, setDeleting] = useState(false);

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

  const handleRename = useCallback(async (wfId: string, newName: string) => {
    if (!newName.trim()) return;
    try {
      await updateWorkflow(wfId, { name: newName.trim() });
      setWorkflows((prev) => prev.map((w) => (w.id === wfId ? { ...w, name: newName.trim() } : w)));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Rename failed');
    }
    setRenamingId(null);
  }, []);

  const handleDuplicate = useCallback(async (wfId: string) => {
    setMenuOpenId(null);
    try {
      const dup = await duplicateWorkflow(wfId);
      navigate(`/workflows/${dup.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Duplicate failed');
    }
  }, [navigate]);

  const handleDelete = useCallback(async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteWorkflow(deleteTarget.id);
      setWorkflows((prev) => prev.filter((w) => w.id !== deleteTarget.id));
      setDeleteTarget(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed');
    } finally {
      setDeleting(false);
    }
  }, [deleteTarget]);

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
            <div
              key={wf.id}
              className="relative flex w-full items-center gap-4 rounded-md border border-wr-border bg-wr-surface px-4 py-3 hover:bg-wr-elevated transition-colors"
            >
              {/* Clickable main area */}
              <button
                type="button"
                onClick={() => navigate(`/workflows/${wf.id}`)}
                className="flex flex-1 items-center gap-4 min-w-0 text-left"
              >
                <div className="flex-1 min-w-0">
                  {renamingId === wf.id ? (
                    <input
                      type="text"
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      onBlur={() => handleRename(wf.id, renameValue)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleRename(wf.id, renameValue);
                        if (e.key === 'Escape') setRenamingId(null);
                      }}
                      onClick={(e) => e.stopPropagation()}
                      autoFocus
                      className="w-full rounded-md border border-wr-border bg-wr-bg px-2 py-1 text-sm text-wr-text focus:outline focus:outline-2 focus:outline-wr-accent"
                    />
                  ) : (
                    <div className="text-sm font-medium text-wr-text">
                      {wf.name}
                    </div>
                  )}
                  {wf.description && (
                    <div className="mt-0.5 text-xs text-wr-text-muted truncate">
                      {wf.description}
                    </div>
                  )}
                </div>
                <div className="shrink-0 flex items-center gap-3">
                  {wf.last_run_status && (
                    <span className="flex items-center gap-1.5 text-xs text-wr-text-muted">
                      <span
                        className={`inline-block h-2 w-2 rounded-full ${STATUS_DOT_CLASSES[wf.last_run_status] ?? 'bg-neutral-500'}`}
                        title={wf.last_run_status}
                      />
                      {wf.last_run_at ? relativeTime(wf.last_run_at) : wf.last_run_status}
                    </span>
                  )}
                  <span className="text-xs text-wr-text-muted">
                    {new Date(wf.created_at).toLocaleDateString()}
                  </span>
                </div>
              </button>

              {/* Three-dot menu */}
              <div className="relative shrink-0">
                <button
                  type="button"
                  data-testid={`menu-btn-${wf.id}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    setMenuOpenId((prev) => (prev === wf.id ? null : wf.id));
                  }}
                  className="rounded p-1 text-wr-text-muted hover:bg-wr-elevated hover:text-wr-text"
                >
                  <span className="material-symbols-outlined text-lg">more_vert</span>
                </button>

                {menuOpenId === wf.id && (
                  <div className="absolute right-0 top-full z-10 mt-1 w-40 rounded-md border border-wr-border bg-wr-surface py-1 shadow-lg">
                    <button
                      type="button"
                      className="w-full px-3 py-1.5 text-left text-sm text-wr-text hover:bg-wr-elevated"
                      onClick={(e) => {
                        e.stopPropagation();
                        setMenuOpenId(null);
                        setRenamingId(wf.id);
                        setRenameValue(wf.name);
                      }}
                    >
                      Rename
                    </button>
                    <button
                      type="button"
                      className="w-full px-3 py-1.5 text-left text-sm text-wr-text hover:bg-wr-elevated"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDuplicate(wf.id);
                      }}
                    >
                      Duplicate
                    </button>
                    <button
                      type="button"
                      className="w-full px-3 py-1.5 text-left text-sm text-red-400 hover:bg-wr-elevated"
                      onClick={(e) => {
                        e.stopPropagation();
                        setMenuOpenId(null);
                        setDeleteTarget(wf);
                      }}
                    >
                      Delete
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Delete confirmation dialog */}
      {deleteTarget && (
        <ConfirmDeleteDialog
          workflowName={deleteTarget.name}
          onConfirm={handleDelete}
          onCancel={() => setDeleteTarget(null)}
          deleting={deleting}
        />
      )}
    </div>
  );
}

export default WorkflowListPage;
