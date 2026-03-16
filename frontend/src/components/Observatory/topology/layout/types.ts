import { Node, Edge } from 'reactflow';

export type LayoutAlgorithm = 'force_directed' | 'hierarchical' | 'geographic' | 'radial';

export interface ApiNode {
  id: string;
  hostname: string;
  vendor: string;
  device_type: string;
  site_id: string;
  group: string;
  rank: number;
  status: string;
  confidence: number;
  ha_role?: string | null;
  metrics?: Record<string, number>;
}

export interface ApiEdge {
  id: string;
  source: string;
  target: string;
  source_interface: string;
  target_interface: string;
  edge_type: string;
  protocol: string;
  confidence: number;
  metrics?: Record<string, any>;
}

export interface ApiGroup {
  id: string;
  label: string;
  accent: string;
  device_count: number;
  has_critical?: boolean;
}

export interface LayoutInput {
  nodes: ApiNode[];
  edges: ApiEdge[];
  groups: ApiGroup[];
  algorithm: LayoutAlgorithm;
  canvasWidth: number;
  canvasHeight: number;
}

export interface LayoutOutput {
  nodes: Node[];
  edges: Edge[];
}
