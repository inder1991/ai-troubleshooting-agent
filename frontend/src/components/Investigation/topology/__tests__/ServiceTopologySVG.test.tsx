import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import ServiceTopologySVG from '../ServiceTopologySVG';

// Fixture helpers — InferredDependency shape is whatever the existing layout
// expects; we pass minimal inputs that drive the layout hook into placing
// two nodes so edge lookups work.
const twoNodeDeps = [
  { source: 'a', target: 'b' } as unknown as any,
];

describe('ServiceTopologySVG — typed edges + walk overlay (Task 4.21)', () => {
  it('renders without crashing on a minimal graph', () => {
    render(
      <ServiceTopologySVG
        dependencies={twoNodeDeps}
        patientZero={null}
        blastRadius={null}
      />,
    );
    // Edge from a->b is present
    const edge = screen.queryByTestId('edge-a-b');
    expect(edge).toBeTruthy();
  });

  it('walk overlay appears when walkPath crosses existing nodes', () => {
    render(
      <ServiceTopologySVG
        dependencies={twoNodeDeps}
        patientZero={null}
        blastRadius={null}
        walkPath={['a', 'b']}
      />,
    );
    expect(screen.getByTestId('walk-overlay')).toBeTruthy();
    expect(screen.getByTestId('walk-overlay-a-b')).toBeTruthy();
  });

  it('no walk overlay when walkPath absent', () => {
    render(
      <ServiceTopologySVG
        dependencies={twoNodeDeps}
        patientZero={null}
        blastRadius={null}
      />,
    );
    expect(screen.queryByTestId('walk-overlay')).toBeNull();
  });
});
