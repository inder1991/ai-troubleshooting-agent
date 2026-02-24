import React from 'react';
import { motion } from 'framer-motion';

const WeldSpark: React.FC = () => {
  return (
    <motion.div
      className="absolute -left-1.5 top-8 z-50 pointer-events-none"
      initial={{ scale: 0, opacity: 1 }}
      animate={{
        scale: [0, 2, 0],
        opacity: [1, 0.8, 0],
        rotate: [0, 45, 90],
      }}
      transition={{ duration: 0.6, ease: 'easeOut' }}
    >
      {/* Yellow blur circle */}
      <div className="w-3 h-3 rounded-full bg-yellow-400 blur-sm" />
      {/* Crossed light bars */}
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="w-4 h-px bg-white rotate-45" />
        <div className="absolute w-4 h-px bg-white -rotate-45" />
      </div>
    </motion.div>
  );
};

export default WeldSpark;
