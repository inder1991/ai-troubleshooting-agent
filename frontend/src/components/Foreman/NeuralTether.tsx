import React, { useEffect, useCallback } from 'react';
import { motion, AnimatePresence, useMotionValue, useTransform } from 'framer-motion';

interface NeuralTetherProps {
  isActive: boolean;
  tabRef: React.RefObject<HTMLButtonElement | null>;
}

const NeuralTether: React.FC<NeuralTetherProps> = ({ isActive, tabRef }) => {
  const targetX = useMotionValue(0);
  const targetY = useMotionValue(0);

  const SOURCE_X = 200;
  const SOURCE_Y = 56;

  const pathD = useTransform(
    [targetX, targetY],
    ([x, y]: number[]) => {
      const midX = (SOURCE_X + x) / 2;
      return `M ${SOURCE_X} ${SOURCE_Y} C ${midX} ${SOURCE_Y}, ${x} ${(SOURCE_Y + y) / 2}, ${x} ${y}`;
    }
  );

  const updateTargetPos = useCallback(() => {
    if (!tabRef.current) return;
    const rect = tabRef.current.getBoundingClientRect();
    targetX.set(rect.left + rect.width / 2);
    targetY.set(rect.top + rect.height / 2);
  }, [tabRef, targetX, targetY]);

  useEffect(() => {
    if (!isActive) return;

    updateTargetPos();

    window.addEventListener('resize', updateTargetPos, { passive: true } as AddEventListenerOptions);
    window.addEventListener('scroll', updateTargetPos, { passive: true, capture: true } as AddEventListenerOptions);

    let resizeObserver: ResizeObserver | null = null;
    if (tabRef.current) {
      resizeObserver = new ResizeObserver(updateTargetPos);
      resizeObserver.observe(tabRef.current);
    }

    return () => {
      window.removeEventListener('resize', updateTargetPos);
      window.removeEventListener('scroll', updateTargetPos, { capture: true } as EventListenerOptions);
      resizeObserver?.disconnect();
    };
  }, [isActive, tabRef, updateTargetPos]);

  return (
    <AnimatePresence>
      {isActive && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.3 }}
          className="fixed inset-0 pointer-events-none z-[55]"
        >
          <svg className="w-full h-full">
            <defs>
              <linearGradient id="tether-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="rgba(7, 182, 213, 0.8)" />
                <stop offset="100%" stopColor="rgba(245, 158, 11, 0.8)" />
              </linearGradient>
            </defs>

            {/* Base glowing path */}
            <motion.path
              d={pathD}
              fill="none"
              stroke="url(#tether-gradient)"
              strokeWidth={1}
              className="drop-shadow-[0_0_8px_rgba(7,182,213,0.5)] opacity-50"
            />

            {/* Tactical animated dashed path */}
            <motion.path
              d={pathD}
              fill="none"
              stroke="url(#tether-gradient)"
              strokeWidth={2}
              strokeDasharray="6 6"
              initial={{ strokeDashoffset: 100 }}
              animate={{ strokeDashoffset: 0 }}
              transition={{ repeat: Infinity, duration: 2, ease: 'linear' }}
            />

            {/* Landing target rings */}
            <motion.circle
              cx={targetX}
              cy={targetY}
              r={12}
              fill="none"
              stroke="rgba(245, 158, 11, 0.5)"
              strokeWidth={1}
              initial={{ scale: 0.5, opacity: 0 }}
              animate={{ scale: 1.5, opacity: [0, 1, 0] }}
              transition={{ repeat: Infinity, duration: 1.5, ease: 'easeOut' }}
            />
            <motion.circle
              cx={targetX}
              cy={targetY}
              r={3}
              fill="#f59e0b"
              className="drop-shadow-[0_0_5px_rgba(245,158,11,1)]"
            />
          </svg>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default NeuralTether;
