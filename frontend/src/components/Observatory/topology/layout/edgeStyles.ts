import type { CSSProperties } from 'react';
import type { ApiEdge } from './types';

const EDGE_STYLES: Record<string, CSSProperties> = {
  physical:      { stroke: '#22c55e', strokeWidth: 3 },
  logical:       { stroke: '#22c55e', strokeWidth: 2, strokeDasharray: '4,2' },
  tunnel:        { stroke: '#06b6d4', strokeWidth: 3, strokeDasharray: '10,5' },
  ha_peer:       { stroke: '#f59e0b', strokeWidth: 2, strokeDasharray: '6,4' },
  mpls:          { stroke: '#f59e0b', strokeWidth: 4 },
  route:         { stroke: '#64748b', strokeWidth: 1, opacity: 0.3 },
  load_balancer: { stroke: '#a855f7', strokeWidth: 2 },
  cloud_attach:  { stroke: '#06b6d4', strokeWidth: 3 },
  stale:         { stroke: '#64748b', strokeWidth: 1, strokeDasharray: '2,4', opacity: 0.4 },
  down:          { stroke: '#ef4444', strokeWidth: 4, strokeDasharray: '6,3' },
};

export function getEdgeStyle(edge: ApiEdge): CSSProperties {
  if (edge.metrics?.status === 'down') return EDGE_STYLES.down;

  const base = { ...(EDGE_STYLES[edge.edge_type] || EDGE_STYLES.logical) };

  // Utilization-based width scaling
  const util = edge.metrics?.utilization;
  if (util != null && util > 0) {
    base.strokeWidth = Math.max(2, Math.min(6, 2 + util / 25));
    if (util > 90) base.stroke = '#ef4444';
    else if (util > 75) base.stroke = '#f59e0b';
  }

  return base;
}

export function getEdgeLabel(edge: ApiEdge): string {
  const parts: string[] = [];
  if (edge.metrics?.speed) parts.push(String(edge.metrics.speed));
  if (edge.metrics?.utilization != null) parts.push(`${Math.round(edge.metrics.utilization)}%`);
  if (edge.edge_type === 'tunnel') parts.push(edge.protocol?.toUpperCase() || 'TUNNEL');
  if (edge.edge_type === 'mpls') parts.push('MPLS');
  if (edge.edge_type === 'ha_peer') parts.push('HA');
  if (edge.metrics?.status === 'down') parts.push('DOWN');
  return parts.join(' \u00b7 ');
}
