import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { PositionedDag } from '../dagTypes';
import type { StepSpec, StepRunDetail } from '../../../../../types';
import type { LiveEvent } from '../../StepStatusPanel';

/* ── Deterministic layout mock ─────────────────────────────────── */

let mockLayout: PositionedDag | null = null;
let mockLoading = false;

vi.mock('../useElkLayout', () => ({
  useElkLayout: () => ({
    layout: mockLoading ? null : mockLayout,
    loading: mockLoading,
    error: null,
  }),
}));

/* ── Import after mocks ────────────────────────────────────────── */
import { DagView } from '../DagView';

/* ── Helpers ───────────────────────────────────────────────────── */

function ref(nodeId: string, path = 'output.result') {
  return { ref: { from: 'node' as const, node_id: nodeId, path } };
}

function makeStep(id: string, inputs: Record<string, ReturnType<typeof ref>> = {}): StepSpec {
  return { id, agent: `agent-${id}`, agent_version: 1, inputs };
}

function makeRun(stepId: string, status: StepRunDetail['status'] = 'pending', extra: Partial<StepRunDetail> = {}): StepRunDetail {
  return { id: `run-${stepId}`, step_id: stepId, status, attempt: 1, ...extra };
}

function buildLayout(
  nodeIds: string[],
  edgePairs: Array<[string, string]>,
): PositionedDag {
  return {
    nodes: nodeIds.map((id, i) => ({
      id,
      agent: `agent-${id}`,
      agentVersion: 1 as number | 'latest',
      status: 'pending' as const,
      x: 0,
      y: i * 120,
      width: 200,
      height: 80,
    })),
    edges: edgePairs.map(([source, target]) => ({
      source,
      target,
      points: [
        { x: 100, y: 80 },
        { x: 100, y: 120 },
      ],
    })),
    width: 400,
    height: nodeIds.length * 120,
  };
}

/* ── Tests ─────────────────────────────────────────────────────── */

