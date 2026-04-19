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

  // ── PR-H: accessibility ─────────────────────────────────────────

  it('SVG root has a descriptive aria-label summarizing the topology', () => {
    const { container } = render(
      <ServiceTopologySVG
        dependencies={twoNodeDeps}
        patientZero={{ service: 'b', first_error_time: '2026-04-19T00:00:00Z' } as any}
        blastRadius={null}
      />,
    );
    const svg = container.querySelector('svg');
    expect(svg).not.toBeNull();
    const label = svg!.getAttribute('aria-label') ?? '';
    expect(label).toMatch(/2 services/);
    expect(label).toMatch(/patient zero b/);
  });

  it('each node is focusable and carries a per-node aria-label', () => {
    render(
      <ServiceTopologySVG
        dependencies={twoNodeDeps}
        patientZero={{ service: 'a', first_error_time: '2026-04-19T00:00:00Z' } as any}
        blastRadius={null}
      />,
    );
    const nodeA = screen.getByTestId('topology-node-a');
    expect(nodeA.getAttribute('tabindex')).toBe('0');
    expect(nodeA.getAttribute('role')).toBe('img');
    expect(nodeA.getAttribute('aria-label')).toMatch(/a.*patient zero/);
    const nodeB = screen.getByTestId('topology-node-b');
    expect(nodeB.getAttribute('aria-label')).toMatch(/b.*dependency|b.*healthy|b.*blast/);
  });
});
