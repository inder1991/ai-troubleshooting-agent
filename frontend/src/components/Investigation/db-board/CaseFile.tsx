import React, { useState, useMemo, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { TaskEvent } from '../../../types';
import { DB_AGENTS, AGENT_STATE_ICON, EVENT_DOT_COLOR, deriveAgentState } from './constants';
import type { AgentState } from './constants';

interface CaseFileProps {
  serviceName: string;
  sessionId: string;
  incidentId?: string;
  events: TaskEvent[];
  elapsedSec: number;
}

const CaseFile: React.FC<CaseFileProps> = ({ serviceName, sessionId, incidentId, events, elapsedSec }) => {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const agentGroups = useMemo(() => {
    return DB_AGENTS.map((agent) => {
      const agentEvents = events.filter((e) => e.agent_name === agent.id);
      return { ...agent, events: agentEvents, state: deriveAgentState(agentEvents) };
    });
  }, [events]);

  const toggle = useCallback((id: string) => setCollapsed((prev) => ({ ...prev, [id]: !prev[id] })), []);

  const m = Math.floor(elapsedSec / 60);
  const s = elapsedSec % 60;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="px-4 pt-4 pb-3 border-b border-duck-border/50 shrink-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="material-symbols-outlined text-violet-400 text-lg" aria-hidden="true">folder_open</span>
          <h3 className="text-sm font-display font-bold text-white">Case File</h3>
        </div>
        <p className="text-xs text-slate-300 font-mono">{serviceName}</p>
        <div className="flex items-center gap-3 mt-1.5">
          <span className="text-body-xs text-duck-accent font-mono">{incidentId || sessionId.slice(0, 8)}</span>
          <span className="text-body-xs text-slate-400 font-mono">{m}m {s}s</span>
        </div>
      </div>

      {/* Agent sections — no cards, just left-border accent */}
      <div className="flex-1 overflow-y-auto py-3 custom-scrollbar">
        {agentGroups.map((agent) => {
          const isCollapsed = collapsed[agent.id] ?? false;
          const si = AGENT_STATE_ICON[agent.state as AgentState];
          return (
            <div key={agent.id} className={`border-l-2 ${agent.borderColor} ml-4 mb-3`}>
              <button
                onClick={() => toggle(agent.id)}
                className="w-full flex items-center gap-2 pl-3 pr-4 py-2 md:py-1.5 hover:bg-duck-surface/30 transition-colors text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent focus-visible:outline-offset-2"
                aria-expanded={!isCollapsed}
                aria-label={`Toggle ${agent.label} events`}
              >
                <span className={`material-symbols-outlined text-[14px] ${si.cls}`}>{si.icon}</span>
                <span className="text-body-xs font-bold text-slate-300 flex-1">{agent.label}</span>
                {agent.events.length > 0 && (
                  <span className="text-body-xs text-slate-400">{agent.events.length}</span>
                )}
                <span
                  className={`material-symbols-outlined text-[12px] text-slate-500 transition-transform duration-200 ${isCollapsed ? '' : 'rotate-90'}`}
                >
                  chevron_right
                </span>
              </button>

              <AnimatePresence>
                {!isCollapsed && agent.events.length > 0 && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.2 }}
                  >
                    <div className="pl-8 pr-4 pb-2 space-y-1">
                      {agent.events.slice(-15).map((ev, i) => {
                        const isReasoning = ev.event_type === 'reasoning';
                        const isToolCall = ev.event_type === 'progress';
                        return (
                          <div key={i} className={`flex items-start gap-1.5 ${isReasoning ? 'pl-2' : ''}`}>
                            <span className={`shrink-0 mt-1.5 ${isToolCall ? 'material-symbols-outlined text-body-xs text-slate-500' : `w-1 h-1 rounded-full ${EVENT_DOT_COLOR[ev.event_type] || 'bg-slate-500'}`}`}
                              aria-hidden="true">
                              {isToolCall ? 'build' : ''}
                            </span>
                            <p className={`text-body-xs sm:text-xs leading-relaxed ${
                              isReasoning ? 'text-slate-300 font-mono' :
                              isToolCall ? 'text-slate-400 font-mono text-body-xs' :
                              'text-slate-400'
                            }`}>
                              {ev.message}
                            </p>
                          </div>
                        );
                      })}
                      {agent.events.length > 15 && (
                        <p className="text-body-xs text-slate-400 mt-1">{agent.events.length - 15} earlier events hidden</p>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default React.memo(CaseFile);
