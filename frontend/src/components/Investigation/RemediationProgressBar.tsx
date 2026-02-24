import React from 'react';
import type { DiagnosticPhase, TokenUsage } from '../../types';

interface RemediationProgressBarProps {
  phase: DiagnosticPhase | null;
  confidence: number;
  tokenUsage: TokenUsage[];
  wsConnected: boolean;
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
  wsConnected,
}) => {
  const activeIdx = getActiveStepIndex(phase);
  const totalTokens = (tokenUsage || []).reduce((sum, t) => sum + t.total_tokens, 0);
  const progressPercent = steps.length > 1 ? Math.round((activeIdx / (steps.length - 1)) * 100) : 0;

  return (
    <footer className="h-20 border-t border-[#07b6d5]/20 bg-slate-950 px-8 flex items-center shrink-0">
      <div className="flex-1 flex items-center gap-12">
        {/* Progress Tracker */}
        <div className="flex-1 flex items-center relative">
          {/* Background connector line */}
          <div className="absolute left-0 right-0 top-1/2 -translate-y-1/2 h-1 bg-slate-800 -z-10" />
          {/* Active connector line */}
          <div
            className="absolute left-0 top-1/2 -translate-y-1/2 h-1 bg-[#07b6d5] -z-10 transition-all duration-700"
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
                        ? 'bg-[#07b6d5] ring-4 ring-[#07b6d5]/20'
                        : isActive
                        ? 'bg-[#07b6d5] ring-4 ring-[#07b6d5]/40 animate-pulse'
                        : 'bg-slate-800 text-slate-500'
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
                    className={`text-[10px] font-bold uppercase tracking-widest ${
                      isPending ? 'text-slate-500' : 'text-[#07b6d5]'
                    }`}
                  >
                    {step.label}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right section: Resolution CTA - matches reference */}
        <div className="shrink-0 flex items-center gap-4 pl-8 border-l border-slate-800">
          {/* Est. Resolution */}
          <div className="text-right">
            <div className="text-[10px] text-slate-500 font-bold uppercase tracking-widest">Fix Confidence</div>
            <div className="text-sm font-mono text-slate-300">
              {confidence > 0 ? `${Math.round(confidence)}%` : '--'}
            </div>
          </div>

          {/* Resolve button */}
          <button className="bg-primary hover:bg-primary/90 text-white px-6 py-2.5 rounded-lg font-bold text-xs uppercase tracking-wider flex items-center gap-2 transition-all shadow-lg shadow-primary/20">
            <span
              className="material-symbols-outlined text-sm"
              style={{ fontFamily: 'Material Symbols Outlined' }}
            >
              task_alt
            </span>
            Resolve Incident
          </button>
        </div>
      </div>
    </footer>
  );
};

export default RemediationProgressBar;