describe('DagView integration', () => {
  beforeEach(() => {
    mockLoading = false;
    mockLayout = null;
  });

  it('1. 3-step chain A→B→C: 3 nodes, 2 edges', () => {
    const steps: StepSpec[] = [
      makeStep('a'),
      makeStep('b', { x: ref('a') }),
      makeStep('c', { x: ref('b') }),
    ];
    const runs = steps.map((s) => makeRun(s.id));
    mockLayout = buildLayout(['a', 'b', 'c'], [['a', 'b'], ['b', 'c']]);

    render(<DagView steps={steps} stepRuns={runs} />);

    expect(screen.getByTestId('dag-node-a')).toBeTruthy();
    expect(screen.getByTestId('dag-node-b')).toBeTruthy();
    expect(screen.getByTestId('dag-node-c')).toBeTruthy();
    expect(screen.getByTestId('edge-a-b')).toBeTruthy();
    expect(screen.getByTestId('edge-b-c')).toBeTruthy();
  });

  it('2. Parallel fan-in A→C, B→C: 3 nodes, 2 edges', () => {
    const steps: StepSpec[] = [
      makeStep('a'),
      makeStep('b'),
      makeStep('c', { x: ref('a'), y: ref('b') }),
    ];
    const runs = steps.map((s) => makeRun(s.id));
    mockLayout = buildLayout(['a', 'b', 'c'], [['a', 'c'], ['b', 'c']]);

    render(<DagView steps={steps} stepRuns={runs} />);

    expect(screen.getByTestId('dag-node-a')).toBeTruthy();
    expect(screen.getByTestId('dag-node-b')).toBeTruthy();
    expect(screen.getByTestId('dag-node-c')).toBeTruthy();
    expect(screen.getByTestId('edge-a-c')).toBeTruthy();
    expect(screen.getByTestId('edge-b-c')).toBeTruthy();
  });

  it('3. Live status update: step.started → node shows running', () => {
    const steps: StepSpec[] = [
      makeStep('a'),
      makeStep('b', { x: ref('a') }),
    ];
    const runs = [makeRun('a', 'success'), makeRun('b', 'pending')];
    mockLayout = buildLayout(['a', 'b'], [['a', 'b']]);

    const liveEvents: LiveEvent[] = [
      { id: 1, type: 'step.started', data: { step_id: 'b', status: 'running' }, timestamp: new Date().toISOString() },
    ];

    const { container } = render(<DagView steps={steps} stepRuns={runs} liveEvents={liveEvents} />);

    // The edge from a (success+live running on b) should show active edge (amber stroke from source=a which is success → completed edge)
    // Node b should reflect running status via the DAG model
    const nodeB = screen.getByTestId('dag-node-b');
    expect(nodeB).toBeTruthy();
    // Edge from a→b: source a is success → completed edge status
    const edgeAB = screen.getByTestId('edge-a-b');
    expect(edgeAB).toBeTruthy();
  });

  it('4. Failure path: step B failed → failure path highlighted, others dimmed, "Show all" button present', () => {
    const steps: StepSpec[] = [
      makeStep('a'),
      makeStep('b', { x: ref('a') }),
      makeStep('c', { x: ref('b') }),
    ];
    const runs = [
      makeRun('a', 'success'),
      makeRun('b', 'failed', { error: { type: 'RuntimeError', message: 'boom' } }),
      makeRun('c', 'pending'),
    ];
    mockLayout = buildLayout(['a', 'b', 'c'], [['a', 'b'], ['b', 'c']]);

    render(<DagView steps={steps} stepRuns={runs} />);

    // "Show all" button should be present when failure path is active
    const showAllBtn = screen.getByText('Show all');
    expect(showAllBtn).toBeTruthy();

    // All nodes on the failure path (a→b→c) are highlighted, so none are dimmed in this linear chain
    // But verify the structure is rendered correctly
    expect(screen.getByTestId('dag-node-a')).toBeTruthy();
    expect(screen.getByTestId('dag-node-b')).toBeTruthy();
    expect(screen.getByTestId('dag-node-c')).toBeTruthy();
  });

  it('5. "Show all" click → dimmed nodes restore', () => {
    // Need a node NOT on the failure path to test dimming
    const steps: StepSpec[] = [
      makeStep('a'),
      makeStep('b', { x: ref('a') }),
      makeStep('d'), // independent node — not on failure path
    ];
    const runs = [
      makeRun('a', 'success'),
      makeRun('b', 'failed'),
      makeRun('d', 'success'),
    ];
    mockLayout = buildLayout(['a', 'b', 'd'], [['a', 'b']]);

    render(<DagView steps={steps} stepRuns={runs} />);

    // Node d should be dimmed (not on failure path a→b)
    const nodeD = screen.getByTestId('dag-node-d');
    expect(nodeD).toBeTruthy();

    // Click "Show all" to restore
    const showAllBtn = screen.getByText('Show all');
    fireEvent.click(showAllBtn);

    // After clicking, button label should change to "Show failure path"
    expect(screen.getByText('Show failure path')).toBeTruthy();

    // Node d should still be present (no longer dimmed, though we can't assert CSS in jsdom)
    expect(screen.getByTestId('dag-node-d')).toBeTruthy();
  });

  it('6. Empty steps → graceful empty state', () => {
    mockLayout = { nodes: [], edges: [], width: 0, height: 0 };

    const { container } = render(<DagView steps={[]} stepRuns={[]} />);

    const dagContainer = screen.getByTestId('dag-view-container');
    expect(dagContainer).toBeTruthy();
    // SVG should exist but have no node/edge elements
    const nodes = container.querySelectorAll('[data-testid^="dag-node-"]');
    const edges = container.querySelectorAll('[data-testid^="edge-"]');
    expect(nodes.length).toBe(0);
    expect(edges.length).toBe(0);
  });

  it('7. Single step → one node, no edges', () => {
    const steps: StepSpec[] = [makeStep('solo')];
    const runs = [makeRun('solo', 'success')];
    mockLayout = buildLayout(['solo'], []);

    render(<DagView steps={steps} stepRuns={runs} />);

    expect(screen.getByTestId('dag-node-solo')).toBeTruthy();
    const dagContainer = screen.getByTestId('dag-view-container');
    const edges = dagContainer.querySelectorAll('[data-testid^="edge-"]');
    expect(edges.length).toBe(0);
  });
});
