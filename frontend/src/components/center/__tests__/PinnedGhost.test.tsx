import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PinnedGhost } from '../PinnedGhost';
import { usePinStore } from '../../../stores/pinStore';

describe('PinnedGhost', () => {
  beforeEach(() => {
    usePinStore.getState().clear();
  });

  it('renders the pinned label with a ghost prefix', () => {
    usePinStore.getState().pin({ id: 'root-cause', label: 'NullPointer', agentCode: 'L' });
    render(<PinnedGhost id="root-cause" label="NullPointer" agentCode="L" />);
    const ghost = screen.getByTestId('pinned-ghost-root-cause');
    expect(ghost.textContent).toMatch(/pinned above/);
    expect(ghost.textContent).toMatch(/NullPointer/);
  });

  it('renders the agent-identity left-border color (red for L)', () => {
    render(<PinnedGhost id="x" label="y" agentCode="L" />);
    expect(screen.getByTestId('pinned-ghost-x').className).toMatch(/border-l-red-500/);
  });

  it('unpin button removes the item from the store', () => {
    usePinStore.getState().pin({ id: 'rc', label: 'x', agentCode: 'L' });
    render(<PinnedGhost id="rc" label="x" agentCode="L" />);
    fireEvent.click(screen.getByTestId('pinned-ghost-unpin-rc'));
    expect(usePinStore.getState().isPinned('rc')).toBe(false);
  });

  it('unpin button has an accessible label', () => {
    render(<PinnedGhost id="rc" label="NPE" agentCode="L" />);
    expect(
      screen.getByRole('button', { name: /unpin NPE/i }),
    ).toBeInTheDocument();
  });

  it('jump-to-pin button scrolls the target into view', () => {
    render(
      <>
        <PinnedGhost id="rc" label="x" agentCode="L" />
        <div data-pin-anchor="rc" data-testid="pin-anchor">
          pinned content
        </div>
      </>,
    );
    const target = screen.getByTestId('pin-anchor');
    let scrolled = false;
    target.scrollIntoView = () => {
      scrolled = true;
    };
    fireEvent.click(screen.getByTestId('pinned-ghost-jump-rc'));
    expect(scrolled).toBe(true);
  });
});
