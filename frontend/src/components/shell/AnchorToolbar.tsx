import React, { useCallback, useEffect, useRef, useState } from 'react';
import * as Toolbar from '@radix-ui/react-toolbar';
import { ChevronLeft, ChevronRight } from 'lucide-react';

/**
 * AnchorToolbar (PR 4 of the War Room grid-shell migration)
 *
 * Replacement for the evidence column's old "overflow-x-auto
 * scrollbar-hide" anchor bar, which stranded mouse-only users when
 * more than ~7 section pills existed.
 *
 * Fixes:
 *   · Explicit left/right chevron buttons that page-scroll the bar
 *   · Fade-mask edges signal "more content past the viewport"
 *   · Radix Toolbar primitive gives arrow-key navigation between pills
 *   · Chevrons auto-disable when at bar bounds
 */

export interface AnchorPill {
  id: string;
  label: string;
  /** Target anchor id; rendered as an <a href="#..."> so click + keyboard both work. */
  anchor: string;
  /** Optional count for the pill's trailing number. */
  count?: number;
  /** Optional tone override — defaults to `paper`. */
  tone?: 'paper' | 'severity-high' | 'severity-medium' | 'severity-low';
}

interface AnchorToolbarProps {
  pills: AnchorPill[];
  className?: string;
}

const TONE_CLASS: Record<NonNullable<AnchorPill['tone']>, string> = {
  paper: 'text-wr-paper hover:bg-wr-bg-elevated',
  'severity-high': 'text-red-400 hover:bg-wr-severity-high/10',
  'severity-medium': 'text-amber-400 hover:bg-wr-severity-medium/10',
  'severity-low': 'text-slate-400 hover:bg-wr-inset/50',
};

export const AnchorToolbar: React.FC<AnchorToolbarProps> = ({ pills, className = '' }) => {
  const viewportRef = useRef<HTMLDivElement>(null);
  const [atStart, setAtStart] = useState(true);
  const [atEnd, setAtEnd] = useState(true);

  const measure = useCallback(() => {
    const el = viewportRef.current;
    if (!el) return;
    const { scrollLeft, scrollWidth, clientWidth } = el;
    setAtStart(scrollLeft <= 1);
    setAtEnd(scrollLeft + clientWidth >= scrollWidth - 1);
  }, []);

  useEffect(() => {
    measure();
    const el = viewportRef.current;
    if (!el) return;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    el.addEventListener('scroll', measure, { passive: true });
    return () => {
      ro.disconnect();
      el.removeEventListener('scroll', measure);
    };
  }, [measure, pills.length]);

  const page = (dir: 'left' | 'right') => {
    const el = viewportRef.current;
    if (!el) return;
    const delta = el.clientWidth * 0.8 * (dir === 'left' ? -1 : 1);
    el.scrollBy({ left: delta, behavior: 'smooth' });
  };

  if (pills.length === 0) return null;

  return (
    <Toolbar.Root
      aria-label="Evidence sections"
      className={`anchor-toolbar flex items-center gap-1 bg-wr-bg/95 backdrop-blur border-b border-wr-border rounded-sm px-1 py-1 ${className}`}
      data-testid="anchor-toolbar"
    >
      <button
        type="button"
        onClick={() => page('left')}
        disabled={atStart}
        aria-label="Scroll sections left"
        className="shrink-0 p-1 rounded text-wr-text-muted disabled:opacity-30 disabled:cursor-default hover:text-wr-paper transition-colors focus-visible:outline focus-visible:outline-1 focus-visible:outline-wr-text-muted"
        data-testid="anchor-chevron-left"
      >
        <ChevronLeft className="w-4 h-4" aria-hidden />
      </button>

      <div
        ref={viewportRef}
        className="anchor-toolbar__viewport flex-1 min-w-0 overflow-x-auto"
        style={{
          // Fade-mask both edges; hidden via inline style so Tailwind's
          // purge doesn't strip dynamic mask values.
          maskImage:
            'linear-gradient(to right, transparent 0, #000 24px, #000 calc(100% - 24px), transparent 100%)',
          WebkitMaskImage:
            'linear-gradient(to right, transparent 0, #000 24px, #000 calc(100% - 24px), transparent 100%)',
          scrollbarWidth: 'none',
        }}
      >
        <div className="flex items-center gap-1.5 min-w-max px-2">
          {pills.map((p) => {
            const tone = TONE_CLASS[p.tone ?? 'paper'];
            return (
              <Toolbar.Link
                key={p.id}
                href={`#${p.anchor}`}
                className={`text-body-xs uppercase font-bold px-2 py-1 rounded whitespace-nowrap transition-colors focus-visible:outline focus-visible:outline-1 focus-visible:outline-wr-text-muted ${tone}`}
                data-testid={`anchor-pill-${p.id}`}
              >
                {p.label}
                {typeof p.count === 'number' && (
                  <span className="ml-1 opacity-70">({p.count})</span>
                )}
              </Toolbar.Link>
            );
          })}
        </div>
      </div>

      <button
        type="button"
        onClick={() => page('right')}
        disabled={atEnd}
        aria-label="Scroll sections right"
        className="shrink-0 p-1 rounded text-wr-text-muted disabled:opacity-30 disabled:cursor-default hover:text-wr-paper transition-colors focus-visible:outline focus-visible:outline-1 focus-visible:outline-wr-text-muted"
        data-testid="anchor-chevron-right"
      >
        <ChevronRight className="w-4 h-4" aria-hidden />
      </button>
    </Toolbar.Root>
  );
};

export default AnchorToolbar;
