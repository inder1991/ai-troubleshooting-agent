import React, { useState, useMemo, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { DiagnosticPhase, TaskEvent } from '../../types';
import ForemanHat from './ForemanHat';

type ForemanState = 'idle' | 'drilling' | 'waiting' | 'resolved';
type ActiveAgent = 'log' | 'platform' | 'code' | 'change' | null;

interface ForemanHUDProps {
  sessionId: string;
  serviceName: string;
  phase: DiagnosticPhase | null;
  confidence: number;
  events: TaskEvent[];
  wsConnected: boolean;
  needsInput: boolean;
  onGoHome: () => void;
  onOpenChat: () => void;
}

function deriveForemanState(
  phase: DiagnosticPhase | null,
  needsInput: boolean,
  wsConnected: boolean
): ForemanState {
  if (needsInput) return 'waiting';
  if (phase === 'complete' || phase === 'diagnosis_complete') return 'resolved';
  if (!wsConnected || !phase || phase === 'initial') return 'idle';
  return 'drilling';
}

const AGENT_MAP: Record<string, ActiveAgent> = {
  log_agent: 'log',
  metrics_agent: 'log',       // metrics shares "log" badge (telemetry)
  k8s_agent: 'platform',
  tracing_agent: 'platform',  // tracing shares "platform" badge
  code_agent: 'code',
  change_agent: 'change',
  fix_generator: 'change',
};

// Names to skip when looking for active agent badge
const SKIP_AGENTS = new Set(['supervisor', 'critic', 'impact_analyzer']);

function deriveActiveAgent(events: TaskEvent[]): ActiveAgent {
  for (let i = events.length - 1; i >= 0; i--) {
    const name = events[i].agent_name?.toLowerCase();
    if (!name || SKIP_AGENTS.has(name)) continue;
    for (const [key, val] of Object.entries(AGENT_MAP)) {
      if (name.includes(key)) return val;
    }
  }
  return null;
}

const avatarVariants = {
  idle: { scale: [1, 1.02, 1], transition: { duration: 3, repeat: Infinity, ease: 'easeInOut' as const } },
  drilling: { x: [0, -1, 1, -1, 0], transition: { duration: 0.3, repeat: Infinity, ease: 'linear' as const } },
  waiting: { opacity: [1, 0.6, 1], transition: { duration: 1.5, repeat: Infinity, ease: 'easeInOut' as const } },
  resolved: { scale: [1, 1.15, 1], transition: { duration: 0.5, ease: 'easeOut' as const } },
};

const ForemanHUD: React.FC<ForemanHUDProps> = ({
  sessionId,
  serviceName,
  phase,
  confidence,
  events,
  wsConnected,
  needsInput,
  onGoHome,
  onOpenChat,
}) => {
  const [autopilot, setAutopilot] = useState(true);

  const foremanState = deriveForemanState(phase, needsInput, wsConnected);
  const activeAgent = deriveActiveAgent(events);

  // H7: Track if resolved flash has already fired — only animate once
  const hasResolvedRef = useRef(false);
  useEffect(() => {
    if (foremanState === 'resolved') {
      hasResolvedRef.current = true;
    }
    // Reset when phase changes away from resolved (new session)
    if (foremanState !== 'resolved') {
      hasResolvedRef.current = false;
    }
  }, [foremanState]);

  // M3: Debounce telemetry text to prevent continuous animation on rapid events
  const rawEventText = useMemo(() => {
    if (!events.length) return 'Awaiting telemetry...';
    const last = events[events.length - 1];
    return last.message || `${last.agent_name}: ${last.event_type}`;
  }, [events]);

  const [latestEventText, setLatestEventText] = useState(rawEventText);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setLatestEventText(rawEventText), 300);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [rawEventText]);

  const borderClass = foremanState === 'waiting'
    ? 'border-amber-500/40 shadow-[0_2px_20px_rgba(245,158,11,0.15)]'
    : foremanState === 'resolved'
      ? 'border-emerald-500/40'
      : 'border-cyan-500/20';

  return (
    <header
      className={`h-16 border-b bg-[#0a1a1d]/80 backdrop-blur-md flex items-center px-4 gap-4 shrink-0 transition-all duration-500 ${borderClass}`}
    >
      {/* Logo / Back */}
      <button onClick={onGoHome} className="flex items-center gap-2 group shrink-0">
        <div className="w-8 h-8 bg-cyan-500 rounded flex items-center justify-center">
          <span className="material-symbols-outlined text-white text-lg" style={{ fontFamily: 'Material Symbols Outlined' }}>bug_report</span>
        </div>
        <span className="font-bold tracking-tight text-lg">
          Debug<span className="text-cyan-400">Duck</span>
        </span>
      </button>

      <div className="h-6 w-px bg-slate-700" />

      {/* Investigation ID */}
      <div className="flex flex-col shrink-0">
        <span className="text-[9px] uppercase tracking-widest text-slate-500 font-bold">Investigation</span>
        <span className="text-[10px] font-mono text-cyan-400">{sessionId.substring(0, 8).toUpperCase()}</span>
      </div>

      <div className="h-6 w-px bg-slate-700" />

      {/* Avatar Cell */}
      <div className="relative w-12 h-12 shrink-0">
        <motion.div
          variants={avatarVariants}
          animate={foremanState}
          className="w-12 h-12 rounded-xl bg-slate-800/80 border border-cyan-500/30 flex items-center justify-center overflow-hidden relative"
        >
          {/* Blueprint SVG Foreman */}
          <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="16" cy="10" r="5" stroke="#07b6d5" strokeWidth="1.2" />
            <path d="M8 28 L12 18 L20 18 L24 28" stroke="#07b6d5" strokeWidth="1.2" strokeLinejoin="round" />
            <path d="M10 7 Q16 2 22 7" stroke="#07b6d5" strokeWidth="1.2" strokeLinecap="round" />
          </svg>
          {/* Dashed thinking ring */}
          {foremanState === 'drilling' && (
            <div className="absolute inset-0 rounded-xl border-2 border-dashed border-cyan-400/50 animate-thinking-ring" />
          )}
        </motion.div>
        <ForemanHat activeAgent={activeAgent} drilling={foremanState === 'drilling'} />
      </div>

      {/* Telemetry */}
      <div className="flex-1 min-w-0 flex flex-col gap-1">
        <AnimatePresence mode="wait">
          <motion.div
            key={latestEventText}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.2 }}
            className="text-[11px] text-slate-300 font-mono truncate"
          >
            {latestEventText}
            <span className="inline-block w-[2px] h-3 bg-cyan-400 ml-1 animate-pulse align-middle" />
          </motion.div>
        </AnimatePresence>
        <div className="flex items-center gap-3">
          <span className="text-[10px] text-cyan-400 font-bold">{confidence}%</span>
          <div className="flex-1 h-1 bg-slate-800 rounded-full overflow-hidden">
            <motion.div
              className="h-full bg-cyan-500 rounded-full"
              animate={{ width: `${confidence}%` }}
              transition={{ duration: 0.6, ease: 'easeOut' }}
            />
          </div>
        </div>
      </div>

      {/* Foreman Bubble (waiting only) */}
      <AnimatePresence>
        {foremanState === 'waiting' && (
          <motion.button
            initial={{ opacity: 0, x: -10, scale: 0.8 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: -10, scale: 0.8 }}
            onClick={onOpenChat}
            className="flex items-center bg-amber-500 text-slate-950 px-3 py-1.5 rounded-r-lg rounded-tl-lg shadow-lg relative cursor-pointer shrink-0 animate-foreman-ping"
          >
            <div className="absolute left-[-6px] bottom-0 w-0 h-0 border-t-[6px] border-t-transparent border-r-[8px] border-r-amber-500 border-b-[6px] border-b-transparent" />
            <span className="text-[10px] font-black uppercase tracking-tight mr-2">Input needed</span>
            <span className="text-[9px] bg-slate-950/20 rounded px-1 animate-pulse">RESPOND</span>
          </motion.button>
        )}
      </AnimatePresence>

      {/* H7: Resolved flash overlay — fires once only */}
      <AnimatePresence>
        {foremanState === 'resolved' && !hasResolvedRef.current && (
          <motion.div
            initial={{ opacity: 0.4 }}
            animate={{ opacity: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 1.5 }}
            className="absolute inset-0 bg-emerald-500/10 pointer-events-none rounded-none"
          />
        )}
      </AnimatePresence>

      {/* Controls */}
      <div className="flex items-center gap-3 shrink-0">
        {/* Autopilot toggle */}
        <button
          onClick={() => setAutopilot((p) => !p)}
          className={`text-[9px] font-bold uppercase tracking-wider px-2 py-1 rounded-md border transition-colors ${
            autopilot
              ? 'bg-cyan-500/15 border-cyan-500/30 text-cyan-400'
              : 'bg-slate-800 border-slate-700 text-slate-500'
          }`}
        >
          {autopilot ? 'Auto' : 'Manual'}
        </button>

        {/* WS indicator */}
        <div className="flex items-center gap-1.5">
          <span className={`w-2 h-2 rounded-full ${wsConnected ? 'bg-cyan-400' : 'bg-red-500'}`} />
          <span className={`text-[9px] font-bold uppercase tracking-wider ${wsConnected ? 'text-cyan-400' : 'text-red-400'}`}>
            {wsConnected ? 'LIVE' : 'OFFLINE'}
          </span>
        </div>

        <div className="h-6 w-px bg-slate-700" />

        {/* Phase pill */}
        {phase && (
          <div className="flex items-center gap-1.5 px-2.5 py-1 bg-slate-800/80 border border-slate-700 rounded-full">
            <span className={`w-1.5 h-1.5 rounded-full ${
              phase === 'complete' || phase === 'diagnosis_complete' ? 'bg-emerald-400' :
              phase === 'error' ? 'bg-red-500' : 'bg-amber-400 animate-pulse'
            }`} />
            <span className="text-[9px] font-bold uppercase tracking-wider text-slate-400">
              {phase.replace(/_/g, ' ')}
            </span>
          </div>
        )}
      </div>
    </header>
  );
};

export default ForemanHUD;
