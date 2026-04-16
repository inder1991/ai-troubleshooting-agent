import type { StepRunStatus } from '../../../../types';

export interface DagNode {
  id: string;
  agent: string;
  agentVersion: number | 'latest';
  status: StepRunStatus;
  duration_ms?: number;
  error?: { type?: string; message?: string };
}

export interface DagEdge {
  source: string;
  target: string;
}

export interface DagModel {
  nodes: DagNode[];
  edges: DagEdge[];
}

export interface PositionedNode extends DagNode {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface PositionedEdge extends DagEdge {
  points: Array<{ x: number; y: number }>;
}

export interface PositionedDag {
  nodes: PositionedNode[];
  edges: PositionedEdge[];
  width: number;
  height: number;
}
