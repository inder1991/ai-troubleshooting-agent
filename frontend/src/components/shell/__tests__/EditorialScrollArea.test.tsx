import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { EditorialScrollArea } from '../EditorialScrollArea';

/**
 * Radix ScrollArea renders its scrollbar elements lazily — they only
 * appear in the DOM once the viewport's contents overflow. In jsdom
 * without real layout, scrollHeight == clientHeight == 0, so the bars
 * never mount.
 *
 * The tests therefore assert on the ScrollArea root + viewport (always
 * rendered) and on the component's own wrapper class, leaving the
 * scrollbar-visibility check to the Playwright visual regression suite
 * in PR 7 where real layout exists.
 */
describe('EditorialScrollArea', () => {
  it('renders children inside the Radix viewport', () => {
    render(
      <EditorialScrollArea data-testid="ea">
        <div>scrollable content</div>
      </EditorialScrollArea>,
    );
    expect(screen.getByText('scrollable content')).toBeInTheDocument();
  });

  it('emits the editorial-scrollarea wrapper class on the Root', () => {
    const { container } = render(
      <EditorialScrollArea data-testid="ea">
        <div>x</div>
      </EditorialScrollArea>,
    );
    expect(container.querySelector('.editorial-scrollarea')).not.toBeNull();
  });

  it('sets viewport role on Radix.ScrollArea.Viewport', () => {
    const { container } = render(
      <EditorialScrollArea>
        <div>x</div>
      </EditorialScrollArea>,
    );
    // Radix sets data-radix-scroll-area-viewport on its Viewport element
    expect(container.querySelector('[data-radix-scroll-area-viewport]')).not.toBeNull();
  });

  it('accepts a custom className on the root', () => {
    const { container } = render(
      <EditorialScrollArea className="custom-scope">
        <div>x</div>
      </EditorialScrollArea>,
    );
    expect(container.querySelector('.editorial-scrollarea.custom-scope')).not.toBeNull();
  });
});
