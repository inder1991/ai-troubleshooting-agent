import { describe, it, expect } from 'vitest';
import type {
  DagNode,
  DagEdge,
  DagModel,
  PositionedNode,
  PositionedEdge,
  PositionedDag,
} from '../dagTypes';

describe('dagTypes structural contracts', () => {
  it('DagNode has required fields', () => {
    const node: DagNode = {
      id: 'step-1',
      agent: 'log-analyzer',
      agentVersion: 2,
      status: 'running',
    };
    expect(node.id).toBe('step-1');
    expect(node.agent).toBe('log-analyzer');
    expect(node.agentVersion).toBe(2);
    expect(node.status).toBe('running');
    expect(node.duration_ms).toBeUndefined();
    expect(node.error).toBeUndefined();
  });

  it('DagNode accepts optional error and duration_ms', () => {
    const node: DagNode = {
      id: 'step-2',
      agent: 'code-nav',
      agentVersion: 'latest',
      status: 'failed',
      duration_ms: 1234,
      error: { type: 'Timeout', message: 'exceeded 30s' },
    };
    expect(node.duration_ms).toBe(1234);
    expect(node.error?.type).toBe('Timeout');
  });

  it('DagEdge has source and target', () => {
    const edge: DagEdge = { source: 'a', target: 'b' };
    expect(edge.source).toBe('a');
    expect(edge.target).toBe('b');
  });

  it('DagModel contains nodes and edges arrays', () => {
    const model: DagModel = {
      nodes: [{ id: 'x', agent: 'a', agentVersion: 1, status: 'pending' }],
      edges: [{ source: 'x', target: 'y' }],
    };
    expect(model.nodes).toHaveLength(1);
    expect(model.edges).toHaveLength(1);
  });

  it('PositionedNode extends DagNode with layout fields', () => {
    const pn: PositionedNode = {
      id: 'n1',
      agent: 'a',
      agentVersion: 1,
      status: 'success',
      x: 10,
      y: 20,
      width: 160,
      height: 60,
    };
    expect(pn.x).toBe(10);
    expect(pn.width).toBe(160);
  });

  it('PositionedEdge extends DagEdge with points', () => {
    const pe: PositionedEdge = {
      source: 'a',
      target: 'b',
      points: [
        { x: 0, y: 0 },
        { x: 50, y: 100 },
      ],
    };
    expect(pe.points).toHaveLength(2);
  });

  it('PositionedDag contains positioned nodes/edges and dimensions', () => {
    const dag: PositionedDag = {
      nodes: [
        { id: 'n', agent: 'a', agentVersion: 1, status: 'pending', x: 0, y: 0, width: 100, height: 50 },
      ],
      edges: [
        { source: 'n', target: 'n2', points: [{ x: 0, y: 0 }] },
      ],
      width: 800,
      height: 600,
    };
    expect(dag.width).toBe(800);
    expect(dag.height).toBe(600);
    expect(dag.nodes[0].x).toBe(0);
    expect(dag.edges[0].points).toHaveLength(1);
  });
});
