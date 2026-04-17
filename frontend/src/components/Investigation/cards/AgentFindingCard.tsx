import React from 'react';

type AgentCode = 'L' | 'M' | 'K' | 'C' | 'D';

const agentStyles: Record<AgentCode, { border: string; bg: string; label: string }> = {
  L: { border: 'card-border-L', bg: 'bg-wr-severity-high/10', label: 'Log Analyzer' },
  M: { border: 'card-border-M', bg: 'bg-wr-severity-medium/10', label: 'Metric Scanner' },
  K: { border: 'card-border-K', bg: 'bg-orange-500/10', label: 'K8s Probe' },
  C: { border: 'card-border-C', bg: 'bg-emerald-500/10', label: 'Change Intel' },
  D: { border: 'card-border-D', bg: 'bg-blue-500/10', label: 'Code Navigator' },
};

const badgeColor: Record<AgentCode, string> = {
  L: 'bg-red-500 text-white',
  M: 'bg-amber-500 text-white',
  K: 'bg-orange-500 text-white',
  C: 'bg-emerald-500 text-white',
  D: 'bg-blue-500 text-white',
};

export interface SignatureMatchDecoration {
  pattern_name: string;
  matched_at_ms: number;
}

export interface AgentFindingCardProps {
  agent: AgentCode;
  title: string;
  children: React.ReactNode;
  /** Phase 4, Task 4.15 — optional baseline + signature decorations. */
  baselineValue?: number | null;
  baselineDeltaPct?: number | null;
  signatureMatch?: SignatureMatchDecoration | null;
  /** Task 4.16 — per-card dissent indicator. */
  criticDissent?: CriticDissentIndicator | null;
}

export interface CriticDissentIndicator {
  advocate_verdict: 'confirmed' | 'challenged' | 'insufficient_evidence';
  challenger_verdict: 'confirmed' | 'challenged' | 'insufficient_evidence';
  judge_verdict: 'confirmed' | 'challenged' | 'needs_more_evidence';
  summary?: string;
}

function hasDissent(d: CriticDissentIndicator | null | undefined): boolean {
  if (!d) return false;
  return !(
    d.advocate_verdict === d.challenger_verdict &&
    d.advocate_verdict === d.judge_verdict
  );
}

function baselineTone(deltaPct: number): string {
  const abs = Math.abs(deltaPct);
  if (abs < 15) return 'text-wr-emerald';
  if (abs < 50) return 'text-wr-amber';
  return 'text-wr-red';
}

const AgentFindingCard: React.FC<AgentFindingCardProps> = ({
  agent,
  title,
  children,
  baselineValue,
  baselineDeltaPct,
  signatureMatch,
  criticDissent,
}) => {
  const style = agentStyles[agent];
  const showBaseline =
    baselineValue !== undefined &&
    baselineValue !== null &&
    baselineDeltaPct !== undefined &&
    baselineDeltaPct !== null;
  const dissent = hasDissent(criticDissent);

  return (
    <div className={`${style.border} ${style.bg} rounded-lg overflow-hidden`}>
      <div className="px-4 py-2.5 flex items-center gap-2">
        <span
          className={`w-6 h-6 rounded-full flex items-center justify-center text-body-xs font-bold ${badgeColor[agent]}`}
        >
          {agent}
        </span>
        <span className="text-body-xs text-slate-400 uppercase tracking-wider">
          {style.label}
        </span>
        <span className="text-xs font-medium text-slate-200 ml-1 flex-1 min-w-0 truncate">
          {title}
        </span>
        {dissent && (
          <span
            data-testid="critic-dissent-icon"
            aria-label="critic disagreement"
            className="inline-flex items-center text-wr-amber text-body-xs"
            title={criticDissent?.summary || 'Advocate and challenger disagreed'}
          >
            <span
              className="material-symbols-outlined"
              style={{ fontFamily: 'Material Symbols Outlined', fontSize: '14px' }}
            >
              alt_route
            </span>
          </span>
        )}
        {signatureMatch && (
          <span
            data-testid="signature-match-pill"
            className="inline-flex items-center gap-1 rounded-full border border-wr-amber/40 bg-wr-amber/10 px-2 py-0.5 text-body-xs text-wr-amber font-mono"
            title={`Signature library matched at ${signatureMatch.matched_at_ms}ms`}
          >
            <span
              className="material-symbols-outlined"
              style={{ fontFamily: 'Material Symbols Outlined', fontSize: '12px' }}
              aria-hidden
            >
              fingerprint
            </span>
            Pattern: {signatureMatch.pattern_name} · {(signatureMatch.matched_at_ms / 1000).toFixed(1)}s
          </span>
        )}
      </div>
      {showBaseline && (
        <div
          data-testid="baseline-strip"
          className={`px-4 pb-1.5 text-body-xs font-mono ${baselineTone(baselineDeltaPct!)}`}
        >
          {baselineDeltaPct! >= 0 ? '+' : ''}
          {baselineDeltaPct}% vs 24h baseline (was {baselineValue})
        </div>
      )}
      <div className="px-4 pb-3">{children}</div>
    </div>
  );
};

export default AgentFindingCard;
