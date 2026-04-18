import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import DisagreementStrip from '../DisagreementStrip';
import type { DivergenceFinding, V4Findings } from '../../../types';

function d(over: Partial<DivergenceFinding> = {}): DivergenceFinding {
  return {
    kind: 'log_error_cluster_no_metric_anomaly',
    severity: 'medium',
    human_summary: 'backend',
    service_name: 'checkout-service',
    metadata: {},
    ...over,
  };
}

function findings(divergences: DivergenceFinding[]): V4Findings {
  return {
    session_id: 's1',
    findings: [],
    divergence_findings: divergences,
  };
}

describe('DisagreementStrip', () => {
  it('renders nothing when findings is null', () => {
    const { container } = render(<DisagreementStrip findings={null} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing when there are zero divergences', () => {
    const { container } = render(<DisagreementStrip findings={findings([])} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders singular headline for one disagreement', () => {
    render(<DisagreementStrip findings={findings([d()])} />);
    expect(screen.getByText(/signals disagree on 1 service\./i)).toBeInTheDocument();
  });

  it('renders plural headline for multiple disagreements', () => {
    render(
      <DisagreementStrip
        findings={findings([
          d({ service_name: 'a' }),
          d({ service_name: 'b' }),
          d({ service_name: 'c' }),
        ])}
      />,
    );
    expect(screen.getByText(/signals disagree on 3 services\./i)).toBeInTheDocument();
  });

  it('shows row summary using the service name', () => {
    render(
      <DisagreementStrip findings={findings([d({ service_name: 'payments-api' })])} />,
    );
    expect(screen.getByRole('button', { name: /payments-api/ })).toBeInTheDocument();
  });

  it('expands a row to reveal possible causes', () => {
    render(<DisagreementStrip findings={findings([d()])} />);
    // collapsed: causes are not in the DOM
    expect(screen.queryByText(/possible causes/i)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /checkout-service/ }));
    expect(screen.getByText(/possible causes/i)).toBeInTheDocument();
  });

  it('collapses the row when clicked a second time', () => {
    render(<DisagreementStrip findings={findings([d()])} />);
    const btn = screen.getByRole('button', { name: /checkout-service/ });
    fireEvent.click(btn);
    expect(screen.getByText(/possible causes/i)).toBeInTheDocument();
    fireEvent.click(btn);
    expect(screen.queryByText(/possible causes/i)).toBeNull();
  });

  it('only one row is expanded at a time', () => {
    render(
      <DisagreementStrip
        findings={findings([
          d({ service_name: 'svc-alpha' }),
          d({ service_name: 'svc-beta' }),
        ])}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /svc-alpha/ }));
    fireEvent.click(screen.getByRole('button', { name: /svc-beta/ }));
    // only one "possible causes" block should be visible at a time
    expect(screen.getAllByText(/possible causes/i)).toHaveLength(1);
  });

  it('uses region role for accessibility', () => {
    render(<DisagreementStrip findings={findings([d()])} />);
    expect(
      screen.getByRole('region', { name: /cross-agent signal disagreements/i }),
    ).toBeInTheDocument();
  });

  it('is not a card — no border class, no card-border-* class', () => {
    render(<DisagreementStrip findings={findings([d()])} />);
    const strip = screen.getByTestId('disagreement-strip');
    expect(strip.className).not.toMatch(/card-border/);
    expect(strip.className).not.toMatch(/rounded-lg/);
    expect(strip.className).not.toMatch(/bg-wr-severity/);
  });

  it('uses cyan accent token (wr-accent-2), not amber', () => {
    render(<DisagreementStrip findings={findings([d()])} />);
    const strip = screen.getByTestId('disagreement-strip');
    expect(strip.className).toMatch(/wr-accent-2/);
    expect(strip.className).not.toMatch(/amber/);
  });
});
