import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';
import type { V4SessionStatus, DiagnosticPhase } from '../types';

/**
 * IncidentLifecycleContext (PR 1 of the War Room grid-shell migration)
 *
 * Single source of truth for the "is this incident live or historical?"
 * question. Every top-of-page component reads this context and adapts
 * its behavior:
 *
 *   active      — investigation is running; poll for updates, render
 *                 live status dots, show the agent NOW strip, allow
 *                 pinning.
 *   recent      — investigation finished in the last 6h; polling
 *                 continues but at reduced cadence, freshness row
 *                 surfaces the resolution info, FixReadyBar is
 *                 actionable.
 *   historical  — investigation is older than 6h; polling is off,
 *                 BlastRadiusList freezes status to close-time,
 *                 FixReadyBar flips to history-bar mode,
 *                 PinPostmortemChip is hidden. Freshness row reads
 *                 "archived" rather than "live".
 *
 * PR 1 ships the provider + hook. Consumers wire up in later PRs as
 * they need the state. Zero visible change until a component reads it.
 */

export type IncidentLifecycle = 'active' | 'recent' | 'historical';

interface LifecycleValue {
  lifecycle: IncidentLifecycle;
  /** Unix ms when the session last updated (for "X ago" rendering). */
  updatedAtMs: number | null;
  /** Convenience: true if this incident has reached a terminal phase. */
  isTerminal: boolean;
  /** Convenience: true iff polling should be suspended. */
  pollingSuspended: boolean;
}

const Ctx = createContext<LifecycleValue | null>(null);

const RECENT_WINDOW_MS = 6 * 60 * 60 * 1000; // 6 hours
const TERMINAL_PHASES: DiagnosticPhase[] = ['complete', 'diagnosis_complete'];

/**
 * Derive the lifecycle value from a session-status snapshot + current
 * wall-clock. Exported so tests can drive it without mounting context.
 */
export function deriveLifecycle(
  status: V4SessionStatus | null,
  now: number = Date.now(),
): LifecycleValue {
  if (!status) {
    return {
      lifecycle: 'active',
      updatedAtMs: null,
      isTerminal: false,
      pollingSuspended: false,
    };
  }

  const isTerminal = TERMINAL_PHASES.includes(status.phase);
  const updatedAtMs = status.updated_at ? Date.parse(status.updated_at) : null;
  const ageMs = updatedAtMs != null ? now - updatedAtMs : 0;

  let lifecycle: IncidentLifecycle = 'active';
  if (isTerminal) {
    lifecycle = ageMs > RECENT_WINDOW_MS ? 'historical' : 'recent';
  }

  return {
    lifecycle,
    updatedAtMs,
    isTerminal,
    pollingSuspended: lifecycle === 'historical',
  };
}

/**
 * Provider — colocate with the InvestigationView (or any parent that
 * already has sessionStatus in scope).
 *
 * PR-D (audit Bug #12, event-driven lifecycle): the provider used to
 * re-derive only when `status` or an externally-supplied `now` prop
 * changed. That made lifecycle transitions dependent on whoever was
 * feeding `now` — typically a 60s polling loop — so a `recent` → `historical`
 * flip (at t+6h) could be delayed indefinitely if polling paused.
 *
 * Now the provider:
 *   1. Recomputes on every `status` change (phase_change hits this
 *      path immediately because `status.phase` is memo input).
 *   2. Runs its own low-frequency internal ticker (60s) while the
 *      incident is `active` or `recent`, so the bucket flip happens
 *      without the parent having to poll. The ticker stops once the
 *      lifecycle reaches `historical` — nothing more to transition to.
 *   3. If the caller still passes `now` explicitly (tests), that value
 *      wins — internal tick is suppressed.
 */
const LIFECYCLE_TICK_MS = 60_000;

export const IncidentLifecycleProvider: React.FC<{
  status: V4SessionStatus | null;
  /** Optional clock-injection for deterministic tests. Suppresses the
   *  internal ticker so tests remain deterministic. */
  now?: number;
  children: React.ReactNode;
}> = ({ status, now, children }) => {
  const [tick, setTick] = useState<number>(() => Date.now());

  // Recompute using the latest clock source: caller-supplied `now` wins
  // (tests), else our internal tick.
  const effectiveNow = now ?? tick;
  const value = useMemo(
    () => deriveLifecycle(status, effectiveNow),
    [status, effectiveNow],
  );

  // Internal ticker — runs only when a clock-override isn't supplied
  // and the incident isn't already historical (nothing to transition
  // to). Resets whenever `status` changes so the bucket math uses a
  // fresh reference point after each phase_change.
  useEffect(() => {
    if (now !== undefined) return;
    if (value.lifecycle === 'historical') return;
    const id = window.setInterval(() => {
      setTick(Date.now());
    }, LIFECYCLE_TICK_MS);
    return () => window.clearInterval(id);
  }, [now, value.lifecycle, status]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
};

/**
 * Hook consumers reach for. Returns a deterministic default when
 * mounted outside a provider so rendering never crashes — callers
 * that need strict enforcement can check `value.lifecycle` themselves.
 */
export function useIncidentLifecycle(): LifecycleValue {
  const value = useContext(Ctx);
  if (!value) {
    return {
      lifecycle: 'active',
      updatedAtMs: null,
      isTerminal: false,
      pollingSuspended: false,
    };
  }
  return value;
}
