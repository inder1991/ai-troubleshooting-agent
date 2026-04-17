import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { IndependentVerificationStrip } from '../IndependentVerificationStrip';

describe('IndependentVerificationStrip', () => {
  it('renders strip with dashed-border distinction when retriever pins present', () => {
    render(
      <IndependentVerificationStrip
        pins={[
          {
            tool_name: 'k8s.list_events',
            query: '...',
            query_timestamp: '2026-04-17T14:30:00Z',
            raw_value: 'pod evicted',
          },
        ]}
      />,
    );
    const strip = screen.getByTestId('indep-verif-strip');
    expect(strip.className).toMatch(/border-dashed/);
    expect(screen.getByText(/Independent verification/i)).toBeInTheDocument();
    expect(screen.getByText(/k8s\.list_events/)).toBeInTheDocument();
  });

  it('renders nothing when no pins', () => {
    const { container } = render(<IndependentVerificationStrip pins={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('uses singular "pin" for one, plural for many', () => {
    const { rerender } = render(
      <IndependentVerificationStrip
        pins={[{ tool_name: 'logs.search', raw_value: 'line' }]}
      />,
    );
    expect(screen.getByText(/1 pin\b/)).toBeInTheDocument();

    rerender(
      <IndependentVerificationStrip
        pins={[
          { tool_name: 'logs.search', raw_value: 'line' },
          { tool_name: 'metrics.query', raw_value: 'value' },
        ]}
      />,
    );
    expect(screen.getByText(/2 pins/)).toBeInTheDocument();
  });

  it('falls back from claim to raw_value to query for the line text', () => {
    render(
      <IndependentVerificationStrip
        pins={[
          { tool_name: 'a.tool', claim: 'claim text' },
          { tool_name: 'b.tool', raw_value: 'raw text' },
          { tool_name: 'c.tool', query: 'query text' },
        ]}
      />,
    );
    expect(screen.getByText(/claim text/)).toBeInTheDocument();
    expect(screen.getByText(/raw text/)).toBeInTheDocument();
    expect(screen.getByText(/query text/)).toBeInTheDocument();
  });
});
