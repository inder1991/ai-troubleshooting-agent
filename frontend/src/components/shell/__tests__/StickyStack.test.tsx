import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { StickyStack } from '../StickyStack';

// jsdom has no ResizeObserver by default. Shim it.
class MockResizeObserver {
  callback: ResizeObserverCallback;
  static instances: MockResizeObserver[] = [];
  constructor(cb: ResizeObserverCallback) {
    this.callback = cb;
    MockResizeObserver.instances.push(this);
  }
  observe() {}
  disconnect() {}
  fire() {
    // @ts-expect-error test shim
    this.callback([], this);
  }
}

const originalRO = (global as unknown as { ResizeObserver: unknown }).ResizeObserver;

describe('StickyStack', () => {
  beforeEach(() => {
    // @ts-expect-error injecting into jsdom
    global.ResizeObserver = MockResizeObserver;
    MockResizeObserver.instances = [];
  });

  afterEach(() => {
    // @ts-expect-error restoring
    global.ResizeObserver = originalRO;
  });

  it('renders children inside a sticky wrapper', () => {
    const { getByText } = render(
      <StickyStack>
        <div>banner row</div>
        <div>anchor bar</div>
      </StickyStack>,
    );
    expect(getByText('banner row')).toBeInTheDocument();
    expect(getByText('anchor bar')).toBeInTheDocument();
  });

  it('applies sticky + z-token class to the wrapper', () => {
    const { getByTestId } = render(
      <StickyStack data-testid="stack">
        <div>x</div>
      </StickyStack>,
    );
    const wrapper = getByTestId('stack');
    expect(wrapper.className).toMatch(/sticky/);
    expect(wrapper.className).toMatch(/top-0/);
    expect(wrapper.className).toMatch(/z-\[var\(--z-column-sticky\)\]/);
  });

  it('publishes --sticky-stack-h on parent after mount', async () => {
    const parent = document.createElement('div');
    document.body.appendChild(parent);

    render(
      <StickyStack data-testid="stack">
        <div style={{ height: 60 }}>x</div>
      </StickyStack>,
      { container: parent },
    );

    // rAF fires on next browser frame; waitFor polls until it does.
    await waitFor(() => {
      const val = parent.style.getPropertyValue('--sticky-stack-h');
      expect(val).toMatch(/^\d+px$/);
    });
    document.body.removeChild(parent);
  });

  it('disconnects the observer on unmount', () => {
    const parent = document.createElement('div');
    document.body.appendChild(parent);

    const { unmount } = render(
      <StickyStack>
        <div>x</div>
      </StickyStack>,
      { container: parent },
    );

    const ro = MockResizeObserver.instances[0];
    const disconnect = vi.spyOn(ro, 'disconnect');

    unmount();

    expect(disconnect).toHaveBeenCalled();
    document.body.removeChild(parent);
  });

  it('observes the wrapper element', () => {
    const parent = document.createElement('div');
    document.body.appendChild(parent);

    const observeSpy = vi.spyOn(MockResizeObserver.prototype, 'observe');
    render(
      <StickyStack data-testid="stack">
        <div>x</div>
      </StickyStack>,
      { container: parent },
    );

    expect(observeSpy).toHaveBeenCalled();
    document.body.removeChild(parent);
    observeSpy.mockRestore();
  });
});
