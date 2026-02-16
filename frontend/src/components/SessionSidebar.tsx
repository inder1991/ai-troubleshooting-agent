import React, { useEffect } from 'react';
import { Plus, LayoutDashboard, Clock, Bot, Settings, Zap } from 'lucide-react';
import type { V4Session, DiagnosticPhase } from '../types';
import { listSessionsV4 } from '../services/api';

interface SessionSidebarProps {
  activeSessionId: string | null;
  onSelectSession: (session: V4Session) => void;
  sessions: V4Session[];
  onSessionsChange: (sessions: V4Session[]) => void;
  onNewMission: () => void;
}

const phaseColors: Record<DiagnosticPhase, string> = {
  initial: 'bg-gray-500',
  collecting_context: 'bg-[#07b6d5]',
  logs_analyzed: 'bg-[#07b6d5]/80',
  metrics_analyzed: 'bg-[#07b6d5]/80',
  k8s_analyzed: 'bg-[#07b6d5]/80',
  tracing_analyzed: 'bg-[#07b6d5]/80',
  code_analyzed: 'bg-[#07b6d5]/80',
  validating: 'bg-yellow-500',
  re_investigating: 'bg-orange-500',
  diagnosis_complete: 'bg-green-500',
  fix_in_progress: 'bg-purple-500',
  complete: 'bg-green-600',
};

const phaseLabel = (phase: DiagnosticPhase): string => {
  return phase.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
};

const navItems = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'sessions', label: 'Sessions', icon: Clock },
  { id: 'agents', label: 'Agents', icon: Bot },
  { id: 'settings', label: 'Settings', icon: Settings },
];

const SessionSidebar: React.FC<SessionSidebarProps> = ({
  activeSessionId,
  onSelectSession,
  sessions,
  onSessionsChange,
  onNewMission,
}) => {
  useEffect(() => {
    loadSessions();
  }, []);

  const loadSessions = async () => {
    try {
      const data = await listSessionsV4();
      onSessionsChange(data);
    } catch (err) {
      console.error('Failed to load sessions:', err);
    }
  };

  return (
    <div className="w-64 bg-[#0a1a1d] border-r border-[#224349] flex flex-col h-full">
      {/* Logo */}
      <div className="p-4 border-b border-[#224349]">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-[#07b6d5]/20 flex items-center justify-center">
            <Zap className="w-4 h-4 text-[#07b6d5]" />
          </div>
          <div>
            <h1 className="text-sm font-bold text-white">DebugDuck</h1>
            <p className="text-[10px] text-gray-500">AI SRE Platform</p>
          </div>
        </div>
      </div>

      {/* New Mission */}
      <div className="px-3 py-3">
        <button
          onClick={onNewMission}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-[#07b6d5] hover:bg-[#07b6d5]/90 text-[#0f2023] rounded-lg text-sm font-bold transition-colors"
        >
          <Plus className="w-4 h-4" />
          New Mission
        </button>
      </div>

      {/* Navigation */}
      <div className="px-3 py-2">
        <p className="text-[10px] text-gray-600 uppercase tracking-wider font-medium px-2 mb-2">
          Navigation
        </p>
        <nav className="space-y-0.5">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-sm text-gray-400 hover:text-white hover:bg-[#1e2f33]/50 transition-colors"
              >
                <Icon className="w-4 h-4" />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </div>

      {/* Sessions list */}
      <div className="flex-1 overflow-y-auto px-3 py-2">
        <p className="text-[10px] text-gray-600 uppercase tracking-wider font-medium px-2 mb-2">
          Recent Sessions
        </p>
        {sessions.length === 0 ? (
          <div className="px-2 py-4 text-center text-gray-600 text-xs">
            No sessions yet
          </div>
        ) : (
          <div className="space-y-0.5">
            {sessions.map((session) => (
              <button
                key={session.session_id}
                onClick={() => onSelectSession(session)}
                className={`w-full text-left px-2.5 py-2.5 rounded-lg transition-colors ${
                  activeSessionId === session.session_id
                    ? 'bg-[#07b6d5]/10 border border-[#07b6d5]/20'
                    : 'hover:bg-[#1e2f33]/50 border border-transparent'
                }`}
              >
                <div className="font-medium text-white text-xs truncate">
                  {session.service_name}
                </div>
                <div className="flex items-center gap-1.5 mt-1">
                  <span
                    className={`inline-block w-1.5 h-1.5 rounded-full ${
                      phaseColors[session.status] || 'bg-gray-500'
                    }`}
                  />
                  <span className="text-[10px] text-gray-500">{phaseLabel(session.status)}</span>
                </div>
                {session.confidence > 0 && (
                  <div className="mt-1">
                    <div className="h-1 bg-[#224349] rounded-full overflow-hidden">
                      <div
                        className="h-full bg-[#07b6d5] rounded-full"
                        style={{ width: `${Math.round(session.confidence * 100)}%` }}
                      />
                    </div>
                  </div>
                )}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="p-3 border-t border-[#224349]">
        <div className="flex items-center gap-2 px-2">
          <div className="w-6 h-6 rounded-full bg-[#07b6d5]/20 flex items-center justify-center">
            <span className="text-[10px] text-[#07b6d5] font-bold">SRE</span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs text-white truncate">SRE Operator</p>
            <p className="text-[10px] text-gray-600">Platform v5</p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SessionSidebar;
