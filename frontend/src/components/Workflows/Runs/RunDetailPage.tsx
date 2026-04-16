import { useState, useEffect, useCallback } from 'react';
import { useParams, useLocation } from 'react-router-dom';
import { useRunEvents } from './useRunEvents';
import { StepStatusPanel } from './StepStatusPanel';
import { EventsRawStream } from './EventsRawStream';
import { DagView } from './DagView';
import { cancelRun, RunTerminalError } from '../../../services/runs';
import { getVersion } from '../../../services/workflows';
import type { RunStatus, StepSpec } from '../../../types';

type ViewMode = 'cards' | 'graph';

const STATUS_CLASSES: Record<RunStatus, string> = {
  running: 'bg-amber-500 animate-pulse',
  pending: 'bg-neutral-500',
  cancelling: 'bg-slate-400',
  cancelled: 'bg-slate-500',
  succeeded: 'bg-emerald-500',
  failed: 'bg-red-500',
};

const TERMINAL: ReadonlySet<RunStatus> = new Set(['succeeded', 'failed', 'cancelled']);

function readViewMode(): ViewMode {
  try {
    const stored = window.localStorage.getItem('wf-run-view-mode');
    return stored === 'graph' ? 'graph' : 'cards';
  } catch {
    return 'cards';
  }
}

export function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const location = useLocation();
  const workflowId = (location.state as { workflowId?: string } | null)?.workflowId ?? null;

  const { run, liveEvents, loading, error, connected } = useRunEvents(runId!);
  const [showRaw, setShowRaw] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>(readViewMode);
  const [dagSteps, setDagSteps] = useState<StepSpec[] | null>(null);
  const [highlightedStepId, setHighlightedStepId] = useState<string | null>(null);

  // Fetch DAG steps when we have workflowId and run data
  useEffect(() => {
    if (!workflowId || !run) return;
    let cancelled = false;

    async function fetchSteps() {
      try {
        const versionDetail = await getVersion(workflowId!, run!.workflow_version_id);
        if (!cancelled) {
          setDagSteps(versionDetail.dag.steps);
        }
      } catch {
        // Silently fail — graph view just won't be available
      }
    }

    fetchSteps();
    return () => { cancelled = true; };
  }, [workflowId, run?.workflow_version_id]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleViewMode = useCallback((mode: ViewMode) => {
    setViewMode(mode);
    try {
      window.localStorage.setItem('wf-run-view-mode', mode);
    } catch {
      // localStorage not available
    }
  }, []);

  if (loading) {
    return (
      <div className="p-6 text-wr-text-secondary">Loading run...</div>
    );
  }

  if (error) {
    return (
      <div className="p-6 text-red-400">
        Error loading run: {error.message}
      </div>
    );
  }

  if (!run) return null;

  const isTerminal = TERMINAL.has(run.status);
  const graphDisabled = !workflowId;

  async function handleCancel() {
    if (!runId || cancelling) return;
    setCancelling(true);
    try {
      await cancelRun(runId);
    } catch (err) {
      if (err instanceof RunTerminalError) {
        // Already terminal — UI will reflect via SSE or next fetch
      }
    } finally {
      setCancelling(false);
    }
  }

  const handleNodeClick = (nodeId: string) => {
    setHighlightedStepId((prev) => (prev === nodeId ? null : nodeId));
  };

  const handleCardClick = (stepId: string) => {
    setHighlightedStepId((prev) => (prev === stepId ? null : stepId));
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold text-wr-text">
            Run {run.id}
          </h1>
          <span
            data-testid="run-status-badge"
            className={`px-2 py-0.5 rounded text-xs font-semibold text-white ${STATUS_CLASSES[run.status] ?? 'bg-neutral-500'}`}
          >
            {run.status}
          </span>
          {/* Connected indicator */}
          <span
            className={`inline-block w-2 h-2 rounded-full ${connected ? 'bg-emerald-400' : 'bg-neutral-600'}`}
            title={connected ? 'SSE connected' : 'SSE disconnected'}
          />

          {/* View mode toggle */}
          <div className="flex rounded border border-wr-border overflow-hidden">
            <button
              className={`px-3 py-1 text-xs font-medium ${viewMode === 'cards' ? 'bg-wr-accent text-white' : 'bg-wr-surface text-wr-text-secondary hover:bg-wr-surface-2'}`}
              onClick={() => handleViewMode('cards')}
              data-testid="view-toggle-cards"
            >Cards</button>
            <button
              className={`px-3 py-1 text-xs font-medium ${viewMode === 'graph' && !graphDisabled ? 'bg-wr-accent text-white' : 'bg-wr-surface text-wr-text-secondary hover:bg-wr-surface-2'}`}
              onClick={() => !graphDisabled && handleViewMode('graph')}
              disabled={graphDisabled}
              title={graphDisabled ? 'Navigate from a workflow to use graph view' : undefined}
              data-testid="view-toggle-graph"
            >Graph</button>
          </div>
        </div>

        <button
          className="px-3 py-1.5 rounded text-sm font-medium bg-red-600 hover:bg-red-700 text-white disabled:opacity-40 disabled:cursor-not-allowed"
          disabled={isTerminal || cancelling}
          onClick={handleCancel}
        >
          {cancelling ? 'Cancelling...' : 'Cancel'}
        </button>
      </div>

      {/* DagView (graph mode) */}
      {viewMode === 'graph' && !graphDisabled && dagSteps && (
        <div className="h-80">
          <DagView
            steps={dagSteps}
            stepRuns={run.step_runs}
            liveEvents={liveEvents}
            selectedNodeId={highlightedStepId}
            onNodeClick={handleNodeClick}
          />
        </div>
      )}

      {/* Step status panel */}
      <StepStatusPanel
        stepRuns={run.step_runs}
        liveEvents={liveEvents}
        highlightedStepId={highlightedStepId}
        onCardClick={handleCardClick}
      />

      {/* Raw events toggle */}
      <div>
        <button
          className="text-sm text-wr-accent hover:underline"
          onClick={() => setShowRaw((v) => !v)}
        >
          {showRaw ? 'Hide raw events' : 'Show raw events'}
        </button>
        {showRaw && (
          <div className="mt-2">
            <EventsRawStream events={liveEvents} />
          </div>
        )}
      </div>
    </div>
  );
}
