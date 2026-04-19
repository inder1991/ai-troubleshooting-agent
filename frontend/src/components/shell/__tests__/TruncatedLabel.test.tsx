import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TruncatedLabel } from '../TruncatedLabel';

class MockResizeObserver {
  static instances: MockResizeObserver[] = [];
  cb: ResizeObserverCallback;
  constructor(cb: ResizeObserverCallback) {
    this.cb = cb;
    MockResizeObserver.instances.push(this);
  }
  observe() {}
  disconnect() {}
  unobserve() {}
}
const originalRO = (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver;

beforeEach(() => {
  (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = MockResizeObserver;
  MockResizeObserver.instances = [];
});
afterEach(() => {
  (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = originalRO;
});

describe('TruncatedLabel', () => {
  it('renders the full text', () => {
    render(<TruncatedLabel text="some short label" data-testid="lbl" />);
    expect(screen.getByTestId('lbl').textContent).toBe('some short label');
  });

  it('sets data-truncated=false when content fits', () => {
    // jsdom returns offsetWidth === scrollWidth === 0 without real layout,
    // which the classifier reads as "not truncated".
    render(<TruncatedLabel text="fits" data-testid="lbl" />);
    expect(screen.getByTestId('lbl').getAttribute('data-truncated')).toBe('false');
  });

  it('applies truncation CSS classes', () => {
    render(<TruncatedLabel text="x" data-testid="lbl" className="extra" />);
    const el = screen.getByTestId('lbl');
    expect(el.className).toMatch(/overflow-hidden/);
    expect(el.className).toMatch(/text-ellipsis/);
    expect(el.className).toMatch(/whitespace-nowrap/);
    expect(el.className).toMatch(/extra/);
  });

  it('honors the `as` prop for the rendered element', () => {
    render(<TruncatedLabel text="x" as="p" data-testid="lbl" />);
    expect(screen.getByTestId('lbl').tagName).toBe('P');
  });

  it('defaults to a span', () => {
    render(<TruncatedLabel text="x" data-testid="lbl" />);
    expect(screen.getByTestId('lbl').tagName).toBe('SPAN');
  });

  it('does not make the span focusable when not truncated', () => {
    render(<TruncatedLabel text="short" data-testid="lbl" />);
    expect(screen.getByTestId('lbl').getAttribute('tabindex')).toBeNull();
  });
});
