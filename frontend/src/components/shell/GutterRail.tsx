import React from 'react';

/**
 * GutterRail (PR 1 of the War Room grid-shell migration)
 *
 * The 48px-wide right-edge column of the grid. Owns persistent UI
 * that used to float over the Navigator column (LedgerTriggerTab) and
 * future collapsed-chat handle, narrow-viewport navigator toggle, etc.
 *
 * Being a real grid column rather than a fixed-position overlay is
 * the whole point — nothing in the gutter can cover content in any
 * other column, because the gutter has its own width allocation.
 *
 * PR 1 ships it dormant (no consumer mounts into it yet). PR 3
 * relocates LedgerTriggerTab and the chat collapsed-handle here.
 */

interface GutterRailProps {
  children?: React.ReactNode;
  className?: string;
}

export function GutterRail({ children, className = '' }: GutterRailProps) {
  return (
    <div
      className={`wr-region-gutter flex flex-col items-center py-2 ${className}`}
      data-testid="gutter-rail"
    >
      {children}
    </div>
  );
}

export default GutterRail;
