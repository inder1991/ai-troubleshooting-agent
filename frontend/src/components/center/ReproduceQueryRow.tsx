import React, { useState, useCallback } from 'react';
import * as Toast from '@radix-ui/react-toast';
import * as Tooltip from '@radix-ui/react-tooltip';
import type { MetricAnomaly, SuggestedPromQLQuery, TimeSeriesDataPoint } from '../../types';
import { runPromQLQuery } from '../../services/api';
import PromQLRunResult from '../Investigation/cards/PromQLRunResult';
import { useIncidentLifecycle } from '../../contexts/IncidentLifecycleContext';

/**
 * ReproduceQueryRow — center-panel addition #3 (the user's #3)
 *
 * Inline affordance on every metric anomaly card that has a matching
 * suggested PromQL query. Two actions:
 *
 *   · copy PromQL → clipboard + 2s confirmation toast
 *   · run inline  → fires runPromQLQuery and renders PromQLRunResult
 *                   under the card
 *
 * The query lookup keys anomaly.metric_name against
 * suggested_promql_queries[].metric. If no match, the row does not
 * render (absence-is-a-signal).
 */

interface ReproduceQueryRowProps {
  anomaly: MetricAnomaly;
  queries: SuggestedPromQLQuery[];
  /** Optional — scopes the backend PromQL rate limiter to this session. */
  sessionId?: string;
}

function matchQuery(
  anomaly: MetricAnomaly,
  queries: SuggestedPromQLQuery[],
): SuggestedPromQLQuery | null {
  // Exact metric-name match wins; fall back to case-insensitive /
  // prefix match so we're lenient with backend naming drift.
  const exact = queries.find((q) => q.metric === anomaly.metric_name);
  if (exact) return exact;
  const ci = queries.find(
    (q) => q.metric.toLowerCase() === anomaly.metric_name.toLowerCase(),
  );
  if (ci) return ci;
  const pref = queries.find((q) =>
    anomaly.metric_name.toLowerCase().startsWith(q.metric.toLowerCase()),
  );
  return pref ?? null;
}

export const ReproduceQueryRow: React.FC<ReproduceQueryRowProps> = ({
  anomaly,
  queries,
  sessionId,
}) => {
  const query = matchQuery(anomaly, queries);
  const { lifecycle } = useIncidentLifecycle();
  // PR-C (audit Bug #9) — running a suggested PromQL from a historical
  // investigation re-executes against live infra. That's a silent side
  // effect against the current system when the user was only reviewing
  // a past incident. Block Run in the `historical` bucket; `recent` is
  // fine (the incident just closed and re-running is genuinely useful).
  const isHistorical = lifecycle === 'historical';
  const [copied, setCopied] = useState(false);
  const [runState, setRunState] = useState<{
    loading: boolean;
    dataPoints: TimeSeriesDataPoint[];
    currentValue: number;
    error?: string;
  } | null>(null);

  const handleCopy = useCallback(() => {
    if (!query) return;
    try {
      void navigator.clipboard.writeText(query.query);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard permissions denied — silent failure; no toast
    }
  }, [query]);

  const handleRun = useCallback(async () => {
    if (!query) return;
    if (isHistorical) return;
    setRunState({ loading: true, dataPoints: [], currentValue: 0 });
    try {
      const end = Math.floor(Date.now() / 1000).toString();
      const start = (Math.floor(Date.now() / 1000) - 3600).toString();
      const result = await runPromQLQuery(query.query, start, end, '60s', sessionId);
      setRunState({
        loading: false,
        dataPoints: result.data_points,
        currentValue: result.current_value,
        error: result.error,
      });
    } catch {
      setRunState({
        loading: false,
        dataPoints: [],
        currentValue: 0,
        error: 'Network request failed',
      });
    }
  }, [query, isHistorical, sessionId]);

  if (!query) return null;

  return (
    <Toast.Provider swipeDirection="right">
      <div
        className="reproduce-query-row mt-2 flex items-center gap-2 text-[11px] text-wr-text-muted"
        data-testid={`reproduce-row-${anomaly.metric_name}`}
      >
        <span className="font-editorial italic">reproduce</span>
        <span className="text-wr-text-subtle">·</span>
        <button
          type="button"
          onClick={handleCopy}
          className="underline-offset-4 hover:underline focus-visible:underline focus:outline-none text-wr-text-muted hover:text-wr-paper transition-colors"
          data-testid="reproduce-copy"
        >
          copy PromQL
        </button>
        <span className="text-wr-text-subtle">·</span>
        <Tooltip.Provider delayDuration={200}>
          <Tooltip.Root>
            <Tooltip.Trigger asChild>
              <button
                type="button"
                onClick={handleRun}
                disabled={runState?.loading || isHistorical}
                aria-disabled={isHistorical || undefined}
                className="underline-offset-4 hover:underline focus-visible:underline focus:outline-none text-wr-text-muted hover:text-wr-paper transition-colors disabled:opacity-50 disabled:cursor-default"
                data-testid="reproduce-run"
                data-historical={isHistorical || undefined}
              >
                {runState?.loading ? 'running…' : 'run inline'}
              </button>
            </Tooltip.Trigger>
            {isHistorical && (
              <Tooltip.Portal>
                <Tooltip.Content
                  className="rounded bg-wr-bg border border-wr-border px-2 py-1 text-[11px] font-editorial italic text-wr-paper/80 max-w-[240px]"
                  sideOffset={4}
                  data-testid="reproduce-run-tooltip"
                >
                  Archived investigation — running would query live infra
                  about a past incident.
                  <Tooltip.Arrow className="fill-wr-border" />
                </Tooltip.Content>
              </Tooltip.Portal>
            )}
          </Tooltip.Root>
        </Tooltip.Provider>
      </div>

      {runState && (
        <div className="mt-2">
          <PromQLRunResult
            dataPoints={runState.dataPoints}
            currentValue={runState.currentValue}
            loading={runState.loading}
            error={runState.error}
          />
        </div>
      )}

      <Toast.Root
        open={copied}
        onOpenChange={setCopied}
        duration={2000}
        className="bg-wr-bg border border-wr-border rounded px-3 py-2 text-[12px] text-wr-paper"
        style={{ zIndex: 'var(--z-toast)' }}
        data-testid="reproduce-toast"
      >
        <Toast.Description>PromQL copied.</Toast.Description>
      </Toast.Root>
      <Toast.Viewport
        className="fixed bottom-4 right-4 flex flex-col gap-2 outline-none"
        style={{ zIndex: 'var(--z-toast)' }}
      />
    </Toast.Provider>
  );
};

export default ReproduceQueryRow;
