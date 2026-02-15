import React, { useState, useEffect } from 'react';
import type { V4Session, StartSessionRequest, DiagnosticPhase } from '../types';
import { listSessionsV4, startSessionV4 } from '../services/api';

interface SessionSidebarProps {
  activeSessionId: string | null;
  onSelectSession: (session: V4Session) => void;
  sessions: V4Session[];
  onSessionsChange: (sessions: V4Session[]) => void;
}

const phaseColors: Record<DiagnosticPhase, string> = {
  initial: 'bg-gray-500',
  collecting_context: 'bg-blue-500',
  logs_analyzed: 'bg-blue-400',
  metrics_analyzed: 'bg-blue-400',
  k8s_analyzed: 'bg-blue-400',
  tracing_analyzed: 'bg-blue-400',
  code_analyzed: 'bg-blue-400',
  validating: 'bg-yellow-500',
  re_investigating: 'bg-orange-500',
  diagnosis_complete: 'bg-green-500',
  fix_in_progress: 'bg-purple-500',
  complete: 'bg-green-600',
};

const phaseLabel = (phase: DiagnosticPhase): string => {
  return phase.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
};

const SessionSidebar: React.FC<SessionSidebarProps> = ({
  activeSessionId,
  onSelectSession,
  sessions,
  onSessionsChange,
}) => {
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState<StartSessionRequest>({
    service_name: '',
    time_window: '1h',
  });

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

  const handleStartSession = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.service_name.trim()) return;

    setLoading(true);
    try {
      const session = await startSessionV4(formData);
      onSessionsChange([session, ...sessions]);
      onSelectSession(session);
      setShowForm(false);
      setFormData({ service_name: '', time_window: '1h' });
    } catch (err) {
      console.error('Failed to start session:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="w-72 bg-gray-900 border-r border-gray-700 flex flex-col h-full">
      <div className="p-4 border-b border-gray-700">
        <h2 className="text-lg font-semibold text-white mb-3">Sessions</h2>
        <button
          onClick={() => setShowForm(!showForm)}
          className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors"
        >
          {showForm ? 'Cancel' : '+ New Session'}
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleStartSession} className="p-4 border-b border-gray-700 space-y-3">
          <div>
            <label className="block text-xs text-gray-400 mb-1">Service Name *</label>
            <input
              type="text"
              value={formData.service_name}
              onChange={(e) => setFormData({ ...formData, service_name: e.target.value })}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded text-sm text-white focus:border-blue-500 focus:outline-none"
              placeholder="e.g. payment-service"
              required
            />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Time Window</label>
            <select
              value={formData.time_window}
              onChange={(e) => setFormData({ ...formData, time_window: e.target.value })}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded text-sm text-white focus:border-blue-500 focus:outline-none"
            >
              <option value="15m">15 minutes</option>
              <option value="30m">30 minutes</option>
              <option value="1h">1 hour</option>
              <option value="3h">3 hours</option>
              <option value="6h">6 hours</option>
              <option value="24h">24 hours</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Trace ID (optional)</label>
            <input
              type="text"
              value={formData.trace_id || ''}
              onChange={(e) => setFormData({ ...formData, trace_id: e.target.value || undefined })}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded text-sm text-white focus:border-blue-500 focus:outline-none"
              placeholder="abc123..."
            />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Namespace (optional)</label>
            <input
              type="text"
              value={formData.namespace || ''}
              onChange={(e) => setFormData({ ...formData, namespace: e.target.value || undefined })}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded text-sm text-white focus:border-blue-500 focus:outline-none"
              placeholder="production"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Repo URL (optional)</label>
            <input
              type="text"
              value={formData.repo_url || ''}
              onChange={(e) => setFormData({ ...formData, repo_url: e.target.value || undefined })}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded text-sm text-white focus:border-blue-500 focus:outline-none"
              placeholder="https://github.com/org/repo"
            />
          </div>
          <button
            type="submit"
            disabled={loading || !formData.service_name.trim()}
            className="w-full px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded text-sm font-medium transition-colors"
          >
            {loading ? 'Starting...' : 'Start Diagnosis'}
          </button>
        </form>
      )}

      <div className="flex-1 overflow-y-auto">
        {sessions.length === 0 ? (
          <div className="p-4 text-center text-gray-500 text-sm">
            No sessions yet. Start a new one above.
          </div>
        ) : (
          sessions.map((session) => (
            <button
              key={session.session_id}
              onClick={() => onSelectSession(session)}
              className={`w-full text-left p-4 border-b border-gray-800 hover:bg-gray-800 transition-colors ${
                activeSessionId === session.session_id ? 'bg-gray-800 border-l-2 border-l-blue-500' : ''
              }`}
            >
              <div className="font-medium text-white text-sm truncate">
                {session.service_name}
              </div>
              <div className="flex items-center gap-2 mt-1">
                <span
                  className={`inline-block w-2 h-2 rounded-full ${phaseColors[session.status] || 'bg-gray-500'}`}
                />
                <span className="text-xs text-gray-400">{phaseLabel(session.status)}</span>
              </div>
              {session.confidence > 0 && (
                <div className="mt-1 text-xs text-gray-500">
                  Confidence: {Math.round(session.confidence * 100)}%
                </div>
              )}
            </button>
          ))
        )}
      </div>
    </div>
  );
};

export default SessionSidebar;
