import React from 'react';
import type { V4Findings, V4SessionStatus, TaskEvent, DiagnosticPhase } from '../../types';
import { synthesizePhaseNarrative } from './phaseNarrative';
import { useIncidentLifecycle } from '../../contexts/IncidentLifecycleContext';
import { useAppControl } from '../../contexts/AppControlContext';
import SessionControlsRow from './SessionControlsRow';
import SignatureMatchPill from './SignatureMatchPill';

/**
 * FreshnessRow — the always-on second line of the War Room banner
 * region. Renders as a single editorial prose line with per-clause
 * micro-typography so status, identifiers, counts, and financials
 * parse instantly:
 *
 *   ● live · 3s · INC-... · 12.7k tokens · $0.042
 *   (phase narrative in italic serif underneath)
 *
 * Absence-is-a-signal rules:
 *   · Every clause drops when its source data is missing
 *   · Incident id hidden if `findings.incident_id` absent
 *   · Tokens / cost hidden if zero
 *
 * Lifecycle-aware copy:
 *   · active    — ● live + phase narrative
 *   · recent    — ● live + phase narrative (resolution-focused)
 *   · historical — archived + "closed X ago" + frozen narrative
 *
 * Manual-override branch:
 *   · ⏸ manual override + "Awaiting operator input."
 */

interface FreshnessRowProps {
  findings: V4Findings | null;
  status: V4SessionStatus | null;
  events: TaskEvent[];
  lastFetchAgoSec: number;
  wsConnected: boolean;
  /** PR-B — session ID for the Cancel / Copy-link controls row. Optional
   *  so consumers who don't need the controls (tests, storybook) can
   *  render the freshness line without wiring session context. */
  sessionId?: string;
}

function formatTokens(tokens: number): string {
  if (tokens >= 1000) {
    return `${(tokens / 1000).toFixed(1)}k tokens`;
  }
  return `${tokens} tokens`;
}

/**
 * PR-E — translate a backend diagnosis_stop_reason enum into an
 * editorial one-liner. The enum values are deliberately technical
 * (max_rounds_reached, coverage_saturated_no_new_signal, etc.) so
 * they read fine in logs and metrics but are hostile as UI copy.
 * Here we turn them into calm, human-readable prose.
 *
 * Returns null when the investigation is still running (stop reason
 * not yet set) or when the reason maps to phase state already shown
 * elsewhere (e.g. `cancelled` — the freshness dot already says so).
 */
function formatStopReason(reason: string | null | undefined): string | null {
  if (!reason) return null;
  if (reason === 'cancelled' || reason === 'error') return null;
  if (reason.startsWith('signature_matched_')) {
    return 'Known pattern matched — stopped early.';
  }
  const map: Record<string, string> = {
    max_rounds_reached: 'Reached the round budget without converging.',
    high_confidence_no_challenges: 'Confident verdict; no open challenges.',
    coverage_saturated_no_new_signal: 'Coverage saturated — no new signal.',
    planner_empty: 'Planner had nothing left to dispatch.',
  };
  return map[reason] ?? null;
}

