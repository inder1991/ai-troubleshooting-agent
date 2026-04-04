import React, { useState, useEffect, useCallback } from 'react';
import { API_BASE_URL } from '../../services/api';

interface LLMSummary {
  session_id: string;
  scan_mode: string;
  total_calls: number;
  successful_calls: number;
  failed_calls: number;
  fallback_calls: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_latency_ms: number;
  total_cost_usd: number;
  budget_used_pct: number;
  per_agent: Record<string, AgentStats>;
  rate_limit_hits: number;
  timeout_count: number;
  parse_failures: number;
}

interface AgentStats {
  agent_name: string;
  calls: number;
  tokens: string;
  cost_usd: number;
  latency_ms: number;
  source: string;
  success_rate: number;
}

interface LLMCostBadgeProps {
  sessionId: string;
  phase: string;
  onToggleBreakdown?: () => void;
}

const LLMCostBadge: React.FC<LLMCostBadgeProps> = ({ sessionId, phase, onToggleBreakdown }) => {
  const [summary, setSummary] = useState<LLMSummary | null>(null);
  const [error, setError] = useState(false);

  const fetchSummary = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v4/session/${sessionId}/llm-summary`);
      if (res.ok) {
        const data = await res.json();
        if (data.llm_summary) setSummary(data.llm_summary);
      }
    } catch { setError(true); }
  }, [sessionId]);

  useEffect(() => {
    fetchSummary();
    const interval = setInterval(fetchSummary, 10000);
    return () => clearInterval(interval);
  }, [fetchSummary]);

  if (error || !summary) return null;

  const budgetPct = Math.round(summary.budget_used_pct * 100);
  const isWarning = budgetPct > 80;
  const costStr = summary.total_cost_usd < 0.01
    ? `<$0.01`
    : `$${summary.total_cost_usd.toFixed(2)}`;
  const latencyStr = summary.total_latency_ms > 1000
    ? `${(summary.total_latency_ms / 1000).toFixed(0)}s`
    : `${summary.total_latency_ms}ms`;

  return (
    <button
      onClick={onToggleBreakdown}
      aria-label="Toggle LLM cost breakdown"
      className={`flex items-center gap-2 px-2.5 py-1 rounded text-[10px] font-mono border transition-colors ${
        isWarning
          ? 'border-amber-500/40 bg-amber-500/10 text-amber-400'
          : 'border-wr-border-subtle bg-wr-inset text-slate-400 hover:border-wr-accent/30'
      }`}
      title="Click for per-agent breakdown"
    >
      <span className={`w-1.5 h-1.5 rounded-full ${phase === 'complete' ? 'bg-emerald-400' : 'bg-amber-400 animate-pulse'}`} />
      <span className="text-slate-500 capitalize">{summary.scan_mode}</span>
      <span className="text-slate-600">|</span>
      <span className="text-wr-accent">{costStr}</span>
      <span className="text-slate-600">|</span>
      <span>{summary.total_calls} calls</span>
      <span className="text-slate-600">|</span>
      <span>{latencyStr}</span>
      <span className="text-slate-600">|</span>
      <span className={isWarning ? 'text-amber-400' : ''}>{budgetPct}%</span>
    </button>
  );
};

export default LLMCostBadge;
