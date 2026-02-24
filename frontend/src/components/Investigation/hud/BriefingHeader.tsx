import React, { useEffect, useRef, useMemo } from 'react';
import { motion, AnimatePresence, useMotionValue, useTransform, animate } from 'framer-motion';
import { HardHat, Activity } from 'lucide-react';

interface BriefingHeaderProps {
  latestEventText: string;
  agentName: string;
  severity: 'P1' | 'P2' | 'P3' | 'P4';
  isProcessing: boolean;
}

const BriefingHeader: React.FC<BriefingHeaderProps> = ({
  latestEventText,
  agentName,
  severity,
  isProcessing,
}) => {
  const prevTextRef = useRef('');
  const count = useMotionValue(0);
  const rounded = useTransform(count, (latest) => Math.round(latest));
  const displayedText = useTransform(rounded, (latest) => latestEventText.slice(0, latest));
  const isStreaming = useMotionValue(false);

  useEffect(() => {
    if (latestEventText === prevTextRef.current) return;
    prevTextRef.current = latestEventText;

    count.set(0);
    isStreaming.set(true);

    const controls = animate(count, latestEventText.length, {
      duration: latestEventText.length * 0.02,
      ease: 'linear',
      onComplete: () => isStreaming.set(false),
    });

    return controls.stop;
  }, [latestEventText, count, isStreaming]);

  const sevColor = severity === 'P1' ? 'text-red-400 bg-red-500/10 border-red-500/30'
    : 'text-amber-400 bg-amber-500/10 border-amber-500/30';

  return (
    <div className="sticky top-0 z-[60] h-14 bg-slate-900/60 backdrop-blur-xl border-b border-slate-800/50 flex items-center px-4 gap-3">
      {/* Worker persona */}
      <div className="relative shrink-0">
        <motion.div
          animate={isProcessing ? { rotate: [0, -10, 10, -5, 5, 0] } : { rotate: 0 }}
          transition={isProcessing ? { repeat: Infinity, duration: 2, ease: 'easeInOut' } : {}}
        >
          <HardHat className="w-5 h-5 text-cyan-400" />
        </motion.div>
        {isProcessing && (
          <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
        )}
      </div>

      {/* Streaming text - uses motion value, zero React re-renders */}
      <div className="flex-1 min-w-0">
        <p className="text-[11px] text-slate-300 font-mono truncate leading-snug">
          <motion.span>{displayedText}</motion.span>
          {isProcessing && (
            <span className="inline-block w-1.5 h-3 bg-cyan-400 ml-0.5 animate-pulse align-text-bottom" />
          )}
        </p>
      </div>

      {/* Agent badge */}
      <AnimatePresence mode="wait">
        <motion.span
          key={agentName}
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 8 }}
          transition={{ duration: 0.2 }}
          className="text-[9px] font-bold text-cyan-400 bg-cyan-500/10 border border-cyan-500/20 px-2 py-0.5 rounded-full shrink-0"
        >
          {agentName}
        </motion.span>
      </AnimatePresence>

      {/* Severity label */}
      <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold border shrink-0 ${sevColor}`}>
        {severity}
      </span>

      {/* Live session indicator */}
      <div className="flex items-center gap-1.5 shrink-0">
        <Activity className="w-3 h-3 text-green-500" />
        <span className="text-[9px] font-mono text-slate-500">LIVE_SESSION_ACTIVE</span>
      </div>
    </div>
  );
};

export default BriefingHeader;
