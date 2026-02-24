import React from 'react';
import { motion } from 'framer-motion';
import { Pin, Info } from 'lucide-react';

interface VineCardProps {
  children: React.ReactNode;
  index: number;
  isRootCause?: boolean;
  isNew?: boolean;
  sectionId: string;
  onPin?: () => void;
  isPinned?: boolean;
}

const VineCard: React.FC<VineCardProps> = ({
  children,
  index,
  isRootCause = false,
  isNew = false,
  sectionId,
  onPin,
  isPinned = false,
}) => {
  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.05, duration: 0.4 }}
      className="relative pl-12 group"
      data-section-id={sectionId}
    >
      {/* Vine node dot */}
      <div
        className={`absolute left-[11px] top-8 w-3 h-3 rounded-full border-2 border-slate-950 transition-all ${
          isRootCause
            ? 'bg-red-500 shadow-[0_0_10px_#ef4444]'
            : 'bg-cyan-500/50 shadow-[0_0_5px_rgba(6,182,212,0.5)]'
        } ${isNew ? 'animate-vine-connect' : ''}`}
      />

      {/* Card shell */}
      <div
        className={`rounded-xl border backdrop-blur-sm transition-all duration-300 ${
          isRootCause
            ? 'border-red-500/50 bg-red-500/5 scale-[1.02] z-10'
            : 'border-slate-800 bg-slate-900/40 hover:border-slate-700'
        } ${isNew ? 'animate-highlight' : ''}`}
      >
        {/* Hover action menu */}
        <div className="absolute top-2 right-2 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity z-20">
          {onPin && (
            <button
              onClick={onPin}
              className={`p-1 rounded-md transition-colors ${
                isPinned
                  ? 'bg-cyan-500/20 text-cyan-400'
                  : 'bg-slate-800/80 text-slate-500 hover:text-cyan-400'
              }`}
              aria-label={isPinned ? 'Unpin evidence' : 'Pin evidence'}
            >
              <Pin className="w-3 h-3" />
            </button>
          )}
          <button
            className="p-1 rounded-md bg-slate-800/80 text-slate-500 hover:text-slate-300 transition-colors"
            aria-label="More info"
          >
            <Info className="w-3 h-3" />
          </button>
        </div>

        {/* Content slot */}
        <div className="p-4 overflow-hidden">
          {children}
        </div>
      </div>
    </motion.div>
  );
};

export default VineCard;
