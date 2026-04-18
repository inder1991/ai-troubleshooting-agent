import React, { useState } from 'react';
import type { DivergenceFinding, DivergenceKind, V4Findings } from '../../types';

// Intentionally not a card. No border, no background fill, no agent badge.
// Typography-led marginalia that sits above the anchor bar in EvidenceFindings.
// The whole point of the visual treatment is to *interrupt* the card grid,
// not join it — so the SRE's eye catches the meta-commentary as different.

interface DisagreementStripProps {
  findings: V4Findings | null;
}

// Map each divergence kind to the two "sides" the SRE needs to reconcile.
// Source: what the system observed. Silent: what's missing / inconsistent.
// Possible causes: honest hypotheses — never prescriptive, never ranked.
const KIND_EXPLAINERS: Record<
  DivergenceKind,
  {
    source: string;          // who said what
    silent: string;          // who didn't
    possibleCauses: string[]; // honest hypotheses, unordered
  }
> = {
  trace_failure_service_no_metric_anomaly: {
    source: 'tracing identified this service as the failure point',
    silent: 'metrics did not flag it',
    possibleCauses: [
      'sampling outlier — tracing hit one bad trace, population is fine',
      'metric-pipeline lag caught up to the trace sample',
      'aggregation dropped the service label',
    ],
  },
  trace_baseline_regression_no_metric_anomaly: {
    source: 'tracing saw a latency regression vs baseline',
    silent: 'metrics report this service as healthy',
    possibleCauses: [
      'sampling window mismatch between the two sources',
      'metric not labelled by service — regression invisible in aggregate',
      'trace baseline out of date',
    ],
  },
  metric_anomaly_service_absent_from_trace: {
    source: 'metrics flagged an anomaly on this service',
    silent: 'tracing never saw it in the sampled request path',
    possibleCauses: [
      'anomaly is upstream / sibling, not on the sampled critical path',
      'tracing sampled away from this hop',
      'service instrumented for metrics but not for traces',
    ],
  },
  metric_anomaly_no_error_logs: {
    source: 'metrics flagged an anomaly on this service',
    silent: 'logs show no repeating error pattern on it',
    possibleCauses: [
      'noisy metric — upstream 4xx counted as errors',
      'app not logging at error level for these failures',
      'log shipper dropping or lagging this service',
    ],
  },
  log_error_cluster_no_metric_anomaly: {
    source: 'logs show a repeating error cluster on this service',
    silent: 'metrics report it as healthy',
    possibleCauses: [
      'error-rate counter missing or unlabelled for this service',
      'errors are caught and logged but not surfaced as a metric',
      'metric baseline already absorbs this pattern',
    ],
  },
  log_error_service_not_in_metrics: {
    source: 'logs name this service',
    silent: 'no metric label ever matches it',
    possibleCauses: [
      'scrape config missing — service fully uninstrumented',
      'log identifier is a URL path, not a deploy / service name',
      'service name mismatch between log field and metric label',
    ],
  },
};

// Compact one-line subject for each row. Lowercase, conversational, no caps-lock chrome.
function summaryFor(d: DivergenceFinding): string {
  const { source, silent } = KIND_EXPLAINERS[d.kind];
  return `${d.service_name} — ${source}, ${silent}`;
}

const DisagreementStrip: React.FC<DisagreementStripProps> = ({ findings }) => {
  const divergences = findings?.divergence_findings ?? [];
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);

  if (divergences.length === 0) return null;

  const count = divergences.length;
  const headline =
    count === 1
      ? 'signals disagree on 1 service.'
      : `signals disagree on ${count} services.`;

  return (
    <div
      className="mb-6 pl-3 border-l border-wr-accent-2/40"
      data-testid="disagreement-strip"
      role="region"
      aria-label="cross-agent signal disagreements"
    >
      {/* Editor's-note headline. Lowercase, quiet, single accent glyph. */}
      <div className="flex items-baseline gap-2 text-body-xs">
        <span
          aria-hidden
          className="text-wr-accent-2 font-mono select-none"
          style={{ fontFeatureSettings: '"tnum"' }}
        >
          ⦿
        </span>
        <span className="text-slate-300 font-editorial italic tracking-tight">
          {headline}
        </span>
      </div>

      {/* Rows: prose, not cards. Click to expand possible causes in place. */}
      <ul className="mt-2 space-y-1" role="list">
        {divergences.map((d, idx) => {
          const isExpanded = expandedIdx === idx;
          const { possibleCauses } = KIND_EXPLAINERS[d.kind];
          return (
            <li key={`${d.kind}-${d.service_name}-${idx}`} className="leading-snug">
              <button
                type="button"
                onClick={() => setExpandedIdx(isExpanded ? null : idx)}
                aria-expanded={isExpanded}
                className="text-left text-body-xs text-slate-400 hover:text-slate-200 focus:text-slate-200 transition-colors w-full"
              >
                <span className="font-mono text-wr-accent-2/70 mr-2 select-none">
                  {isExpanded ? '–' : '+'}
                </span>
                {summaryFor(d)}
              </button>

              {isExpanded && (
                <div
                  className="ml-5 mt-1 mb-1 text-body-xs text-slate-500 animate-[fadeSlideUp_180ms_cubic-bezier(0.16,1,0.3,1)_forwards] motion-reduce:animate-none"
                  role="region"
                  aria-label={`possible causes for ${d.service_name}`}
                >
                  <div className="text-slate-400 mb-1">possible causes</div>
                  <ul className="space-y-0.5">
                    {possibleCauses.map((c, ci) => (
                      <li key={ci} className="flex gap-2">
                        <span
                          aria-hidden
                          className="text-wr-accent-2/50 font-mono select-none"
                        >
                          ·
                        </span>
                        <span>{c}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
};

export default DisagreementStrip;
