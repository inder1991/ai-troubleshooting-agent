import React, { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { V4Session, DiagnosticPhase } from '../../types';
import { listSessionsV4 } from '../../services/api';
import { ActivityFeedRow, SectionHeader, TimeRangeSelector } from '../shared';
import type { SystemStatus } from '../shared';

interface LiveIntelligenceFeedProps {
  sessions: V4Session[];
  onSessionsChange: (sessions: V4Session[]) => void;
  onSelectSession: (session: V4Session) => void;
}

const phaseToStatus = (phase: DiagnosticPhase): { status: SystemStatus; label: string } => {
  if (['initial', 'collecting_context'].includes(phase)) return { status: 'in_progress', label: 'Collecting' };
  if (['logs_analyzed', 'metrics_analyzed', 'k8s_analyzed', 'tracing_analyzed', 'code_analyzed'].includes(phase)) return { status: 'in_progress', label: 'Analyzing' };
  if (['validating', 're_investigating'].includes(phase)) return { status: 'in_progress', label: 'Validating' };
  if (phase === 'fix_in_progress') return { status: 'degraded', label: 'Remediating' };
  if (['diagnosis_complete', 'complete'].includes(phase)) return { status: 'healthy', label: 'Resolved' };
  if (phase === 'error') return { status: 'critical', label: 'Error' };
  return { status: 'unknown', label: String(phase) };
};

const capabilityAgents = (cap?: string): string[] => {
  switch (cap) {
    case 'troubleshoot_app': return ['Log', 'Metric', 'Trace', 'Code'];
    case 'pr_review': return ['Code', 'Security'];
    case 'github_issue_fix': return ['Code', 'Patch'];
    case 'cluster_diagnostics': return ['Node', 'Network', 'Storage', 'CtrlPlane'];
    case 'network_troubleshooting': return ['Path', 'Firewall', 'NAT'];
    default: return ['Agent'];
  }
};

const computeDuration = (created: string, updated: string): string => {
  const ms = new Date(updated).getTime() - new Date(created).getTime();
  if (ms < 60000) return `${Math.round(ms / 1000)}s`;
  return `${Math.round(ms / 60000)}m`;
};

const LiveIntelligenceFeed: React.FC<LiveIntelligenceFeedProps> = ({
  onSessionsChange,
  onSelectSession,
}) => {
  const [timeRange, setTimeRange] = useState<string>('1h');

  const { data: sessions = [], isLoading, isError } = useQuery({
    queryKey: ['live-sessions'],
    queryFn: listSessionsV4,
    refetchInterval: 10000,
    staleTime: 5000,
  });

  useEffect(() => {
    onSessionsChange(sessions);
  }, [sessions, onSessionsChange]);

  return (
    <section>
      <SectionHeader
        title="Live Intelligence Feed"
        count={sessions.length}
        action={
          <TimeRangeSelector
            selected={timeRange}
            onChange={setTimeRange}
          />
        }
      >
        {isLoading && (
          <div className="w-3 h-3 border border-duck-accent border-t-transparent rounded-full animate-spin" />
        )}
      </SectionHeader>

      <div className="bg-duck-panel border border-duck-border rounded-xl overflow-hidden">
        <div className="max-h-[480px] overflow-y-auto custom-scrollbar">
          {isLoading && sessions.length === 0 ? (
            <div className="space-y-2 p-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-16 rounded-md bg-duck-surface animate-pulse" style={{ opacity: 1 - i * 0.3 }} />
              ))}
            </div>
          ) : isError && !isLoading ? (
            <div className="flex flex-col items-center justify-center h-64 text-center">
              <span className="material-symbols-outlined text-4xl text-red-500 mb-3" aria-hidden="true">wifi_off</span>
              <p className="text-sm font-semibold text-slate-300 mb-1">Feed Disconnected</p>
              <p className="text-xs text-slate-500">Failed to sync with the intelligence server. Retrying...</p>
            </div>
          ) : sessions.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-64 text-center">
              <div className="w-16 h-16 rounded-full bg-duck-border/30 flex items-center justify-center mb-4">
                <span className="material-symbols-outlined text-2xl text-duck-accent" aria-hidden="true">satellite_alt</span>
              </div>
              <p className="text-sm font-semibold text-slate-300 mb-1">No Active Sessions</p>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">Launch an investigation from Quick Actions to begin monitoring.</p>
            </div>
          ) : (
            sessions.slice(0, 15).map((session) => {
              const { status, label } = phaseToStatus(session.status);
              const agents = capabilityAgents(session.capability);
              const duration = computeDuration(session.created_at, session.updated_at);
              const timestamp = new Date(session.created_at).toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
              });

              return (
                <ActivityFeedRow
                  key={session.session_id}
                  targetService={session.service_name}
                  targetNamespace={session.capability || ''}
                  timestamp={timestamp}
                  status={status}
                  phase={label}
                  confidenceScore={Math.round(session.confidence)}
                  durationStr={duration}
                  activeAgents={agents}
                  onClick={() => onSelectSession(session)}
                />
              );
            })
          )}
        </div>
      </div>
    </section>
  );
};

export default LiveIntelligenceFeed;
