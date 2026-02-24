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
          className={`fixed bottom-6 right-6 z-[60] w-12 h-12 rounded-full flex items-center justify-center shadow-lg shadow-black/40 transition-colors ${
            isWaiting
              ? 'bg-amber-500/20 border border-amber-500/50 hover:bg-amber-500/30'
              : 'bg-slate-800 border border-cyan-500/30 hover:bg-slate-700'
          }`}
          title={isWaiting ? 'Input Required — Open Mission Log' : 'Open Mission Log'}
        >
          {/* Unread badge */}
          {unreadCount > 0 && (
            <span className="absolute -top-1 -left-1 min-w-[18px] h-[18px] flex items-center justify-center rounded-full bg-amber-500 text-[9px] font-bold text-black px-1">
              {unreadCount > 9 ? '9+' : unreadCount}
            </span>
          )}

          {/* SVG Icon */}
          <LedgerSVG
            className={`transition-colors ${
              isWaiting ? 'stroke-amber-400' : 'stroke-cyan-400'
            } hover:drop-shadow-[0_0_8px_rgba(7,182,213,0.4)]`}
          />

          {/* Waiting pulse ring */}
          {isWaiting && (
            <span className="absolute inset-0 rounded-full border-2 border-amber-400/50 animate-ping" />
          )}
        </motion.button>
      )}
    </AnimatePresence>
  );
};

export default LedgerTriggerTab;
