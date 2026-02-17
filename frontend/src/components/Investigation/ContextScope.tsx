import React, { useEffect, useState, useCallback } from 'react';
import type { V4Session, V4SessionStatus, DiagnosticPhase } from '../../types';
import { getSessionStatus } from '../../services/api';

interface ContextScopeProps {
  session: V4Session;
}

const phaseLabel = (phase: DiagnosticPhase): string =>
  phase.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

const ContextScope: React.FC<ContextScopeProps> = ({ session }) => {
  const [status, setStatus] = useState<V4SessionStatus | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const data = await getSessionStatus(session.session_id);
      setStatus(data);
    } catch {
      // silent
    }
  }, [session.session_id]);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  const confidence = status?.confidence ?? session.confidence;
  const confidencePercent = Math.round(confidence * 100);
  const phase = status?.phase ?? session.status;
  const totalTokens = status?.token_usage?.reduce((sum, t) => sum + t.total_tokens, 0) ?? 0;

  return (
    <div className="flex flex-col h-full bg-slate-900/20 border-l border-[#07b6d5]/10">
      {/* Header */}
      <div className="p-4 border-b border-[#07b6d5]/10 flex items-center gap-2">
        <span className="material-symbols-outlined text-slate-400 text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>info</span>
        <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400">Context & Scope</h2>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-8 custom-scrollbar">
        {/* System Info - matches reference metadata table */}
        <section>
          <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">System Info</h3>
          <div className="space-y-3">
            <div className="flex justify-between items-center border-b border-slate-800/50 pb-2">
              <span className="text-[11px] text-slate-400">Service</span>
              <span className="text-[11px] font-mono text-slate-200">{session.service_name}</span>
            </div>
            <div className="flex justify-between items-center border-b border-slate-800/50 pb-2">
              <span className="text-[11px] text-slate-400">Session ID</span>
              <span className="text-[11px] font-mono text-[#07b6d5]">{session.session_id.substring(0, 8).toUpperCase()}</span>
            </div>
            <div className="flex justify-between items-center border-b border-slate-800/50 pb-2">
              <span className="text-[11px] text-slate-400">Phase</span>
              <span className="text-[11px] font-mono text-slate-200">{phaseLabel(phase)}</span>
            </div>
            <div className="flex justify-between items-center border-b border-slate-800/50 pb-2">
              <span className="text-[11px] text-slate-400">Confidence</span>
              <span className={`text-[11px] font-mono font-bold ${
                confidencePercent >= 70 ? 'text-green-400' : confidencePercent >= 40 ? 'text-amber-400' : 'text-red-400'
              }`}>
                {confidencePercent}%
              </span>
            </div>
            <div className="flex justify-between items-center border-b border-slate-800/50 pb-2">
              <span className="text-[11px] text-slate-400">Created</span>
              <span className="text-[11px] font-mono text-slate-200">
                {new Date(session.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
              </span>
            </div>
          </div>
        </section>

        {/* Upstream Dependencies - matches reference */}
        <section>
          <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">Upstream Dependencies</h3>
          <div className="bg-slate-800/30 rounded-lg p-3 border border-slate-800 space-y-3">
            {totalTokens > 0 && status?.token_usage ? (
              status.token_usage.map((t, i) => (
                <div key={i} className="flex items-center gap-3">
                  <div className={`w-1.5 h-1.5 rounded-full ${i === status.token_usage.length - 1 ? 'bg-red-500 animate-pulse' : 'bg-green-500'}`} />
                  <span className="text-[11px] text-slate-300">{t.agent_name}</span>
                  <span className="ml-auto text-[10px] text-slate-500">{t.total_tokens.toLocaleString()} tokens</span>
                </div>
              ))
            ) : (
              <>
                <div className="flex items-center gap-3">
                  <div className="w-1.5 h-1.5 rounded-full bg-green-500" />
                  <span className="text-[11px] text-slate-300">Log Analyzer</span>
                  <span className="ml-auto text-[10px] text-slate-500">Ready</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="w-1.5 h-1.5 rounded-full bg-green-500" />
                  <span className="text-[11px] text-slate-300">Metric Scanner</span>
                  <span className="ml-auto text-[10px] text-slate-500">Ready</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
                  <span className="text-[11px] text-primary font-medium">K8s Probe</span>
                  <span className="ml-auto text-[10px] text-primary">Active</span>
                </div>
              </>
            )}
          </div>
        </section>

        {/* Labels - matches reference */}
        <section>
          <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">Labels</h3>
          <div className="flex flex-wrap gap-2">
            <span className="bg-slate-800 px-2 py-1 rounded text-[10px] text-slate-400 border border-slate-700">
              svc:{session.service_name}
            </span>
            <span className="bg-slate-800 px-2 py-1 rounded text-[10px] text-slate-400 border border-slate-700">
              phase:{phase}
            </span>
            <span className="bg-slate-800 px-2 py-1 rounded text-[10px] text-slate-400 border border-slate-700">
              confidence:{confidencePercent}%
            </span>
          </div>
        </section>
      </div>

      {/* Footer action */}
      <div className="p-4 border-t border-[#07b6d5]/10">
        <button className="w-full py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-xs font-bold transition-colors border border-slate-700 flex items-center justify-center gap-2">
          <span className="material-symbols-outlined text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>history</span>
          View Previous Incidents
        </button>
      </div>
    </div>
  );
};

export default ContextScope;
