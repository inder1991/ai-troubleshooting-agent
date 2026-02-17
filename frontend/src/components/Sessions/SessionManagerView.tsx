import React, { useEffect } from 'react';
import type { V4Session } from '../../types';
import { listSessionsV4 } from '../../services/api';
import SessionStats from './SessionStats';
import SessionTable from './SessionTable';

interface SessionManagerViewProps {
  sessions: V4Session[];
  onSessionsChange: (sessions: V4Session[]) => void;
  onSelectSession: (session: V4Session) => void;
}

const SessionManagerView: React.FC<SessionManagerViewProps> = ({
  sessions,
  onSessionsChange,
  onSelectSession,
}) => {
  useEffect(() => {
    const load = async () => {
      try {
        const data = await listSessionsV4();
        onSessionsChange(data);
      } catch {
        // silent
      }
    };
    load();
    const interval = setInterval(load, 10000);
    return () => clearInterval(interval);
  }, [onSessionsChange]);

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-6xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="flex items-center gap-2 mb-6">
          <span className="material-symbols-outlined text-xl" style={{ fontFamily: 'Material Symbols Outlined', color: '#07b6d5' }}>history</span>
          <h1 className="text-xl font-bold text-white">Session Manager</h1>
        </div>

        {/* Stats */}
        <div className="mb-6">
          <SessionStats sessions={sessions} />
        </div>

        {/* Table */}
        <SessionTable sessions={sessions} onSelectSession={onSelectSession} />
      </div>
    </div>
  );
};

export default SessionManagerView;
