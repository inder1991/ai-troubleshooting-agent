import React from 'react';
import type { NetworkFindings } from '../../types';
import PathHopList from './PathHopList';
import NATChainDisplay from './NATChainDisplay';

interface DiagnosisPanelProps {
  findings: NetworkFindings;
  direction: 'forward' | 'return';
}

const STATUS_COLORS: Record<string, string> = {
  reachable: '#22c55e',
  blocked: '#ef4444',
  partial: '#f59e0b',
  unknown: '#64748b',
};

const DiagnosisPanel: React.FC<DiagnosisPanelProps> = ({ findings, direction }) => {
  const state = direction === 'return' && findings.return_state ? findings.return_state : findings.state;
  const status = state.diagnosis_status || 'unknown';
  const confidence = state.confidence ?? 0;
  const statusColor = STATUS_COLORS[status.toLowerCase()] || STATUS_COLORS.unknown;

  return (
    <div className="flex flex-col gap-4 h-full overflow-y-auto pr-1 custom-scrollbar">
      {/* Executive Summary */}
      <div
        className="rounded-lg p-4"
        style={{ backgroundColor: '#0f2023', border: '1px solid #224349' }}
      >
        <div
          className="text-xs font-mono uppercase tracking-wider mb-2"
          style={{ color: '#64748b' }}
        >
          Diagnosis
        </div>
        <div
          className="text-sm font-mono font-bold mb-2"
          style={{ color: statusColor }}
        >
          {status.toUpperCase()}
        </div>
        {state.executive_summary && (
          <p className="text-xs font-mono leading-relaxed" style={{ color: '#e2e8f0' }}>
            {state.executive_summary}
          </p>
        )}
      </div>

      {/* Confidence Meter */}
      <div
        className="rounded-lg p-4"
        style={{ backgroundColor: '#0f2023', border: '1px solid #224349' }}
      >
        <div className="flex items-center justify-between mb-2">
          <span
            className="text-xs font-mono uppercase tracking-wider"
            style={{ color: '#64748b' }}
          >
            Confidence
          </span>
          <span
            className="text-sm font-mono font-bold tabular-nums"
            style={{ color: '#07b6d5' }}
          >
            {Math.round(confidence * 100)}%
          </span>
        </div>
        <div
          className="h-2 rounded-full overflow-hidden"
          style={{ backgroundColor: '#1a3a3f' }}
        >
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{
              width: `${Math.round(confidence * 100)}%`,
              backgroundColor: '#07b6d5',
            }}
          />
        </div>
        {state.confidence_breakdown && (
          <div className="space-y-1.5 mt-3 pt-3" style={{ borderTop: '1px solid #1a3a3f' }}>
            {Object.entries(state.confidence_breakdown)
              .filter(([k]) => !['overall', 'penalties', 'path_source'].includes(k))
              .map(([key, val]) => (
                <div key={key} className="flex justify-between text-[11px] font-mono">
                  <span style={{ color: '#64748b' }}>{key.replace(/_/g, ' ')}</span>
                  <span style={{ color: '#94a3b8' }}>{(Number(val) * 100).toFixed(0)}%</span>
                </div>
              ))}
          </div>
        )}
      </div>

      {/* Path Hop List */}
      {state.trace_hops && state.trace_hops.length > 0 && (
        <div
          className="rounded-lg p-4"
          style={{ backgroundColor: '#0f2023', border: '1px solid #224349' }}
        >
          <PathHopList hops={state.trace_hops} />
        </div>
      )}

      {/* NAT Identity Chain */}
      {state.identity_chain && state.identity_chain.length > 0 && (
        <div
          className="rounded-lg p-4"
          style={{ backgroundColor: '#0f2023', border: '1px solid #224349' }}
        >
          <NATChainDisplay chain={state.identity_chain} />
        </div>
      )}

      {/* Next Steps */}
      {state.next_steps && state.next_steps.length > 0 && (
        <div
          className="rounded-lg p-4"
          style={{ backgroundColor: '#0f2023', border: '1px solid #224349' }}
        >
          <div
            className="text-xs font-mono uppercase tracking-wider mb-2"
            style={{ color: '#64748b' }}
          >
            Next Steps
          </div>
          <ul className="space-y-1.5">
            {state.next_steps.map((step, i) => (
              <li
                key={i}
                className="flex items-start gap-2 text-xs font-mono"
                style={{ color: '#e2e8f0' }}
              >
                <span style={{ color: '#07b6d5' }}>&#8227;</span>
                <span>{step}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Session Info */}
      <div
        className="rounded-lg p-4"
        style={{ backgroundColor: '#0f2023', border: '1px solid #224349' }}
      >
        <div
          className="text-xs font-mono uppercase tracking-wider mb-2"
          style={{ color: '#64748b' }}
        >
          Session
        </div>
        <div className="space-y-1 text-xs font-mono" style={{ color: '#94a3b8' }}>
          <div>
            <span style={{ color: '#64748b' }}>Flow ID: </span>
            <span className="break-all">{findings.flow_id}</span>
          </div>
          <div>
            <span style={{ color: '#64748b' }}>Session: </span>
            <span className="break-all">{findings.session_id}</span>
          </div>
          <div>
            <span style={{ color: '#64748b' }}>Phase: </span>
            <span>{findings.phase}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DiagnosisPanel;
