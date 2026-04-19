import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import BannerRow from '../BannerRow';
import type { ScheduledSignals, Signal } from '../signalScheduler';

function sig(over: Partial<Signal> = {}): Signal {
  return {
    kind: 'fetch-fail',
    severity: 'warn',
    headline: 'Connection issue — data may be stale.',
    actionLabel: 'Retry',
    ...over,
  };
}

function sched(top: Signal | null, suppressed: Signal[] = []): ScheduledSignals {
  return { top, suppressed };
}

describe('BannerRow', () => {
  it('renders nothing when schedule.top is null', () => {
    const { container } = render(<BannerRow schedule={sched(null)} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders the top signal headline', () => {
    render(<BannerRow schedule={sched(sig())} />);
    expect(screen.getByTestId('banner-headline').textContent).toMatch(
      /Connection issue/,
    );
  });

  it('renders the action button when actionLabel is set', () => {
    const onAction = vi.fn();
    render(<BannerRow schedule={sched(sig())} onAction={onAction} />);
    const btn = screen.getByTestId('banner-action');
    fireEvent.click(btn);
    expect(onAction).toHaveBeenCalledTimes(1);
    expect(onAction.mock.calls[0][0].kind).toBe('fetch-fail');
  });

  it('omits action button when no actionLabel', () => {
    render(<BannerRow schedule={sched(sig({ actionLabel: undefined }))} />);
    expect(screen.queryByTestId('banner-action')).toBeNull();
  });

  it('shows "+N hidden warnings" when suppressed signals exist', () => {
    render(
      <BannerRow
        schedule={sched(sig(), [sig({ kind: 'ws-disconnected', headline: 'offline' })])}
      />,
    );
    expect(screen.getByTestId('banner-suppressed-trigger').textContent).toMatch(
      /\+ 1 hidden warning/,
    );
  });

  it('hides suppressed trigger when there are no suppressed signals', () => {
    render(<BannerRow schedule={sched(sig(), [])} />);
    expect(screen.queryByTestId('banner-suppressed-trigger')).toBeNull();
  });

  it('uses text-link prose rather than ⦿ glyphs for suppressed count', () => {
    render(
      <BannerRow schedule={sched(sig(), [sig({ kind: 'drain', headline: 'draining' })])} />,
    );
    const trigger = screen.getByTestId('banner-suppressed-trigger');
    // No ⦿ glyph, no other dot characters in the trigger text
    expect(trigger.textContent).not.toMatch(/⦿/);
    expect(trigger.textContent).not.toMatch(/●/);
    expect(trigger.className).toMatch(/font-editorial/);
    expect(trigger.className).toMatch(/italic/);
  });
});
