import React from 'react';
import type { V4Findings, V4SessionStatus, TaskEvent, DiagnosticPhase } from '../../types';
import { synthesizePhaseNarrative } from './phaseNarrative';
import { useIncidentLifecycle } from '../../contexts/IncidentLifecycleContext';
import { useAppControl } from '../../contexts/AppControlContext';

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
}

function formatTokens(tokens: number): string {
  if (tokens >= 1000) {
    return `${(tokens / 1000).toFixed(1)}k tokens`;
  }
  return `${tokens} tokens`;
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
}) => {
  const { lifecycle, updatedAtMs } = useIncidentLifecycle();
  const { isManualOverride } = useAppControl();

  // ── Compute clauses ──
  const isArchived = lifecycle === 'historical';

  // Dot + status label (leading clause)
  let dotClass: string;
  let statusLabel: string;
  if (isManualOverride) {
    dotClass = 'bg-amber-400';
    statusLabel = '⏸ manual override';
  } else if (isArchived) {
    dotClass = 'bg-slate-500';
    statusLabel = 'archived';
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

  // Freshness clause
  const freshnessClause = isArchived
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
  const costClause = usd > 0 ? `$${usd.toFixed(3)}` : null;

  // Phase narrative
  const narrative = synthesizePhaseNarrative({
    events,
    phase: status?.phase ?? null,
    isManualOverride,
    isHistorical: isArchived,
  });

  return (
    <div
      className="freshness-row px-6 py-1.5 flex flex-col gap-0.5"
      data-testid="freshness-row"
    >
      {/* Clause line — micro-typography per clause */}
      <p className="flex items-baseline flex-wrap gap-x-2 text-[12px] leading-[1.5]">
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
      </p>

      {/* Phase narrative line */}
      {narrative && (
        <p
          className="font-editorial italic text-[12px] leading-[1.4] text-wr-text-subtle"
          data-testid="phase-narrative"
        >
          {narrative}
        </p>
      )}
    </div>
  );
};

export default FreshnessRow;
