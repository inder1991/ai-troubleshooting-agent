import React, { useEffect } from 'react';
import { motion } from 'framer-motion';
import { Plus, LayoutDashboard, Clock, Bot, Settings, Zap } from 'lucide-react';
import type { V4Session, DiagnosticPhase } from '../types';
import { listSessionsV4 } from '../services/api';

interface SessionSidebarProps {
  activeSessionId: string | null;
  onSelectSession: (session: V4Session) => void;
  sessions: V4Session[];
  onSessionsChange: (sessions: V4Session[]) => void;
  onNewMission: () => void;
  onSettings?: () => void;
}

const phaseColors: Record<DiagnosticPhase, string> = {
  initial: 'bg-gray-500',
  collecting_context: 'bg-[#e09f3e]',
  logs_analyzed: 'bg-[#e09f3e]/80',
  metrics_analyzed: 'bg-[#e09f3e]/80',
  k8s_analyzed: 'bg-[#e09f3e]/80',
  tracing_analyzed: 'bg-[#e09f3e]/80',
  code_analyzed: 'bg-[#e09f3e]/80',
  validating: 'bg-yellow-500',
  re_investigating: 'bg-orange-500',
  diagnosis_complete: 'bg-green-500',
  fix_in_progress: 'bg-purple-500',
  complete: 'bg-green-600',
  cancelled: 'bg-slate-500',
  error: 'bg-red-500',
};

const phaseLabel = (phase: DiagnosticPhase | undefined): string => {
  if (!phase) return 'Unknown';
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
  onSettings,
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
    <div className="w-64 bg-[#12110e] border-r border-[#3d3528] flex flex-col h-full">
      {/* Logo */}
      <div className="p-4 border-b border-[#3d3528]">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-[#e09f3e]/20 flex items-center justify-center">
            <Zap className="w-4 h-4 text-[#e09f3e]" />
          </div>
          <div>
            <h1 className="text-sm font-bold text-white">DebugDuck</h1>
            <p className="text-body-xs text-gray-500">AI SRE Platform</p>
          </div>
        </div>
      </div>

      {/* New Mission */}
      <div className="px-3 py-3">
        <button
          onClick={onNewMission}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-[#e09f3e] hover:bg-[#e09f3e]/90 text-[#1a1814] rounded-lg text-sm font-bold transition-colors"
        >
          <Plus className="w-4 h-4" />
          New Mission
        </button>
      </div>

      {/* Navigation */}
      <div className="px-3 py-2">
        <p className="text-body-xs text-gray-600 uppercase tracking-wider font-medium px-2 mb-2">
          Navigation
        </p>
        <nav className="space-y-0.5">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                onClick={item.id === 'settings' ? onSettings : undefined}
                className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-sm text-gray-400 hover:text-white hover:bg-[#252118]/50 transition-colors"
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
        <p className="text-body-xs text-gray-600 uppercase tracking-wider font-medium px-2 mb-2">
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
                className="relative w-full text-left px-2.5 py-2.5 rounded-lg border border-transparent"
              >
                {activeSessionId === session.session_id && (
                  <motion.div
                    layoutId="sidebar-active-highlight"
                    className="absolute inset-0 bg-[#e09f3e]/10 border border-[#e09f3e]/20 rounded-lg -z-10"
                    transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                  />
                )}
                <div className="font-medium text-white text-xs truncate">
                  {session.service_name}
                </div>
                <div className="flex items-center gap-1.5 mt-1">
                  <span
                    className={`inline-block w-1.5 h-1.5 rounded-full ${
                      phaseColors[session.status] || 'bg-gray-500'
                    }`}
                  />
                  <span className="text-body-xs text-gray-500">{phaseLabel(session.status)}</span>
                </div>
                {session.confidence > 0 && (
                  <div className="mt-1">
                    <div className="h-1 bg-[#3d3528] rounded-full overflow-hidden">
                      <motion.div
                        className="h-full bg-[#e09f3e] rounded-full shadow-[0_0_10px_rgba(34,211,238,0.5)]"
                        initial={{ width: 0 }}
                        animate={{ width: `${Math.round(session.confidence)}%` }}
                        transition={{ type: 'spring', bounce: 0, duration: 0.8 }}
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
      <div className="p-3 border-t border-[#3d3528]">
        <div className="flex items-center gap-2 px-2">
          <div className="w-6 h-6 rounded-full bg-[#e09f3e]/20 flex items-center justify-center">
            <span className="text-body-xs text-[#e09f3e] font-bold">SRE</span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs text-white truncate">SRE Operator</p>
            <p className="text-body-xs text-gray-600">Platform v5</p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SessionSidebar;
