import React from 'react';
import * as Popover from '@radix-ui/react-popover';
import type { Signal, ScheduledSignals } from './signalScheduler';

/**
 * BannerRow — the conditional first line of the War Room banner region
 * (Mode 3). Renders only when a system-level signal is active. The
 * highest-severity signal takes the row; all other active signals are
 * surfaced as a "+N hidden warnings" text-link that opens a Radix
 * Popover listing them.
 *
 * Critique fixes landed:
 *   · No ⦿ glyphs — prose text-link instead
 *   · Severity encoded on the left-gutter tick only, not the text
 *   · Radix Popover (not Menu) for suppressed-signal detail
 */

interface BannerRowProps {
  schedule: ScheduledSignals;
  onAction?: (signal: Signal) => void;
}

function severityTick(severity: Signal['severity']): string {
  switch (severity) {
    case 'page': return 'bg-red-500';
    case 'warn': return 'bg-amber-400';
    case 'info': return 'bg-slate-400';
  }
}

export const BannerRow: React.FC<BannerRowProps> = ({ schedule, onAction }) => {
  const { top, suppressed } = schedule;
  if (!top) return null;

  return (
    <div
      className="banner-row flex items-center gap-3 px-6 py-2.5 border-b border-wr-border bg-wr-bg"
      data-testid="banner-row"
      role="status"
      aria-live="polite"
    >
      {/* Severity tick */}
      <span
        aria-hidden
        className={`inline-block w-1 h-5 rounded-full ${severityTick(top.severity)} shrink-0`}
      />

      {/* Headline prose */}
      <p
        className="flex-1 min-w-0 text-[13px] text-wr-paper leading-[1.4]"
        data-testid="banner-headline"
      >
        {top.headline}
      </p>

      {/* Action button */}
      {top.actionLabel && (
        <button
          type="button"
          onClick={() => onAction?.(top)}
          className="shrink-0 text-[12px] font-medium text-wr-paper underline-offset-4 hover:underline focus-visible:underline focus:outline-none"
          data-testid="banner-action"
        >
          {top.actionLabel}
        </button>
      )}

      {/* +N hidden warnings (Radix Popover — no ⦿ glyph) */}
      {suppressed.length > 0 && (
        <Popover.Root>
          <Popover.Trigger asChild>
            <button
              type="button"
              className="shrink-0 font-editorial italic text-[11px] text-wr-text-muted hover:text-wr-paper hover:underline focus-visible:underline focus:outline-none underline-offset-4 transition-colors"
              data-testid="banner-suppressed-trigger"
            >
              + {suppressed.length} hidden warning{suppressed.length === 1 ? '' : 's'}
            </button>
          </Popover.Trigger>
          <Popover.Portal>
            <Popover.Content
              side="bottom"
              align="end"
              sideOffset={8}
              className="suppressed-signals-popover bg-wr-bg border border-wr-border rounded-sm px-4 py-3 max-w-[420px]"
              style={{ zIndex: 'var(--z-tooltip)' }}
              data-testid="banner-suppressed-popover"
            >
              <ul className="space-y-1.5">
                {suppressed.map((s) => (
                  <li
                    key={s.kind}
                    className="flex items-start gap-2.5 text-[12px] text-wr-text-muted"
                  >
                    <span
                      aria-hidden
                      className={`mt-1.5 inline-block w-1 h-1 rounded-full ${severityTick(s.severity)} shrink-0`}
                    />
                    <span className="leading-[1.4]">{s.headline}</span>
                  </li>
                ))}
              </ul>
              <Popover.Arrow className="fill-wr-border" />
            </Popover.Content>
          </Popover.Portal>
        </Popover.Root>
      )}
    </div>
  );
};

export default BannerRow;
