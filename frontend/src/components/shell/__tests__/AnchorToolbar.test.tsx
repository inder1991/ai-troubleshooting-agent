import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AnchorToolbar, AnchorPill } from '../AnchorToolbar';

// jsdom shim
class MockResizeObserver {
  observe() {}
  disconnect() {}
  unobserve() {}
}

const originalRO = (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver;

beforeEach(() => {
  (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = MockResizeObserver;
});
afterEach(() => {
  (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = originalRO;
});

function pills(n: number): AnchorPill[] {
  return Array.from({ length: n }).map((_, i) => ({
    id: `p${i}`,
    label: `Section ${i}`,
    anchor: `section-${i}`,
    count: i + 1,
  }));
}

describe('AnchorToolbar', () => {
  it('renders nothing when given no pills', () => {
    const { container } = render(<AnchorToolbar pills={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders a Radix Toolbar with all pills as anchor links', () => {
    render(<AnchorToolbar pills={pills(3)} />);
    expect(screen.getByTestId('anchor-toolbar')).toBeInTheDocument();
    expect(screen.getByTestId('anchor-pill-p0')).toHaveAttribute('href', '#section-0');
    expect(screen.getByTestId('anchor-pill-p1')).toHaveAttribute('href', '#section-1');
    expect(screen.getByTestId('anchor-pill-p2')).toHaveAttribute('href', '#section-2');
  });

  it('shows counts alongside labels when provided', () => {
    render(<AnchorToolbar pills={pills(1)} />);
    const pill = screen.getByTestId('anchor-pill-p0');
    expect(pill.textContent).toMatch(/Section 0/);
    expect(pill.textContent).toMatch(/\(1\)/);
  });

  it('renders both chevron buttons with accessible names', () => {
    render(<AnchorToolbar pills={pills(2)} />);
    expect(screen.getByLabelText(/scroll sections left/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/scroll sections right/i)).toBeInTheDocument();
  });

  it('applies severity tone classes per pill', () => {
    render(
      <AnchorToolbar
        pills={[
          { id: 'rc', label: 'Root Cause', anchor: 'section-root-cause', tone: 'severity-high' },
          { id: 'tr', label: 'Traces', anchor: 'section-traces', tone: 'paper' },
        ]}
      />,
    );
    expect(screen.getByTestId('anchor-pill-rc').className).toMatch(/text-red-400/);
    expect(screen.getByTestId('anchor-pill-tr').className).toMatch(/text-wr-paper/);
  });

  it('chevrons start disabled when content does not overflow', () => {
    render(<AnchorToolbar pills={pills(2)} />);
    // In jsdom without layout, scrollWidth === clientWidth === 0
    expect(screen.getByTestId('anchor-chevron-left')).toBeDisabled();
    expect(screen.getByTestId('anchor-chevron-right')).toBeDisabled();
  });

  it('chevrons do not throw when clicked even if disabled', () => {
    render(<AnchorToolbar pills={pills(2)} />);
    // Smoke test — Radix buttons ignore disabled click but shouldn't crash
    fireEvent.click(screen.getByTestId('anchor-chevron-left'));
    fireEvent.click(screen.getByTestId('anchor-chevron-right'));
  });
});
