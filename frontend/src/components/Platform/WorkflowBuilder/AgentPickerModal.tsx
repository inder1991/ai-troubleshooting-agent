import React, { useState, useEffect, useRef } from 'react';
import { API_BASE_URL } from '../../../services/api';
import { t } from '../../../styles/tokens';

interface AgentSummary {
  id: string;
  name: string;
  workflow: string;
  status: 'active' | 'degraded' | 'offline';
}

const WORKFLOW_LABELS: Record<string, string> = {
  app_diagnostics: 'App',
  cluster_diagnostics: 'Cluster',
  network_diagnostics: 'Network',
  database_diagnostics: 'Database',
};

const STATUS_COLOR: Record<string, string> = {
  active: t.green,
  degraded: t.amber,
  offline: t.red,
};

interface Props {
  onSelect: (agentId: string) => void;
  onClose: () => void;
}

const AgentPickerModal: React.FC<Props> = ({ onSelect, onClose }) => {
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    searchRef.current?.focus();
    window.fetch(`${API_BASE_URL}/api/v4/agents`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data?.agents) {
          setAgents(data.agents.map((a: any) => ({
            id: a.id,
            name: a.name || a.id,
            workflow: a.workflow || 'app_diagnostics',
            status: a.status || 'active',
          })));
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  const filtered = agents.filter(a =>
    search === '' ||
    a.id.toLowerCase().includes(search.toLowerCase()) ||
    a.name.toLowerCase().includes(search.toLowerCase())
  );

  const groups: Record<string, AgentSummary[]> = {};
  filtered.forEach(a => {
    const g = WORKFLOW_LABELS[a.workflow] || a.workflow;
    groups[g] = groups[g] || [];
    groups[g].push(a);
  });

  return (
    // Backdrop
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.6)' }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        className="flex flex-col rounded-lg overflow-hidden"
        style={{
          width: 400,
          maxHeight: 480,
          background: t.bgSurface,
          border: `1px solid ${t.borderDefault}`,
          boxShadow: '0 24px 48px rgba(0,0,0,0.5)',
        }}
        role="dialog"
        aria-modal="true"
        aria-label="Choose an agent"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b flex-shrink-0"
          style={{ borderColor: t.borderDefault }}>
          <span className="text-sm font-display font-semibold" style={{ color: t.textPrimary }}>Choose an Agent</span>
          <button onClick={onClose} aria-label="Close agent picker">
            <span className="material-symbols-outlined" style={{ fontSize: 18, color: t.textMuted }}>close</span>
          </button>
        </div>

        {/* Search */}
        <div className="px-4 py-2 border-b flex-shrink-0" style={{ borderColor: t.borderDefault }}>
          <div className="flex items-center gap-2" style={{
            background: t.bgDeep,
            border: `1px solid ${t.borderDefault}`,
            borderRadius: 6,
            padding: '6px 10px',
          }}>
            <span className="material-symbols-outlined" style={{ fontSize: 14, color: t.textFaint }}>search</span>
            <input
              ref={searchRef}
              type="text"
              placeholder="Search agents..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="flex-1 text-xs font-sans bg-transparent outline-none"
              style={{ color: t.textPrimary }}
              aria-label="Search agents"
            />
          </div>
        </div>

        {/* Agent list */}
        <div className="flex-1 overflow-auto">
          {loading && (
            <div className="flex items-center justify-center h-16 text-xs font-sans" style={{ color: t.textMuted }}>
              Loading agents...
            </div>
          )}
          {!loading && filtered.length === 0 && (
            <div className="flex items-center justify-center h-16 text-xs font-sans" style={{ color: t.textMuted }}>
              No agents found
            </div>
          )}
          {!loading && Object.entries(groups).map(([groupLabel, groupAgents]) => (
            <div key={groupLabel}>
              <div className="px-4 py-1.5 text-[10px] font-sans uppercase tracking-widest sticky top-0"
                style={{ color: t.textFaint, background: t.bgSurface, borderBottom: `1px solid ${t.bgTrack}` }}>
                {groupLabel}
              </div>
              {groupAgents.map(agent => (
                <button
                  key={agent.id}
                  onClick={() => { onSelect(agent.id); onClose(); }}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-left"
                  style={{
                    borderBottom: `1px solid ${t.borderFaint}`,
                    opacity: agent.status === 'offline' ? 0.45 : 1,
                  }}
                  disabled={agent.status === 'offline'}
                >
                  <div className="w-2 h-2 rounded-full flex-shrink-0"
                    style={{ background: STATUS_COLOR[agent.status] || t.textFaint }} />
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-sans truncate" style={{ color: t.textPrimary }}>{agent.name}</div>
                    <div className="text-[10px] font-mono truncate mt-0.5" style={{ color: t.textMuted }}>{agent.id}</div>
                  </div>
                  {agent.status === 'offline' && (
                    <span className="text-[10px] font-sans flex-shrink-0" style={{ color: t.textFaint }}>offline</span>
                  )}
                </button>
              ))}
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t flex justify-end flex-shrink-0" style={{ borderColor: t.borderDefault }}>
          <button
            onClick={onClose}
            className="text-xs font-sans px-3 py-1.5 rounded"
            style={{ color: t.textMuted, border: `1px solid ${t.borderDefault}` }}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
};

export default AgentPickerModal;
