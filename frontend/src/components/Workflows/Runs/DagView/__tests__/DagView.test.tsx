import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { PositionedDag } from '../dagTypes';
import type { StepSpec, StepRunDetail } from '../../../../../types';

/* ── Mock useElkLayout to avoid elkjs WASM ──────────────────────── */

const MOCK_LAYOUT: PositionedDag = {
  nodes: [
    { id: 'step-a', agent: 'agent-a', agentVersion: 1, status: 'success', x: 0, y: 0, width: 200, height: 80 },
    { id: 'step-b', agent: 'agent-b', agentVersion: 2, status: 'running', x: 0, y: 160, width: 200, height: 80 },
  ],
  edges: [
    { source: 'step-a', target: 'step-b', points: [{ x: 100, y: 80 }, { x: 100, y: 160 }] },
  ],
  width: 400,
  height: 320,
};

let mockLoading = false;

vi.mock('../useElkLayout', () => ({
  useElkLayout: () => ({
    layout: mockLoading ? null : MOCK_LAYOUT,
    loading: mockLoading,
    error: null,
  }),
}));

/* ── Import after mocks ─────────────────────────────────────────── */
import { DagView } from '../DagView';

/* ── Test fixtures ──────────────────────────────────────────────── */

const STEPS: StepSpec[] = [
  {
    id: 'step-a',
    agent: 'agent-a',
    agent_version: 1,
    inputs: {},
  },
  {
    id: 'step-b',
    agent: 'agent-b',
    agent_version: 2,
    inputs: {
      x: { ref: { from: 'node' as const, node_id: 'step-a', path: '$.out' } },
    },
  },
];

const STEP_RUNS: StepRunDetail[] = [
  { id: 'r1', step_id: 'step-a', status: 'success', attempt: 1, duration_ms: 500 },
  { id: 'r2', step_id: 'step-b', status: 'running', attempt: 1 },
];

describe('DagView', () => {
  beforeEach(() => {
    mockLoading = false;
  });

  it('renders dag-view-container with SVG', () => {
    render(<DagView steps={STEPS} stepRuns={STEP_RUNS} />);
    const container = screen.getByTestId('dag-view-container');
    expect(container).toBeTruthy();
    const svg = container.querySelector('svg');
    expect(svg).toBeTruthy();
  });

  it('renders one dag-node-* per step', () => {
    render(<DagView steps={STEPS} stepRuns={STEP_RUNS} />);
    expect(screen.getByTestId('dag-node-step-a')).toBeTruthy();
    expect(screen.getByTestId('dag-node-step-b')).toBeTruthy();
  });

  it('renders edge elements between dependent steps', () => {
    render(<DagView steps={STEPS} stepRuns={STEP_RUNS} />);
    expect(screen.getByTestId('edge-step-a-step-b')).toBeTruthy();
  });

  it('shows "Computing layout..." when loading', () => {
    mockLoading = true;
    render(<DagView steps={STEPS} stepRuns={STEP_RUNS} />);
    expect(screen.getByText('Computing layout...')).toBeTruthy();
  });

  it('has Fit button that is present and clickable', () => {
    render(<DagView steps={STEPS} stepRuns={STEP_RUNS} />);
    const btn = screen.getByRole('button', { name: /fit/i });
    expect(btn).toBeTruthy();
    fireEvent.click(btn);
    // No error — clickable
  });
});
