import React, { useState, useEffect } from 'react';
import { API_BASE_URL } from '../../services/api';

interface AgentStats {
  agent_name: string;
  calls: number;
  tokens: string;
  cost_usd: number;
  latency_ms: number;
  source: string;
  success_rate: number;
}

interface AgentCostBreakdownProps {
  sessionId: string;
  visible: boolean;
  onClose: () => void;
}

const AgentCostBreakdown: React.FC<AgentCostBreakdownProps> = ({ sessionId, visible, onClose }) => {
  const [agents, setAgents] = useState<Record<string, AgentStats>>({});
  const [totals, setTotals] = useState({ calls: 0, cost: 0, latency: 0, inputTokens: 0, outputTokens: 0 });
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!visible) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [visible, onClose]);

  useEffect(() => {
    if (!visible) return;
    const fetchData = async () => {
      setError(false);
      try {
        const res = await fetch(`${API_BASE_URL}/api/v4/session/${sessionId}/llm-summary`);
        if (res.ok) {
          const data = await res.json();
          const summary = data.llm_summary;
          if (summary) {
            setAgents(summary.per_agent || {});
            setTotals({
              calls: summary.total_calls,
              cost: summary.total_cost_usd,
              latency: summary.total_latency_ms,
              inputTokens: summary.total_input_tokens,
              outputTokens: summary.total_output_tokens,
            });
          }
        }
      } catch { setError(true); }
    };
    fetchData();
  }, [sessionId, visible]);

  if (!visible) return null;

  const agentList = Object.values(agents).sort((a, b) => b.cost_usd - a.cost_usd);

  return (
    <div className="absolute top-full right-0 mt-1 z-50 bg-wr-inset border border-wr-border-subtle rounded-lg shadow-xl w-[min(480px,calc(100vw-2rem))] p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">LLM Cost Breakdown</span>
        <button onClick={onClose} aria-label="Close cost breakdown" onKeyDown={(e) => { if (e.key === 'Escape') onClose(); }} className="text-slate-600 hover:text-slate-300">
          <span className="material-symbols-outlined text-[14px]">close</span>
        </button>
      </div>

      {error && (
        <p className="text-[11px] text-red-400 py-4 text-center">Failed to load cost data</p>
      )}

      {!error && <table className="w-full text-[10px] font-mono">
        <thead>
          <tr className="text-slate-500 border-b border-wr-border-subtle">
            <th className="text-left py-1 pr-2">Agent</th>
            <th className="text-right py-1 px-1">Calls</th>
            <th className="text-right py-1 px-1">Tokens</th>
            <th className="text-right py-1 px-1">Cost</th>
            <th className="text-right py-1 px-1">Time</th>
            <th className="text-right py-1 pl-1">Status</th>
          </tr>
        </thead>
        <tbody>
          {agentList.map(agent => (
            <tr key={agent.agent_name} className="text-slate-300 border-b border-wr-border-subtle/50 hover:bg-wr-bg">
              <td className="py-1.5 pr-2 truncate max-w-[100px]">{agent.agent_name.replace('cluster_', '')}</td>
              <td className="text-right py-1.5 px-1">{agent.calls}</td>
              <td className="text-right py-1.5 px-1 text-slate-500">{agent.tokens}</td>
              <td className="text-right py-1.5 px-1 text-wr-accent">${agent.cost_usd.toFixed(3)}</td>
              <td className="text-right py-1.5 px-1">{(agent.latency_ms / 1000).toFixed(1)}s</td>
              <td className="text-right py-1.5 pl-1">
                {agent.source === 'heuristic' ? (
                  <span className="text-amber-400" title="Heuristic fallback">&#x26A0;</span>
                ) : agent.success_rate >= 1 ? (
                  <span className="text-emerald-400">&#x2713;</span>
                ) : (
                  <span className="text-red-400">&#x2717;</span>
                )}
                <span className="ml-1 text-slate-600">{agent.source === 'heuristic' ? 'Heur' : 'LLM'}</span>
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="text-slate-400 border-t border-wr-border-subtle font-semibold">
            <td className="py-1.5 pr-2">Total</td>
            <td className="text-right py-1.5 px-1">{totals.calls}</td>
            <td className="text-right py-1.5 px-1 text-slate-500">{Math.round(totals.inputTokens/1000)}K/{Math.round(totals.outputTokens/1000)}K</td>
            <td className="text-right py-1.5 px-1 text-wr-accent">${totals.cost.toFixed(3)}</td>
            <td className="text-right py-1.5 px-1">{(totals.latency / 1000).toFixed(1)}s</td>
            <td></td>
          </tr>
        </tfoot>
      </table>}
    </div>
  );
};

export default AgentCostBreakdown;
