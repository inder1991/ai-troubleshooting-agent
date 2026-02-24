import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { findingVariants, ribbonExpandVariants } from '../../styles/animations';
import { formatTime } from '../../utils/format';
import type { AgentCapsuleData, FilterMode } from './Investigator';

interface AgentCapsuleProps {
  capsule: AgentCapsuleData;
  filterMode: FilterMode;
  isActive: boolean;
}

const agentColorBar: Record<string, string> = {
  log_agent: 'bg-red-500',
  metrics_agent: 'bg-cyan-500',
  k8s_agent: 'bg-orange-500',
  tracing_agent: 'bg-violet-500',
  code_agent: 'bg-blue-500',
  change_agent: 'bg-emerald-500',
  critic: 'bg-amber-500',
  fix_generator: 'bg-pink-500',
};

const agentIcon: Record<string, string> = {
  log_agent: 'search',
  metrics_agent: 'bar_chart',
  k8s_agent: 'dns',
  tracing_agent: 'route',
  code_agent: 'code',
  change_agent: 'difference',
  critic: 'gavel',
  fix_generator: 'build',
};

export const AgentCapsule: React.FC<AgentCapsuleProps> = ({ capsule, filterMode, isActive }) => {
  const barColor = agentColorBar[capsule.agent] || 'bg-slate-500';
  const icon = agentIcon[capsule.agent] || 'circle';

  const showReasoning = filterMode === 'all' || filterMode === 'reasoning';
  const showFindings = filterMode === 'all' || filterMode === 'findings';
  const showRaw = filterMode === 'all' || filterMode === 'raw';

  return (
    <div className="relative bg-slate-800/20 border border-slate-700/30 rounded-lg overflow-hidden">
      {/* Agent Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-800/30">
        <div className={`w-1 h-4 rounded-full ${barColor}`} />
        <span
          className="material-symbols-outlined text-slate-400 text-xs"
          style={{ fontFamily: 'Material Symbols Outlined' }}
        >
          {icon}
        </span>
        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-300">
          {capsule.agent.replace(/_/g, ' ')}
        </span>
        <span className="text-[9px] text-slate-600 font-mono ml-auto">
          {formatTime(capsule.startedEvent.timestamp)}
        </span>
        {/* Status dot */}
        {isActive ? (
          <span className="w-2 h-2 rounded-full bg-cyan-500 animate-pulse" />
        ) : capsule.isComplete ? (
          <span className="material-symbols-outlined text-green-500 text-xs" style={{ fontFamily: 'Material Symbols Outlined' }}>check_circle</span>
        ) : null}
      </div>

      <div className="px-3 py-2 space-y-2">
        {/* Layer 2: Reasoning (Intelligence) */}
        {capsule.reasoningEvents.length > 0 && (
          <div className={!showReasoning ? 'semantic-dim' : undefined}>
            {capsule.reasoningEvents.map((ev, i) => (
              <p key={i} className="text-[11px] text-slate-400 italic font-mono leading-relaxed">
                {ev.message}
              </p>
            ))}
          </div>
        )}

        {/* Layer 1: Findings (Scan) */}
        {capsule.findingEvents.length > 0 && (
          <div className={!showFindings ? 'semantic-dim' : undefined}>
            <AnimatePresence initial={false}>
              {capsule.findingEvents.map((ev, i) => {
                const severity = String(ev.details?.severity || 'medium');
                const isHighSev = severity === 'critical' || severity === 'high';

                if (isHighSev) {
                  return (
                    <motion.div
                      key={`f-${i}`}
                      variants={findingVariants}
                      initial="hidden"
                      animate="visible"
                      className={`border-l-4 ${
                        severity === 'critical' ? 'border-red-500 finding-glow-red' : 'border-red-500'
                      } bg-slate-800/40 p-3 rounded-lg mb-1.5`}
                    >
                      <div className="flex items-center gap-2 text-[10px] mb-1">
                        <span
                          className="material-symbols-outlined text-red-400 text-sm"
                          style={{ fontFamily: 'Material Symbols Outlined' }}
                        >
                          lightbulb
                        </span>
                        <span className="font-bold uppercase text-red-400">{severity}</span>
                      </div>
                      <p className="text-xs text-slate-300">{ev.message.split(' — ')[0]}</p>
                    </motion.div>
                  );
                }

                return (
                  <FindingRibbon key={`f-${i}`} event={ev} severity={severity} />
                );
              })}
            </AnimatePresence>
          </div>
        )}

        {/* Layer 3: Tool Calls (Raw) — backend emits tool invocations only;
             errors are separate event_type='error' events in alertEvents */}
        {capsule.toolCallEvents.length > 0 && (
          <div className={`flex gap-1.5 flex-wrap ${!showRaw ? 'semantic-dim' : ''}`}>
            {capsule.toolCallEvents.map((ev, i) => (
              <div
                key={i}
                className="w-4 h-[2px] rounded-full tool-line-success"
                title={`${String(ev.details?.tool || 'tool')}: ${ev.message}`}
              />
            ))}
          </div>
        )}

        {/* Alert & governance events */}
        {capsule.alertEvents.length > 0 && (
          <div className="space-y-1">
            {capsule.alertEvents.map((ev, i) => {
              const isError = ev.event_type === 'error';
              const isGovernance = ev.event_type === 'fix_proposal' || ev.event_type === 'fix_approved' || ev.event_type === 'attestation_required';
              const colorClass = isError
                ? 'bg-red-500/10 border border-red-500/20 text-red-400'
                : isGovernance
                  ? 'bg-cyan-500/10 border border-cyan-500/20 text-cyan-400'
                  : 'bg-amber-500/10 border border-amber-500/20 text-amber-400';
              const iconName = isError ? 'error' : isGovernance ? 'verified_user' : 'warning';
              return (
                <div
                  key={`alert-${i}`}
                  className={`flex items-center gap-2 text-[10px] px-2 py-1 rounded ${colorClass}`}
                >
                  <span
                    className="material-symbols-outlined text-xs"
                    style={{ fontFamily: 'Material Symbols Outlined' }}
                  >
                    {iconName}
                  </span>
                  <span className="truncate">{ev.message}</span>
                </div>
              );
            })}
          </div>
        )}

        {/* Breadcrumbs summary */}
        {capsule.isComplete && capsule.breadcrumbs.length > 0 && (
          <div className="flex items-center gap-1.5 text-[9px] text-slate-600">
            <span
              className="material-symbols-outlined text-xs"
              style={{ fontFamily: 'Material Symbols Outlined' }}
            >
              attach_file
            </span>
            <span>{capsule.breadcrumbs.length} evidence trails</span>
          </div>
        )}
      </div>
    </div>
  );
};

