import React from 'react';
import type { ClusterDomainReport } from '../../types';

interface ExecutionProgressProps {
  domainReports: ClusterDomainReport[];
  phase: string;
}

const DOMAIN_COLORS: Record<string, string> = {
  ctrl_plane: '#f59e0b',
  node:       '#e09f3e',
  network:    '#10b981',
  storage:    '#8b5cf6',
  rbac:       '#ef4444',
};

const ALL_DOMAINS = ['ctrl_plane', 'node', 'network', 'storage', 'rbac'];

type PhaseStatus = 'pending' | 'running' | 'complete' | 'failed';

interface PhaseInfo {
  label: string;
  status: PhaseStatus;
  detail?: string;
}

function statusIcon(status: PhaseStatus): React.ReactNode {
  switch (status) {
    case 'complete':
      return <span className="text-emerald-500 text-[11px]">&#10003;</span>;
    case 'failed':
      return <span className="text-red-500 text-[11px]">&#10007;</span>;
    case 'running':
      return <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse inline-block" />;
    default:
      return <span className="w-1.5 h-1.5 rounded-full bg-slate-600 inline-block" />;
  }
}

const ExecutionProgress: React.FC<ExecutionProgressProps> = ({ domainReports, phase }) => {
  const agentsDone = domainReports.filter(
    r => r.status === 'SUCCESS' || r.status === 'PARTIAL' || r.status === 'FAILED',
  ).length;
  const anyRunning = domainReports.some(r => r.status === 'RUNNING');
  const anyFailed = domainReports.some(r => r.status === 'FAILED');
  const totalAgents = Math.max(domainReports.filter(r => r.status !== 'SKIPPED').length, ALL_DOMAINS.length);
  const maxDuration = Math.max(...domainReports.map(r => r.duration_ms || 0), 1);

  const phases: PhaseInfo[] = [
    {
      label: 'Pre-processing',
      status: phase === 'pre_flight' ? 'running' : 'complete',
    },
    {
      label: `Domain Agents (${agentsDone}/${totalAgents})`,
      status:
        agentsDone >= totalAgents
          ? anyFailed ? 'failed' : 'complete'
          : anyRunning || agentsDone > 0
            ? 'running'
            : 'pending',
    },
    {
      label: 'Intelligence + Synthesis',
      status:
        phase === 'complete'
          ? 'complete'
          : agentsDone >= totalAgents
            ? 'running'
            : 'pending',
    },
  ];

  return (
    <div className="bg-[#141210] rounded border border-[#2a2520] p-3 max-h-[220px] overflow-hidden">
      <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Execution Progress</span>

      <div className="mt-3 space-y-3">
        {phases.map((p, idx) => {
          const isAgentPhase = idx === 1;
          return (
            <div key={p.label}>
              {/* Phase row */}
              <div className="flex items-center gap-2">
                {statusIcon(p.status)}
                <span className={`text-[11px] font-mono flex-1 ${p.status === 'running' ? 'text-amber-400' : p.status === 'complete' ? 'text-slate-300' : 'text-slate-400'}`}>
                  {p.label}
                </span>
              </div>

              {/* Domain agent mini bars */}
              {isAgentPhase && (
                <div className="mt-1.5 ml-4 flex items-end gap-1">
                  {ALL_DOMAINS.map(domain => {
                    const report = domainReports.find(r => r.domain === domain);
                    const color = DOMAIN_COLORS[domain] || '#94a3b8';
                    const pct = report && maxDuration > 0
                      ? Math.max(((report.duration_ms || 0) / maxDuration) * 100, 4)
                      : 4;
                    const isRunning = report?.status === 'RUNNING' || report?.status === 'PENDING';
                    const isFailed = report?.status === 'FAILED';
                    const isDone = report?.status === 'SUCCESS' || report?.status === 'PARTIAL';

                    return (
                      <div key={domain} className="flex flex-col items-center gap-0.5" style={{ width: '16%' }}>
                        <div className="w-full h-[28px] bg-[#1a1814] rounded-sm relative overflow-hidden">
                          <div
                            className={`absolute bottom-0 left-0 right-0 rounded-sm transition-all duration-500 ${isRunning ? 'animate-pulse' : ''}`}
                            style={{
                              height: `${pct}%`,
                              backgroundColor: color,
                              opacity: isFailed ? 0.35 : isDone ? 0.8 : 0.25,
                            }}
                          />
                        </div>
                        <span className="text-[10px] text-slate-400 font-mono truncate w-full text-center">
                          {domain.replace('_', ' ').slice(0, 4)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Connector line between phases */}
              {idx < phases.length - 1 && (
                <div className="ml-[3px] h-2 border-l border-dashed border-[#2a2520]" />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default ExecutionProgress;
