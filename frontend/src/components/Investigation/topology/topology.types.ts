import type { SimulationNodeDatum } from 'd3-force';

// ─── Node Types ──────────────────────────────────────────────────────────────

export type NodeRole = 'patient_zero' | 'upstream' | 'downstream' | 'normal';

export interface TopologyNodeDatum extends SimulationNodeDatum {
  id: string;
  role: NodeRole;
  isCrashloop: boolean;
  isOomKilled: boolean;
  // d3-force mutable fields inherited from SimulationNodeDatum:
  // x?, y?, vx?, vy?, fx?, fy?, index?
}

// ─── Edge Types ──────────────────────────────────────────────────────────────

export type EdgeType = 'error' | 'blast_radius' | 'normal' | 'causal_path';

export interface TopologyEdgeDatum {
  source: string;
  target: string;
  type: EdgeType;
  evidence?: string;
}

// ─── Resolved (post-simulation) Types ────────────────────────────────────────

export interface ResolvedNode {
  id: string;
  role: NodeRole;
  x: number;
  y: number;
  isCrashloop: boolean;
  isOomKilled: boolean;
}

export interface ResolvedEdge {
  source: ResolvedNode;
  target: ResolvedNode;
  type: EdgeType;
  evidence?: string;
  pathId: string;
  pathD: string;
}

export interface ForceLayoutResult {
  nodes: ResolvedNode[];
  edges: ResolvedEdge[];
  width: number;
  height: number;
}

// ─── Visual Constants ────────────────────────────────────────────────────────

export const NODE_RADIUS = 22;
export const TOPOLOGY_PADDING = 50;

export const NODE_COLORS: Record<NodeRole, { fill: string; stroke: string }> = {
  patient_zero: { fill: '#7f1d1d', stroke: '#ef4444' },
  upstream: { fill: '#431407', stroke: '#f97316' },
  downstream: { fill: '#1e3a5f', stroke: '#3b82f6' },
  normal: { fill: '#0f3443', stroke: '#06b6d4' },
};

export const EDGE_COLORS: Record<EdgeType, { stroke: string; width: number; opacity: number }> = {
  error: { stroke: '#ef4444', width: 2, opacity: 0.8 },
  blast_radius: { stroke: '#f97316', width: 1.5, opacity: 0.6 },
  normal: { stroke: '#475569', width: 1, opacity: 0.4 },
  causal_path: { stroke: '#ef4444', width: 3, opacity: 0.9 },
};
