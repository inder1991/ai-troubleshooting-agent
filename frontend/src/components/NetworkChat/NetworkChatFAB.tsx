import React from 'react';

interface NetworkChatFABProps {
  onClick: () => void;
  hasUnread?: boolean;
}

const NetworkChatFAB: React.FC<NetworkChatFABProps> = ({ onClick, hasUnread }) => (
  <button
    onClick={onClick}
    title="Network Assistant"
    aria-label="Open Network Assistant"
    className="fixed bottom-6 right-6 z-50 w-12 h-12 rounded-full bg-duck-accent text-duck-bg shadow-[0_4px_20px_rgba(224,159,62,0.3)] hover:shadow-[0_4px_24px_rgba(224,159,62,0.5)] transition-all duration-200 flex items-center justify-center hover:scale-105 active:scale-95 focus-visible:outline focus-visible:outline-2 focus-visible:outline-amber-400"
  >
    <span className="material-symbols-outlined text-[22px]">chat</span>
    {hasUnread && (
      <span className="absolute -top-0.5 -right-0.5 w-3 h-3 bg-red-500 rounded-full border-2 border-duck-bg" />
    )}
  </button>
);

export default NetworkChatFAB;
