import React from 'react';
import type { V4SessionStatus, TaskEvent } from '../../types';

/**
 * AGENTS card — promoted to top of Navigator column in PR 5.
 *
 * Fuses the old left-panel Agent Pulse Indicator (deleted in PR 2) into
 * the right panel's existing Agent Status Matrix. The card tells one
 * story top-to-bottom in three time horizons:
 *
 *   NOW         — agents currently running (pulsing capsules)
 *   inventory   — each agent's final status + token count
 *   total       — session-wide token footer
 *
 * When no agents are active, the NOW strip collapses to height 0.
 * When all agents are pending at session start, the NOW strip simply
 * doesn't render.
 */

interface AgentRow {
  name: string;
  code: string;
  status: 'pending' | 'active' | 'complete' | 'error';
  tokens: number;
  key: string;    // backend agent_name key, e.g. 'log_agent'
}

// Identity color per agent (shared convention with the editorial log's
// left-borders). Used only in the NOW strip's pulsing capsules.
const AGENT_PILL_COLOR: Record<string, string> = {
  log_agent:      'bg-wr-severity-high/20 text-red-400 border-wr-severity-high/40',
  metrics_agent:  'bg-wr-severity-medium/20 text-amber-400 border-wr-severity-medium/40',
  k8s_agent:      'bg-orange-500/20 text-orange-400 border-orange-500/40',
  tracing_agent:  'bg-violet-500/20 text-violet-400 border-violet-500/40',
  code_agent:     'bg-blue-500/20 text-blue-400 border-blue-500/40',
  change_agent:   'bg-emerald-500/20 text-emerald-400 border-emerald-500/40',
};

function buildAgentRows(
  status: V4SessionStatus | null,
  events: TaskEvent[],
): AgentRow[] {
  const agents: { key: string; name: string; code: string }[] = [
    { key: 'log_agent',     name: 'Log Analyzer',     code: 'L' },
    { key: 'metrics_agent', name: 'Metric Scanner',   code: 'M' },
    { key: 'k8s_agent',     name: 'K8s Probe',        code: 'K' },
    { key: 'tracing_agent', name: 'Trace Walker',     code: 'T' },
    { key: 'code_agent',    name: 'Code Navigator',   code: 'N' },
    { key: 'change_agent',  name: 'Change Intel',     code: 'C' },
  ];

  const started = new Set<string>();
  const completed = new Set<string>();
  const errored = new Set<string>();
  for (const e of events) {
    if (e.event_type === 'started') started.add(e.agent_name);
    if (e.event_type === 'summary' || e.event_type === 'success') completed.add(e.agent_name);
    if (e.event_type === 'error') errored.add(e.agent_name);
  }

  const tokenMap: Record<string, number> = {};
  status?.token_usage?.forEach((t) => { tokenMap[t.agent_name] = t.total_tokens; });

  return agents.map((a) => ({
    key: a.key,
    name: a.name,
    code: a.code,
    status: errored.has(a.key)   ? 'error'    :
            completed.has(a.key) ? 'complete' :
            started.has(a.key)   ? 'active'   : 'pending',
    tokens: tokenMap[a.key] || 0,
  }));
}

// ── NOW strip ──────────────────────────────────────────────────────

const LiveAgentStrip: React.FC<{ rows: AgentRow[] }> = ({ rows }) => {
  const active = rows.filter((r) => r.status === 'active');
  if (active.length === 0) return null;
  return (
    <div
      className="mb-3 pb-3 border-b border-wr-border"
      data-testid="live-agent-strip"
    >
      <div className="text-[10px] font-bold text-slate-500 uppercase tracking-[0.15em] mb-1.5">
        Now
      </div>
      <div className="flex flex-wrap gap-1.5">
        {active.map((a) => (
          <span
            key={a.key}
            data-testid={`live-agent-${a.key}`}
            className={
              'text-body-xs px-2 py-0.5 rounded-full border font-bold uppercase animate-pulse ' +
              (AGENT_PILL_COLOR[a.key] ?? 'bg-slate-500/20 text-slate-400 border-slate-500/40')
            }
          >
            {a.name.replace(/_/g, ' ')}
          </span>
        ))}
      </div>
    </div>
  );
};

// ── Inventory row ──────────────────────────────────────────────────

const InventoryRow: React.FC<{ row: AgentRow }> = ({ row }) => (
  <div className="flex items-center gap-2" data-testid={`agents-row-${row.key}`}>
    <span
      className={
        'w-5 h-5 rounded-full flex items-center justify-center text-body-xs font-bold ' +
        (row.code === 'L' ? 'bg-wr-severity-high/20 text-red-400' :
         row.code === 'M' ? 'bg-wr-severity-medium/20 text-amber-400' :
         row.code === 'K' ? 'bg-orange-500/20 text-orange-400' :
         row.code === 'C' ? 'bg-emerald-500/20 text-emerald-400' :
         row.code === 'T' ? 'bg-violet-500/20 text-violet-400' :
         row.code === 'N' ? 'bg-blue-500/20 text-blue-400' :
         'bg-slate-500/20 text-slate-400')
      }
    >
      {row.code}
    </span>
    <span className="text-body-xs text-slate-300 flex-1">{row.name}</span>
    <span
      className={
        'w-2 h-2 rounded-full ' +
        (row.status === 'active'   ? 'bg-amber-400 animate-pulse' :
         row.status === 'complete' ? 'bg-green-500' :
         row.status === 'error'    ? 'bg-red-500' : 'bg-slate-600')
      }
      role="status"
      aria-label={`${row.name}: ${row.status}`}
      title={row.status}
    />
    {row.tokens > 0 && (
      <span className="text-body-xs font-mono text-slate-400">{row.tokens.toLocaleString()}</span>
    )}
  </div>
);

// ── Component ──────────────────────────────────────────────────────

interface AgentsCardProps {
  status: V4SessionStatus | null;
  events: TaskEvent[];
}

const AgentsCard: React.FC<AgentsCardProps> = ({ status, events }) => {
  const rows = buildAgentRows(status, events);
  const totalTokens = rows.reduce((s, r) => s + r.tokens, 0);

  return (
    <section data-testid="agents-card">
      <h3 className="text-body-xs font-bold text-slate-400 uppercase tracking-widest mb-2">
        Agents
      </h3>
      <div className="bg-wr-bg/40 border border-wr-border rounded-lg p-3">
        <LiveAgentStrip rows={rows} />
        <div className="space-y-2">
          {rows.map((row) => (
            <InventoryRow key={row.key} row={row} />
          ))}
          {totalTokens > 0 && (
            <div className="border-t border-wr-border-strong pt-2 flex justify-between">
              <span className="text-body-xs text-slate-400">Total</span>
              <span
                className="text-body-xs font-mono text-slate-400"
                data-testid="agents-total-tokens"
              >
                {totalTokens.toLocaleString()} tokens
              </span>
            </div>
          )}
        </div>
      </div>
    </section>
  );
};

export default AgentsCard;
