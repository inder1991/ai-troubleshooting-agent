import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { triggerTabVariants } from '../../styles/chat-animations';
import { useChatContext } from '../../contexts/ChatContext';

const LedgerSVG: React.FC<{ className?: string }> = ({ className }) => (
  <svg
    width="24"
    height="24"
    viewBox="0 0 24 24"
    fill="none"
    className={className}
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    {/* Book body */}
    <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
    <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
    {/* Page lines */}
    <line x1="8" y1="7" x2="16" y2="7" />
    <line x1="8" y1="10" x2="14" y2="10" />
    <line x1="8" y1="13" x2="12" y2="13" />
    {/* Bookmark ribbon */}
    <path d="M14 2v6l2-1.5L18 8V2" />
  </svg>
);

const LedgerTriggerTab: React.FC = () => {
  const { isOpen, toggleDrawer, unreadCount, isWaiting } = useChatContext();

  return (
    <AnimatePresence mode="wait">
      {!isOpen && (
        <motion.button
          key="ledger-tab"
          variants={triggerTabVariants}
          initial="hidden"
          animate="visible"
          exit="exit"
          onClick={toggleDrawer}
          className={`fixed top-16 right-0 bottom-0 z-[60] w-12 flex flex-col items-center justify-center gap-3 border-l transition-colors ${
            isWaiting
              ? 'bg-amber-500/10 border-amber-500/40 hover:bg-amber-500/20'
              : 'bg-slate-900/90 border-cyan-500/20 hover:bg-slate-800/90'
          }`}
          title="Open Mission Log"
        >
          {/* Unread badge */}
          {unreadCount > 0 && (
            <span className="absolute top-20 left-1 min-w-[18px] h-[18px] flex items-center justify-center rounded-full bg-amber-500 text-[9px] font-bold text-black px-1">
              {unreadCount > 9 ? '9+' : unreadCount}
            </span>
          )}

          {/* SVG Icon */}
          <LedgerSVG
            className={`transition-colors ${
              isWaiting ? 'stroke-amber-400' : 'stroke-cyan-400'
            } hover:drop-shadow-[0_0_8px_rgba(7,182,213,0.4)]`}
          />

          {/* Vertical label */}
          <span
            className={`text-[9px] font-bold tracking-[0.2em] writing-mode-vertical ${
              isWaiting ? 'text-amber-400' : 'text-slate-500'
            }`}
            style={{ writingMode: 'vertical-rl', textOrientation: 'mixed' }}
          >
            {isWaiting ? 'INPUT REQUIRED' : 'MISSION LOG'}
          </span>

          {/* Waiting pulse dot */}
          {isWaiting && (
            <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
          )}
        </motion.button>
      )}
    </AnimatePresence>
  );
};

export default LedgerTriggerTab;
