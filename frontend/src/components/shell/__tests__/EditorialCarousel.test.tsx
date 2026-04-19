import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { EditorialCarousel } from '../EditorialCarousel';

class MockResizeObserver {
  observe() {}
  disconnect() {}
  unobserve() {}
}
class MockIntersectionObserver {
  observe() {}
  disconnect() {}
  unobserve() {}
  takeRecords() { return []; }
}
const originalRO = (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver;
const originalIO = (globalThis as unknown as { IntersectionObserver: unknown }).IntersectionObserver;

// Embla calls matchMedia(...).addEventListener — jsdom's default
// MediaQueryList lacks that method. Shim a minimal MQL that Embla can
// attach listeners to without crashing.
const originalMM = window.matchMedia;

beforeEach(() => {
  (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = MockResizeObserver;
  (globalThis as unknown as { IntersectionObserver: unknown }).IntersectionObserver = MockIntersectionObserver;
  // @ts-expect-error jsdom shim
  window.matchMedia = (q: string) => ({
    matches: false,
    media: q,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    onchange: null,
    dispatchEvent: () => false,
  });
});
afterEach(() => {
  (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = originalRO;
  (globalThis as unknown as { IntersectionObserver: unknown }).IntersectionObserver = originalIO;
  window.matchMedia = originalMM;
});

describe('EditorialCarousel', () => {
  it('renders nothing when given zero items', () => {
    const { container } = render(
      <EditorialCarousel
        items={[]}
        renderItem={(x: string) => <div>{x}</div>}
        getKey={(x, i) => `k-${i}`}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders each item as a slide', () => {
    render(
      <EditorialCarousel
        items={['a', 'b', 'c']}
        renderItem={(x) => <div>slide-{x}</div>}
        getKey={(x) => x}
      />,
    );
    expect(screen.getByText('slide-a')).toBeInTheDocument();
    expect(screen.getByText('slide-b')).toBeInTheDocument();
    expect(screen.getByText('slide-c')).toBeInTheDocument();
  });

  it('renders explicit chevron buttons with accessible names', () => {
    render(
      <EditorialCarousel
        items={['a', 'b']}
        renderItem={(x) => <div>{x}</div>}
        getKey={(x) => x}
      />,
    );
    expect(screen.getByLabelText(/previous slide/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/next slide/i)).toBeInTheDocument();
  });

  it('uses region role + custom aria-label on the root', () => {
    render(
      <EditorialCarousel
        items={['a']}
        renderItem={(x) => <div>{x}</div>}
        getKey={(x) => x}
        ariaLabel="Symptoms"
      />,
    );
    expect(screen.getByRole('region', { name: 'Symptoms' })).toBeInTheDocument();
  });

  it('renders as many slides as items × slidesToShow math allows', () => {
    render(
      <EditorialCarousel
        items={['a', 'b', 'c', 'd']}
        renderItem={(x) => <div>s-{x}</div>}
        getKey={(x) => x}
        slidesToShow={2}
      />,
    );
    expect(screen.getByTestId('editorial-slide-0')).toBeInTheDocument();
    expect(screen.getByTestId('editorial-slide-3')).toBeInTheDocument();
  });
});
