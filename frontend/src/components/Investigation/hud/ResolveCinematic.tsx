import React, { useMemo } from 'react';
import { motion } from 'framer-motion';
import { ShieldCheck, Download, ArrowRight, Zap } from 'lucide-react';
import type { V4Findings } from '../../../types';

interface ResolveCinematicProps {
  findings: V4Findings | null;
  onDismiss: () => void;
}

const ResolveCinematic: React.FC<ResolveCinematicProps> = ({ findings, onDismiss }) => {
  const incidentId = findings?.incident_id || findings?.session_id || 'N/A';
  const mttr = 'N/A';

  const stats = useMemo(() => {
    const rootCauseCount = findings?.error_patterns?.filter(p => p.causal_role === 'root_cause').length || 0;
    const findingsList = findings?.findings || [];
    const uniqueAgents = new Set<string>();
    for (let i = 0; i < findingsList.length; i++) {
      if (findingsList[i].agent_name) uniqueAgents.add(findingsList[i].agent_name);
    }
    return { rootCauseCount, agentCount: uniqueAgents.size };
  }, [findings]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[100] bg-slate-950/90 backdrop-blur-xl flex items-center justify-center"
      onClick={onDismiss}
    >
      {/* Emerald Sweep */}
      <motion.div
        className="absolute inset-0 pointer-events-none"
        initial={{ x: '-100%' }}
        animate={{ x: '100%' }}
        transition={{ duration: 1.2, ease: 'easeInOut' }}
      >
        <div className="w-full h-full bg-gradient-to-r from-transparent via-emerald-500/20 to-transparent" />
      </motion.div>

      {/* Dossier Drop */}
      <motion.div
        initial={{ scale: 0.9, y: 40, opacity: 0 }}
        animate={{ scale: 1, y: 0, opacity: 1 }}
        transition={{ delay: 0.4, type: 'spring', stiffness: 200, damping: 20 }}
        className="relative bg-slate-900/90 border border-emerald-500/30 rounded-2xl p-8 max-w-md w-full mx-4 shadow-[0_0_60px_rgba(16,185,129,0.15)]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Shield icon */}
        <div className="flex justify-center mb-6">
          <div className="w-16 h-16 rounded-full bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center">
            <ShieldCheck className="w-8 h-8 text-emerald-400" />
          </div>
        </div>

        {/* Heading */}
        <h2 className="text-center text-2xl font-black uppercase italic text-emerald-400 tracking-wider mb-6">
          System Restored
        </h2>

        {/* 2x2 stat grid */}
        <div className="grid grid-cols-2 gap-3 mb-6">
          <StatCell label="Incident ID" value={incidentId.slice(0, 12)} />
          <StatCell label="MTTR" value={mttr} />
          <StatCell label="Root Causes" value={`${stats.rootCauseCount} identified`} />
          <StatCell label="Agents Used" value={`${stats.agentCount} active`} />
        </div>

        {/* Actions */}
        <div className="space-y-2">
          <button className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/30 transition-colors text-sm font-bold">
            <Download className="w-4 h-4" />
            Download Incident Dossier
          </button>
          <button
            onClick={onDismiss}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-slate-800/50 text-slate-400 border border-slate-700/50 hover:bg-slate-800 transition-colors text-sm"
          >
            Return to Dashboard
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>

        {/* Worker's Salute */}
        <div className="mt-6 pt-4 border-t border-slate-800/50 flex items-center justify-center gap-2">
          <Zap className="w-3 h-3 text-amber-400" />
          <span className="text-[10px] text-slate-500 italic">
            All systems nominal. Excellent work, Engineer.
          </span>
        </div>
      </motion.div>
    </motion.div>
  );
};

const StatCell: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="bg-slate-800/30 rounded-lg border border-slate-700/30 p-3">
    <div className="text-[9px] text-slate-500 uppercase tracking-wider mb-1">{label}</div>
    <div className="text-sm font-bold font-mono text-slate-200">{value}</div>
  </div>
);

export default ResolveCinematic;
