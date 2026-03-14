import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

// In a real app, you would fetch these via TanStack Query from /api/v4/metrics
const telemetry = [
  { label: 'CPU Utilization', value: '23%', icon: 'memory' },
  { label: 'Memory Usage', value: '61%', icon: 'dns' },
  { label: 'API Latency', value: '12ms', icon: 'speed' },
];

export const SystemHealthTicker: React.FC = () => {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setIndex((prev) => (prev + 1) % telemetry.length);
    }, 3000);
    return () => clearInterval(timer);
  }, []);

  const current = telemetry[index];

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-duck-surface border border-duck-border overflow-hidden min-w-[160px] h-[34px]">
      <span className="material-symbols-outlined text-[16px] text-duck-muted" aria-hidden="true">
        {current.icon}
      </span>

      <AnimatePresence mode="wait">
        <motion.div
          key={current.label}
          initial={{ y: 10, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: -10, opacity: 0 }}
          transition={{ duration: 0.2, ease: 'easeInOut' }}
          className="flex items-center gap-1.5 text-xs w-full"
        >
          <span className="text-duck-muted font-medium">{current.label}:</span>
          <span className="text-white font-bold ml-auto">{current.value}</span>
        </motion.div>
      </AnimatePresence>
    </div>
  );
};
