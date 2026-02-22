import React from 'react';
import type { MetricAnomaly, CorrelatedSignalGroup, Severity } from '../../../types';

interface REDMethodStatusBarProps {
  metricAnomalies: MetricAnomaly[];
  correlatedSignals: CorrelatedSignalGroup[];
}

interface REDCategory {
  label: string;
  value: string;
  severity: Severity | 'ok';
}

const dotColor: Record<Severity | 'ok', string> = {
  ok: 'bg-green-500',
  critical: 'bg-red-500',
  high: 'bg-red-500',
  medium: 'bg-amber-500',
  low: 'bg-cyan-500',
  info: 'bg-slate-500',
};

const textColor: Record<Severity | 'ok', string> = {
  ok: 'text-green-400',
  critical: 'text-red-400',
  high: 'text-red-400',
  medium: 'text-amber-400',
  low: 'text-cyan-400',
  info: 'text-slate-400',
};

const RATE_PATTERNS = /request|req|rate|rps|throughput|qps/i;
const ERROR_PATTERNS = /error|err|fault|fail|5xx|4xx/i;
const DURATION_PATTERNS = /latency|duration|response.?time|p50|p95|p99|elapsed/i;

function classifyAnomaly(ma: MetricAnomaly): 'rate' | 'errors' | 'duration' | null {
  const name = ma.metric_name;
  if (ERROR_PATTERNS.test(name)) return 'errors';
  if (DURATION_PATTERNS.test(name)) return 'duration';
  if (RATE_PATTERNS.test(name)) return 'rate';
  return null;
}

function formatValue(value: number, category: 'rate' | 'errors' | 'duration'): string {
  if (category === 'rate') {
    if (value >= 1000) return `${(value / 1000).toFixed(1)}k req/s`;
    return `${value.toFixed(0)} req/s`;
  }
  if (category === 'errors') {
    // If value looks like a percentage already (< 100), display as %
    if (value <= 100) return `${value.toFixed(1)}%`;
    return `${value.toFixed(0)}`;
  }
  if (category === 'duration') {
    if (value >= 1000) return `${(value / 1000).toFixed(2)}s`;
    return `${value.toFixed(0)}ms`;
  }
  return `${value.toFixed(1)}`;
}

const REDMethodStatusBar: React.FC<REDMethodStatusBarProps> = ({
  metricAnomalies,
  correlatedSignals,
}) => {
  // Classify anomalies into RED categories
  const rateAnomalies = metricAnomalies.filter((ma) => classifyAnomaly(ma) === 'rate');
  const errorAnomalies = metricAnomalies.filter((ma) => classifyAnomaly(ma) === 'errors');
  const durationAnomalies = metricAnomalies.filter((ma) => classifyAnomaly(ma) === 'duration');

  // Also check correlated signals for RED signal groups
  const redSignal = correlatedSignals.find((cs) => cs.signal_type === 'RED');

  const buildCategory = (
    label: string,
    category: 'rate' | 'errors' | 'duration',
    anomalies: MetricAnomaly[]
  ): REDCategory => {
    if (anomalies.length === 0) {
      return { label, value: 'OK', severity: 'ok' };
    }
    // Pick the highest severity anomaly
    const worst = anomalies.sort(
      (a, b) => severityRank(a.severity) - severityRank(b.severity)
    )[0];
    return {
      label,
      value: formatValue(worst.current_value, category),
      severity: worst.severity,
    };
  };

  const categories: REDCategory[] = [
    buildCategory('Rate', 'rate', rateAnomalies),
    buildCategory('Errors', 'errors', errorAnomalies),
    buildCategory('Duration', 'duration', durationAnomalies),
  ];

  // Don't render if all OK and no RED signal group
  if (categories.every((c) => c.severity === 'ok') && !redSignal) return null;

  // Gather signal group narratives
  const narratives = correlatedSignals
    .filter((cs) => cs.narrative)
    .map((cs) => ({ group: cs.group_name, narrative: cs.narrative, metrics: cs.metrics }));

  return (
    <div className="space-y-2">
      <div className="flex gap-2 flex-wrap">
        {categories.map((cat) => (
          <div
            key={cat.label}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-800/60 border border-slate-700/50"
          >
            <span className={`w-2 h-2 rounded-full ${dotColor[cat.severity]}`} />
            <span className="text-[10px] text-slate-400">{cat.label}:</span>
            <span className={`text-[10px] font-mono font-bold ${textColor[cat.severity]}`}>
              {cat.value}
            </span>
          </div>
        ))}
      </div>
      {narratives.length > 0 && (
        <div className="space-y-1.5">
          {narratives.map((n, i) => (
            <div key={i} className="bg-slate-800/30 rounded-lg border border-slate-700/30 px-2.5 py-1.5">
              <div className="flex items-center gap-1.5 mb-0.5">
                <span className="text-[9px] font-bold text-cyan-400 uppercase">{n.group}</span>
                {n.metrics?.length > 0 && (
                  <span className="text-[9px] text-slate-600 font-mono">{n.metrics.length} metrics</span>
                )}
              </div>
              <p className="text-[10px] text-slate-400">{n.narrative}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

function severityRank(s: Severity): number {
  const ranks: Record<Severity, number> = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
  return ranks[s] ?? 4;
}

export default REDMethodStatusBar;
