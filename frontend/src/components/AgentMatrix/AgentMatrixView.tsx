import React, { useState, useEffect, useCallback, useMemo } from 'react';
import type { AgentInfo, AgentMatrixResponse } from '../../types';
import { getAgents } from '../../services/api';
import AgentMatrixHeader from './AgentMatrixHeader';
import WorkflowTabs from './WorkflowTabs';
import type { WorkflowTab } from './WorkflowTabs';
import AgentGrid from './AgentGrid';
import AgentMatrixFooter from './AgentMatrixFooter';
import AgentDetailView from './AgentDetailView';

interface AgentMatrixViewProps {
  onGoHome: () => void;
}

const AgentMatrixView: React.FC<AgentMatrixViewProps> = ({ onGoHome }) => {
  const [data, setData] = useState<AgentMatrixResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<WorkflowTab>('app_diagnostics');
  const [selectedAgent, setSelectedAgent] = useState<AgentInfo | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');

  const fetchAgents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getAgents();
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch agents');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  const filteredAgents = (data?.agents ?? [])
    .filter((a) => a.workflow === activeTab)
    .filter((a) => {
      if (!searchQuery) return true;
      const q = searchQuery.toLowerCase();
      return (
        a.name.toLowerCase().includes(q) ||
        a.description.toLowerCase().includes(q) ||
        a.tools.some((t) => t.toLowerCase().includes(q))
      );
    })
    .filter((a) => statusFilter === 'all' || a.status === statusFilter);

  const appCount = data?.agents.filter((a) => a.workflow === 'app_diagnostics').length ?? 0;
  const clusterCount = data?.agents.filter((a) => a.workflow === 'cluster_diagnostics').length ?? 0;
  const dbCount = data?.agents.filter((a) => a.workflow === 'database_diagnostics').length ?? 0;
  const assistantCount = data?.agents.filter((a) => a.workflow === 'assistant').length ?? 0;

  const degradedByWorkflow = useMemo(() => {
    if (!data) return {};
    const counts: Record<string, number> = {};
    for (const a of data.agents) {
      if (a.status === 'degraded' || a.status === 'offline') {
        counts[a.workflow] = (counts[a.workflow] || 0) + 1;
      }
    }
    return counts;
  }, [data]);

  const STATUS_DOTS: Record<string, string> = {
    all: '#64748b',
    active: '#e09f3e',
    degraded: '#f59e0b',
    offline: '#ef4444',
  };

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ backgroundColor: '#1a1814' }}>
      <AgentMatrixHeader onGoHome={onGoHome} />

      {/* Loading state */}
      {loading && (
        <div className="flex-1 flex items-center justify-center" style={{ animation: 'fadeSlideUp 300ms cubic-bezier(0.25, 1, 0.5, 1)' }}>
          <div className="flex flex-col items-center gap-4">
            <div className="w-10 h-10 rounded-full border-2 border-t-transparent animate-spin" style={{ borderColor: '#e09f3e', borderTopColor: 'transparent' }} />
            <span className="text-xs font-mono uppercase tracking-widest" style={{ color: '#64748b' }}>
              Loading agents...
            </span>
          </div>
        </div>
      )}

      {/* Error state */}
      {!loading && error && (
        <div className="flex-1 flex items-center justify-center">
          <div className="flex flex-col items-center gap-4 text-center max-w-md">
            <span
              className="material-symbols-outlined text-4xl"
              style={{ color: '#ef4444' }}
            >
              error
            </span>
            <p className="text-sm" style={{ color: '#ef4444' }}>{error}</p>
            <button
              onClick={fetchAgents}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium border transition-colors hover:text-white"
              style={{ borderColor: '#3d3528', color: '#8a7e6b' }}
            >
              <span className="material-symbols-outlined text-base">refresh</span>
              Retry
            </button>
          </div>
        </div>
      )}

      {/* Main content */}
      {!loading && !error && data && (
        <>
          <WorkflowTabs
            activeTab={activeTab}
            onTabChange={setActiveTab}
            appCount={appCount}
            clusterCount={clusterCount}
            dbCount={dbCount}
            assistantCount={assistantCount}
            degradedByWorkflow={degradedByWorkflow}
          />

          {/* Search + Status Filter */}
          <div className="flex items-center gap-3 px-8 pb-3">
            <div className="flex items-center gap-2 flex-1 max-w-md">
              <span className="material-symbols-outlined text-base" style={{ color: '#64748b' }}>search</span>
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search agents by name, description, or tool..."
                className="flex-1 bg-transparent text-sm text-white placeholder:text-slate-600 outline-none"
              />
              {searchQuery && (
                <button onClick={() => setSearchQuery('')} className="text-slate-600 hover:text-slate-300">
                  <span className="material-symbols-outlined text-sm">close</span>
                </button>
              )}
            </div>
            <div className="flex items-center gap-1.5">
              {['all', 'active', 'degraded', 'offline'].map((status) => (
                <button
                  key={status}
                  onClick={() => setStatusFilter(status)}
                  onMouseDown={e => { e.currentTarget.style.transform = 'scale(0.95)'; }}
                  onMouseUp={e => { e.currentTarget.style.transform = 'scale(1)'; }}
                  onMouseLeave={e => { e.currentTarget.style.transform = 'scale(1)'; }}
                  className="flex items-center gap-1.5 text-body-xs uppercase px-2.5 py-1 rounded"
                  style={{
                    backgroundColor: statusFilter === status ? 'rgba(224,159,62,0.15)' : 'transparent',
                    color: statusFilter === status ? '#e09f3e' : '#64748b',
                    border: `1px solid ${statusFilter === status ? 'rgba(224,159,62,0.3)' : '#2a2520'}`,
                    transition: 'transform 100ms cubic-bezier(0.25, 1, 0.5, 1), background-color 200ms cubic-bezier(0.25, 1, 0.5, 1), color 200ms cubic-bezier(0.25, 1, 0.5, 1)',
                  }}
                >
                  <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: STATUS_DOTS[status] }} />
                  {status}
                </button>
              ))}
            </div>
          </div>

          <div className="flex-1 flex overflow-hidden">
            {/* Grid — takes full width when no agent selected, shrinks when detail open */}
            <div
              className={`${selectedAgent ? 'w-1/2 border-r' : 'w-full'} overflow-y-auto transition-all duration-300`}
              style={{ borderColor: '#2a2520' }}
            >
              <AgentGrid agents={filteredAgents} onSelectAgent={setSelectedAgent} compact={!!selectedAgent} selectedAgentId={selectedAgent?.id} />
            </div>

            {/* Detail slide-over panel */}
            {selectedAgent && (
              <div
                className="w-1/2 overflow-y-auto"
                style={{
                  backgroundColor: '#141210',
                  animation: 'slideInRight 250ms cubic-bezier(0.25, 1, 0.5, 1) forwards',
                }}
              >
                <AgentDetailView agent={selectedAgent} onBack={() => setSelectedAgent(null)} />
              </div>
            )}
          </div>
          <AgentMatrixFooter summary={data.summary} />
        </>
      )}
    </div>
  );
};

export default AgentMatrixView;
