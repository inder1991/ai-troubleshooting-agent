import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import type { PositionedEdge } from '../dagTypes';
import type { EdgeStatus } from '../dagHelpers';
import DagEdge from '../DagEdge';

function makeEdge(overrides: Partial<PositionedEdge> = {}): PositionedEdge {
  return {
    source: 'A',
    target: 'B',
    points: [
      { x: 0, y: 0 },
      { x: 50, y: 25 },
      { x: 100, y: 50 },
    ],
    ...overrides,
  };
}

function renderInSvg(ui: React.ReactElement) {
  const { container } = render(<svg>{ui}</svg>);
  return container;
}

describe('DagEdge', () => {
  it('1. renders path with correct d attribute from points', () => {
    const container = renderInSvg(<DagEdge edge={makeEdge()} edgeStatus="pending" />);
    const path = container.querySelector('[data-testid="edge-A-B"] path');
    expect(path).toBeTruthy();
    expect(path!.getAttribute('d')).toBe('M 0 0 L 50 25 L 100 50');
  });

  it('2. pending edge has neutral color stroke', () => {
    const container = renderInSvg(<DagEdge edge={makeEdge()} edgeStatus="pending" />);
    const path = container.querySelector('[data-testid="edge-A-B"] path');
    expect(path!.getAttribute('stroke')).toBe('#525252');
  });

  it('3. active edge has amber stroke and flow particle path with dag-flow-particle class', () => {
    const container = renderInSvg(<DagEdge edge={makeEdge()} edgeStatus="active" />);
    const g = container.querySelector('[data-testid="edge-A-B"]')!;
    const paths = g.querySelectorAll('path');
    // base path + flow particle path
    expect(paths.length).toBeGreaterThanOrEqual(2);
    expect(paths[0].getAttribute('stroke')).toBe('#d97706');
    const flowPath = g.querySelector('.dag-flow-particle');
    expect(flowPath).toBeTruthy();
  });

  it('4. completed edge has emerald stroke and glow path', () => {
    const container = renderInSvg(<DagEdge edge={makeEdge()} edgeStatus="completed" />);
    const g = container.querySelector('[data-testid="edge-A-B"]')!;
    const paths = g.querySelectorAll('path');
    // base path + glow path
    expect(paths.length).toBeGreaterThanOrEqual(2);
    expect(paths[0].getAttribute('stroke')).toBe('#059669');
    // glow path has wider stroke and lower opacity
    expect(paths[1].getAttribute('stroke-width')).toBe('4');
    expect(paths[1].getAttribute('stroke-opacity')).toBe('0.3');
  });

  it('5. dimmed edge has opacity 0.1', () => {
    const container = renderInSvg(<DagEdge edge={makeEdge()} edgeStatus="pending" dimmed />);
    const g = container.querySelector('[data-testid="edge-A-B"]');
    expect(g!.getAttribute('opacity')).toBe('0.1');
  });
});
