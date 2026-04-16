import { describe, it, expect } from 'vitest';
import type { StepSpec, MappingExpr, PredicateExpr } from '../../../../../types';
import type { DagModel, DagEdge } from '../dagTypes';
import {
  extractDependencies,
  buildDagModel,
  computeFailurePath,
  isEdgeOnFailurePath,
  edgeStatus,
} from '../dagHelpers';

/* ── helpers ───────────────────────────────────────────────────── */
function makeStep(overrides: Partial<StepSpec> & { id: string }): StepSpec {
  return {
    agent: 'test-agent',
    agent_version: 1,
    inputs: {},
    ...overrides,
  };
}

function nodeRef(node_id: string, path = 'output'): MappingExpr {
  return { ref: { from: 'node', node_id, path } };
}

/* ── extractDependencies ───────────────────────────────────────── */
describe('extractDependencies', () => {
  it('1. node ref in inputs → returns node_id', () => {
    const step = makeStep({ id: 'B', inputs: { data: nodeRef('A') } });
    expect(extractDependencies(step)).toEqual(['A']);
  });

  it('2. when predicate with node ref → returns node_id', () => {
    const step = makeStep({
      id: 'B',
      when: { op: 'exists', args: [nodeRef('A')] },
    });
    expect(extractDependencies(step)).toContain('A');
  });

  it('3. fallback_step_id → included', () => {
    const step = makeStep({ id: 'B', fallback_step_id: 'C' });
    expect(extractDependencies(step)).toContain('C');
  });

  it('4. nested and/or predicates → finds deep refs', () => {
    const step = makeStep({
      id: 'D',
      when: {
        op: 'and',
        args: [
          { op: 'eq', args: [nodeRef('A'), { literal: 'ok' }] },
          { op: 'or', args: [
            { op: 'exists', args: [nodeRef('B')] },
            { op: 'in', args: [nodeRef('C'), { literal: [1, 2] }] },
          ]},
        ],
      },
    });
    const deps = extractDependencies(step);
    expect(deps).toContain('A');
    expect(deps).toContain('B');
    expect(deps).toContain('C');
  });

  it('5. not wrapper → finds inner refs', () => {
    const step = makeStep({
      id: 'X',
      when: {
        op: 'not',
        // runtime convention: `args: [inner]` (not `arg`)
        args: [{ op: 'exists', args: [nodeRef('Y')] }],
      } as unknown as PredicateExpr,
    });
    expect(extractDependencies(step)).toContain('Y');
  });

  it('6. transform (coalesce) args with refs → finds them', () => {
    const step = makeStep({
      id: 'T',
      inputs: {
        merged: { op: 'coalesce', args: [nodeRef('A'), nodeRef('B'), { literal: 'fallback' }] },
      },
    });
    const deps = extractDependencies(step);
    expect(deps).toContain('A');
    expect(deps).toContain('B');
  });

  it('7. only literal inputs → empty', () => {
    const step = makeStep({ id: 'L', inputs: { x: { literal: 42 } } });
    expect(extractDependencies(step)).toEqual([]);
  });
});

/* ── buildDagModel ─────────────────────────────────────────────── */
describe('buildDagModel', () => {
  it('8. 3-step chain A→B→C → correct nodes and edges', () => {
    const steps: StepSpec[] = [
      makeStep({ id: 'A' }),
      makeStep({ id: 'B', inputs: { x: nodeRef('A') } }),
      makeStep({ id: 'C', inputs: { y: nodeRef('B') } }),
    ];
    const statusMap = new Map([
      ['A', { status: 'success' as const }],
      ['B', { status: 'running' as const }],
      ['C', { status: 'pending' as const }],
    ]);
    const model = buildDagModel(steps, statusMap);
    expect(model.nodes).toHaveLength(3);
    expect(model.edges).toEqual([
      { source: 'A', target: 'B' },
      { source: 'B', target: 'C' },
    ]);
    expect(model.nodes[1].status).toBe('running');
  });

  it('9. ref to nonexistent step → edge excluded', () => {
    const steps: StepSpec[] = [
      makeStep({ id: 'A', inputs: { x: nodeRef('GHOST') } }),
    ];
    const statusMap = new Map([['A', { status: 'pending' as const }]]);
    const model = buildDagModel(steps, statusMap);
    expect(model.edges).toEqual([]);
  });
});

