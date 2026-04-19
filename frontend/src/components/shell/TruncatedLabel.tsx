import React, { useEffect, useRef, useState } from 'react';
import * as HoverCard from '@radix-ui/react-hover-card';

/**
 * TruncatedLabel (PR 6 of the War Room grid-shell migration)
 *
 * Wraps text that may be too long for its container. When truncation
 * is detected, a Radix HoverCard reveals the full text on hover or
 * keyboard focus. Uses offsetWidth < scrollWidth as the truncation
 * signal — the standard CSS overflow approach.
 *
 * When the text fits, the component is effectively a zero-overhead
 * passthrough — no HoverCard is mounted.
 *
 * Invariants:
 *   · Screen readers always see the full text via the span's title.
 *   · Keyboard users reach the full text via Tab + focus.
 *   · Mouse users reach it via hover after a 200ms delay.
 *   · Touch users reach it via long-press (browser default on title).
 */

interface TruncatedLabelProps {
  text: string;
  className?: string;
  /** Optional override of the visible element tag (default `span`). */
  as?: 'span' | 'div' | 'p' | 'strong';
  /** Optional data-testid. */
  'data-testid'?: string;
}

export const TruncatedLabel: React.FC<TruncatedLabelProps> = ({
  text,
  className = '',
  as: Tag = 'span',
  ...rest
}) => {
  const ref = useRef<HTMLElement>(null);
  const [isTruncated, setIsTruncated] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => {
      setIsTruncated(el.offsetWidth < el.scrollWidth);
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [text]);

  const visible = (
    <Tag
      ref={ref as React.Ref<HTMLElement>}
      className={`truncated-label block overflow-hidden text-ellipsis whitespace-nowrap ${className}`}
      title={isTruncated ? text : undefined}
      data-testid={rest['data-testid']}
      data-truncated={isTruncated ? 'true' : 'false'}
      // Focusable only when truncated — keyboard users tab to the
      // content, not to every passthrough label.
      tabIndex={isTruncated ? 0 : undefined}
    >
      {text}
    </Tag>
  );

  if (!isTruncated) return visible;

  return (
    <HoverCard.Root openDelay={200} closeDelay={150}>
      <HoverCard.Trigger asChild>{visible}</HoverCard.Trigger>
      <HoverCard.Portal>
        <HoverCard.Content
          side="bottom"
          align="start"
          sideOffset={6}
          className="truncated-label__card bg-wr-bg border border-wr-border rounded-sm px-3 py-2 max-w-[460px] text-[12px] text-wr-paper leading-[1.45]"
          style={{ zIndex: 'var(--z-tooltip)' }}
          data-testid={`${rest['data-testid'] ?? 'truncated-label'}-card`}
        >
          {text}
          <HoverCard.Arrow className="fill-wr-border" />
        </HoverCard.Content>
      </HoverCard.Portal>
    </HoverCard.Root>
  );
};

export default TruncatedLabel;
