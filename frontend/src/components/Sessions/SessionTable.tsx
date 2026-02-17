import React, { useState } from 'react';
import type { V4Session, DiagnosticPhase } from '../../types';

interface SessionTableProps {
  sessions: V4Session[];
  onSelectSession: (session: V4Session) => void;
}

const phaseColors: Record<string, string> = {
  initial: 'bg-gray-400',
  collecting_context: 'bg-cyan-400',
  logs_analyzed: 'bg-cyan-400',
  metrics_analyzed: 'bg-cyan-400',
  k8s_analyzed: 'bg-cyan-400',
  tracing_analyzed: 'bg-cyan-400',
  code_analyzed: 'bg-cyan-400',
  validating: 'bg-yellow-400',
  re_investigating: 'bg-orange-400',
  diagnosis_complete: 'bg-green-400',
  fix_in_progress: 'bg-purple-400',
  complete: 'bg-green-500',
  error: 'bg-red-500',
};

const phaseLabel = (phase: DiagnosticPhase | string): string =>
  phase.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

type SortKey = 'service_name' | 'status' | 'created_at';

const SessionTable: React.FC<SessionTableProps> = ({ sessions, onSelectSession }) => {
  const [sortKey, setSortKey] = useState<SortKey>('created_at');
  const [sortAsc, setSortAsc] = useState(false);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(true);
    }
  };

  const sorted = [...sessions].sort((a, b) => {
    let cmp = 0;
    if (sortKey === 'service_name') {
      cmp = a.service_name.localeCompare(b.service_name);
    } else if (sortKey === 'status') {
      cmp = a.status.localeCompare(b.status);
    } else {
      cmp = new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
    }
    return sortAsc ? cmp : -cmp;
  });

  if (sessions.length === 0) {
    return (
      <div className="rounded-xl p-8 text-center border" style={{ backgroundColor: 'rgba(30,47,51,0.3)', borderColor: '#224349' }}>
        <p className="text-gray-500 text-sm">No sessions found.</p>
      </div>
    );
  }

  const SortHeader: React.FC<{ label: string; field: SortKey }> = ({ label, field }) => (
    <button
      onClick={() => handleSort(field)}
      className="flex items-center gap-1 text-xs text-gray-500 font-medium hover:text-gray-300 transition-colors"
    >
      {label}
      <span className="material-symbols-outlined text-xs" style={{ fontFamily: 'Material Symbols Outlined' }}>swap_vert</span>
    </button>
  );

  return (
    <div className="rounded-xl overflow-hidden border" style={{ backgroundColor: 'rgba(30,47,51,0.3)', borderColor: '#224349' }}>
      <table className="w-full text-sm">
        <thead>
          <tr style={{ borderBottom: '1px solid #224349' }}>
            <th className="text-left px-4 py-3 w-8">
              <span className="text-xs text-gray-500">Status</span>
            </th>
            <th className="text-left px-4 py-3">
              <SortHeader label="Session Name" field="service_name" />
            </th>
            <th className="text-left px-4 py-3">
              <SortHeader label="Phase" field="status" />
            </th>
            <th className="text-left px-4 py-3">
              <SortHeader label="Created" field="created_at" />
            </th>
            <th className="text-right px-4 py-3">
              <span className="text-xs text-gray-500">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((session) => (
            <tr
              key={session.session_id}
              className="hover:bg-[#162a2e]/50 transition-colors"
              style={{ borderBottom: '1px solid rgba(34,67,73,0.5)' }}
            >
              <td className="px-4 py-3">
                <div
                  className={`w-2.5 h-2.5 rounded-full ${
                    phaseColors[session.status] || 'bg-gray-400'
                  }`}
                />
              </td>
              <td className="px-4 py-3">
                <div className="text-white font-medium">{session.service_name}</div>
                <div className="text-[10px] text-gray-500 font-mono">
                  {session.session_id.substring(0, 8)}
                </div>
              </td>
              <td className="px-4 py-3">
                <span className="text-xs text-gray-300">{phaseLabel(session.status)}</span>
              </td>
              <td className="px-4 py-3 text-xs text-gray-400">
                {new Date(session.created_at).toLocaleString([], {
                  month: 'short',
                  day: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </td>
              <td className="px-4 py-3 text-right">
                <button
                  onClick={() => onSelectSession(session)}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs transition-colors"
                  style={{ backgroundColor: 'rgba(7,182,213,0.1)', color: '#07b6d5' }}
                >
                  <span className="material-symbols-outlined text-xs" style={{ fontFamily: 'Material Symbols Outlined' }}>visibility</span>
                  View
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default SessionTable;
