import React, { useState, useEffect } from 'react';
import { API_BASE_URL } from '../../../services/api';
import type { CatalogAgent } from './useAgentCatalog';

interface Execution {
  execution_id: string;
  status: string;
  started_at: string;
  duration_ms?: number;
  findings_count?: number;
}

interface Props { agent: CatalogAgent; onClose: () => void; }

const STATUS_COLOR: Record<string, string> = {
  completed: '#22c55e', failed: '#ef4444', timed_out: '#f59e0b', running: '#07b6d5',
};

const copyYaml = (agent: CatalogAgent) => {
  const yaml = `- id: ${agent.id}\n  agent: ${agent.id}\n  input:\n    # fill required fields\n`;
  navigator.clipboard.writeText(yaml);
};

const AgentDetailPanel: React.FC<Props> = ({ agent, onClose }) => {
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    window.fetch(`${API_BASE_URL}/api/v4/agents/${agent.id}/executions`)
      .then(r => r.ok ? r.json() : { executions: [] })
      .then(d => setExecutions(d.executions || []))
      .catch(() => {});
  }, [agent.id]);

  const handleCopy = () => {
    copyYaml(agent);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="h-full flex flex-col overflow-hidden" style={{ background: '#0c1a1f' }}>
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b flex-shrink-0" style={{ borderColor: '#1e2a2e' }}>
        <div>
          <div className="text-sm font-mono font-bold" style={{ color: '#e8e0d4' }}>{agent.name}</div>
          <div className="text-body-xs font-mono mt-0.5" style={{ color: '#64748b' }}>{agent.id}</div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleCopy}
            className="flex items-center gap-1 px-2.5 py-1 rounded text-body-xs font-mono"
            style={{ border: '1px solid #1e2a2e', color: copied ? '#22c55e' : '#64748b', background: 'transparent' }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 13 }}>{copied ? 'check' : 'content_copy'}</span>
            {copied ? 'Copied!' : 'Copy YAML'}
          </button>
          <button onClick={onClose}>
            <span className="material-symbols-outlined" style={{ fontSize: 18, color: '#64748b' }}>close</span>
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-auto px-5 py-4 space-y-5">
        {/* Description */}
        <div>
          <div className="text-body-xs font-mono uppercase tracking-widest mb-1" style={{ color: '#3d4a50' }}>Description</div>
          <div className="text-xs font-mono" style={{ color: '#9a9080' }}>{agent.description || '—'}</div>
        </div>

        {/* Meta grid */}
        <div className="grid grid-cols-2 gap-3">
          {[
            { label: 'Workflow', value: agent.workflow },
            { label: 'Role', value: agent.role },
            { label: 'Timeout', value: agent.timeout_s ? `${agent.timeout_s}s` : '—' },
            { label: 'Model', value: agent.llm_config?.model || 'default' },
          ].map(({ label, value }) => (
            <div key={label} className="rounded p-2.5" style={{ background: '#0a1214', border: '1px solid #1a2428' }}>
              <div className="text-body-xs font-mono uppercase tracking-widest mb-1" style={{ color: '#3d4a50' }}>{label}</div>
              <div className="text-xs font-mono truncate" style={{ color: '#e8e0d4' }}>{value}</div>
            </div>
          ))}
        </div>

        {/* Tools */}
        <div>
          <div className="text-body-xs font-mono uppercase tracking-widest mb-2" style={{ color: '#3d4a50' }}>Tools</div>
          {agent.tools.length === 0 ? (
            <div className="text-xs font-mono" style={{ color: '#3d4a50' }}>No tools defined</div>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {agent.tools.map(t => (
                <span
                  key={t}
                  className="px-2 py-0.5 rounded text-body-xs font-mono"
                  style={{ background: 'rgba(7,182,213,0.08)', border: '1px solid rgba(7,182,213,0.2)', color: '#07b6d5' }}
                >
                  {t}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Standalone invocation — disabled */}
        <div className="rounded p-3" style={{ background: '#0a1214', border: '1px solid #1a2428' }}>
          <div className="flex items-center gap-2 mb-1">
            <span className="material-symbols-outlined" style={{ fontSize: 14, color: '#3d4a50' }}>play_circle</span>
            <span className="text-xs font-mono font-semibold" style={{ color: '#3d4a50' }}>Try it</span>
            <span className="text-body-xs font-mono px-1.5 py-0.5 rounded" style={{ background: '#1a2428', color: '#4a5568' }}>COMING SOON</span>
          </div>
          <div className="text-body-xs font-mono" style={{ color: '#3d4a50' }}>
            Standalone agent invocation available after platform backend ships.
          </div>
        </div>

        {/* Recent executions */}
        <div>
          <div className="text-body-xs font-mono uppercase tracking-widest mb-2" style={{ color: '#3d4a50' }}>Recent Executions</div>
          {executions.length === 0 ? (
            <div className="text-xs font-mono" style={{ color: '#3d4a50' }}>No recent executions</div>
          ) : (
            <div className="space-y-1.5">
              {executions.slice(0, 5).map(ex => (
                <div
                  key={ex.execution_id}
                  className="flex items-center justify-between text-body-xs font-mono rounded px-2.5 py-2"
                  style={{ background: '#0a1214', border: '1px solid #1a2428' }}
                >
                  <span style={{ color: STATUS_COLOR[ex.status] || '#64748b' }}>● {ex.status}</span>
                  <span style={{ color: '#4a5568' }}>{ex.duration_ms ? `${(ex.duration_ms / 1000).toFixed(1)}s` : '—'}</span>
                  <span style={{ color: '#3d4a50' }}>{ex.started_at ? new Date(ex.started_at).toLocaleTimeString() : '—'}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default AgentDetailPanel;
