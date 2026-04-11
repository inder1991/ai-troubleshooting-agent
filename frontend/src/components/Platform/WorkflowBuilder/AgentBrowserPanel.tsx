import React, { useState, useEffect, useCallback } from 'react';
import { API_BASE_URL } from '../../../services/api';
import { t } from '../../../styles/tokens';

interface AgentSummary {
  id: string;
  name: string;
  workflow: string;
  status: 'active' | 'degraded' | 'offline';
}

const WORKFLOW_LABELS: Record<string, string> = {
  app_diagnostics:      'App',
  cluster_diagnostics:  'Cluster',
  network_diagnostics:  'Network',
  database_diagnostics: 'Database',
};

const STATUS_COLOR: Record<string, string> = {
  active:   t.green,
  degraded: t.amber,
  offline:  t.red,
};

interface Props {
  onInsertAgent: (agentId: string) => void;
}

const AgentBrowserPanel: React.FC<Props> = ({ onInsertAgent }) => {
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const [search, setSearch] = useState('');

  const loadAgents = useCallback(() => {
    setLoading(true);
    setError(false);
    window.fetch(`${API_BASE_URL}/api/v4/agents`)
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
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
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { loadAgents(); }, [loadAgents]);

  const handleCopy = (agentId: string) => {
    onInsertAgent(agentId);
    setCopied(agentId);
    setTimeout(() => setCopied(null), 1500);
  };

  const filtered = agents.filter(a =>
    search === '' ||
    a.id.toLowerCase().includes(search.toLowerCase()) ||
    a.name.toLowerCase().includes(search.toLowerCase())
  );

  // Group by workflow label
  const groups: Record<string, AgentSummary[]> = {};
  filtered.forEach(a => {
    const g = WORKFLOW_LABELS[a.workflow] || a.workflow;
    groups[g] = groups[g] || [];
    groups[g].push(a);
  });

  return (
    <div className="flex flex-col h-full" style={{ background: t.bgBase }}>
      {/* Header */}
      <div className="px-3 py-2 border-b flex-shrink-0" style={{ borderColor: t.borderDefault }}>
        <div className="text-body-xs font-sans uppercase tracking-widest mb-2" style={{ color: t.textFaint }}>
          Agents
        </div>
        <label htmlFor="agent-search" className="sr-only">Search agents</label>
        <input
          id="agent-search"
          type="text"
          placeholder="Search..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="w-full text-body-xs font-mono px-2 py-1.5 rounded"
          style={{
            background: t.bgDeep,
            border: `1px solid ${t.borderDefault}`,
            color: t.textPrimary,
            outline: 'none',
          }}
          onFocus={e => { e.currentTarget.style.borderColor = t.cyanBorder; }}
          onBlur={e => { e.currentTarget.style.borderColor = t.borderDefault; }}
        />
      </div>

      {/* Agent list */}
      <div className="flex-1 overflow-auto">
        {loading && (
          <div className="flex items-center justify-center h-16 text-body-xs font-sans" style={{ color: t.textFaint }}>
            Loading...
          </div>
        )}
        {error && (
          <div className="flex flex-col items-center justify-center h-24 gap-2 px-3">
            <span className="text-body-xs font-sans text-center" style={{ color: t.textMuted }}>
              Failed to load agents.
            </span>
            <button
              onClick={loadAgents}
              className="text-body-xs font-sans px-2 py-1 rounded"
              style={{ background: t.cyanBg, border: `1px solid ${t.cyanBorder}`, color: t.cyan }}
            >
              Retry
            </button>
          </div>
        )}
        {!loading && !error && filtered.length === 0 && (
          <div className="flex items-center justify-center h-16 text-body-xs font-sans" style={{ color: t.textFaint }}>
            No agents found
          </div>
        )}
        {!loading && !error && Object.entries(groups).map(([groupLabel, groupAgents]) => (
          <div key={groupLabel}>
            <div
              className="px-3 py-1.5 text-body-xs font-sans uppercase tracking-widest sticky top-0"
              style={{ color: t.textFaint, background: t.bgSurface, borderBottom: `1px solid ${t.bgTrack}` }}
            >
              {groupLabel}
            </div>
            {groupAgents.map(agent => (
              <AgentRow
                key={agent.id}
                agent={agent}
                copied={copied === agent.id}
                onCopy={() => handleCopy(agent.id)}
              />
            ))}
          </div>
        ))}
      </div>

      {/* Footer hint */}
      <div className="px-3 py-2 border-t flex-shrink-0" style={{ borderColor: t.borderDefault }}>
        <p className="text-body-xs font-sans" style={{ color: t.textFaint, lineHeight: 1.4 }}>
          Click to copy <span className="font-mono">agent: id</span> to clipboard
        </p>
      </div>
    </div>
  );
};

interface AgentRowProps {
  agent: AgentSummary;
  copied: boolean;
  onCopy: () => void;
}

const AgentRow: React.FC<AgentRowProps> = ({ agent, copied, onCopy }) => {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      onClick={onCopy}
      className="w-full flex items-center gap-2 px-3 py-2 text-left"
      aria-label={`Copy ${agent.id} to editor`}
      style={{
        borderBottom: `1px solid ${t.borderFaint}`,
        background: hovered ? t.cyanHover : 'transparent',
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div
        className="w-1.5 h-1.5 rounded-full flex-shrink-0"
        style={{ background: STATUS_COLOR[agent.status] || t.textFaint }}
      />
      <div className="flex-1 min-w-0">
        <div className="text-body-xs font-mono truncate" style={{ color: t.textPrimary }}>
          {agent.id}
        </div>
      </div>
      <span
        className="text-body-xs font-sans flex-shrink-0 transition-opacity"
        style={{ color: copied ? t.green : t.cyan, opacity: hovered || copied ? 1 : 0 }}
      >
        {copied ? 'copied' : 'copy'}
      </span>
    </button>
  );
};

export default AgentBrowserPanel;
