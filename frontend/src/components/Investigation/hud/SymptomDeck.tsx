import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Layers } from 'lucide-react';

interface SymptomDeckProps {
  symptoms: any[];
  renderSymptom: (symptom: any, idx: number) => React.ReactNode;
}

const SymptomDeck: React.FC<SymptomDeckProps> = ({ symptoms, renderSymptom }) => {
  const [expanded, setExpanded] = useState(false);

  if (symptoms.length === 0) return null;

  if (expanded) {
    return (
      <div className="space-y-3">
        <button
          onClick={() => setExpanded(false)}
          className="text-[10px] text-cyan-400 hover:text-cyan-300 font-mono border border-cyan-500/30 bg-cyan-500/5 rounded-lg px-3 py-1.5 transition-colors"
        >
          Collapse Stack
        </button>
        {symptoms.map((symptom, idx) => (
          <motion.div
            key={idx}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: idx * 0.03, duration: 0.3 }}
          >
            {renderSymptom(symptom, idx)}
          </motion.div>
        ))}
        {symptoms.length > 5 && (
          <div className="sticky bottom-2 flex justify-center mt-4">
            <button
              onClick={() => setExpanded(false)}
              className="text-[10px] text-cyan-400 bg-slate-900/90 backdrop-blur border border-cyan-500/30 rounded-full px-4 py-1.5 shadow-lg hover:bg-slate-800 transition-colors"
            >
              Collapse Stack
            </button>
          </div>
        )}
      </div>
    );
  }

  return (
    <motion.div
      className="relative group cursor-pointer"
      onClick={() => setExpanded(true)}
      whileHover={{ y: -2 }}
      transition={{ type: 'spring', stiffness: 400 }}
    >
      {/* Ghost card 2 (deepest) */}
      <div className="absolute inset-x-2 top-0 h-full translate-y-3 scale-95 bg-slate-800/20 border border-slate-700/30 rounded-xl -z-20" />
      {/* Ghost card 1 (middle) */}
      <div className="absolute inset-x-1 top-0 h-full translate-y-1.5 scale-[0.975] bg-slate-800/40 border border-slate-700/50 rounded-xl -z-10" />

      {/* Main card */}
      <div className="relative bg-slate-900/80 border border-slate-700 group-hover:border-cyan-500/50 rounded-xl overflow-hidden transition-colors">
        {/* Header */}
        <div className="px-4 py-2.5 border-b border-slate-800/50 flex items-center gap-2">
          <Layers className="w-3.5 h-3.5 text-cyan-400" />
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
            Symptom Cluster
          </span>
          <span className="text-[9px] font-mono text-cyan-400 bg-cyan-500/10 border border-cyan-500/20 px-1.5 py-0.5 rounded-full ml-auto">
            {symptoms.length} EVENTS
          </span>
        </div>

        {/* Top symptom preview (muted) */}
        <div className="px-4 py-3 opacity-60 grayscale pointer-events-none">
          {renderSymptom(symptoms[0], 0)}
        </div>

        {/* CTA */}
        <div className="px-4 py-2 border-t border-dashed border-cyan-500/20">
          <span className="text-[10px] text-cyan-400/70 font-mono">
            Click to Fan Out Stack
          </span>
        </div>
      </div>
    </motion.div>
  );
};

export default SymptomDeck;