function formatClosedAgo(updatedAtMs: number | null): string {
  if (!updatedAtMs) return 'some time ago';
  const deltaMin = Math.max(1, Math.floor((Date.now() - updatedAtMs) / 60000));
  if (deltaMin < 60) return `${deltaMin}m ago`;
  const hours = Math.floor(deltaMin / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export const FreshnessRow: React.FC<FreshnessRowProps> = ({
  findings,
  status,
  events,
  lastFetchAgoSec,
  wsConnected,
  sessionId,
}) => {
  const { lifecycle, updatedAtMs, isTerminal } = useIncidentLifecycle();
  const { isManualOverride } = useAppControl();

  // ── Compute clauses ──
  const isArchived = lifecycle === 'historical';
  // PR-D (audit Bug #13): once the investigation is terminal — even if
  // it just completed 5s ago — the `live` dot and seconds-counter are
  // misleading; agents are no longer running. Flip the leading clause
  // to a neutral "resolved / archived" voice as soon as the phase goes
  // terminal, so the banner reflects "investigation ended" instead of
  // "still running with zero updates."
  const isFinished = isTerminal;

  // Dot + status label (leading clause)
  let dotClass: string;
  let statusLabel: string;
  if (isManualOverride) {
    dotClass = 'bg-amber-400';
    statusLabel = '⏸ manual override';
  } else if (isArchived) {
    dotClass = 'bg-slate-500';
    statusLabel = 'archived';
  } else if (isFinished) {
    // recent-bucket, terminal phase — investigation wrapped; no more
    // polling semantics to communicate.
    dotClass = 'bg-slate-400';
    statusLabel = 'resolved';
  } else if (!wsConnected) {
    dotClass = 'bg-slate-500';
    statusLabel = 'reconnecting';
  } else if (lastFetchAgoSec <= 10) {
    dotClass = 'bg-green-500';
    statusLabel = 'live';
  } else if (lastFetchAgoSec <= 30) {
    dotClass = 'bg-amber-400';
    statusLabel = 'live';
  } else {
    dotClass = 'bg-red-500';
    statusLabel = 'stale';
  }

  // Freshness clause. Terminal phases (recent + historical) surface
  // close-time instead of a ticking seconds counter — the counter
  // implies "waiting for the next poll", which is no longer true.
  const freshnessClause = isFinished
    ? `closed ${formatClosedAgo(updatedAtMs)}`
    : `${lastFetchAgoSec}s`;

  // Incident id
  const incidentId = findings?.incident_id ?? null;

  // Tokens and cost
  const totalTokens = (status?.token_usage ?? []).reduce(
    (s, t) => s + t.total_tokens,
    0,
  );
  const tokensClause = totalTokens > 0 ? formatTokens(totalTokens) : null;

  const usd = status?.budget?.llm_usd_used ?? 0;
  const usdMax = status?.budget?.llm_usd_max ?? 0;
  const costClause = usd > 0 ? `$${usd.toFixed(3)}` : null;
  // PR-I — surface a cost-burn warning when we've spent > 80% of the
  // budgeted LLM USD. Gives operators a moment to intervene before
  // the investigation hits the cap and stops dispatching agents.
  // Hidden until 80% + when no cap is configured (usdMax === 0).
  const budgetPct = usdMax > 0 ? usd / usdMax : 0;
  const burnClause =
    usdMax > 0 && budgetPct >= 0.8
      ? `${Math.round(budgetPct * 100)}% of budget`
      : null;
  const burnHigh = budgetPct >= 0.95;

  // Phase narrative
  const narrative = synthesizePhaseNarrative({
    events,
    phase: status?.phase ?? null,
    isManualOverride,
    isHistorical: isArchived,
  });

  // PR-H (audit Bug #24) — assistive tech needs a polite live region
  // so screen-reader users hear the state label change ("live" → "stale"
  // → "resolved") instead of silently re-rendering. Keep the whole
  // first clause line as the live region so dot-change, freshness-age,
  // tokens, and cost all coalesce into one announcement.
  return (
    <div
      className="freshness-row px-6 py-1.5 flex flex-col gap-0.5"
      data-testid="freshness-row"
    >
      {/* Clause line — micro-typography per clause. Session controls
          (Copy link, Cancel) hug the right edge so they never steal
          attention but are always reachable. */}
      <div className="flex items-baseline gap-3">
      <p
        className="flex-1 min-w-0 flex items-baseline flex-wrap gap-x-2 text-[12px] leading-[1.5]"
        aria-live="polite"
        aria-atomic="true"
        role="status"
      >
        <span className="inline-flex items-baseline gap-1.5 text-wr-paper font-medium">
          <span
            className={`inline-block w-1.5 h-1.5 rounded-full ${dotClass}`}
            aria-hidden
          />
          {statusLabel}
        </span>

        <span className="text-wr-text-muted tabular-nums" data-testid="freshness-age">
          · {freshnessClause}
        </span>

        {incidentId && (
          <span
            className="font-mono text-[11px] text-wr-text-muted"
            data-testid="freshness-incident-id"
          >
            · {incidentId}
          </span>
        )}

        {tokensClause && (
          <span
            className="font-editorial italic text-wr-text-muted"
            data-testid="freshness-tokens"
          >
            · {tokensClause}
          </span>
        )}

        {costClause && (
          <span
            className="font-editorial italic text-wr-text-muted"
            data-testid="freshness-cost"
          >
            · {costClause}
          </span>
        )}

        {burnClause && (
          <span
            className={`font-editorial italic tabular-nums ${
              burnHigh ? 'text-red-400' : 'text-amber-400'
            }`}
            data-testid="freshness-burn"
            aria-label={`${burnClause} — ${burnHigh ? 'critical' : 'warning'}`}
          >
            · {burnClause}
          </span>
        )}

        {/* PR-E — signature-match pill hugs the clause line. Pattern
            name + confidence live here; details expand on hover. */}
        {status?.signature_match && (
          <SignatureMatchPill match={status.signature_match} />
        )}
      </p>

      {/* Session controls — always-on right-aligned cluster. Copy link
          and Cancel are non-optional user controls; hiding them would
          force SREs back to closing the tab. */}
      {sessionId && (
        <SessionControlsRow
          sessionId={sessionId}
          findings={findings}
          status={status}
        />
      )}
      </div>

      {/* Phase narrative line — separate live region so phase-change
          narration ("Log Agent is investigating…" → "Metric Scanner is
          correlating…") is announced independently of the freshness
          clause. Polite to avoid interrupting the operator mid-task. */}
      {narrative && (
        <p
          className="font-editorial italic text-[12px] leading-[1.4] text-wr-text-subtle"
          data-testid="phase-narrative"
          aria-live="polite"
          aria-atomic="true"
        >
          {narrative}
        </p>
      )}

      {/* PR-E — stop-reason line. Backend has emitted
          diagnosis_stop_reason for months; the UI never rendered it,
          so "why did the investigation end?" was invisible to
          operators. Surface it as a small italic line beneath the
          phase narrative, only when the investigation has actually
          stopped and the reason maps to a human-readable phrase. */}
      {(() => {
        const stopPhrase = formatStopReason(status?.diagnosis_stop_reason);
        if (!stopPhrase) return null;
        return (
          <p
            className="font-editorial italic text-[12px] leading-[1.4] text-wr-text-subtle"
            data-testid="freshness-stop-reason"
            aria-live="polite"
          >
            {stopPhrase}
          </p>
        );
      })()}
    </div>
  );
};

export default FreshnessRow;
