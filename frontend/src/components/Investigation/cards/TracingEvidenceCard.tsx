import React, { useState } from 'react';
import type { TraceAnalysisResult, PatternKind, PatternFinding } from '../../../types';
import TraceTelescope from '../TraceTelescope/TraceTelescope';

interface TracingEvidenceCardProps {
  trace: TraceAnalysisResult;
  backendUrl?: string;
}

/**
 * Evidence-stack card summarizing TracingAgent output.
 *
 * Shows:
 *   - 1-line consensus summary
 *   - Provenance + confidence pills
 *   - Envoy-flag badge (deterministic)
 *   - Pattern pills (deterministic pre-analysis)
 *   - Mini waterfall thumbnail
 *   - Handoff-services chips
 *   - Explore button → opens TraceTelescope
 */
export default function TracingEvidenceCard({ trace, backendUrl }: TracingEvidenceCardProps) {
  const [telescopeOpen, setTelescopeOpen] = useState(false);
  const failureSvc = trace.failure_point?.service_name ?? trace.failure_point?.service;
  const consensus = buildConsensusLine(trace);
  const provenance = provenanceFor(trace);
  const tierLabel = tierLabelFor(trace.tier_decision);

  return (
    <>
      <article
        className="bg-wr-surface/40 border border-wr-border rounded-lg p-4 space-y-3"
        data-testid="tracing-evidence-card"
      >
        {/* Heading */}
        <header className="flex items-start justify-between gap-4">
          <div>
            <p className="text-body-xs uppercase tracking-widest text-wr-text-muted">
              Distributed trace
            </p>
            <p className="text-sm text-wr-text font-medium mt-0.5">{consensus}</p>
          </div>
          <button
            type="button"
            onClick={() => setTelescopeOpen(true)}
            className="shrink-0 text-body-xs font-semibold text-wr-accent border border-wr-accent/60 px-2.5 py-1 rounded hover:bg-wr-accent/10 transition-colors"
            data-testid="open-telescope"
          >
            Explore trace →
          </button>
        </header>

        {/* Provenance row */}
        <div className="flex flex-wrap items-center gap-2 text-body-xs">
          <span className={`px-2 py-0.5 rounded border ${provenance.cls}`} data-testid="provenance-badge">
            {provenance.label}
          </span>
          <span className="px-2 py-0.5 rounded border border-wr-border text-wr-text-muted">
            {trace.overall_confidence}% confidence
          </span>
          {tierLabel && (
            <span className="px-2 py-0.5 rounded border border-wr-border text-wr-text-muted">
              {tierLabel}
            </span>
          )}
          {trace.cross_trace_consensus && (
            <span className={`px-2 py-0.5 rounded border ${consensusClass(trace.cross_trace_consensus)}`}>
              {trace.cross_trace_consensus}
            </span>
          )}
          {trace.sampling_mode && (
            <span className="px-2 py-0.5 rounded text-wr-text-muted">
              {trace.sampling_mode}
            </span>
          )}
        </div>

        {/* Envoy flags — deterministic */}
        {trace.envoy_findings && trace.envoy_findings.length > 0 && (
          <div className="flex flex-wrap items-center gap-2" data-testid="envoy-flags">
            <span className="text-body-xs text-wr-text-muted">Envoy:</span>
            {trace.envoy_findings.map((f) => (
              <span
                key={f.span_id}
                className="px-2 py-0.5 rounded border border-red-500/40 bg-red-950/30 text-body-xs text-red-200"
                title={f.human_summary}
              >
                {f.flag} — {f.service_name}
              </span>
            ))}
          </div>
        )}

        {/* Pattern findings — deterministic */}
        {trace.pattern_findings && trace.pattern_findings.length > 0 && (
          <div className="flex flex-wrap items-center gap-2" data-testid="pattern-findings">
            <span className="text-body-xs text-wr-text-muted">Patterns:</span>
            {trace.pattern_findings.slice(0, 6).map((p, i) => (
              <span
                key={i}
                className={`px-2 py-0.5 rounded border text-body-xs ${severityClass(p.severity)}`}
                title={p.human_summary}
              >
                {patternLabel(p)}
              </span>
            ))}
          </div>
        )}

        {/* Mini waterfall thumbnail */}
        {trace.call_chain.length > 0 && (
          <MiniWaterfall spans={trace.call_chain} />
        )}

        {/* Handoff services */}
        {(trace.services_in_chain?.length ?? 0) > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 text-body-xs">
            <span className="text-wr-text-muted">Services:</span>
            {(trace.services_in_chain || []).slice(0, 8).map((s) => (
              <span
                key={s}
                className={`px-1.5 py-0.5 rounded border font-mono ${
                  s === failureSvc
                    ? 'border-red-500/40 bg-red-950/30 text-red-200'
                    : (trace.hot_services || []).includes(s)
                    ? 'border-orange-500/40 bg-orange-950/30 text-orange-200'
                    : 'border-wr-border text-wr-text-muted'
                }`}
              >
                {s}
              </span>
            ))}
            {(trace.services_in_chain || []).length > 8 && (
              <span className="text-wr-text-muted">+{(trace.services_in_chain || []).length - 8} more</span>
            )}
          </div>
        )}
      </article>

      {telescopeOpen && (
        <TraceTelescope
          trace={trace}
          backendUrl={backendUrl}
          onClose={() => setTelescopeOpen(false)}
        />
      )}
    </>
  );
}

// ── Helpers ─────────────────────────────────────────────────────────────

