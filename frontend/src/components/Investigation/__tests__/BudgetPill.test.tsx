import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BudgetPill } from '../BudgetPill';

describe('BudgetPill', () => {
  it('renders neutral ratio below 80% thresholds', () => {
    render(
      <BudgetPill
        toolCalls={{ used: 20, max: 100 }}
        llmUsd={{ used: 0.2, max: 1.0 }}
      />
    );
    expect(screen.getByText('20/100 calls')).toBeInTheDocument();
    expect(screen.getByText('$0.20 / $1.00')).toBeInTheDocument();
    const pill = screen.getByTestId('budget-pill');
    expect(pill.className).not.toMatch(/wr-amber/);
    expect(pill.className).not.toMatch(/wr-red|text-red/);
  });

  it('turns amber at 80% on either axis', () => {
    render(
      <BudgetPill
        toolCalls={{ used: 85, max: 100 }}
        llmUsd={{ used: 0.42, max: 1.0 }}
      />
    );
    expect(screen.getByText('85/100 calls')).toBeInTheDocument();
    expect(screen.getByTestId('budget-pill').className).toMatch(/wr-amber/);
  });

  it('turns red at 100%', () => {
    render(
      <BudgetPill
        toolCalls={{ used: 100, max: 100 }}
        llmUsd={{ used: 1.0, max: 1.0 }}
      />
    );
    expect(screen.getByTestId('budget-pill').className).toMatch(/wr-red|text-red/);
  });

  it('formats USD to two decimal places', () => {
    render(
      <BudgetPill
        toolCalls={{ used: 1, max: 100 }}
        llmUsd={{ used: 0.0567, max: 1.0 }}
      />
    );
    expect(screen.getByText('$0.06 / $1.00')).toBeInTheDocument();
  });

  it('amber triggers if LLM hits 80% even when tool-calls are low', () => {
    render(
      <BudgetPill
        toolCalls={{ used: 1, max: 100 }}
        llmUsd={{ used: 0.85, max: 1.0 }}
      />
    );
    expect(screen.getByTestId('budget-pill').className).toMatch(/wr-amber/);
  });

  it('returns null when no budget data', () => {
    const { container } = render(<BudgetPill toolCalls={null} llmUsd={null} />);
    expect(container.firstChild).toBeNull();
  });
});
