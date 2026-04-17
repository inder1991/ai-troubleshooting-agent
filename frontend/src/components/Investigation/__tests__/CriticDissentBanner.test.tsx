import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CriticDissentBanner } from '../CriticDissentBanner';

describe('CriticDissentBanner', () => {
  it('renders verdict matrix and summary', () => {
    render(
      <CriticDissentBanner
        dissent={{
          advocate_verdict: 'confirmed',
          challenger_verdict: 'challenged',
          judge_verdict: 'needs_more_evidence',
          summary: 'Conflicting evidence on memory pressure timing',
        }}
      />,
    );
    expect(screen.getByText(/Conflicting evidence/)).toBeInTheDocument();
    expect(screen.getByText(/advocate:/)).toBeInTheDocument();
    expect(screen.getByText(/confirmed/)).toBeInTheDocument();
    expect(screen.getByText(/challenged/)).toBeInTheDocument();
    expect(screen.getByText(/needs_more_evidence/)).toBeInTheDocument();
  });

  it('returns null when verdicts agree', () => {
    const { container } = render(
      <CriticDissentBanner
        dissent={{
          advocate_verdict: 'confirmed',
          challenger_verdict: 'confirmed',
          judge_verdict: 'confirmed',
        }}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('returns null when dissent is null', () => {
    const { container } = render(<CriticDissentBanner dissent={null} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders without a summary when none is provided', () => {
    render(
      <CriticDissentBanner
        dissent={{
          advocate_verdict: 'confirmed',
          challenger_verdict: 'challenged',
          judge_verdict: 'needs_more_evidence',
        }}
      />,
    );
    expect(screen.getByTestId('critic-dissent-banner')).toBeInTheDocument();
  });
});