function buildConsensusLine(trace: TraceAnalysisResult): string {
  const failureSvc = trace.failure_point?.service_name ?? trace.failure_point?.service;
  const minedCount = trace.mined_trace_ids?.length ?? 0;
  const envoyFlag = trace.envoy_findings?.[0]?.flag;

  if (minedCount > 1 && trace.cross_trace_consensus === 'unanimous' && failureSvc) {
    return `${minedCount} of ${minedCount} mined traces agree — failure at ${failureSvc}${envoyFlag ? ` (${envoyFlag})` : ''}.`;
  }
  if (failureSvc && envoyFlag) {
    return `Failure at ${failureSvc}: ${trace.envoy_findings![0].human_summary}`;
  }
  if (failureSvc) {
    return `Failure at ${failureSvc}${trace.failure_point?.error_message ? ` — ${trace.failure_point.error_message.slice(0, 80)}` : ''}.`;
  }
  if (trace.total_spans === 0) {
    return trace.trace_source === 'elasticsearch'
      ? 'No trace data found in Jaeger/Tempo OR Elasticsearch.'
      : 'No trace data available for this trace ID.';
  }
  return `Traced ${trace.total_spans} spans across ${trace.total_services} services (${Math.round(trace.total_duration_ms)}ms total).`;
}

function provenanceFor(trace: TraceAnalysisResult): { label: string; cls: string } {
  switch (trace.trace_source) {
    case 'jaeger':
      return { label: 'Jaeger-native', cls: 'border-emerald-500/40 text-emerald-300 bg-emerald-500/10' };
    case 'tempo':
      return { label: 'Tempo-native', cls: 'border-emerald-500/40 text-emerald-300 bg-emerald-500/10' };
    case 'summarized':
      return {
        label: `Summarized (from ${trace.total_spans} spans)`,
        cls: 'border-wr-accent/50 text-wr-accent bg-wr-accent/10',
      };
    case 'elasticsearch': {
      const conf = trace.elk_reconstruction_confidence ?? 0;
      return {
        label: `ELK-reconstructed · ${conf}%`,
        cls: 'border-orange-500/40 text-orange-300 bg-orange-500/10',
      };
    }
    default:
      return { label: trace.trace_source, cls: 'border-wr-border text-wr-text-muted' };
  }
}

function tierLabelFor(tier: TraceAnalysisResult['tier_decision']): string | null {
  if (!tier) return null;
  const names = { 0: 'Tier 0 · no LLM', 1: 'Tier 1 · Haiku', 2: 'Tier 2 · Sonnet' } as const;
  return names[tier.tier];
}

function consensusClass(consensus: string): string {
  if (consensus === 'unanimous') return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300';
  if (consensus === 'majority') return 'border-wr-accent/50 bg-wr-accent/10 text-wr-accent';
  return 'border-orange-500/40 bg-orange-500/10 text-orange-300';
}

function severityClass(sev: string): string {
  switch (sev) {
    case 'critical': return 'border-red-500/50 bg-red-950/30 text-red-200';
    case 'high':     return 'border-orange-500/50 bg-orange-950/30 text-orange-200';
    case 'medium':   return 'border-wr-accent/50 bg-wr-accent/10 text-wr-accent';
    default:         return 'border-wr-border text-wr-text-muted';
  }
}

function patternLabel(p: PatternFinding): string {
  const kindLabels: Record<PatternKind, string> = {
    n_plus_one: 'N+1',
    fan_out_amplification: 'Fan-out',
    app_level_retry: 'Retry',
    critical_path_hotspot: 'Hotspot',
    baseline_latency_regression: 'Regression',
  };
  const base = kindLabels[p.kind] || p.kind;
  const meta = p.metadata || {};
  if (p.kind === 'fan_out_amplification' && typeof meta.amplification_factor === 'number') {
    return `${base} ${meta.amplification_factor}×`;
  }
  if (p.kind === 'n_plus_one' && typeof meta.child_count === 'number') {
    return `${base} ×${meta.child_count}`;
  }
  if (p.kind === 'app_level_retry' && typeof meta.attempts === 'number') {
    return `${base} ${meta.attempts}×${meta.all_failed ? ' all-fail' : ''}`;
  }
  if (p.kind === 'critical_path_hotspot' && typeof meta.fraction_of_trace === 'number') {
    return `${base} ${Math.round((meta.fraction_of_trace as number) * 100)}%`;
  }
  if (p.kind === 'baseline_latency_regression' && typeof meta.ratio === 'number') {
    return `${base} ${meta.ratio}×`;
  }
  return base;
}

// ── Mini waterfall thumbnail ────────────────────────────────────────────

function MiniWaterfall({ spans }: { spans: TraceAnalysisResult['call_chain'] }) {
  const showN = Math.min(spans.length, 8);
  const slice = spans.slice(0, showN);
  const maxDuration = Math.max(1, ...slice.map((s) => s.duration_ms));
  return (
    <div className="bg-wr-bg/40 rounded p-2 space-y-0.5" data-testid="mini-waterfall">
      {slice.map((s) => {
        const widthPct = Math.max((s.duration_ms / maxDuration) * 100, 2);
        const barColor =
          s.status === 'error' ? 'bg-red-500/70' :
          s.status === 'timeout' ? 'bg-orange-500/70' :
          s.critical_path ? 'bg-wr-accent/70' : 'bg-emerald-500/60';
        return (
          <div key={s.span_id} className="flex items-center gap-2">
            <span className="text-[10px] font-mono w-28 truncate text-wr-text-muted">
              {(s.service_name || s.service).slice(0, 14)}
            </span>
            <div className="flex-1 h-2 bg-wr-surface/50 rounded overflow-hidden">
              <div className={`h-full rounded ${barColor}`} style={{ width: `${widthPct}%` }} />
            </div>
          </div>
        );
      })}
      {spans.length > showN && (
        <p className="text-[10px] text-wr-text-muted text-right pt-1">
          +{spans.length - showN} more spans
        </p>
      )}
    </div>
  );
}
