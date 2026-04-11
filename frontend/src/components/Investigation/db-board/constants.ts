/** Shared constants for the Database Investigation Board */

// Visualization color scales — single source of truth
export const VIZ_COLORS = {
  excellent: '#10b981',   // emerald
  good: '#d4922e',        // tan/amber
  warning: '#f59e0b',     // amber
  danger: '#f97316',      // orange
  critical: '#ef4444',    // red
  neutral: '#64748b',     // slate
} as const;

export const PLAN_NODE_COLORS: Record<string, string> = {
  'Seq Scan': '#ef4444',
  'Index Scan': '#10b981',
  'Index Only Scan': '#10b981',
  'Sort': '#f59e0b',
  'Hash': '#a78bfa',
  'Hash Join': '#a78bfa',
  'Nested Loop': '#d4922e',
  'Merge Join': '#d4922e',
  'Aggregate': '#3b82f6',
  'default': '#64748b',
};

export const DB_AGENTS = [
  { id: 'query_analyst', label: 'Query Analyst', icon: 'query_stats', borderColor: 'border-l-amber-400', color: 'text-amber-400' },
  { id: 'health_analyst', label: 'Health Analyst', icon: 'monitor_heart', borderColor: 'border-l-emerald-400', color: 'text-emerald-400' },
  { id: 'schema_analyst', label: 'Schema Analyst', icon: 'schema', borderColor: 'border-l-violet-400', color: 'text-violet-400' },
  { id: 'synthesizer', label: 'Synthesizer', icon: 'hub', borderColor: 'border-l-duck-accent', color: 'text-duck-accent' },
] as const;

export const DB_AGENT_IDS = DB_AGENTS.map((a) => a.id);

export type EventStatus = 'success' | 'error' | 'started' | 'progress' | 'finding' | 'warning' | 'pending';

export type AgentState = 'pending' | 'scanning' | 'complete' | 'error';

export const AGENT_STATE_ICON: Record<AgentState, { icon: string; cls: string }> = {
  pending: { icon: 'radio_button_unchecked', cls: 'text-slate-400' },
  scanning: { icon: 'pending', cls: 'text-amber-400 animate-spin' },
  complete: { icon: 'check_circle', cls: 'text-emerald-400' },
  error: { icon: 'error', cls: 'text-red-400' },
};

export const EVENT_DOT_COLOR: Record<string, string> = {
  error: 'bg-red-400',
  finding: 'bg-amber-400',
  success: 'bg-emerald-400',
  warning: 'bg-amber-400',
  reasoning: 'bg-duck-accent',
  started: 'bg-slate-500',
  progress: 'bg-slate-500',
};

export const SEVERITY_BORDER: Record<string, string> = {
  critical: 'border-l-red-500',
  high: 'border-l-orange-500',
  medium: 'border-l-amber-500',
  low: 'border-l-emerald-500',
};

export const SEVERITY_TEXT: Record<string, string> = {
  critical: 'text-red-400',
  high: 'text-orange-400',
  medium: 'text-amber-400',
  low: 'text-emerald-400',
};

export const SEVERITY_BADGE: Record<string, string> = {
  critical: 'bg-wr-severity-high/10 text-red-400 border-wr-severity-high/30',
  high: 'bg-orange-500/10 text-orange-400 border-orange-500/30',
  medium: 'bg-wr-severity-medium/10 text-amber-400 border-wr-severity-medium/30',
  low: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
};

/** Derive agent state from its event stream */
export function deriveAgentState(agentEvents: Array<{ event_type: string }>): AgentState {
  if (agentEvents.length === 0) return 'pending';
  const last = agentEvents[agentEvents.length - 1];
  if (last.event_type === 'success') return 'complete';
  if (last.event_type === 'error') return 'error';
  return 'scanning';
}

// Severity visual styles — single source of truth
export const SEV_DOT: Record<string, string> = {
  critical: 'bg-red-400',
  high: 'bg-orange-400',
  medium: 'bg-amber-400',
  low: 'bg-emerald-400',
};

export const SEV_BADGE: Record<string, string> = {
  critical: 'bg-wr-severity-high/10 text-red-400 border-wr-severity-high/30',
  high: 'bg-orange-500/10 text-orange-400 border-orange-500/30',
  medium: 'bg-wr-severity-medium/10 text-amber-400 border-wr-severity-medium/30',
  low: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
};

export function formatDuration(sec: number): string {
  if (sec >= 3600) return `${Math.floor(sec / 3600)}h ${Math.floor((sec % 3600) / 60)}m`;
  return `${Math.floor(sec / 60)}m ${sec % 60}s`;
}

/** Get status icon for an event type */
export function getStatusIcon(status: string): { icon: string; cls: string } {
  if (status === 'success') return { icon: 'check_circle', cls: 'text-emerald-400' };
  if (status === 'error') return { icon: 'error', cls: 'text-red-400' };
  if (status === 'started' || status === 'progress') return { icon: 'progress_activity', cls: 'text-amber-400 animate-spin' };
  return { icon: 'radio_button_unchecked', cls: 'text-slate-400' };
}
