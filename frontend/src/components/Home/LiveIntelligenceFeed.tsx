import React, { useEffect, useState } from 'react';
import type { V4Session, DiagnosticPhase } from '../../types';
import { listSessionsV4 } from '../../services/api';

interface LiveIntelligenceFeedProps {
  sessions: V4Session[];
  onSessionsChange: (sessions: V4Session[]) => void;
  onSelectSession: (session: V4Session) => void;
}

const statusConfig = (phase: DiagnosticPhase): {
  label: string;
  dotColor: string;
  textColor: string;
  bgColor: string;
  borderColor: string;
  animate: boolean;
} => {
  switch (phase) {
    case 'initial':
    case 'collecting_context':
      return {
        label: 'Analyzing',
        dotColor: 'bg-[#07b6d5]',
        textColor: 'text-[#07b6d5]',
        bgColor: 'bg-[#07b6d5]/10',
        borderColor: 'border-[#07b6d5]/20',
        animate: true,
      };
    case 'logs_analyzed':
    case 'metrics_analyzed':
    case 'k8s_analyzed':
    case 'tracing_analyzed':
    case 'code_analyzed':
      return {
        label: 'Analyzing',
        dotColor: 'bg-indigo-400',
        textColor: 'text-indigo-400',
        bgColor: 'bg-indigo-500/10',
        borderColor: 'border-indigo-500/20',
        animate: true,
      };
    case 'validating':
    case 're_investigating':
      return {
        label: 'Remediating',
        dotColor: 'bg-[#07b6d5]',
        textColor: 'text-[#07b6d5]',
        bgColor: 'bg-[#07b6d5]/10',
        borderColor: 'border-[#07b6d5]/20',
        animate: true,
      };
    case 'fix_in_progress':
      return {
        label: 'Remediating',
        dotColor: 'bg-amber-400',
        textColor: 'text-amber-400',
        bgColor: 'bg-amber-500/10',
        borderColor: 'border-amber-500/20',
        animate: true,
      };
    case 'diagnosis_complete':
    case 'complete':
      return {
        label: 'Resolved',
        dotColor: 'bg-emerald-400',
        textColor: 'text-emerald-400',
        bgColor: 'bg-emerald-500/10',
        borderColor: 'border-emerald-500/20',
        animate: false,
      };
    default:
      return {
        label: String(phase).replace(/_/g, ' '),
        dotColor: 'bg-slate-400',
        textColor: 'text-slate-400',
        bgColor: 'bg-slate-500/10',
        borderColor: 'border-slate-500/20',
        animate: false,
      };
  }
};

const agentColor = (index: number): string => {
  const colors = ['bg-[#07b6d5]', 'bg-indigo-400', 'bg-emerald-400', 'bg-amber-400', 'bg-violet-400'];
  return colors[index % colors.length];
};

const LiveIntelligenceFeed: React.FC<LiveIntelligenceFeedProps> = ({
  sessions,
  onSessionsChange,
  onSelectSession,
}) => {
  const [loading, setLoading] = useState(false);

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
      {/* Section Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h2 className="text-xl font-bold text-white tracking-tight">Live Intelligence Feed</h2>
          <span className="px-2 py-0.5 bg-[#07b6d5]/10 text-[#07b6d5] text-[10px] font-black uppercase rounded tracking-widest border border-[#07b6d5]/20">
            Real-time
          </span>
          {loading && (
            <div className="w-3 h-3 border border-[#07b6d5] border-t-transparent rounded-full animate-spin" />
          )}
        </div>
        <button className="text-xs text-slate-400 hover:text-white flex items-center gap-1 transition-colors">
          <span className="material-symbols-outlined text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>filter_list</span>
          Filter Stream
        </button>
      </div>

      {/* Feed Container - bounded height with internal scroll */}
      <div className="bg-[#1e2f33]/10 border border-[#224349] rounded-xl overflow-hidden">
        {/* Feed Header - 12-col grid */}
        <div className="grid grid-cols-12 gap-4 px-6 py-3 bg-[#1e2f33]/20 border-b border-[#224349]">
          <div className="col-span-2 text-[10px] font-bold text-slate-500 uppercase tracking-widest">Timestamp</div>
          <div className="col-span-2 text-[10px] font-bold text-slate-500 uppercase tracking-widest">Agent ID</div>
          <div className="col-span-6 text-[10px] font-bold text-slate-500 uppercase tracking-widest">Action Description</div>
          <div className="col-span-2 text-[10px] font-bold text-slate-500 uppercase tracking-widest text-right">Status</div>
        </div>

        {/* Feed Content - max-height with scroll */}
        <div className="max-h-[400px] overflow-y-auto custom-scrollbar">
          {sessions.length === 0 ? (
            <div className="flex items-center justify-center py-16 text-slate-500">
              <div className="text-center">
                <span className="material-symbols-outlined text-3xl text-slate-600 mb-2 block" style={{ fontFamily: 'Material Symbols Outlined' }}>satellite_alt</span>
                <p className="text-sm">No active sessions. Launch a capability to begin monitoring.</p>
              </div>
            </div>
          ) : (
            sessions.slice(0, 15).map((session, idx) => {
              const status = statusConfig(session.status);
              const agentId = `Duck-${String(idx + 1).padStart(2, '0')}`;

              return (
                <div
                  key={session.session_id}
                  onClick={() => onSelectSession(session)}
                  className="grid grid-cols-12 gap-4 px-6 py-4 border-b border-[#224349]/50 hover:bg-[#1e2f33]/10 transition-colors group cursor-pointer"
                >
                  {/* Timestamp */}
                  <div className="col-span-2 font-mono text-xs text-slate-500">
                    {new Date(session.created_at).toLocaleTimeString([], {
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                    })}
                  </div>

                  {/* Agent ID */}
                  <div className="col-span-2 flex items-center gap-2">
                    <span className={`w-1.5 h-1.5 ${agentColor(idx)} rounded-full`} />
                    <span className="text-xs font-semibold text-slate-300">{agentId}</span>
                  </div>

                  {/* Action Description */}
                  <div className="col-span-6 text-sm text-slate-300">
                    Investigating <span className="text-[#07b6d5]/80 font-mono">{session.service_name}</span>
                    {session.confidence > 0 && (
                      <span className="text-slate-500 ml-2">
                        — Confidence: {Math.round(session.confidence)}%
                      </span>
                    )}
                  </div>

                  {/* Status Badge */}
                  <div className="col-span-2 flex justify-end items-center">
                    <span className={`px-2.5 py-1 ${status.bgColor} ${status.textColor} text-[10px] font-bold uppercase rounded-full border ${status.borderColor} flex items-center gap-1.5`}>
                      {status.animate && (
                        <span className={`w-1 h-1 ${status.dotColor} rounded-full animate-pulse`} />
                      )}
                      {status.label}
                    </span>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </section>
  );
};

export default LiveIntelligenceFeed;
