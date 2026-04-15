import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';

export type PanelState = 'dormant' | 'scanning' | 'lit' | 'error';

interface PanelZoneProps {
  title: string;
  icon: string;
  agentName: string;
  state: PanelState;
  children: React.ReactNode;
  className?: string;
  /** When true, agent finished but this panel had no relevant data */
  notApplicable?: boolean;
}

const PanelZone: React.FC<PanelZoneProps> = ({
  title,
  icon,
  agentName,
  state,
  children,
  className = '',
  notApplicable = false,
}) => {
  return (
    <div className={`flex flex-col min-h-0 ${className}`}>
      {/* Zone label — always visible, minimal */}
      <div className="flex items-center gap-1.5 mb-1.5">
        <span
          className={`material-symbols-outlined text-[14px] ${
            state === 'lit' ? 'text-duck-accent' : 'text-slate-400'
          }`}
          aria-hidden="true"
        >
          {icon}
        </span>
        <span
          className={`text-body-xs font-display font-bold ${
            state === 'lit' ? 'text-slate-300' : 'text-slate-400'
          }`}
        >
          {title}
        </span>
        {state === 'scanning' && (
          <span className="text-body-xs text-amber-400 ml-auto flex items-center gap-1" aria-label="Scanning in progress">
            <span className="material-symbols-outlined text-[12px] animate-spin">progress_activity</span>
            {agentName}
          </span>
        )}
      </div>

      {/* Content area — no card wrapper */}
      <AnimatePresence>
        {state === 'dormant' && (
          <motion.div
            key="dormant"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex-1 min-h-[100px] md:min-h-0 flex items-center justify-center border border-dashed border-duck-border/30 rounded-lg"
          >
            <span className="text-body-xs text-slate-400 italic">
              {notApplicable ? 'No issues found' : `Waiting for ${agentName}`}
            </span>
          </motion.div>
        )}
        {state === 'scanning' && (
          <motion.div
            key="scanning"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex-1 flex items-center justify-center border border-amber-500/40 rounded-lg bg-amber-500/5"
          >
            <span className="text-body-xs text-amber-400">Analyzing...</span>
          </motion.div>
        )}
        {state === 'error' && (
          <motion.div
            key="error"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex-1 flex items-center justify-center border border-red-500/20 rounded-lg bg-red-500/[0.03] min-h-[100px] md:min-h-0"
          >
            <div className="flex items-center gap-1.5 text-body-xs text-red-400">
              <span className="material-symbols-outlined text-[14px]" aria-hidden="true">error</span>
              Failed to collect data
            </div>
          </motion.div>
        )}
        {state === 'lit' && (
          <motion.div
            key="lit"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, ease: "easeOut" }}
            className="flex-1 min-h-0 overflow-hidden"
          >
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default React.memo(PanelZone);
