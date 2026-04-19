import type { V4SessionStatus, V4Findings, DiagnosticPhase } from '../../types';

/**
 * Signal scheduler for the War Room banner region.
 *
 * Takes every system-state input that could trigger a top-of-page
 * message and returns exactly one "top" signal (the highest-severity
 * one) plus the list of suppressed signals (for the "+N hidden
 * warnings" Popover).
 *
 * Deterministic, pure. No side effects. Unit-testable.
 *
 * Severity order (highest wins):
 *   attestation > fetch-fail > drain > budget-cap >
 *   parallel-incident > stale-session > ws-disconnected
 *
 * A single active signal ⇒ Mode 3 (banner row renders).
 * No active signals ⇒ Mode 1 (freshness row only).
 */

export type SignalKind =
  | 'attestation'
  | 'fetch-fail'
  | 'drain'
  | 'budget-cap'
  | 'parallel-incident'
  | 'stale-session'
  | 'ws-disconnected';

export type SignalSeverity = 'page' | 'warn' | 'info';

export interface Signal {
  kind: SignalKind;
  severity: SignalSeverity;
  /** Short prose headline, rendered in the banner row. */
  headline: string;
  /** Optional action label — rendered as a button when present. */
  actionLabel?: string;
  /** Arbitrary payload the renderer can use for onClick etc. */
  meta?: Record<string, unknown>;
}

export interface SchedulerInputs {
  /** Consecutive /findings fetch failures; banner fires at >= 3. */
  fetchFailCount: number;
  /** True when the user explicitly dismissed the most recent fetch-fail. */
  fetchErrorDismissed: boolean;
  /** Live WebSocket connection. */
  wsConnected: boolean;
  /** Current incident phase. */
  phase: DiagnosticPhase | null;
  /** Attestation gate payload. */
  attestationGate?: { title?: string } | null;
  /** Drain-mode flag (backend is shutting down). */
  drainMode?: boolean;
  /** Current budget telemetry from session status. */
  budget?: V4SessionStatus['budget'] | null;
  /** Parallel active incident IDs (if the backend surfaces them). */
  parallelIncidentIds?: string[];
  /** Seconds since last user activity. */
  idleSeconds?: number;
  /** Session lifecycle — historical incidents suppress stale-session. */
  isHistorical?: boolean;
}

const SEVERITY_ORDER: Record<SignalKind, number> = {
  attestation:          7,
  'fetch-fail':         6,
  drain:                5,
  'budget-cap':         4,
  'parallel-incident':  3,
  'stale-session':      2,
  'ws-disconnected':    1,
};

export interface ScheduledSignals {
  /** Highest-severity signal to render in Mode 3 banner. Null means
   *  no banner row; freshness row is the only surface (Mode 1). */
  top: Signal | null;
  /** All other active signals, already in severity order. Rendered
   *  as "+N hidden warnings" text-link + Popover list. */
  suppressed: Signal[];
}

/** Generate all active signals in an arbitrary order. */
function collectSignals(inp: SchedulerInputs): Signal[] {
  const out: Signal[] = [];

  if (inp.attestationGate) {
    out.push({
      kind: 'attestation',
      severity: 'page',
      headline:
        inp.attestationGate.title ??
        'Action requires approval.',
      actionLabel: 'Review',
    });
  }

  if (inp.fetchFailCount >= 3 && !inp.fetchErrorDismissed) {
    out.push({
      kind: 'fetch-fail',
      severity: 'warn',
      headline: `Connection issue — data may be stale (${inp.fetchFailCount} failed attempts).`,
      actionLabel: 'Retry',
      meta: { count: inp.fetchFailCount },
    });
  }

  if (inp.drainMode) {
    out.push({
      kind: 'drain',
      severity: 'warn',
      headline:
        'System is draining — current investigation will finish; new ones are paused.',
    });
  }

  if (inp.budget) {
    const toolRatio =
      inp.budget.tool_calls_max > 0
        ? inp.budget.tool_calls_used / inp.budget.tool_calls_max
        : 0;
    const usdRatio =
      inp.budget.llm_usd_max > 0
        ? inp.budget.llm_usd_used / inp.budget.llm_usd_max
        : 0;
    if (toolRatio >= 1 || usdRatio >= 1) {
      out.push({
        kind: 'budget-cap',
        severity: 'warn',
        headline: 'Budget cap reached — agents paused.',
        actionLabel: 'Raise cap',
      });
    }
  }

  if (inp.parallelIncidentIds && inp.parallelIncidentIds.length > 0) {
    const id = inp.parallelIncidentIds[0];
    const extra = inp.parallelIncidentIds.length - 1;
    const headline =
      extra > 0
        ? `${id} is also live (+${extra} more).`
        : `${id} is also live.`;
    out.push({
      kind: 'parallel-incident',
      severity: 'warn',
      headline,
      actionLabel: 'Switch',
      meta: { ids: inp.parallelIncidentIds },
    });
  }

  if (!inp.isHistorical && (inp.idleSeconds ?? 0) >= 9 * 60) {
    out.push({
      kind: 'stale-session',
      severity: 'info',
      headline: 'Session idle — investigation auto-pauses in 60s.',
      actionLabel: 'Stay active',
    });
  }

  if (!inp.wsConnected) {
    out.push({
      kind: 'ws-disconnected',
      severity: 'info',
      headline: 'Real-time updates paused — will reconnect automatically.',
    });
  }

  return out;
}

export function scheduleSignals(inp: SchedulerInputs): ScheduledSignals {
  const all = collectSignals(inp);
  if (all.length === 0) return { top: null, suppressed: [] };

  // Sort high-to-low severity.
  const sorted = [...all].sort(
    (a, b) => SEVERITY_ORDER[b.kind] - SEVERITY_ORDER[a.kind],
  );

  return {
    top: sorted[0],
    suppressed: sorted.slice(1),
  };
}
