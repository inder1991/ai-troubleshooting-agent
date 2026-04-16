import { useState, useMemo } from 'react';
import type { StepRunDetail, StepRunStatus } from '../../../types';

export interface LiveEvent {
  id: number;
  type: string;
  data: {
    node_id?: string;
    step_id?: string;
    status?: StepRunStatus;
    attempt?: number;
    error?: { type?: string; message?: string };
    output?: unknown;
    [key: string]: unknown;
  };
  timestamp: string;
}

interface StepStatusPanelProps {
  stepRuns: StepRunDetail[];
  liveEvents?: LiveEvent[];
}

const STATUS_CLASSES: Record<StepRunStatus, string> = {
  running: 'bg-amber-500 animate-pulse',
  success: 'bg-emerald-500',
  failed: 'bg-red-500',
  skipped: 'bg-gray-500',
  cancelled: 'bg-slate-500',
  pending: 'bg-neutral-500',
};

function formatDuration(ms: number): string {
  if (ms < 1000) return '<1s';
  const totalSec = Math.floor(ms / 1000);
  if (totalSec < 60) return `${totalSec}s`;
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  return sec > 0 ? `${min}m ${sec}s` : `${min}m`;
}

/** Merge stepRuns with live SSE events to derive current display state. */
function mergeWithEvents(
  stepRuns: StepRunDetail[],
  liveEvents: LiveEvent[],
): StepRunDetail[] {
  // Build a map from step_id → latest overrides from events
  const overrides = new Map<string, Partial<StepRunDetail>>();

  for (const evt of liveEvents) {
    const stepId = evt.data.step_id;
    if (!stepId) continue;

    const current = overrides.get(stepId) ?? {};

    if (evt.type === 'step.started') {
      current.status = 'running';
      if (evt.data.attempt != null) current.attempt = evt.data.attempt;
    } else if (evt.type === 'step.completed') {
      current.status = (evt.data.status as StepRunStatus) ?? 'success';
      if (evt.data.output !== undefined) current.output = evt.data.output;
    } else if (evt.type === 'step.failed') {
      current.status = 'failed';
      if (evt.data.error) current.error = evt.data.error;
    } else if (evt.data.status) {
      current.status = evt.data.status;
    }

    overrides.set(stepId, current);
  }

  return stepRuns.map((sr) => {
    const ov = overrides.get(sr.step_id);
    if (!ov) return sr;
    return { ...sr, ...ov };
  });
}

function StepCard({ step }: { step: StepRunDetail }) {
  const [showOutput, setShowOutput] = useState(false);
  const badgeClass = STATUS_CLASSES[step.status] ?? STATUS_CLASSES.pending;

  return (
    <div className="rounded-lg border border-wr-border bg-wr-surface p-4 space-y-2">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <span className="font-medium text-wr-text">{step.step_id}</span>
        <span
          data-testid={`status-badge-${step.step_id}`}
          className={`px-2 py-0.5 rounded text-xs font-semibold text-white ${badgeClass}${step.status === 'skipped' ? ' italic' : ''}`}
        >
          {step.status}
        </span>
      </div>

      {/* Attempt + duration */}
      <div className="flex items-center gap-3 text-sm text-wr-text-secondary">
        <span>Attempt {step.attempt}</span>
        {step.duration_ms != null && (
          <span>{formatDuration(step.duration_ms)}</span>
        )}
      </div>

      {/* Error (always visible for failed) */}
      {step.status === 'failed' && step.error?.message && (
        <div className="text-sm text-red-400 bg-red-900/20 rounded p-2">
          {step.error.type && <span className="font-semibold">{step.error.type}: </span>}
          {step.error.message}
        </div>
      )}

      {/* Expandable output */}
      {step.output !== undefined && (
        <div>
          <button
            className="text-xs text-wr-accent hover:underline"
            onClick={() => setShowOutput((v) => !v)}
          >
            {showOutput ? 'Hide output' : 'Show output'}
          </button>
          {showOutput && (
            <pre className="mt-1 text-xs bg-wr-bg rounded p-2 overflow-auto max-h-48 text-wr-text-secondary font-mono">
              {JSON.stringify(step.output, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

export function StepStatusPanel({ stepRuns, liveEvents = [] }: StepStatusPanelProps) {
  const merged = useMemo(
    () => mergeWithEvents(stepRuns, liveEvents),
    [stepRuns, liveEvents],
  );

  return (
    <div className="space-y-3">
      {merged.map((step) => (
        <StepCard key={`${step.step_id}-${step.id}`} step={step} />
      ))}
    </div>
  );
}
