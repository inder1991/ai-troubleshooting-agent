import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Hammer, X, FileCheck, Download, ArrowRight } from 'lucide-react';

interface PinnedItem {
  id: string;
  agentType: string;
  title: string;
}

interface AssemblyWorkbenchProps {
  pinnedItems: PinnedItem[];
  onUnpin: (id: string) => void;
  fixReady: boolean;
}

const agentColors: Record<string, string> = {
  L: '#ef4444',
  M: '#06b6d4',
  K: '#f97316',
  D: '#3b82f6',
  C: '#10b981',
};

const AssemblyWorkbench: React.FC<AssemblyWorkbenchProps> = ({
  pinnedItems,
  onUnpin,
  fixReady,
}) => {
  if (pinnedItems.length === 0) return null;

  return (
    <div className="sticky bottom-4 mx-6 z-50 bg-slate-950/80 backdrop-blur-2xl border border-cyan-500/30 rounded-2xl shadow-[0_-20px_50px_rgba(0,0,0,0.5)] overflow-hidden">
      {/* Status bar */}
      <div className="px-4 py-2 bg-cyan-500/5 border-b border-cyan-500/20 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Hammer className="w-3.5 h-3.5 text-cyan-400 animate-bounce" />
          <span className="text-[10px] font-bold uppercase tracking-wider text-cyan-400">
            Assembly Dock
          </span>
          <span className="text-[9px] font-mono text-slate-500">
            {pinnedItems.length} Evidence Links
          </span>
        </div>

        {/* Fix ready indicator */}
        {fixReady && (
          <div className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-[9px] font-mono text-emerald-400">RESOLUTION_ENGINE_READY</span>
          </div>
        )}
      </div>

      {/* Evidence slots */}
      <div className="px-4 py-3 overflow-x-auto custom-scrollbar">
        <div className="flex gap-3">
          <AnimatePresence>
            {pinnedItems.map((item) => (
              <motion.div
                key={item.id}
                layoutId={`pin-${item.id}`}
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.8 }}
                className="relative w-32 shrink-0 bg-slate-900/60 border border-slate-700/50 rounded-lg p-2.5 group/pin"
              >
                <div className="flex items-center gap-1.5 mb-1.5">
                  <div
                    className="w-1.5 h-1.5 rounded-full shrink-0"
                    style={{ backgroundColor: agentColors[item.agentType] || '#64748b' }}
                  />
                  <span className="text-[8px] font-bold text-slate-500 uppercase">
                    {item.agentType}
                  </span>
                </div>
                <p className="text-[9px] text-slate-400 line-clamp-2 italic">
                  &ldquo;{item.title}&rdquo;
                </p>
                {/* Unpin button */}
                <button
                  onClick={() => onUnpin(item.id)}
                  className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center opacity-50 group-hover/pin:opacity-100 transition-opacity hover:bg-red-500/20 hover:border-red-500/50"
                  aria-label="Remove from dock"
                >
                  <X className="w-2.5 h-2.5 text-slate-400" />
                </button>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      </div>

      {/* Action footer */}
      <div className="px-4 py-2 border-t border-slate-800/50 flex justify-end">
        <button
          disabled={!fixReady}
          className={`flex items-center gap-2 px-4 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-all ${
            fixReady
              ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/30'
              : 'bg-slate-800/50 text-slate-600 border border-slate-700/50 cursor-not-allowed'
          }`}
        >
          <FileCheck className="w-3 h-3" />
          Finalize Incident Dossier
          <ArrowRight className="w-3 h-3" />
        </button>
      </div>
    </div>
  );
};

export default AssemblyWorkbench;
