import React, { useState, useEffect, useCallback } from 'react';
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

  // If an agent is selected, show detail view
  if (selectedAgent) {
    return (
      <AgentDetailView
        agent={selectedAgent}
        onBack={() => setSelectedAgent(null)}
      />
    );
  }

  const filteredAgents = data?.agents.filter((a) => a.workflow === activeTab) ?? [];
  const appCount = data?.agents.filter((a) => a.workflow === 'app_diagnostics').length ?? 0;
  const clusterCount = data?.agents.filter((a) => a.workflow === 'cluster_diagnostics').length ?? 0;

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ backgroundColor: '#0f2023' }}>
      <AgentMatrixHeader onGoHome={onGoHome} />

      {/* Loading state */}
      {loading && (
        <div className="flex-1 flex items-center justify-center">
          <div className="flex flex-col items-center gap-4">
            <div className="w-10 h-10 rounded-full border-2 border-t-transparent animate-spin" style={{ borderColor: '#07b6d5', borderTopColor: 'transparent' }} />
            <span className="text-xs font-mono uppercase tracking-widest" style={{ color: '#64748b' }}>
              Scanning neural workforce...
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
              style={{ fontFamily: 'Material Symbols Outlined', color: '#ef4444' }}
            >
              error
            </span>
            <p className="text-sm" style={{ color: '#ef4444' }}>{error}</p>
            <button
              onClick={fetchAgents}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium border transition-colors hover:text-white"
              style={{ borderColor: '#224349', color: '#94a3b8' }}
            >
              <span className="material-symbols-outlined text-base" style={{ fontFamily: 'Material Symbols Outlined' }}>refresh</span>
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
          />
          <div className="flex-1 overflow-y-auto">
            <AgentGrid agents={filteredAgents} onSelectAgent={setSelectedAgent} />
          </div>
          <AgentMatrixFooter summary={data.summary} />
        </>
      )}
    </div>
  );
};

export default AgentMatrixView;
