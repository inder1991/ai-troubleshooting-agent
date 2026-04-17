import React from 'react';
import type { InferredDependency, PatientZero, BlastRadiusData, PodHealthStatus } from '../../../types';
import { useTopologyLayout, type TopologyNode, type TopologyEdge } from './useTopologyLayout';

interface ServiceTopologySVGProps {
  dependencies: InferredDependency[];
  patientZero: PatientZero | null;
  blastRadius: BlastRadiusData | null;
  podStatuses?: PodHealthStatus[];
  /** Phase-4 Task 4.21 — highlight a walk path returned by the Planner's
   * upstream_walk. Rendered as an overlay with the topology-glow class. */
  walkPath?: string[];
}

const NODE_RADIUS = 20;

const nodeStyles: Record<TopologyNode['role'], { fill: string; stroke: string; className?: string }> = {
  patient_zero: { fill: '#7f1d1d', stroke: '#ef4444', className: 'topology-node-error' },
  upstream: { fill: '#431407', stroke: '#f97316' },
  downstream: { fill: '#1e3a5f', stroke: '#3b82f6' },
  blast_radius: { fill: '#431407', stroke: '#f97316' },
  normal: { fill: '#0f3443', stroke: '#06b6d4' },
};

// Legacy edge types keep their existing classes.
const edgeStyles: Record<TopologyEdge['type'], string> = {
  error: 'topology-edge-error',
  blast_radius: 'topology-edge-warning',
  normal: 'topology-edge-normal',
  // Phase-4 typed-edge vocabulary (Task 2.1's CausalRuleEngine).
  causes: 'topology-edge-causes',
  precedes: 'topology-edge-precedes',
  correlates: 'topology-edge-correlates',
  contradicts: 'topology-edge-contradicts',
  supports: 'topology-edge-supports',
};

// Inline stroke + dasharray fallback so component tests can assert on
// the rendering without depending on external CSS being loaded.
const edgeInline: Record<TopologyEdge['type'], { stroke: string; dasharray: string }> = {
  error: { stroke: 'var(--wr-red)', dasharray: '' },
  blast_radius: { stroke: 'var(--wr-amber)', dasharray: '' },
  normal: { stroke: '#475569', dasharray: '' },
  causes: { stroke: 'var(--wr-red)', dasharray: '' },
  precedes: { stroke: 'var(--wr-amber)', dasharray: '6,3' },
  correlates: { stroke: '#94a3b8', dasharray: '2,3' },
  contradicts: { stroke: 'var(--wr-red)', dasharray: '2,3' },
  supports: { stroke: 'var(--wr-emerald)', dasharray: '2,3' },
};

