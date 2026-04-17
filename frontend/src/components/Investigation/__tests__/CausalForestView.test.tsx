import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import CausalForestView from '../CausalForestView';

describe('CausalForestView (edge-type legend)', () => {
  it('renders a legend entry for each of the 5 typed edges', () => {
    render(<CausalForestView />);
    expect(screen.getByTestId('topology-edge-legend')).toBeInTheDocument();
    ['causes', 'precedes', 'correlates', 'contradicts', 'supports'].forEach(
      (t) => {
        expect(screen.getByTestId(`legend-${t}`)).toBeInTheDocument();
        expect(screen.getByText(t)).toBeInTheDocument();
      },
    );
  });

  it('describes each edge type so users know what it means', () => {
    render(<CausalForestView />);
    expect(screen.getByText(/Certified cause/)).toBeInTheDocument();
    expect(screen.getByText(/Temporal precedence/)).toBeInTheDocument();
    expect(screen.getByText(/Observed together/)).toBeInTheDocument();
    expect(screen.getByText(/Contradicted by evidence/)).toBeInTheDocument();
    expect(screen.getByText(/Consistent with/)).toBeInTheDocument();
  });
});
