import React from 'react';
import type { DiagnosticPhase, TokenUsage } from '../types';

interface StatusBarProps {
  phase: DiagnosticPhase | null;
  confidence: number;
  tokenUsage: TokenUsage[];
  wsConnected: boolean;
}

const phaseLabel = (phase: DiagnosticPhase): string => {
  return phase.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
};

const phaseColor = (phase: DiagnosticPhase): string => {
  const colors: Record<DiagnosticPhase, string> = {
    initial: 'text-gray-400',
    collecting_context: 'text-blue-400',
    logs_analyzed: 'text-blue-300',
    metrics_analyzed: 'text-blue-300',
    k8s_analyzed: 'text-blue-300',
    tracing_analyzed: 'text-blue-300',
    code_analyzed: 'text-blue-300',
    validating: 'text-yellow-400',
    re_investigating: 'text-orange-400',
    diagnosis_complete: 'text-green-400',
    fix_in_progress: 'text-purple-400',
    complete: 'text-green-500',
    error: 'text-red-500',
  };
  return colors[phase];
};

const StatusBar: React.FC<StatusBarProps> = ({
  phase,
  confidence,
  tokenUsage,
  wsConnected,
}) => {
  const totalTokens = tokenUsage.reduce((sum, t) => sum + t.total_tokens, 0);
  const confidencePercent = Math.round(confidence * 100);

  return (
    <div className="h-8 bg-gray-900 border-t border-gray-700 flex items-center px-4 gap-6 text-xs">
      {/* WebSocket status */}
      <div className="flex items-center gap-1.5">
        <span
          className={`w-2 h-2 rounded-full ${wsConnected ? 'bg-green-500' : 'bg-red-500'}`}
        />
        <span className="text-gray-500">
          {wsConnected ? 'Connected' : 'Disconnected'}
        </span>
      </div>

      {/* Phase */}
      {phase && (
        <div className="flex items-center gap-1.5">
          <span className="text-gray-500">Phase:</span>
          <span className={`font-medium ${phaseColor(phase)}`}>
            {phaseLabel(phase)}
          </span>
        </div>
      )}

      {/* Confidence */}
      {confidence > 0 && (
        <div className="flex items-center gap-1.5">
          <span className="text-gray-500">Confidence:</span>
          <span
            className={`font-medium ${
              confidencePercent >= 80
                ? 'text-green-400'
                : confidencePercent >= 50
                ? 'text-yellow-400'
                : 'text-red-400'
            }`}
          >
            {confidencePercent}%
          </span>
        </div>
      )}

      {/* Tokens */}
      {totalTokens > 0 && (
        <div className="flex items-center gap-1.5 ml-auto">
          <span className="text-gray-500">Tokens:</span>
          <span className="text-gray-300 font-mono">{totalTokens.toLocaleString()}</span>
        </div>
      )}
    </div>
  );
};

export default StatusBar;