const ServiceTopologySVG: React.FC<ServiceTopologySVGProps> = ({
  dependencies,
  patientZero,
  blastRadius,
  podStatuses = [],
  walkPath,
}) => {
  const { nodes, edges, width, height } = useTopologyLayout(dependencies, patientZero, blastRadius);

  // Derive which services have crashlooping pods
  const crashloopServices = new Set<string>();
  for (const pod of podStatuses) {
    if (pod.crash_loop || pod.oom_killed) {
      // Match pod_name prefix against topology node IDs (e.g., "order-svc-abc123" → "order-svc")
      for (const node of nodes) {
        if (pod.pod_name.startsWith(node.id) || pod.pod_name.includes(node.id)) {
          crashloopServices.add(node.id);
        }
      }
    }
  }
  // Also mark patient_zero if any pod is crashlooping and no specific match was found
  const hasCrashloop = podStatuses.some((p) => p.crash_loop || p.oom_killed);
  if (hasCrashloop && crashloopServices.size === 0 && patientZero) {
    crashloopServices.add(patientZero.service);
  }

  if (nodes.length === 0) {
    return (
      <div className="h-32 flex items-center justify-center text-body-xs text-slate-500">
        Topology will populate as dependencies are discovered
      </div>
    );
  }

  const nodeMap = new Map(nodes.map((n) => [n.id, n]));

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="w-full"
      style={{ minHeight: '100px', maxHeight: '260px' }}
      role="img"
      aria-label="Service topology diagram"
    >
      <defs>
        <filter id="glow-red">
          <feGaussianBlur stdDeviation="3" result="coloredBlur" />
          <feMerge>
            <feMergeNode in="coloredBlur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <marker
          id="arrowhead"
          markerWidth="8"
          markerHeight="6"
          refX="8"
          refY="3"
          orient="auto"
        >
          <polygon points="0 0, 8 3, 0 6" fill="#475569" />
        </marker>
        <marker
          id="arrowhead-red"
          markerWidth="8"
          markerHeight="6"
          refX="8"
          refY="3"
          orient="auto"
        >
          <polygon points="0 0, 8 3, 0 6" fill="#ef4444" />
        </marker>
      </defs>

      {/* Edges */}
      {edges.map((edge, i) => {
        const src = nodeMap.get(edge.source);
        const tgt = nodeMap.get(edge.target);
        if (!src || !tgt) return null;

        const marker =
          edge.type === 'error' || edge.type === 'causes' || edge.type === 'contradicts'
            ? 'url(#arrowhead-red)'
            : 'url(#arrowhead)';
        const dx = tgt.x - src.x;
        const dy = tgt.y - src.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const nx = dx / dist;
        const ny = dy / dist;
        const inline = edgeInline[edge.type];
        return (
          <line
            key={i}
            data-testid={`edge-${edge.source}-${edge.target}`}
            x1={src.x + nx * NODE_RADIUS}
            y1={src.y + ny * NODE_RADIUS}
            x2={tgt.x - nx * NODE_RADIUS}
            y2={tgt.y - ny * NODE_RADIUS}
            className={edgeStyles[edge.type]}
            stroke={inline.stroke}
            strokeDasharray={inline.dasharray || undefined}
            markerEnd={marker}
          />
        );
      })}

      {/* Walk overlay (Task 4.21) — highlight every edge along walkPath */}
      {walkPath && walkPath.length >= 2 && (
        <g data-testid="walk-overlay">
          {walkPath.slice(0, -1).map((from, i) => {
            const to = walkPath[i + 1];
            const src = nodeMap.get(from);
            const tgt = nodeMap.get(to);
            if (!src || !tgt) return null;
            const dx = tgt.x - src.x;
            const dy = tgt.y - src.y;
            const dist = Math.sqrt(dx * dx + dy * dy) || 1;
            const nx = dx / dist;
            const ny = dy / dist;
            return (
              <line
                key={`${from}-${to}`}
                data-testid={`walk-overlay-${from}-${to}`}
                x1={src.x + nx * NODE_RADIUS}
                y1={src.y + ny * NODE_RADIUS}
                x2={tgt.x - nx * NODE_RADIUS}
                y2={tgt.y - ny * NODE_RADIUS}
                stroke="var(--wr-amber)"
                strokeWidth={3}
                strokeOpacity={0.9}
                className="topology-glow"
              />
            );
          })}
        </g>
      )}

      {/* Nodes */}
      {nodes.map((node) => {
        const style = nodeStyles[node.role];
        const isCrashloop = crashloopServices.has(node.id);
        return (
          <g key={node.id} className={`${style.className || ''} ${isCrashloop ? 'topology-node-crashloop' : ''}`}>
            {/* Pulsing outer ring for crashloop nodes */}
            {isCrashloop && (
              <circle
                cx={node.x}
                cy={node.y}
                r={NODE_RADIUS + 4}
                fill="none"
                stroke="#ef4444"
                strokeWidth={2}
                className="animate-pulse-red"
                opacity={0.6}
              />
            )}
            <circle
              cx={node.x}
              cy={node.y}
              r={NODE_RADIUS}
              fill={isCrashloop ? '#7f1d1d' : style.fill}
              stroke={isCrashloop ? '#ef4444' : style.stroke}
              strokeWidth={node.role === 'patient_zero' || isCrashloop ? 2.5 : 1.5}
              filter={node.role === 'patient_zero' || isCrashloop ? 'url(#glow-red)' : undefined}
            />
            <text
              x={node.x}
              y={node.y + NODE_RADIUS + 14}
              textAnchor="middle"
              fill="#94a3b8"
              fontSize="9"
              fontFamily="monospace"
            >
              {node.id.length > 14 ? node.id.slice(0, 12) + '..' : node.id}
            </text>
            {node.role === 'patient_zero' && (
              <text
                x={node.x}
                y={node.y + 4}
                textAnchor="middle"
                fill="#ef4444"
                fontSize="10"
                fontWeight="bold"
              >
                P0
              </text>
            )}
            {node.role !== 'patient_zero' && (
              <text
                x={node.x}
                y={node.y + 4}
                textAnchor="middle"
                fill="#94a3b8"
                fontSize="8"
              >
                {node.id.slice(0, 3).toUpperCase()}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
};

export default ServiceTopologySVG;
