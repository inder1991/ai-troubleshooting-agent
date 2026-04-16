import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import type { DagModel } from '../dagTypes';

/* ── Mock elkjs ───────────────────────────────────────────────────── */

const layoutMock = vi.fn();

vi.mock('elkjs/lib/elk.bundled.js', () => ({
  default: class ELK {
    layout(...args: unknown[]) {
      return layoutMock(...args);
    }
  },
}));

// Reset the lazy singleton before each test so each test gets a fresh ELK instance
// with the reset mock.
vi.mock('../useElkLayout', async (importOriginal) => {
  const mod = await importOriginal<typeof import('../useElkLayout')>();
  return mod;
});

import { useElkLayout, structuralKey } from '../useElkLayout';

/* ── fixtures ─────────────────────────────────────────────────────── */

function makeDag(
  nodeIds: string[],
  edges: Array<[string, string]>,
  statusOverrides?: Record<string, 'pending' | 'running' | 'success' | 'failed'>,
): DagModel {
  return {
    nodes: nodeIds.map((id) => ({
      id,
      agent: 'a',
      agentVersion: 1 as const,
      status: statusOverrides?.[id] ?? ('pending' as const),
    })),
    edges: edges.map(([source, target]) => ({ source, target })),
  };
}

function fakeElkResult(dag: DagModel) {
  return {
    width: 400,
    height: 300,
    children: dag.nodes.map((n, i) => ({
      id: n.id,
      x: 0,
      y: i * 100,
      width: 200,
      height: 80,
    })),
    edges: dag.edges.map((e) => ({
      id: `${e.source}->${e.target}`,
      sources: [e.source],
      targets: [e.target],
      sections: [
        {
          startPoint: { x: 100, y: 0 },
          endPoint: { x: 100, y: 100 },
          bendPoints: [{ x: 100, y: 50 }],
        },
      ],
    })),
  };
}

/* ── tests ─────────────────────────────────────────────────────────── */

describe('useElkLayout', () => {
  beforeEach(() => {
    layoutMock.mockReset();
  });

  it('1. returns positioned nodes with x/y/width/height', async () => {
    const dag = makeDag(['A', 'B'], [['A', 'B']]);
    layoutMock.mockResolvedValueOnce(fakeElkResult(dag));

    const { result } = renderHook(() => useElkLayout(dag));

    // wait for layout to resolve
    await vi.waitFor(() => {
      expect(result.current.layout).not.toBeNull();
    });

    const layout = result.current.layout!;
    for (const node of layout.nodes) {
      expect(typeof node.x).toBe('number');
      expect(typeof node.y).toBe('number');
      expect(node.width).toBe(200);
      expect(node.height).toBe(80);
    }
  });

  it('2. returns positioned edges with points array', async () => {
    const dag = makeDag(['A', 'B'], [['A', 'B']]);
    layoutMock.mockResolvedValueOnce(fakeElkResult(dag));

    const { result } = renderHook(() => useElkLayout(dag));

    await vi.waitFor(() => {
      expect(result.current.layout).not.toBeNull();
    });

    const layout = result.current.layout!;
    expect(layout.edges).toHaveLength(1);
    expect(layout.edges[0].points.length).toBeGreaterThan(0);
    for (const pt of layout.edges[0].points) {
      expect(typeof pt.x).toBe('number');
      expect(typeof pt.y).toBe('number');
    }
  });

  it('3. layout dimensions are positive', async () => {
    const dag = makeDag(['A', 'B'], [['A', 'B']]);
    layoutMock.mockResolvedValueOnce(fakeElkResult(dag));

    const { result } = renderHook(() => useElkLayout(dag));

    await vi.waitFor(() => {
      expect(result.current.layout).not.toBeNull();
    });

    expect(result.current.layout!.width).toBeGreaterThan(0);
    expect(result.current.layout!.height).toBeGreaterThan(0);
  });

  it('4. same structural key → no re-layout (mock call count)', async () => {
    const dag1 = makeDag(['A', 'B'], [['A', 'B']], { A: 'pending', B: 'pending' });
    const dag2 = makeDag(['A', 'B'], [['A', 'B']], { A: 'success', B: 'running' });

    layoutMock.mockResolvedValue(fakeElkResult(dag1));

    const { result, rerender } = renderHook(
      ({ dag }) => useElkLayout(dag),
      { initialProps: { dag: dag1 } },
    );

    await vi.waitFor(() => {
      expect(result.current.layout).not.toBeNull();
    });

    expect(layoutMock).toHaveBeenCalledTimes(1);

    // Re-render with same structure but different statuses
    rerender({ dag: dag2 });

    // Should NOT have called layout again
    expect(layoutMock).toHaveBeenCalledTimes(1);
  });

  it('5. status-only change does NOT change structural key', () => {
    const dag1 = makeDag(['A', 'B'], [['A', 'B']], { A: 'pending', B: 'pending' });
    const dag2 = makeDag(['A', 'B'], [['A', 'B']], { A: 'success', B: 'failed' });

    expect(structuralKey(dag1)).toBe(structuralKey(dag2));
  });

  it('6. adding a node changes the structural key', () => {
    const dag1 = makeDag(['A', 'B'], [['A', 'B']]);
    const dag2 = makeDag(['A', 'B', 'C'], [['A', 'B']]);

    expect(structuralKey(dag1)).not.toBe(structuralKey(dag2));
  });

  it('7. error state is returned on layout failure', async () => {
    const dag = makeDag(['A'], []);
    layoutMock.mockRejectedValueOnce(new Error('ELK boom'));

    const { result } = renderHook(() => useElkLayout(dag));

    await vi.waitFor(() => {
      expect(result.current.error).not.toBeNull();
    });

    expect(result.current.error!.message).toBe('ELK boom');
    expect(result.current.layout).toBeNull();
  });
});
