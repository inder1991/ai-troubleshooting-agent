import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CoverageGapsBanner } from '../CoverageGapsBanner';

describe('CoverageGapsBanner', () => {
  it('renders nothing when no gaps', () => {
    const { container } = render(<CoverageGapsBanner gaps={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders count and expands to show gap reasons', () => {
    render(
      <CoverageGapsBanner
        gaps={[
          'metrics_agent: prometheus unreachable',
          'k8s_agent: circuit open',
        ]}
      />
    );
    expect(screen.getByText(/2 checks skipped/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /show/i }));
    expect(screen.getByText(/prometheus unreachable/)).toBeInTheDocument();
    expect(screen.getByText(/circuit open/)).toBeInTheDocument();
  });

  it('collapses back when "hide" clicked', () => {
    render(<CoverageGapsBanner gaps={['metrics_agent: reason']} />);
    fireEvent.click(screen.getByRole('button', { name: /show/i }));
    expect(screen.getByText(/metrics_agent: reason/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /hide/i }));
    expect(screen.queryByText(/metrics_agent: reason/)).toBeNull();
  });

  it('uses singular "check" for one gap', () => {
    render(<CoverageGapsBanner gaps={['metrics_agent: only one']} />);
    expect(screen.getByText(/1 check skipped/i)).toBeInTheDocument();
  });

  it('renders with amber accent (wr-amber)', () => {
    render(<CoverageGapsBanner gaps={['metrics_agent: any']} />);
    const banner = screen.getByTestId('coverage-gaps-banner');
    expect(banner.className).toMatch(/wr-amber|amber/);
  });
});
