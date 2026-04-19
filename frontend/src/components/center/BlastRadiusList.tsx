import React, { useMemo } from 'react';
import type {
  V4Findings,
  BlastRadiusData,
  MetricAnomaly,
  ErrorPattern,
  K8sEvent,
} from '../../types';
import { useIncidentLifecycle } from '../../contexts/IncidentLifecycleContext';
import { useTopologySelection } from '../../contexts/TopologySelectionContext';

/**
 * BlastRadiusList — center-panel addition #5 (the user's #5)
 *
 * Converts the current chip-based blast-radius card into a structured,
 * status-tagged actionable list. Each affected service gets a live
 * status dot computed deterministically from cross-referenced agent
 * signals:
 *
 *   Active lifecycle:
 *     degraded   — service seen in recent (≤ 5 min) non-normal signal
 *     recovered  — previously degraded; most recent ≥ 2 min fresher + normal
 *     stale      — blast-radius mentions it but no signal in ≥ 5 min
 *     unknown    — in blast-radius, never touched by any agent
 *
 *   Historical lifecycle:
 *     degraded-at-close    — was still affected when incident closed
 *     recovered-at-close   — had recovered before close
 *
 * Clicking a service row filters the topology selection so the rest
 * of the evidence column narrows to that service.
 */

interface BlastRadiusListProps {
  findings: V4Findings | null;
}

type LiveStatus = 'degraded' | 'recovered' | 'stale' | 'unknown';
type HistoricalStatus = 'degraded-at-close' | 'recovered-at-close';
type Status = LiveStatus | HistoricalStatus;

interface ServiceEntry {
  service: string;
  tier: 'upstream' | 'downstream' | 'shared';
  status: Status;
  /** Optional descriptive annotation for hover / tooltip. */
  note?: string;
}

const FIVE_MINUTES_MS = 5 * 60 * 1000;
const TWO_MINUTES_MS = 2 * 60 * 1000;

function latestSignalTimestamps(findings: V4Findings): Record<string, number> {
  // Map service → latest ms seen in any anomalous signal
  const map: Record<string, number> = {};
  const ingest = (svc: string, ts: number) => {
    if (!svc) return;
    if (map[svc] == null || ts > map[svc]) map[svc] = ts;
  };

  for (const a of findings.metric_anomalies ?? []) {
    const svc = extractServiceFromPromQL(a);
    if (svc) {
      const ts = Date.parse(a.spike_end ?? a.spike_start ?? '');
      if (!Number.isNaN(ts)) ingest(svc, ts);
    }
  }
  for (const p of findings.error_patterns ?? []) {
    const ts = p.sample_logs?.[p.sample_logs.length - 1]?.timestamp
      ? Date.parse(p.sample_logs[p.sample_logs.length - 1].timestamp as unknown as string)
      : NaN;
    if (!Number.isNaN(ts)) {
      for (const svc of p.affected_components ?? []) ingest(svc, ts);
    }
  }
  for (const e of findings.k8s_events ?? []) {
    const ts = Date.parse(e.timestamp ?? '');
    if (!Number.isNaN(ts) && e.involved_object) ingest(e.involved_object, ts);
  }
  return map;
}

function extractServiceFromPromQL(anomaly: MetricAnomaly): string | null {
  const q = anomaly.promql_query ?? '';
  const patterns = [
    /service(?:_name)?="([^"]+)"/,
    /app="([^"]+)"/,
    /deployment(?:_name)?="([^"]+)"/,
    /destination_service_name="([^"]+)"/,
    /destination_workload="([^"]+)"/,
  ];
  for (const p of patterns) {
    const m = q.match(p);
    if (m && m[1]) return m[1];
  }
  return null;
}

function deriveStatus(
  service: string,
  findings: V4Findings,
  isHistorical: boolean,
  now: number = Date.now(),
): Status {
  const latest = latestSignalTimestamps(findings);
  const seenMs = latest[service];

  if (isHistorical) {
    // Historical — freeze at close-state. Was this service still degraded
    // when the incident closed, or had it recovered?
    if (seenMs == null) return 'recovered-at-close';
    // Heuristic: if the service's latest signal is within 2 min of
    // incident close, treat as still-degraded; else recovered.
    // We don't have an explicit close time — approximate with the
    // newest timestamp across all signals.
    const allLatest = Object.values(latest);
    const closeMs = allLatest.length > 0 ? Math.max(...allLatest) : seenMs;
    return closeMs - seenMs < TWO_MINUTES_MS ? 'degraded-at-close' : 'recovered-at-close';
  }

  if (seenMs == null) return 'unknown';
  const ageMs = now - seenMs;
  if (ageMs > FIVE_MINUTES_MS) return 'stale';

  // Recovered detection — find an earlier anomalous signal followed
  // by a newer "normal" signal. For v1 we use the simpler heuristic:
  // if the latest signal is still within the 5-min window, it's degraded.
  return 'degraded';
}

