import React from 'react';
import * as Tooltip from '@radix-ui/react-tooltip';
import type {
  DiagnosticPhase,
  TokenUsage,
  BudgetTelemetry,
  SelfConsistencySummary,
  V4Findings,
} from '../../types';
import { BudgetPill } from './BudgetPill';
import { SelfConsistencyBadge } from './SelfConsistencyBadge';

interface RemediationProgressBarProps {
  phase: DiagnosticPhase | null;
  confidence: number;
  tokenUsage: TokenUsage[];
  wsConnected: boolean;
  // Relocated from Investigator.tsx in PR 4 — session-wide telemetry
  // belongs in the session-wide footer, not the left panel.
  budget?: BudgetTelemetry | null;
  selfConsistency?: SelfConsistencySummary | null;
  /** PR-B — findings for the Resolve Incident button's enablement
   *  gate. Button is visible-but-disabled when no remediation plan
   *  is ready; educates the user via tooltip rather than hiding. */
  findings?: V4Findings | null;
  /** PR-B — optional click handler. When absent, the button is
   *  clickable-but-noop; wired in PR-B via InvestigationView. */
  onResolve?: () => void;
}

function deriveResolveState(
  phase: DiagnosticPhase | null,
  findings: V4Findings | null | undefined,
): { canResolve: boolean; tooltip: string } {
  const hasFix = Boolean(
    findings?.root_cause_location ||
      (findings?.diff_analysis && findings.diff_analysis.length > 0) ||
      (findings?.suggested_fix_areas && findings.suggested_fix_areas.length > 0),
  );
  if (hasFix && (phase === 'diagnosis_complete' || phase === 'complete')) {
    return { canResolve: true, tooltip: 'Apply remediation and mark incident resolved.' };
  }
  if (phase === 'cancelled') {
    return {
      canResolve: false,
      tooltip: 'Investigation was cancelled. Re-run to propose a remediation.',
    };
  }
  if (phase === 'error') {
    return {
      canResolve: false,
      tooltip: 'Investigation errored out. Check logs before proposing a fix.',
    };
  }
  if (phase === 'logs_analyzed' || phase === 'metrics_analyzed' || phase === 'k8s_analyzed') {
    return {
      canResolve: false,
      tooltip: 'Waiting for agents to propose a remediation plan.',
    };
  }
  return {
    canResolve: false,
    tooltip: 'A remediation plan will appear here once the diagnosis completes.',
  };
}

interface StepDef {
  id: string;
  label: string;
  icon: string;
  matchPhases: DiagnosticPhase[];
}

const steps: StepDef[] = [
  {
    id: 'detection',
    label: 'Detection',
    icon: 'radar',
    matchPhases: ['initial', 'collecting_context'],
  },
  {
    id: 'analysis',
    label: 'Analysis',
    icon: 'analytics',
    matchPhases: ['logs_analyzed', 'metrics_analyzed', 'k8s_analyzed', 'tracing_analyzed', 'code_analyzed'],
  },
  {
    id: 'mitigation',
    label: 'Mitigation',
    icon: 'engineering',
    matchPhases: ['validating', 're_investigating', 'diagnosis_complete'],
  },
  {
    id: 'verification',
    label: 'Verification',
    icon: 'verified',
    matchPhases: ['fix_in_progress', 'complete'],
  },
];

const getActiveStepIndex = (phase: DiagnosticPhase | null): number => {
  if (!phase) return 0;
  const idx = steps.findIndex((s) => s.matchPhases.includes(phase));
  return idx >= 0 ? idx : 0;
};

