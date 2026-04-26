import React from 'react';
import * as ScrollArea from '@radix-ui/react-scroll-area';

/**
 * EditorialScrollArea (PR 4 of the War Room grid-shell migration)
 *
 * Single wrapper around Radix ScrollArea that enforces three
 * invariants across every scrollable surface in the War Room:
 *
 *   1. Scrollbars are always visible on mouse-only inputs — the
 *      browser-hidden "overflow-y-auto + scrollbar-hide" pattern
 *      that stranded users is banned.
 *   2. Scrollbars are themed against the warm-paper palette so they
 *      read as intentional chrome, not browser default.
 *   3. Keyboard interop is preserved — Radix ScrollArea exposes the
 *      viewport as a focusable container so PageUp / PageDown /
 *      arrow-key scroll works.
 *
 * Consumers forward a ref to the viewport when they need to
 * programmatic-scroll (e.g. auto-follow-to-bottom in long logs).
 */

export interface EditorialScrollAreaProps {
  children: React.ReactNode;
  className?: string;
  /** Orientation hint; defaults to 'vertical' (the common case). */
  orientation?: 'vertical' | 'horizontal' | 'both';
  /** Optional forwarded ref for the viewport element. */
  viewportRef?: React.RefObject<HTMLDivElement | null>;
  /** Optional data-testid for the outer ScrollArea.Root. */
  'data-testid'?: string;
  onScroll?: React.UIEventHandler<HTMLDivElement>;
}

export const EditorialScrollArea: React.FC<EditorialScrollAreaProps> = ({
  children,
  className = '',
  orientation = 'vertical',
  viewportRef,
  onScroll,
  ...rest
}) => {
  const showVertical = orientation === 'vertical' || orientation === 'both';
  const showHorizontal = orientation === 'horizontal' || orientation === 'both';

  return (
    <ScrollArea.Root
      className={`editorial-scrollarea relative h-full w-full overflow-hidden ${className}`}
      scrollHideDelay={600}
      data-testid={rest['data-testid']}
    >
      <ScrollArea.Viewport
        ref={viewportRef}
        // [&>div]:!block + !min-w-0 — Radix wraps the children in a
        // `display: table; min-width: 100%` div by default, which lets
        // wide content (4-up stat grids, long pre blocks, unwrapped
        // hashes) expand past the column and then get clipped by the
        // region's overflow:hidden. Force block layout so the viewport
        // constrains its content to the grid column width.
        className="h-full w-full [&>div]:!block [&>div]:!min-w-0"
        onScroll={onScroll}
      >
        {children}
      </ScrollArea.Viewport>

      {showVertical && (
        <ScrollArea.Scrollbar
          orientation="vertical"
          className="editorial-scrollbar editorial-scrollbar--vertical flex select-none touch-none p-0.5 transition-colors duration-200 ease-out w-2.5"
        >
          <ScrollArea.Thumb className="editorial-scrollbar__thumb relative flex-1 rounded bg-wr-text-muted/40 hover:bg-wr-text-muted/60 transition-colors" />
        </ScrollArea.Scrollbar>
      )}

      {showHorizontal && (
        <ScrollArea.Scrollbar
          orientation="horizontal"
          className="editorial-scrollbar editorial-scrollbar--horizontal flex select-none touch-none p-0.5 transition-colors duration-200 ease-out h-2.5 flex-col"
        >
          <ScrollArea.Thumb className="editorial-scrollbar__thumb relative flex-1 rounded bg-wr-text-muted/40 hover:bg-wr-text-muted/60 transition-colors" />
        </ScrollArea.Scrollbar>
      )}

      {orientation === 'both' && <ScrollArea.Corner className="bg-transparent" />}
    </ScrollArea.Root>
  );
};

export default EditorialScrollArea;
