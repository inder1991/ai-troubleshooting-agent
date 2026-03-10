import React, { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import * as Tooltip from '@radix-ui/react-tooltip';
import { getAgents } from '../../services/api';
import type { AgentInfo } from '../../types';

type VisualStatus = 'idle' | 'analyzing' | 'degraded' | 'offline';

const RECENT_THRESHOLD_MS = 60_000; // 60 seconds

const deriveVisualStatus = (agent: AgentInfo): VisualStatus => {
  if (agent.status === 'offline') return 'offline';
  if (agent.status === 'degraded') return 'degraded';
  // active + recent execution in last 60s = analyzing
  const now = Date.now();
  const hasRecent = agent.recent_executions.some(
    (ex) => now - new Date(ex.timestamp).getTime() < RECENT_THRESHOLD_MS
  );
  return hasRecent ? 'analyzing' : 'idle';
};

const dotColor: Record<VisualStatus, string> = {
  idle: 'bg-duck-surface',
  analyzing: 'bg-duck-accent animate-pulse',
  degraded: 'bg-amber-500',
  offline: 'bg-red-500',
};

const dotLabel: Record<VisualStatus, string> = {
  idle: 'Idle',
  analyzing: 'Analyzing',
  degraded: 'Degraded',
  offline: 'Offline',
};

interface ActiveOp {
  id: string;
  agentName: string;
  summary: string;
  status: VisualStatus;
  timestamp: number;
}

export const AgentFleetPulse: React.FC = () => {
  const { data, isLoading } = useQuery({
    queryKey: ['agent-fleet'],
    queryFn: getAgents,
    refetchInterval: 5000,
    staleTime: 3000,
  });

  const agents = data?.agents ?? [];
  const summary = data?.summary ?? { total: 0, active: 0, degraded: 0, offline: 0 };

  const agentsWithVisual = useMemo(
    () => agents.map((a) => ({ ...a, visual: deriveVisualStatus(a) })),
    [agents]
  );

  const activeOps = useMemo(() => {
    const now = Date.now();
    const ops: ActiveOp[] = [];
    for (const agent of agents) {
      for (const ex of agent.recent_executions) {
        const ts = new Date(ex.timestamp).getTime();
        if (now - ts < RECENT_THRESHOLD_MS) {
          ops.push({
            id: `${agent.id}-${ex.session_id}-${ex.timestamp}`,
            agentName: agent.name,
            summary: ex.summary || `Session ${ex.session_id.slice(0, 8)}`,
            status: deriveVisualStatus(agent),
            timestamp: ts,
          });
        }
      }
    }
    return ops.sort((a, b) => b.timestamp - a.timestamp).slice(0, 4);
  }, [agents]);

  const analyzingCount = agentsWithVisual.filter((a) => a.visual === 'analyzing').length;

  return (
    <div className="bg-duck-panel border border-duck-border rounded-lg h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-3 pt-3 pb-2 shrink-0">
        <h3 className="text-xs font-bold text-duck-muted uppercase tracking-wider">Agent Fleet</h3>
        {!isLoading && (
          <div className="flex items-center gap-3 text-[10px] font-mono text-slate-400">
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-duck-accent" />
              {analyzingCount}
            </span>
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
              {summary.degraded}
            </span>
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
              {summary.offline}
            </span>
          </div>
        )}
      </div>

      {/* Swarm */}
      <div className="px-3 pb-2 overflow-y-auto custom-scrollbar" style={{ maxHeight: 80 }}>
        <Tooltip.Provider delayDuration={0}>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(12px,1fr))] gap-1">
            {isLoading
              ? Array.from({ length: 25 }).map((_, i) => (
                  <div key={i} className="w-2.5 h-2.5 rounded-sm bg-duck-surface animate-pulse" />
                ))
              : agentsWithVisual.map((agent) => (
                  <Tooltip.Root key={agent.id}>
                    <Tooltip.Trigger asChild>
                      <div
                        className={`w-2.5 h-2.5 rounded-sm transition-colors duration-300 cursor-default ${dotColor[agent.visual]}`}
                      />
                    </Tooltip.Trigger>
                    <Tooltip.Portal>
                      <Tooltip.Content
                        className="z-50 bg-duck-flyout border border-duck-border rounded px-2.5 py-1.5 shadow-xl"
                        sideOffset={5}
                      >
                        <p className="text-[10px] font-bold text-white">{agent.name}</p>
                        <p className="text-[10px] text-duck-muted">
                          {dotLabel[agent.visual]} · {agent.role}
                        </p>
                        <Tooltip.Arrow className="fill-duck-border" />
                      </Tooltip.Content>
                    </Tooltip.Portal>
                  </Tooltip.Root>
                ))}
          </div>
        </Tooltip.Provider>
      </div>

      {/* Divider */}
      <div className="h-px bg-duck-border/50 mx-3" />

      {/* Ticker */}
      <div className="flex-1 overflow-hidden px-3 py-2">
        {activeOps.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <p className="text-[10px] text-duck-muted italic">All agents standing by</p>
          </div>
        ) : (
          <AnimatePresence initial={false}>
            {activeOps.map((op) => (
              <motion.div
                key={op.id}
                initial={{ opacity: 0, height: 0, y: -10 }}
                animate={{ opacity: 1, height: 'auto', y: 0 }}
                exit={{ opacity: 0, height: 0 }}
                className="flex items-start gap-2 py-1.5 border-b border-duck-border/30 last:border-0"
              >
                <span
                  className={`w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${dotColor[op.status]}`}
                />
                <div className="min-w-0">
                  <span className="text-[10px] font-bold text-duck-accent">{op.agentName}</span>
                  <span className="text-[10px] text-duck-muted ml-1 truncate">
                    → {op.summary}
                  </span>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        )}
      </div>
    </div>
  );
};
