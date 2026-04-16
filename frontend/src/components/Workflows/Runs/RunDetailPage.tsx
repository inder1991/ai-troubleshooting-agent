import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useRunEvents } from './useRunEvents';
import { StepStatusPanel } from './StepStatusPanel';
import { EventsRawStream } from './EventsRawStream';
import { cancelRun, RunTerminalError } from '../../../services/runs';
import type { RunStatus } from '../../../types';

const STATUS_CLASSES: Record<RunStatus, string> = {
  running: 'bg-amber-500 animate-pulse',
  pending: 'bg-neutral-500',
  cancelling: 'bg-slate-400',
  cancelled: 'bg-slate-500',
  succeeded: 'bg-emerald-500',
  failed: 'bg-red-500',
};

const TERMINAL: ReadonlySet<RunStatus> = new Set(['succeeded', 'failed', 'cancelled']);

export function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const { run, liveEvents, loading, error, connected } = useRunEvents(runId!);
  const [showRaw, setShowRaw] = useState(false);
  const [cancelling, setCancelling] = useState(false);

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
        </div>

        <button
          className="px-3 py-1.5 rounded text-sm font-medium bg-red-600 hover:bg-red-700 text-white disabled:opacity-40 disabled:cursor-not-allowed"
          disabled={isTerminal || cancelling}
          onClick={handleCancel}
        >
          {cancelling ? 'Cancelling...' : 'Cancel'}
        </button>
      </div>

      {/* Step status panel */}
      <StepStatusPanel stepRuns={run.step_runs} liveEvents={liveEvents} />

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
