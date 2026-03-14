import React, { useState, useEffect, useCallback } from 'react';
import type { AgentInfo, AgentExecution, AgentTraceEntry } from '../../types';
import { getAgentExecutions } from '../../services/api';
import NeuralArchitectureDiagram from './NeuralArchitectureDiagram';
import CoreConfigPanel from './CoreConfigPanel';
import ToolbeltPanel from './ToolbeltPanel';
import ExecutionTracePanel from './ExecutionTracePanel';
import RecentCasesPanel from './RecentCasesPanel';

interface AgentDetailViewProps {
  agent: AgentInfo;
  onBack: () => void;
}

const STATUS_COLORS: Record<AgentInfo['status'], string> = {
  active: '#e09f3e',
  degraded: '#f59e0b',
  offline: '#ef4444',
};

const STATUS_LABELS: Record<AgentInfo['status'], string> = {
  active: 'ONLINE',
  degraded: 'DEGRADED',
  offline: 'OFFLINE',
};

const AgentDetailView: React.FC<AgentDetailViewProps> = ({ agent, onBack }) => {
  const [executions, setExecutions] = useState<AgentExecution[]>(agent.recent_executions || []);
  const [loadingExecs, setLoadingExecs] = useState(false);
  const [latestTrace, setLatestTrace] = useState<AgentTraceEntry[] | undefined>(undefined);

  const fetchExecutions = useCallback(async () => {
    setLoadingExecs(true);
    try {
      const result = await getAgentExecutions(agent.id);
      setExecutions(result.executions);
      // Use trace from latest execution if available
      if (result.executions.length > 0 && result.executions[0].trace) {
        setLatestTrace(result.executions[0].trace);
      }
    } catch {
      // Fall back to agent.recent_executions already set
    } finally {
      setLoadingExecs(false);
    }
  }, [agent.id]);

  useEffect(() => {
    fetchExecutions();
  }, [fetchExecutions]);

  // Use trace from the first recent execution if we already have it
  useEffect(() => {
    if (!latestTrace && agent.recent_executions.length > 0 && agent.recent_executions[0].trace) {
      setLatestTrace(agent.recent_executions[0].trace);
    }
  }, [agent.recent_executions, latestTrace]);

  const statusColor = STATUS_COLORS[agent.status];

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ backgroundColor: '#1a1814' }}>
      {/* Top bar */}
      <header
        className="flex items-center gap-4 px-8 py-5 border-b flex-shrink-0"
        style={{ borderColor: '#3d3528', backgroundColor: '#0a1214' }}
      >
        <button
          onClick={onBack}
          className="flex items-center justify-center w-9 h-9 rounded-lg border transition-colors hover:text-white"
          style={{ borderColor: '#3d3528', color: '#64748b' }}
          title="Back to Agent Matrix"
        >
          <span className="material-symbols-outlined text-lg">arrow_back</span>
        </button>

        <div
          className="w-11 h-11 rounded-lg flex items-center justify-center border"
          style={{
            backgroundColor: 'rgba(224,159,62,0.1)',
            borderColor: 'rgba(224,159,62,0.2)',
          }}
        >
          <span
            className="material-symbols-outlined text-xl"
            style={{ color: '#e09f3e' }}
          >
            {agent.icon}
          </span>
        </div>

        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-lg font-mono font-bold text-white">{agent.name}</h1>
            <span
              className="text-[9px] font-mono font-semibold uppercase px-2 py-0.5 rounded-full"
              style={{ backgroundColor: 'rgba(224,159,62,0.15)', color: '#e09f3e' }}
            >
              LVL {agent.level}
            </span>
            <span
              className="flex items-center gap-1.5 text-[10px] font-mono uppercase px-2 py-0.5 rounded-full"
              style={{
                backgroundColor: `${statusColor}15`,
                color: statusColor,
              }}
            >
              <span
                className="w-1.5 h-1.5 rounded-full"
                style={{ backgroundColor: statusColor }}
              />
              {STATUS_LABELS[agent.status]}
            </span>
          </div>
          <p className="text-xs mt-0.5" style={{ color: '#8a7e6b' }}>{agent.description}</p>
        </div>
      </header>

      {/* Two-column layout */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="flex gap-6 max-w-[1600px] mx-auto">
          {/* Left column: 40% */}
          <div className="w-2/5 flex flex-col gap-4 flex-shrink-0">
            <NeuralArchitectureDiagram stages={agent.architecture_stages} />
            <CoreConfigPanel llmConfig={agent.llm_config} timeoutS={agent.timeout_s} />
            <ToolbeltPanel
              tools={agent.tools}
              toolHealthChecks={agent.tool_health_checks}
              degradedTools={agent.degraded_tools}
            />
          </div>

          {/* Right column: 60% */}
          <div className="flex-1 flex flex-col gap-4">
            <ExecutionTracePanel trace={latestTrace} isLoading={loadingExecs} />
            <RecentCasesPanel executions={executions} isLoading={loadingExecs} />
          </div>
        </div>
      </div>
    </div>
  );
};

export default AgentDetailView;
