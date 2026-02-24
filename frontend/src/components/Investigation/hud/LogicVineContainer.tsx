import React from 'react';
import { motion } from 'framer-motion';

const LogicVineContainer: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  return (
    <div className="relative">
      {/* The Base Track */}
      <div className="absolute left-[16px] top-0 bottom-0 w-px bg-cyan-500/10" />

      {/* The Data Pulse - Infinite Flowing Gradient */}
      <div className="absolute left-[16px] top-0 bottom-0 w-px overflow-hidden">
        <motion.div
          className="w-full h-32 bg-gradient-to-b from-transparent via-cyan-400 to-transparent"
          animate={{ y: ['-100%', '800%'] }}
          transition={{ repeat: Infinity, duration: 2.5, ease: 'linear' }}
        />
      </div>

      <div className="space-y-8 py-4">{children}</div>
    </div>
  );
};

export default LogicVineContainer;
