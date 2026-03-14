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

function formatAgentName(name: string): string {
  return name.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join(' ');
}

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
    <div className="flex flex-col overflow-hidden">
      {/* Top bar */}
      <header
        className="flex items-center gap-4 px-4 py-3 border-b flex-shrink-0"
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

        <div className="flex-1" style={{ animation: 'fadeSlideUp 250ms cubic-bezier(0.25, 1, 0.5, 1) 100ms both' }}>
          <div className="flex items-center gap-3">
            <h1 className="text-lg font-bold text-white">{formatAgentName(agent.name)}</h1>
            <span
              className="text-[9px] font-semibold uppercase px-2 py-0.5 rounded-full"
              style={{ backgroundColor: 'rgba(224,159,62,0.15)', color: '#e09f3e' }}
            >
              {agent.workflow.replace(/_/g, ' ')}
            </span>
            <span
              className="flex items-center gap-1.5 text-[10px] uppercase px-2 py-0.5 rounded-full"
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

      {/* Single column layout — activity first, config second */}
      <div className="flex-1 overflow-y-auto p-4">
        <div className="flex flex-col gap-4">
          {/* Activity first — what operators care about */}
          <ExecutionTracePanel trace={latestTrace} isLoading={loadingExecs} />
          <RecentCasesPanel executions={executions} isLoading={loadingExecs} />

          {/* Config second — rarely changes */}
          <ToolbeltPanel
            tools={agent.tools}
            toolHealthChecks={agent.tool_health_checks}
            degradedTools={agent.degraded_tools}
          />
          <CoreConfigPanel llmConfig={agent.llm_config} timeoutS={agent.timeout_s} />
          <NeuralArchitectureDiagram stages={agent.architecture_stages} />
        </div>
      </div>
    </div>
  );
};

export default AgentDetailView;