// ─── Finding Ribbon (Medium/Low severity, expandable) ──────────────────────

const FindingRibbon: React.FC<{ event: import('../../types').TaskEvent; severity: string }> = ({ event, severity }) => {
  const [expanded, setExpanded] = useState(false);
  const sevColor = severity === 'medium' ? 'text-amber-400 border-amber-500/30' : 'text-blue-400 border-blue-500/30';

  return (
    <motion.div
      variants={findingVariants}
      initial="hidden"
      animate="visible"
      className="mb-1"
    >
      <motion.div
        variants={ribbonExpandVariants}
        animate={expanded ? 'expanded' : 'collapsed'}
        className={`border-l-2 ${severity === 'medium' ? 'border-amber-500 finding-glow-amber' : 'border-blue-500'} rounded cursor-pointer`}
        onClick={() => setExpanded(!expanded)}
      >
        <div className={`flex items-center gap-2 text-[10px] px-2 py-1 ${sevColor}`}>
          <span className="font-bold uppercase">{severity}</span>
          <span className="text-slate-400 truncate flex-1">{event.message.split(' — ')[0]}</span>
          <span
            className={`material-symbols-outlined text-xs transition-transform ${expanded ? 'rotate-90' : ''}`}
            style={{ fontFamily: 'Material Symbols Outlined' }}
          >
            chevron_right
          </span>
        </div>
        {expanded && (
          <p className="text-[11px] text-slate-300 px-2 pb-2 leading-relaxed">
            {event.message}
          </p>
        )}
      </motion.div>
    </motion.div>
  );
};
