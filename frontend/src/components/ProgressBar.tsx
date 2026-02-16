import React from 'react';
import { Radar, Brain, Wrench } from 'lucide-react';
import type { DiagnosticPhase, TokenUsage } from '../types';

interface ProgressBarProps {
  phase: DiagnosticPhase | null;
  confidence: number;
  tokenUsage: TokenUsage[];
  wsConnected: boolean;
}

const phases: {
  id: string;
  label: string;
  icon: typeof Radar;
  matchPhases: DiagnosticPhase[];
}[] = [
  {
    id: 'detection',
    label: 'DETECTION',
    icon: Radar,
    matchPhases: ['initial', 'collecting_context', 'logs_analyzed', 'metrics_analyzed'],
  },
  {
    id: 'analysis',
    label: 'ANALYSIS',
    icon: Brain,
    matchPhases: ['k8s_analyzed', 'tracing_analyzed', 'code_analyzed', 'validating', 're_investigating'],
  },
  {
    id: 'mitigation',
    label: 'MITIGATION',
    icon: Wrench,
    matchPhases: ['diagnosis_complete', 'fix_in_progress', 'complete'],
  },
];

const getActivePhaseIndex = (phase: DiagnosticPhase | null): number => {
  if (!phase) return -1;
  return phases.findIndex((p) => p.matchPhases.includes(phase));
};

const ProgressBar: React.FC<ProgressBarProps> = ({
  phase,
  confidence,
  tokenUsage,
  wsConnected,
}) => {
  const activeIdx = getActivePhaseIndex(phase);
  const totalTokens = (tokenUsage || []).reduce((sum, t) => sum + t.total_tokens, 0);
  const confidencePercent = Math.round(confidence * 100);

  return (
    <div className="h-12 bg-[#1e2f33]/80 border-t border-[#224349] flex items-center px-4 gap-6">
      {/* Connection indicator */}
      <div className="flex items-center gap-1.5">
        <span
          className={`w-1.5 h-1.5 rounded-full ${
            wsConnected ? 'bg-green-400 animate-pulse' : 'bg-red-400'
          }`}
        />
        <span className="text-[10px] text-gray-500 uppercase tracking-wider">
          {wsConnected ? 'Live' : 'Offline'}
        </span>
      </div>

      {/* Phase steps */}
      <div className="flex items-center gap-1 flex-1">
        {phases.map((p, idx) => {
          const Icon = p.icon;
          const isActive = idx === activeIdx;
          const isComplete = idx < activeIdx;
          const isPending = idx > activeIdx;

          return (
            <React.Fragment key={p.id}>
              {idx > 0 && (
                <div
                  className={`w-8 h-px mx-1 ${
                    isComplete ? 'bg-[#07b6d5]' : 'bg-[#224349]'
                  }`}
                />
              )}
              <div
                className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                  isActive
                    ? 'bg-[#07b6d5]/10 text-[#07b6d5] border border-[#07b6d5]/20'
                    : isComplete
                    ? 'text-[#07b6d5]/70'
                    : isPending
                    ? 'text-gray-600'
                    : 'text-gray-500'
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                <span>{p.label}</span>
                {isActive && (
                  <span className="w-1.5 h-1.5 rounded-full bg-[#07b6d5] animate-pulse ml-0.5" />
                )}
              </div>
            </React.Fragment>
          );
        })}
      </div>

      {/* Confidence */}
      {confidence > 0 && (
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-gray-500 uppercase tracking-wider">Confidence</span>
          <div className="w-16 h-1.5 bg-[#224349] rounded-full overflow-hidden">
            <div
              className="h-full bg-[#07b6d5] rounded-full transition-all duration-500"
              style={{ width: `${confidencePercent}%` }}
            />
          </div>
          <span className="text-xs text-[#07b6d5] font-mono font-medium w-8">
            {confidencePercent}%
          </span>
        </div>
      )}

      {/* Token count */}
      {totalTokens > 0 && (
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] text-gray-500 uppercase tracking-wider">Tokens</span>
          <span className="text-xs text-gray-300 font-mono">
            {totalTokens.toLocaleString()}
          </span>
        </div>
      )}
    </div>
  );
};

export default ProgressBar;