/* ── computeFailurePath ────────────────────────────────────────── */
describe('computeFailurePath', () => {
  function mkModel(
    nodeStatuses: Record<string, 'pending' | 'running' | 'success' | 'failed' | 'skipped' | 'cancelled'>,
    edges: Array<[string, string]>,
  ): DagModel {
    return {
      nodes: Object.entries(nodeStatuses).map(([id, status]) => ({
        id,
        agent: 'a',
        agentVersion: 1 as const,
        status,
      })),
      edges: edges.map(([source, target]) => ({ source, target })),
    };
  }

  it('10. linear A→B(fail)→C → all highlighted, nothing dimmed', () => {
    const model = mkModel({ A: 'success', B: 'failed', C: 'pending' }, [['A', 'B'], ['B', 'C']]);
    const { highlighted, dimmed } = computeFailurePath(model);
    expect(highlighted.has('A')).toBe(true);
    expect(highlighted.has('B')).toBe(true);
    expect(highlighted.has('C')).toBe(true);
    expect(dimmed.size).toBe(0);
  });

  it('11. branching A→B(fail), A→C(ok) → A,B highlighted; C dimmed', () => {
    const model = mkModel(
      { A: 'success', B: 'failed', C: 'success' },
      [['A', 'B'], ['A', 'C']],
    );
    const { highlighted, dimmed } = computeFailurePath(model);
    expect(highlighted.has('A')).toBe(true);
    expect(highlighted.has('B')).toBe(true);
    expect(dimmed.has('C')).toBe(true);
  });

  it('12. no failures → empty highlighted', () => {
    const model = mkModel({ A: 'success', B: 'success' }, [['A', 'B']]);
    const { highlighted, dimmed } = computeFailurePath(model);
    expect(highlighted.size).toBe(0);
    expect(dimmed.size).toBe(0);
  });

  it('13. diamond A→B,A→C,B→D,C→D, B fails → A,B,D highlighted; C dimmed', () => {
    const model = mkModel(
      { A: 'success', B: 'failed', C: 'success', D: 'pending' },
      [['A', 'B'], ['A', 'C'], ['B', 'D'], ['C', 'D']],
    );
    const { highlighted, dimmed } = computeFailurePath(model);
    expect(highlighted.has('A')).toBe(true);
    expect(highlighted.has('B')).toBe(true);
    expect(highlighted.has('D')).toBe(true);
    expect(dimmed.has('C')).toBe(true);
  });
});

/* ── edgeStatus ────────────────────────────────────────────────── */
describe('edgeStatus', () => {
  it('14. each input → correct output', () => {
    expect(edgeStatus('running')).toBe('active');
    expect(edgeStatus('success')).toBe('completed');
    expect(edgeStatus('failed')).toBe('failed');
    expect(edgeStatus('pending')).toBe('pending');
    expect(edgeStatus('skipped')).toBe('pending');
    expect(edgeStatus('cancelled')).toBe('pending');
  });
});

/* ── isEdgeOnFailurePath ───────────────────────────────────────── */
describe('isEdgeOnFailurePath', () => {
  it('15. both highlighted → true, mixed → false', () => {
    const highlighted = new Set(['A', 'B']);
    const edge1: DagEdge = { source: 'A', target: 'B' };
    const edge2: DagEdge = { source: 'A', target: 'C' };
    expect(isEdgeOnFailurePath(edge1, highlighted)).toBe(true);
    expect(isEdgeOnFailurePath(edge2, highlighted)).toBe(false);
  });
});
