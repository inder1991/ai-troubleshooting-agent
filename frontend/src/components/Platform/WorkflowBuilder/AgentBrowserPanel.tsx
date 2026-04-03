import React, { useState, useEffect } from 'react';
import { API_BASE_URL } from '../../../services/api';

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
  active: '#22c55e',
  degraded: '#f59e0b',
  offline: '#ef4444',
};

interface Props {
  onInsertAgent: (agentId: string) => void;
}

const AgentBrowserPanel: React.FC<Props> = ({ onInsertAgent }) => {
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState<string | null>(null);
  const [search, setSearch] = useState('');

  useEffect(() => {
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
    <div className="flex flex-col h-full" style={{ background: '#0a1214' }}>
      {/* Header */}
      <div className="px-3 py-2 border-b flex-shrink-0" style={{ borderColor: '#1e2a2e' }}>
        <div className="text-[10px] font-sans uppercase tracking-widest mb-2" style={{ color: '#3d4a50' }}>
          Agents
        </div>
        <input
          type="text"
          placeholder="Search..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="w-full text-[10px] font-mono px-2 py-1.5 rounded outline-none"
          style={{
            background: '#080f12',
            border: '1px solid #1e2a2e',
            color: '#e8e0d4',
          }}
        />
      </div>

      {/* Agent list */}
      <div className="flex-1 overflow-auto">
        {loading && (
          <div className="flex items-center justify-center h-16 text-[10px] font-sans" style={{ color: '#3d4a50' }}>
            Loading...
          </div>
        )}
        {!loading && filtered.length === 0 && (
          <div className="flex items-center justify-center h-16 text-[10px] font-sans" style={{ color: '#3d4a50' }}>
            No agents found
          </div>
        )}
        {Object.entries(groups).map(([groupLabel, groupAgents]) => (
          <div key={groupLabel}>
            <div className="px-3 py-1.5 text-[9px] font-sans uppercase tracking-widest sticky top-0"
              style={{ color: '#3d4a50', background: '#0c1a1f', borderBottom: '1px solid #1a2428' }}>
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
      <div className="px-3 py-2 border-t flex-shrink-0" style={{ borderColor: '#1e2a2e' }}>
        <p className="text-[9px] font-sans" style={{ color: '#3d4a50', lineHeight: 1.4 }}>
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
      style={{
        borderBottom: '1px solid #0f1a1e',
        background: hovered ? 'rgba(7,182,213,0.04)' : 'transparent',
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      title={`Copy: agent: ${agent.id}`}
    >
      <div
        className="w-1.5 h-1.5 rounded-full flex-shrink-0"
        style={{ background: STATUS_COLOR[agent.status] || '#3d4a50' }}
      />
      <div className="flex-1 min-w-0">
        <div className="text-[10px] font-mono truncate" style={{ color: '#e8e0d4' }}>
          {agent.id}
        </div>
      </div>
      <span
        className="text-[9px] font-sans flex-shrink-0 transition-opacity"
        style={{ color: copied ? '#22c55e' : '#07b6d5', opacity: hovered || copied ? 1 : 0 }}
      >
        {copied ? 'copied' : 'copy'}
      </span>
    </button>
  );
};

export default AgentBrowserPanel;
