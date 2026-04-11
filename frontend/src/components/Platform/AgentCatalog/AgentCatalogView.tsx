import React, { useState, useMemo } from 'react';
import { useAgentCatalog } from './useAgentCatalog';
import AgentCatalogCard from './AgentCatalogCard';
import AgentDetailPanel from './AgentDetailPanel';
import type { CatalogAgent } from './useAgentCatalog';

const WORKFLOWS = ['all', 'app_diagnostics', 'cluster_diagnostics', 'network', 'database'];

const AgentCatalogView: React.FC = () => {
  const { agents, loading, error, refresh } = useAgentCatalog();
  const [search, setSearch] = useState('');
  const [workflowFilter, setWorkflowFilter] = useState('all');
  const [selected, setSelected] = useState<CatalogAgent | null>(null);

  const filtered = useMemo(() => agents.filter(a => {
    const matchesSearch = !search ||
      a.name.toLowerCase().includes(search.toLowerCase()) ||
      a.id.toLowerCase().includes(search.toLowerCase());
    const matchesWorkflow = workflowFilter === 'all' || a.workflow === workflowFilter;
    return matchesSearch && matchesWorkflow;
  }), [agents, search, workflowFilter]);

  return (
    <div className="flex h-full" style={{ background: '#0a1214' }}>
      {/* Left: catalog list */}
      <div className="flex flex-col" style={{ width: selected ? 360 : '100%', borderRight: selected ? '1px solid #1e2a2e' : 'none', transition: 'width 0.2s' }}>
        {/* Header */}
        <div className="px-5 pt-5 pb-3 border-b" style={{ borderColor: '#1e2a2e' }}>
          <div className="flex items-center justify-between mb-3">
            <div>
              <h1 className="text-base font-mono font-bold" style={{ color: '#e8e0d4' }}>Agent Catalog</h1>
              <p className="text-xs font-mono mt-0.5" style={{ color: '#64748b' }}>
                {agents.length} agents · {agents.filter(a => a.status === 'active').length} active
              </p>
            </div>
            <button onClick={refresh} className="p-1.5 rounded" style={{ color: '#64748b' }}>
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>refresh</span>
            </button>
          </div>

          {/* Search */}
          <div className="relative mb-2">
            <span className="material-symbols-outlined absolute left-2 top-1/2 -translate-y-1/2" style={{ color: '#64748b', fontSize: 15 }}>search</span>
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search agents..."
              className="w-full pl-8 pr-3 py-1.5 rounded text-xs font-mono outline-none"
              style={{ background: '#0f1e22', border: '1px solid #1e2a2e', color: '#e8e0d4' }}
            />
          </div>

          {/* Workflow filter pills */}
          <div className="flex gap-1 flex-wrap">
            {WORKFLOWS.map(w => (
              <button
                key={w}
                onClick={() => setWorkflowFilter(w)}
                className="px-2 py-0.5 rounded text-body-xs font-mono transition-colors"
                style={{
                  background: workflowFilter === w ? 'rgba(7,182,213,0.15)' : 'transparent',
                  border: `1px solid ${workflowFilter === w ? '#07b6d5' : '#1e2a2e'}`,
                  color: workflowFilter === w ? '#07b6d5' : '#64748b',
                }}
              >
                {w === 'all' ? 'All' : w.replace(/_/g, ' ')}
              </button>
            ))}
          </div>
        </div>

        {/* Grid */}
        <div className="flex-1 overflow-auto p-4">
          {loading && (
            <div className="flex items-center justify-center h-32 text-xs font-mono" style={{ color: '#64748b' }}>
              Loading agents...
            </div>
          )}
          {error && (
            <div className="flex items-center justify-center h-32 text-xs font-mono" style={{ color: '#ef4444' }}>
              {error}
            </div>
          )}
          {!loading && !error && (
            <div className="grid gap-2" style={{ gridTemplateColumns: selected ? '1fr' : 'repeat(auto-fill, minmax(220px, 1fr))' }}>
              {filtered.map(agent => (
                <AgentCatalogCard
                  key={agent.id}
                  agent={agent}
                  selected={selected?.id === agent.id}
                  onClick={() => setSelected(selected?.id === agent.id ? null : agent)}
                />
              ))}
            </div>
          )}
          {!loading && !error && filtered.length === 0 && (
            <div className="text-xs font-mono text-center py-12" style={{ color: '#64748b' }}>
              No agents match your filter.
            </div>
          )}
        </div>
      </div>

      {/* Right: detail panel */}
      {selected && (
        <div className="flex-1 overflow-hidden">
          <AgentDetailPanel agent={selected} onClose={() => setSelected(null)} />
        </div>
      )}
    </div>
  );
};

export default AgentCatalogView;
