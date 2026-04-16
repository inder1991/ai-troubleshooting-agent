import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { fireEvent } from '@testing-library/dom';
import type { PositionedNode } from '../dagTypes';
import DagNode from '../DagNode';

function makeNode(overrides: Partial<PositionedNode> = {}): PositionedNode {
  return {
    id: 'step-1',
    agent: 'log-analyzer',
    agentVersion: 2,
    status: 'pending',
    x: 10,
    y: 20,
    width: 180,
    height: 70,
    ...overrides,
  };
}

function renderInSvg(ui: React.ReactElement) {
  const { container } = render(<svg>{ui}</svg>);
  return container;
}

describe('DagNode', () => {
  it('1. renders rect with correct fill for success status', () => {
    const container = renderInSvg(<DagNode node={makeNode({ status: 'success' })} />);
    const rect = container.querySelector('[data-testid="dag-node-step-1"] rect');
    expect(rect).toBeTruthy();
    expect(rect!.getAttribute('fill')).toBe('#059669');
  });

  it('2. running node has animate-pulse class', () => {
    const container = renderInSvg(<DagNode node={makeNode({ status: 'running' })} />);
    const pulseRect = container.querySelector('[data-testid="dag-node-step-1"] rect.animate-pulse');
    expect(pulseRect).toBeTruthy();
  });

  it('3. failed node shows error indicator', () => {
    const container = renderInSvg(
      <DagNode node={makeNode({ status: 'failed', error: { message: 'boom' } })} />,
    );
    const indicator = container.querySelector('[data-testid="dag-node-error-step-1"]');
    expect(indicator).toBeTruthy();
  });

  it('4. dimmed node has opacity 0.2', () => {
    const container = renderInSvg(<DagNode node={makeNode()} dimmed />);
    const g = container.querySelector('[data-testid="dag-node-step-1"]');
    expect(g!.getAttribute('opacity')).toBe('0.2');
  });

  it('5. click calls onClick with nodeId', () => {
    const handler = vi.fn();
    const container = renderInSvg(<DagNode node={makeNode()} onClick={handler} />);
    const g = container.querySelector('[data-testid="dag-node-step-1"]')!;
    fireEvent.click(g);
    expect(handler).toHaveBeenCalledWith('step-1');
  });

  it('6. selected node has accent stroke color', () => {
    const container = renderInSvg(<DagNode node={makeNode({ status: 'success' })} selected />);
    const rect = container.querySelector('[data-testid="dag-node-step-1"] rect');
    expect(rect!.getAttribute('stroke')).toBe('#e09f3e');
    expect(rect!.getAttribute('stroke-width')).toBe('3');
  });

  it('7. shows duration text when duration_ms set', () => {
    const container = renderInSvg(
      <DagNode node={makeNode({ status: 'success', duration_ms: 1234 })} />,
    );
    const g = container.querySelector('[data-testid="dag-node-step-1"]')!;
    expect(g.textContent).toContain('1.2s');
  });
});
