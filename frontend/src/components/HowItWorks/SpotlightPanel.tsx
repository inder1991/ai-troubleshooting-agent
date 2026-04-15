import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { DuckVariant, DuckState } from './DuckAvatar';
import { DuckSVGContent } from './DuckAvatar';
import { WF_COLORS } from './workflowConfigs';

interface SpotlightPanelProps {
  activeAgent: {
    duck: DuckVariant;
    name: string;
    subtitle: string;
    state: DuckState;
    progress: number;
  } | null;
  isComplete: boolean;
}

const RING_R = 16;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_R;

const SpotlightPanel: React.FC<SpotlightPanelProps> = ({ activeAgent, isComplete }) => {
  const duck: DuckVariant = isComplete
    ? 'supervisor'
    : activeAgent?.duck ?? 'supervisor';
  const name = isComplete
    ? 'Supervisor'
    : activeAgent?.name ?? 'Supervisor';
  const subtitle = isComplete
    ? 'Diagnosis Complete'
    : activeAgent?.subtitle ?? 'Processing...';
  const duckState: DuckState = isComplete
    ? 'done'
    : activeAgent?.state ?? 'working';
  const progress = isComplete ? 1 : (activeAgent?.progress ?? 0);

  const dashOffset = RING_CIRCUMFERENCE * (1 - progress);

  return (
    <div
      className="w-[200px] shrink-0 flex flex-col items-center justify-center gap-4 border-r"
      style={{
        backgroundColor: WF_COLORS.panelBg,
        borderColor: WF_COLORS.border,
      }}
    >
      {/* Large duck avatar */}
      <AnimatePresence mode="wait">
        <motion.div
          key={duck}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.3, ease: 'easeOut' }}
        >
          <svg width={80} height={80} viewBox="0 0 24 24" style={{ overflow: 'visible' }}>
            <DuckSVGContent variant={duck} state={duckState} />
          </svg>
        </motion.div>
      </AnimatePresence>

      {/* Progress ring */}
      <svg width={36} height={36} viewBox="-18 -18 36 36">
        <circle r={RING_R} fill="none" stroke={WF_COLORS.border} strokeWidth="2.5" />
        <circle
          r={RING_R}
          fill="none"
          stroke={isComplete ? WF_COLORS.green : WF_COLORS.amber}
          strokeWidth="2.5"
          strokeDasharray={RING_CIRCUMFERENCE}
          strokeDashoffset={dashOffset}
          strokeLinecap="round"
          transform="rotate(-90)"
          style={{ transition: 'stroke-dashoffset 0.3s ease' }}
        />
        {isComplete && (
          <text
            textAnchor="middle"
            dominantBaseline="central"
            fill={WF_COLORS.green}
            fontSize="12"
            fontFamily="DM Sans, system-ui"
          >
            ✓
          </text>
        )}
      </svg>

      {/* Role name */}
      <AnimatePresence mode="wait">
        <motion.div
          key={name}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.3 }}
          className="text-center px-3"
        >
          <div
            className="text-sm font-bold"
            style={{ color: WF_COLORS.labelText, fontFamily: 'DM Sans, Inter, system-ui, sans-serif' }}
          >
            {name}
          </div>
          <div
            className="text-body-xs mt-1"
            style={{ color: WF_COLORS.mutedText, fontFamily: 'Inter, system-ui, sans-serif' }}
          >
            {subtitle}
          </div>
        </motion.div>
      </AnimatePresence>
    </div>
  );
};

export default SpotlightPanel;
