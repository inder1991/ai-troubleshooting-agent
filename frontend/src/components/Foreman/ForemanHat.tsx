import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Terminal, Box, Code2, GitBranch } from 'lucide-react';

type ActiveAgent = 'log' | 'platform' | 'code' | 'change' | null;

interface ForemanHatProps {
  activeAgent: ActiveAgent;
  drilling: boolean;
}

const agentIconMap = {
  log: Terminal,
  platform: Box,
  code: Code2,
  change: GitBranch,
};

const agentColorMap = {
  log: '#ef4444',
  platform: '#f97316',
  code: '#3b82f6',
  change: '#10b981',
};

const ForemanHat: React.FC<ForemanHatProps> = ({ activeAgent, drilling }) => {
  if (!activeAgent) return null;

  const Icon = agentIconMap[activeAgent];
  const color = agentColorMap[activeAgent];

  return (
    <div className="absolute -top-0.5 -right-0.5 z-10">
      <AnimatePresence mode="wait">
        <motion.div
          key={activeAgent}
          initial={{ scale: 0, rotate: -90 }}
          animate={{ scale: 1, rotate: 0 }}
          exit={{ scale: 0, rotate: 90 }}
          transition={{ type: 'spring', stiffness: 400, damping: 15 }}
          className="relative w-5 h-5 rounded-full flex items-center justify-center"
          style={{ backgroundColor: color }}
        >
          <Icon size={10} className="text-white" />
          {/* M12: Only render ping span when drilling — no infinite animation leak */}
          {drilling && (
            <motion.span
              className="absolute inset-0 rounded-full"
              style={{ backgroundColor: color, opacity: 0.4 }}
              animate={{ scale: [1, 1.5, 1], opacity: [0.4, 0, 0.4] }}
              transition={{ duration: 1, repeat: Infinity, ease: 'easeOut' }}
            />
          )}
        </motion.div>
      </AnimatePresence>
    </div>
  );
};

export default ForemanHat;
