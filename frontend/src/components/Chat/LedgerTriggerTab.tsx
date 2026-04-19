import React from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { useChatUI } from '../../contexts/ChatContext';
import { useRegionPortals } from '../../contexts/RegionPortalsContext';

const TacticalLogIcon: React.FC<{ isWaiting: boolean }> = ({ isWaiting }) => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    className={`transition-colors ${isWaiting ? 'stroke-amber-400' : 'stroke-cyan-400'}`}
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    {/* Stamped metal plate */}
    <rect x="2" y="2" width="20" height="20" rx="1" strokeOpacity={0.4} />
    {/* Notebook binding notches */}
    <path d="M2 6H5" strokeWidth="2.5" strokeLinecap="square" />
    <path d="M2 12H5" strokeWidth="2.5" strokeLinecap="square" />
    <path d="M2 18H5" strokeWidth="2.5" strokeLinecap="square" />
    {/* Data entry lines */}
    <line x1="9" y1="7" x2="19" y2="7" strokeWidth="2" />
    <line x1="9" y1="12" x2="17" y2="12" strokeWidth="2" />
    <line x1="9" y1="17" x2="14" y2="17" strokeWidth="2" />
  </svg>
);

const LedgerTriggerTab: React.FC = () => {
  const { isOpen, toggleDrawer, unreadCount, isWaiting, pendingAction } = useChatUI();
  const { gutterRef } = useRegionPortals();
  const hasPendingAction = pendingAction?.blocking === true;

  // PR 3 — LedgerTab relocates from fixed positioning to the reserved
  // gutter rail so it can never cover Navigator content. Portals into
  // the gutter region element published by RegionPortalsContext; falls
  // back to a document.body portal if the grid isn't mounted yet.
  const target = gutterRef.current ?? (typeof document !== 'undefined' ? document.body : null);
  if (!target) return null;

  const content = (
    <AnimatePresence>
      {!isOpen && (
        <motion.button
          key="ledger-tab"
          layoutId="chat-trigger"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ type: 'spring', stiffness: 300, damping: 25 }}
          onClick={toggleDrawer}
          className={`relative flex flex-col items-center gap-2 py-3 px-1.5 mx-auto rounded-l-lg border-r-0 cursor-pointer ${
            isWaiting
              ? 'bg-amber-950/30 border border-r-0 border-amber-500/50 shadow-[inset_-2px_0_12px_rgba(245,158,11,0.2)]'
              : hasPendingAction
                ? 'bg-amber-500/10 border border-r-0 border-amber-500/50'
                : 'bg-wr-bg/80 border border-r-0 border-cyan-500/30'
          }`}
          style={{
            boxShadow: isWaiting
              ? '-10px 0 15px rgba(0,0,0,0.5), inset -2px 0 12px rgba(245,158,11,0.2)'
              : '-10px 0 15px rgba(0,0,0,0.5)',
          }}
          title={isWaiting ? 'Input Required — Open Mission Log' : 'Open Mission Log'}
          data-testid="ledger-trigger-tab"
        >
          {/* Unread badge */}
          {unreadCount > 0 && (
            <span className="absolute -top-2 -left-2 min-w-[18px] h-[18px] flex items-center justify-center rounded-full bg-red-600 ring-1 ring-slate-950 text-body-xs font-bold text-white px-1">
              {unreadCount > 9 ? '9+' : unreadCount}
            </span>
          )}

          {/* Pending action badge */}
          {hasPendingAction && (
            <span className="absolute -top-1 -right-1 w-3 h-3 rounded-full bg-amber-400 animate-pulse" />
          )}

          {/* Hardware LED indicator */}
          <span className="relative flex items-center justify-center w-1.5 h-1.5">
            <span
              className={`absolute inset-0 rounded-full ${
                isWaiting ? 'bg-amber-400' : 'bg-cyan-500/50'
              }`}
            />
            {isWaiting && (
              <span className="absolute inset-0 rounded-full bg-amber-400 animate-ping blur-[1px]" />
            )}
          </span>

          {/* Tactical icon */}
          <TacticalLogIcon isWaiting={isWaiting} />

          {/* Dymo-label vertical text */}
          <span
            className={`text-body-xs font-mono font-black tracking-[0.3em] transition-colors ${
              isWaiting ? 'text-amber-400' : 'text-cyan-500/70'
            }`}
            style={{ writingMode: 'vertical-lr' }}
          >
            {isWaiting ? 'ACTION' : 'LEDGER'}
          </span>

          {/* Machined edge highlight */}
          <span className="absolute right-0 top-2 bottom-2 w-[1px] bg-gradient-to-b from-transparent via-cyan-500/20 to-transparent pointer-events-none" />
        </motion.button>
      )}
    </AnimatePresence>
  );

  return createPortal(content, target);
};

export default LedgerTriggerTab;
