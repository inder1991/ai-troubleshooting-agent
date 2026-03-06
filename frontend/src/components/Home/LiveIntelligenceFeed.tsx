import React, { useEffect, useState } from 'react';
import type { V4Session, DiagnosticPhase } from '../../types';
import { listSessionsV4 } from '../../services/api';
import { ActivityFeedRow, SectionHeader, TimeRangeSelector, SkeletonLoader } from '../shared';
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
  sessions,
  onSessionsChange,
  onSelectSession,
}) => {
  const [loading, setLoading] = useState(false);
  const [timeRange, setTimeRange] = useState<string>('1h');

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const data = await listSessionsV4();
        onSessionsChange(data);
      } catch {
        // silently fail
      } finally {
        setLoading(false);
      }
    };
    load();
    const interval = setInterval(load, 10000);
    return () => clearInterval(interval);
  }, [onSessionsChange]);

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
        {loading && (
          <div className="w-3 h-3 border border-[#07b6d5] border-t-transparent rounded-full animate-spin" />
        )}
      </SectionHeader>

      <div className="bg-[#0a1517] border border-[#224349] rounded-xl overflow-hidden">
        <div className="max-h-[480px] overflow-y-auto custom-scrollbar">
          {loading && sessions.length === 0 ? (
            <div className="flex flex-col gap-1 p-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <SkeletonLoader key={i} type="row" height="h-16" />
              ))}
            </div>
          ) : sessions.length === 0 ? (
            <div className="flex items-center justify-center py-20 text-slate-500">
              <div className="text-center max-w-xs">
                <span
                  className="material-symbols-outlined text-4xl text-slate-600 mb-3 block"
                  style={{ fontFamily: 'Material Symbols Outlined' }}
                >
                  satellite_alt
                </span>
                <p className="text-sm font-semibold text-slate-400 mb-1">No Active Sessions</p>
                <p className="text-xs text-slate-600 leading-relaxed">
                  Launch an investigation, PR review, or cluster scan from Quick Actions to begin monitoring.
                </p>
              </div>
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
