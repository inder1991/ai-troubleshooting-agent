import React from 'react';
import { motion } from 'framer-motion';

const TargetingBrackets: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  return (
    <div className="relative">
      {/* Static Bracket SVG without heavy filters */}
      <svg
        className="absolute inset-0 w-full h-full pointer-events-none z-10"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
      >
        {/* Top-left */}
        <path d="M 0 15 L 0 0 L 15 0" fill="none" stroke="#ef4444" strokeWidth="2" />
        {/* Top-right */}
        <path d="M 85 0 L 100 0 L 100 15" fill="none" stroke="#ef4444" strokeWidth="2" />
        {/* Bottom-left */}
        <path d="M 0 85 L 0 100 L 15 100" fill="none" stroke="#ef4444" strokeWidth="2" />
        {/* Bottom-right */}
        <path d="M 85 100 L 100 100 L 100 85" fill="none" stroke="#ef4444" strokeWidth="2" />
      </svg>

      {/* GPU-accelerated glow: animate opacity on pre-blurred element */}
      <motion.div
        className="absolute inset-0 shadow-[inset_0_0_20px_rgba(239,68,68,0.3)] pointer-events-none rounded"
        animate={{ opacity: [0, 1, 0] }}
        transition={{ repeat: Infinity, duration: 2, ease: 'easeInOut' }}
        style={{ willChange: 'opacity' }}
      />

      {children}
    </div>
  );
};

export default TargetingBrackets;
