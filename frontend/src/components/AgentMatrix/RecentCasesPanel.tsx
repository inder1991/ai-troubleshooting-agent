import React from 'react';
import type { AgentExecution } from '../../types';

interface RecentCasesPanelProps {
  executions: AgentExecution[];
  isLoading: boolean;
}

const STATUS_STYLES: Record<string, { color: string; bg: string }> = {
  SUCCESS: { color: '#22c55e', bg: 'rgba(34,197,94,0.1)' },
  FAILED: { color: '#ef4444', bg: 'rgba(239,68,68,0.1)' },
  TIMEOUT: { color: '#f59e0b', bg: 'rgba(245,158,11,0.1)' },
  RUNNING: { color: '#e09f3e', bg: 'rgba(224,159,62,0.1)' },
};

function relativeTime(ts: string): string {
  const now = Date.now();
  const then = new Date(ts).getTime();
  const diffMs = now - then;

  if (diffMs < 60000) return 'just now';
  if (diffMs < 3600000) return `${Math.floor(diffMs / 60000)}m ago`;
  if (diffMs < 86400000) return `${Math.floor(diffMs / 3600000)}h ago`;
  return `${Math.floor(diffMs / 86400000)}d ago`;
}

const RecentCasesPanel: React.FC<RecentCasesPanelProps> = ({ executions, isLoading }) => {
  const cases = executions.slice(0, 5);

  return (
    <div className="rounded-lg border p-4" style={{ backgroundColor: '#0a1214', borderColor: '#3d3528' }}>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-mono uppercase tracking-widest" style={{ color: '#64748b' }}>
          Recent Cases
        </h3>
        <span className="text-[10px] font-mono" style={{ color: '#475569' }}>
          Last {cases.length} executions
        </span>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 py-6 justify-center">
          <div
            className="w-4 h-4 rounded-full border-2 border-t-transparent animate-spin"
            style={{ borderColor: '#e09f3e', borderTopColor: 'transparent' }}
          />
          <span className="text-xs font-mono" style={{ color: '#475569' }}>Loading cases...</span>
        </div>
      )}

      {!isLoading && cases.length === 0 && (
        <div className="flex flex-col items-center gap-2 py-6">
          <span
            className="material-symbols-outlined text-2xl"
            style={{ color: '#1e3a3e' }}
          >
            folder_off
          </span>
          <span className="text-xs font-mono" style={{ color: '#475569' }}>No recent executions</span>
        </div>
      )}

      {!isLoading && cases.length > 0 && (
        <div className="flex flex-col gap-2">
          {cases.map((exec, i) => {
            const style = STATUS_STYLES[exec.status.toUpperCase()] ?? STATUS_STYLES.RUNNING;
            return (
              <div
                key={`${exec.session_id}-${i}`}
                className="flex items-start gap-3 rounded-lg px-3 py-2.5 border"
                style={{ backgroundColor: '#1e1b15', borderColor: '#1e3a3e' }}
              >
                {/* Status badge */}
                <span
                  className="text-[9px] font-mono font-semibold uppercase px-1.5 py-0.5 rounded flex-shrink-0 mt-0.5"
                  style={{ color: style.color, backgroundColor: style.bg }}
                >
                  {exec.status}
                </span>

                {/* Summary + metadata */}
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-slate-300 truncate">{exec.summary}</p>
                  <div className="flex items-center gap-3 mt-1">
                    <span className="text-[10px] font-mono" style={{ color: '#475569' }}>
                      {exec.duration_ms}ms
                    </span>
                    {exec.confidence > 0 && (
                      <span className="text-[10px] font-mono" style={{ color: '#475569' }}>
                        conf: {(exec.confidence * 100).toFixed(0)}%
                      </span>
                    )}
                    <span className="text-[10px] font-mono" style={{ color: '#374151' }}>
                      {relativeTime(exec.timestamp)}
                    </span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default RecentCasesPanel;
