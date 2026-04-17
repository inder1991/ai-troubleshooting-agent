import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SelfConsistencyBadge } from '../SelfConsistencyBadge';

describe('SelfConsistencyBadge', () => {
  it('renders 3/3 agreement in emerald', () => {
    render(<SelfConsistencyBadge nRuns={3} agreedCount={3} penaltyPct={0} />);
    const badge = screen.getByText('3/3 agree');
    expect(badge).toBeInTheDocument();
    expect(badge.className).toMatch(/wr-emerald|emerald/);
  });

  it('renders 2/3 majority with penalty in amber', () => {
    render(<SelfConsistencyBadge nRuns={3} agreedCount={2} penaltyPct={20} />);
    const badge = screen.getByText(/2\/3 agree \(-20% conf\)/);
    expect(badge).toBeInTheDocument();
    expect(badge.className).toMatch(/wr-amber|amber/);
  });

  it('renders 1/3 inconclusive in red', () => {
    render(<SelfConsistencyBadge nRuns={3} agreedCount={1} penaltyPct={100} />);
    const badge = screen.getByText(/1\/3 agree \(inconclusive\)/);
    expect(badge).toBeInTheDocument();
    expect(badge.className).toMatch(/wr-red|text-red/);
  });

  it('hides when self-consistency was not run', () => {
    const { container } = render(
      <SelfConsistencyBadge nRuns={1} agreedCount={1} penaltyPct={0} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('hides when nRuns is 0', () => {
    const { container } = render(
      <SelfConsistencyBadge nRuns={0} agreedCount={0} penaltyPct={0} />
    );
    expect(container.firstChild).toBeNull();
  });
});
