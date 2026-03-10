import React from 'react';
import type { V4Session, TaskEvent, DiagnosticPhase } from '../../types';

interface DatabaseWarRoomProps {
  session: V4Session;
  events: TaskEvent[];
  wsConnected: boolean;
  phase: DiagnosticPhase | null;
  confidence: number;
}

const DB_AGENTS = ['query_analyst', 'health_analyst', 'schema_analyst', 'synthesizer'];

const DatabaseWarRoom: React.FC<DatabaseWarRoomProps> = ({
  session,
  events,
  wsConnected,
  phase,
  confidence,
}) => {
  // Extract DB-specific findings from events
  const dbFindings = events.filter(
    (e) => DB_AGENTS.includes(e.agent_name) && (e.event_type === 'finding' || e.event_type === 'success' || e.event_type === 'error')
  );

  return (
    <div className="flex flex-col h-full overflow-hidden bg-duck-bg">
      {/* Header Bar */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-duck-border bg-duck-card/30">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-violet-500/10 border border-violet-500/20">
            <span className="material-symbols-outlined text-violet-400 text-lg">database</span>
          </div>
          <div>
            <h2 className="text-sm font-bold text-white">{session.service_name}</h2>
            <p className="text-[10px] text-slate-500">Database Diagnostics — {phase || 'initializing'}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold ${
            wsConnected ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'
          }`}>
            <span className={`w-1.5 h-1.5 rounded-full ${wsConnected ? 'bg-emerald-400' : 'bg-red-400'}`} />
            {wsConnected ? 'LIVE' : 'DISCONNECTED'}
          </span>
          <span className="text-[10px] text-slate-500">Confidence: {confidence}%</span>
        </div>
      </div>

      {/* Three-column grid */}
      <div className="grid grid-cols-12 flex-1 overflow-hidden">
        {/* Left: DB Investigator (col-3) */}
        <div className="col-span-3 border-r border-duck-border overflow-y-auto p-4 space-y-4">
          {/* DB Profile Banner */}
          <div className="bg-violet-500/5 border border-violet-500/20 rounded-lg p-3">
            <div className="flex items-center gap-2 mb-2">
              <span className="material-symbols-outlined text-violet-400 text-sm">database</span>
              <span className="text-xs font-bold text-violet-400 uppercase tracking-wider">DB Profile</span>
            </div>
            <p className="text-sm text-white font-mono">{session.service_name}</p>
            <p className="text-[10px] text-slate-500 mt-1">Session: {session.session_id.slice(0, 8)}</p>
          </div>

          {/* Event Timeline */}
          <div>
            <h3 className="text-xs font-bold text-duck-muted uppercase tracking-wider mb-2">Event Timeline</h3>
            <div className="space-y-2">
              {events.slice(-15).reverse().map((event, i) => (
                <div key={i} className="flex items-start gap-2">
                  <span className={`w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0 ${
                    event.event_type === 'error' ? 'bg-red-400' :
                    event.event_type === 'success' ? 'bg-emerald-400' :
                    event.event_type === 'warning' ? 'bg-amber-400' :
                    'bg-cyan-400 animate-pulse'
                  }`} />
                  <div>
                    <p className="text-[11px] text-slate-300">{event.message}</p>
                    <p className="text-[9px] text-slate-600">{event.agent_name || 'system'}</p>
                  </div>
                </div>
              ))}
              {events.length === 0 && (
                <p className="text-[11px] text-slate-600 italic">Waiting for agents...</p>
              )}
            </div>
          </div>
        </div>

        {/* Center: Evidence Findings (col-5) */}
        <div className="col-span-5 border-r border-duck-border overflow-y-auto p-4">
          <h3 className="text-xs font-bold text-duck-muted uppercase tracking-wider mb-3">Findings</h3>
          <div className="space-y-3">
            {dbFindings.length === 0 && phase !== 'complete' && (
              <div className="text-center py-8">
                <span className="material-symbols-outlined text-4xl text-slate-700 mb-2 block">search</span>
                <p className="text-sm text-slate-500">Agents are investigating...</p>
              </div>
            )}
            {dbFindings.map((finding, i) => (
              <div
                key={i}
                className="bg-duck-card/30 border border-duck-border rounded-lg p-3"
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-bold text-white">{finding.agent_name}</span>
                  <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                    finding.event_type === 'error' ? 'bg-red-500/10 text-red-400' :
                    finding.event_type === 'success' ? 'bg-emerald-500/10 text-emerald-400' :
                    'bg-cyan-500/10 text-cyan-400'
                  }`}>
                    {finding.event_type.toUpperCase()}
                  </span>
                </div>
                <p className="text-[11px] text-slate-300">{finding.message}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Right: DB Navigator (col-4) */}
        <div className="col-span-4 overflow-y-auto p-4 space-y-4">
          {/* Connection Pool Summary */}
          <div>
            <h3 className="text-xs font-bold text-duck-muted uppercase tracking-wider mb-2">Connection Pool</h3>
            <div className="bg-duck-card/30 border border-duck-border rounded-lg p-3">
              <div className="flex items-center justify-center h-24">
                <span className="text-slate-600 text-xs italic">ConnectionPoolGauge will render here</span>
              </div>
            </div>
          </div>

          {/* Agent Status */}
          <div>
            <h3 className="text-xs font-bold text-duck-muted uppercase tracking-wider mb-2">Agent Status</h3>
            <div className="space-y-2">
              {DB_AGENTS.map((agent) => {
                const agentEvents = events.filter((e) => e.agent_name === agent);
                const lastEvent = agentEvents[agentEvents.length - 1];
                const status = lastEvent?.event_type || 'pending';
                return (
                  <div key={agent} className="flex items-center justify-between bg-duck-card/20 rounded-lg px-3 py-2">
                    <span className="text-[11px] text-slate-300 font-mono">{agent}</span>
                    <span className={`text-[10px] font-bold ${
                      status === 'success' ? 'text-emerald-400' :
                      status === 'error' ? 'text-red-400' :
                      status === 'started' ? 'text-cyan-400' :
                      status === 'progress' ? 'text-amber-400' :
                      'text-slate-600'
                    }`}>
                      {status.toUpperCase()}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Investigation Summary (when complete) */}
          {phase === 'complete' && (
            <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-lg p-3">
              <div className="flex items-center gap-2 mb-2">
                <span className="material-symbols-outlined text-emerald-400 text-sm">check_circle</span>
                <span className="text-xs font-bold text-emerald-400 uppercase tracking-wider">Investigation Complete</span>
              </div>
              <p className="text-[11px] text-slate-300">
                {events.find((e) => e.agent_name === 'synthesizer' && e.event_type === 'success')?.message || 'Analysis complete.'}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default DatabaseWarRoom;
