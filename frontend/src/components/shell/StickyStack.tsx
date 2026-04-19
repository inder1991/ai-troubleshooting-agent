import React, { useLayoutEffect, useRef } from 'react';

/**
 * StickyStack (PR 1 of the War Room grid-shell migration)
 *
 * Single sticky wrapper per column. Every element inside renders as a
 * normal block, but the WHOLE STACK sticks to the top of its scroll
 * container via `position: sticky; top: 0`. The stack measures its own
 * height through a ResizeObserver and publishes the value as the
 * `--sticky-stack-h` custom property on its parent element.
 *
 * Why:
 *   Section anchors in the same scroll container use
 *   `scroll-margin-top: calc(var(--sticky-stack-h, 0px) + 8px)`, so
 *   jump-link clicks ALWAYS land below the stuck chrome — even when
 *   the sticky-stack contents change (banner appears, filter bar
 *   toggles, etc.). Add or remove a sticky element and every anchor
 *   re-adjusts automatically.
 *
 * Thrash guards:
 *   ResizeObserver fires liberally in a live multi-agent environment
 *   (token streaming, status dots pulsing, etc.). We coalesce callbacks
 *   with requestAnimationFrame and cap CSS-variable writes at ~10 Hz
 *   via a 100ms debounce. Writes only happen when the height actually
 *   changes.
 *
 * No props other than `children` and optional className — the stack is
 * meant to be ultra-predictable.
 */

interface StickyStackProps {
  children: React.ReactNode;
  className?: string;
  /**
   * Optional test hook — exposes the element for jsdom tests that need
   * to drive ResizeObserver manually.
   */
  'data-testid'?: string;
}

const MIN_WRITE_INTERVAL_MS = 100;

export function StickyStack({
  children,
  className = '',
  ...rest
}: StickyStackProps) {
  const ref = useRef<HTMLDivElement>(null);
  const rafRef = useRef<number | null>(null);
  const lastWriteAtRef = useRef<number>(0);
  const lastHeightRef = useRef<number>(-1);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;

    const parent = el.parentElement;
    if (!parent) return;

    const write = (height: number) => {
      // Skip writes at the same height — nothing to sync.
      if (height === lastHeightRef.current) return;
      const now =
        typeof performance !== 'undefined' && performance.now
          ? performance.now()
          : Date.now();
      if (now - lastWriteAtRef.current < MIN_WRITE_INTERVAL_MS) return;
      lastHeightRef.current = height;
      lastWriteAtRef.current = now;
      parent.style.setProperty('--sticky-stack-h', `${height}px`);
    };

    const scheduleMeasure = () => {
      if (rafRef.current != null) return;
      rafRef.current = requestAnimationFrame(() => {
        rafRef.current = null;
        if (el) write(el.offsetHeight);
      });
    };

    // Initial measurement + subscribe.
    scheduleMeasure();
    const ro = new ResizeObserver(scheduleMeasure);
    ro.observe(el);

    return () => {
      ro.disconnect();
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  return (
    <div
      ref={ref}
      className={`sticky top-0 z-[var(--z-column-sticky)] ${className}`}
      data-testid={rest['data-testid']}
    >
      {children}
    </div>
  );
}

export default StickyStack;