const RemediationProgressBar: React.FC<RemediationProgressBarProps> = ({
  phase,
  confidence,
  tokenUsage,
  wsConnected: _wsConnected,
  budget = null,
  selfConsistency = null,
  findings = null,
  onResolve,
}) => {
  const { canResolve, tooltip: resolveTooltip } = deriveResolveState(phase, findings);
  const activeIdx = getActiveStepIndex(phase);
  const totalTokens = (tokenUsage || []).reduce((sum, t) => sum + t.total_tokens, 0);
  const progressPercent = steps.length > 1 ? Math.round((activeIdx / (steps.length - 1)) * 100) : 0;

  return (
    <footer className="h-20 border-t border-[#e09f3e]/20 bg-slate-950 px-8 flex items-center shrink-0">
      <div className="flex-1 flex items-center gap-12">
        {/* Progress Tracker */}
        <div className="flex-1 flex items-center relative">
          {/* Background connector line */}
          <div className="absolute left-0 right-0 top-1/2 -translate-y-1/2 h-1 bg-wr-surface -z-10" />
          {/* Active connector line */}
          <div
            className="absolute left-0 top-1/2 -translate-y-1/2 h-1 bg-[#e09f3e] -z-10 transition-all duration-700"
            style={{ width: `${progressPercent}%` }}
          />

          <div className="flex items-center justify-between w-full">
            {steps.map((step, idx) => {
              const isComplete = idx < activeIdx;
              const isActive = idx === activeIdx;
              const isPending = idx > activeIdx;

              return (
                <div key={step.id} className="flex flex-col items-center gap-2 bg-slate-950 px-3">
                  <div
                    className={`w-8 h-8 rounded-full flex items-center justify-center text-white transition-all ${
                      isComplete
                        ? 'bg-[#e09f3e] ring-4 ring-[#e09f3e]/20'
                        : isActive
                        ? 'bg-[#e09f3e] ring-4 ring-[#e09f3e]/40 animate-pulse'
                        : 'bg-wr-surface text-slate-400'
                    }`}
                    aria-label={`${step.label}: ${isComplete ? 'complete' : isActive ? 'in progress' : 'pending'}`}
                    title={`${step.label}: ${isComplete ? 'Complete' : isActive ? 'In Progress' : 'Pending'}`}
                  >
                    <span
                      className="material-symbols-outlined text-sm"
                      style={{ fontFamily: 'Material Symbols Outlined' }}
                    >
                      {isComplete ? 'check' : step.icon}
                    </span>
                  </div>
                  <span
                    className={`text-body-xs font-bold uppercase tracking-widest ${
                      isPending ? 'text-slate-400' : 'text-[#e09f3e]'
                    }`}
                  >
                    {step.label}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Session-wide telemetry (relocated from left panel in PR 4).
            Rendered only when the backend emits them — never placeholders. */}
        {(budget || selfConsistency) && (
          <div
            className="shrink-0 flex items-center gap-2 pl-8 border-l border-wr-border"
            data-testid="session-telemetry"
          >
            {budget && (
              <BudgetPill
                toolCalls={{
                  used: budget.tool_calls_used,
                  max: budget.tool_calls_max,
                }}
                llmUsd={{
                  used: budget.llm_usd_used,
                  max: budget.llm_usd_max,
                }}
              />
            )}
            {selfConsistency && (
              <SelfConsistencyBadge
                nRuns={selfConsistency.n_runs}
                agreedCount={selfConsistency.agreed_count}
                penaltyPct={selfConsistency.penalty_pct}
              />
            )}
          </div>
        )}

        {/* Right section: Resolution CTA - matches reference */}
        <div className="shrink-0 flex items-center gap-4 pl-8 border-l border-wr-border">
          {/* Est. Resolution */}
          <div className="text-right">
            <div className="text-body-xs text-slate-400 font-bold uppercase tracking-widest">Fix Confidence</div>
            <div className="text-sm font-mono text-slate-300">
              {confidence > 0 ? `${Math.round(confidence)}%` : '--'}
            </div>
          </div>

          {/* PR-B — Resolve button. Always rendered to avoid button-
              blindness; disabled when no remediation plan is ready,
              with a phase-aware tooltip educating the user on the
              workflow. Keyboard-reachable regardless of disabled state. */}
          <Tooltip.Provider>
            <Tooltip.Root>
              <Tooltip.Trigger asChild>
                <button
                  onClick={canResolve && onResolve ? onResolve : undefined}
                  disabled={!canResolve}
                  aria-label={resolveTooltip}
                  className={
                    'px-6 py-2.5 rounded-lg font-bold text-xs uppercase tracking-wider flex items-center gap-2 transition-all ' +
                    (canResolve
                      ? 'bg-primary hover:bg-primary/90 text-white shadow-lg shadow-primary/20 cursor-pointer'
                      : 'bg-wr-surface text-slate-400 cursor-not-allowed opacity-60')
                  }
                  data-testid="resolve-incident-btn"
                >
                  <span
                    className="material-symbols-outlined text-sm"
                    style={{ fontFamily: 'Material Symbols Outlined' }}
                  >
                    task_alt
                  </span>
                  Resolve Incident
                </button>
              </Tooltip.Trigger>
              <Tooltip.Portal>
                <Tooltip.Content
                  side="top"
                  sideOffset={6}
                  className="bg-wr-bg border border-wr-border rounded px-2 py-1 text-[11px] text-wr-paper max-w-[240px]"
                  style={{ zIndex: 'var(--z-tooltip)' }}
                  data-testid="resolve-incident-tooltip"
                >
                  {resolveTooltip}
                  <Tooltip.Arrow className="fill-wr-border" />
                </Tooltip.Content>
              </Tooltip.Portal>
            </Tooltip.Root>
          </Tooltip.Provider>
        </div>
      </div>
    </footer>
  );
};

export default RemediationProgressBar;