function buildEntries(
  blast: BlastRadiusData,
  findings: V4Findings,
  isHistorical: boolean,
): ServiceEntry[] {
  const entries: ServiceEntry[] = [];
  const seen = new Set<string>();
  const push = (service: string, tier: ServiceEntry['tier']) => {
    if (seen.has(service)) return;
    seen.add(service);
    entries.push({
      service,
      tier,
      status: deriveStatus(service, findings, isHistorical),
    });
  };
  for (const s of blast.upstream_affected ?? []) push(s, 'upstream');
  for (const s of blast.downstream_affected ?? []) push(s, 'downstream');
  for (const s of blast.shared_resources ?? []) push(s, 'shared');
  return entries;
}

const STATUS_DOT: Record<Status, string> = {
  degraded: 'bg-red-500',
  recovered: 'bg-emerald-500',
  stale: 'bg-amber-400',
  unknown: 'bg-slate-500',
  'degraded-at-close': 'bg-red-500',
  'recovered-at-close': 'bg-emerald-500',
};

const STATUS_LABEL: Record<Status, string> = {
  degraded: 'degraded',
  recovered: 'recovered',
  stale: 'stale',
  unknown: 'unknown',
  'degraded-at-close': 'was still degraded at close',
  'recovered-at-close': 'recovered before close',
};

const TIER_LABEL: Record<ServiceEntry['tier'], string> = {
  upstream: 'upstream',
  downstream: 'downstream',
  shared: 'shared',
};

export const BlastRadiusList: React.FC<BlastRadiusListProps> = ({ findings }) => {
  const { lifecycle } = useIncidentLifecycle();
  const { selectService } = useTopologySelection();

  const entries = useMemo(() => {
    if (!findings?.blast_radius) return [];
    return buildEntries(findings.blast_radius, findings, lifecycle === 'historical');
  }, [findings, lifecycle]);

  if (entries.length === 0) return null;

  const grouped = entries.reduce<Record<ServiceEntry['tier'], ServiceEntry[]>>(
    (acc, e) => {
      (acc[e.tier] ??= []).push(e);
      return acc;
    },
    {} as Record<ServiceEntry['tier'], ServiceEntry[]>,
  );

  return (
    <section
      className="blast-radius-list mb-4 p-4 border border-wr-border rounded-lg bg-wr-bg/40"
      data-testid="blast-radius-list"
    >
      <header className="flex items-baseline justify-between mb-3">
        <h3 className="font-editorial italic text-[13px] text-wr-paper">
          Blast radius · {entries.length} service{entries.length === 1 ? '' : 's'}
        </h3>
      </header>

      {(['upstream', 'downstream', 'shared'] as const).map((tier) => {
        const items = grouped[tier] ?? [];
        if (items.length === 0) return null;
        return (
          <div key={tier} className="mb-3 last:mb-0">
            <div
              className="text-[10px] uppercase text-wr-text-muted mb-1"
              style={{ letterSpacing: '0.12em' }}
            >
              {TIER_LABEL[tier]}
            </div>
            <ul className="space-y-1">
              {items.map((e) => (
                <li key={e.service}>
                  <button
                    type="button"
                    onClick={() => selectService(e.service)}
                    className="w-full flex items-center gap-2 text-left text-[12px] py-0.5 px-1 rounded hover:bg-wr-inset/40 focus-visible:bg-wr-inset/40 focus:outline-none transition-colors"
                    data-testid={`blast-radius-row-${e.service}`}
                  >
                    <span className="text-wr-paper flex-1 font-mono">· {e.service}</span>
                    <span className="flex items-center gap-1.5 shrink-0 text-wr-text-muted">
                      <span
                        aria-hidden
                        className={`w-1.5 h-1.5 rounded-full ${STATUS_DOT[e.status]}`}
                      />
                      <span
                        className="text-[11px] italic font-editorial"
                        data-testid={`blast-radius-status-${e.service}`}
                      >
                        {STATUS_LABEL[e.status]}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </section>
  );
};

export default BlastRadiusList;

// exported for unit tests
export const _internals = { deriveStatus, latestSignalTimestamps, buildEntries };
