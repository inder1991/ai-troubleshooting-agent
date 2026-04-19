import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { useState } from 'react';
import { PaneDrawer } from '../PaneDrawer';

// Build a synthetic RefObject whose .current is the state element —
// Radix evaluates container on every render, so once the state
// update for the mount target fires, the next render sees a valid
// container ref and the Dialog.Portal mounts there.
function Harness({
  open = true,
  maxInlineSize = '300px',
}: { open?: boolean; maxInlineSize?: string }) {
  const [mountEl, setMountEl] = useState<HTMLDivElement | null>(null);

  // Synthetic ref object. Kept stable across renders via the closure.
  const refObject = { current: mountEl } as { current: HTMLDivElement | null };

  return (
    <div data-testid="mount-target" ref={setMountEl} style={{ position: 'relative' }}>
      {mountEl && (
        <PaneDrawer
          open={open}
          onOpenChange={() => {}}
          mountInto={refObject}
          maxInlineSize={maxInlineSize}
          title="Test drawer"
        >
          <div>drawer content</div>
        </PaneDrawer>
      )}
    </div>
  );
}

describe('PaneDrawer', () => {
  it('renders children when open', () => {
    render(<Harness open />);
    expect(screen.getByText('drawer content')).toBeInTheDocument();
  });

  it('does not render children when closed', () => {
    render(<Harness open={false} />);
    expect(screen.queryByText('drawer content')).toBeNull();
  });

  it('mounts inside the provided container, not document.body', () => {
    render(<Harness open />);
    const mount = screen.getByTestId('mount-target');
    expect(mount.contains(screen.getByText('drawer content'))).toBe(true);
  });

  it('caps inline-size via the style prop', () => {
    render(<Harness open maxInlineSize="min(640px, 50cqi)" />);
    const content = screen.getByText('drawer content').parentElement;
    // Radix Dialog.Content is the element that gets the style prop
    expect(content?.getAttribute('style')).toMatch(/max-inline-size:\s*min\(640px,\s*50cqi\)/);
  });

  it('provides an accessible title to screen readers', () => {
    render(<Harness open />);
    // sr-only Dialog.Title still reachable via accessible-name lookup
    expect(screen.getByText('Test drawer')).toBeInTheDocument();
  });
});
