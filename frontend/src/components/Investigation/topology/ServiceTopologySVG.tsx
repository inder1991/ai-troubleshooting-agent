import React from 'react';
import type { InferredDependency, PatientZero, BlastRadiusData, PodHealthStatus } from '../../../types';
import { useTopologyLayout, type TopologyNode, type TopologyEdge } from './useTopologyLayout';

interface ServiceTopologySVGProps {
  dependencies: InferredDependency[];
  patientZero: PatientZero | null;
  blastRadius: BlastRadiusData | null;
  podStatuses?: PodHealthStatus[];
}

const NODE_RADIUS = 20;

const nodeStyles: Record<TopologyNode['role'], { fill: string; stroke: string; className?: string }> = {
  patient_zero: { fill: '#7f1d1d', stroke: '#ef4444', className: 'topology-node-error' },
  upstream: { fill: '#431407', stroke: '#f97316' },
  downstream: { fill: '#1e3a5f', stroke: '#3b82f6' },
  blast_radius: { fill: '#431407', stroke: '#f97316' },
  normal: { fill: '#0f3443', stroke: '#06b6d4' },
};

const edgeStyles: Record<TopologyEdge['type'], string> = {
  error: 'topology-edge-error',
  blast_radius: 'topology-edge-warning',
  normal: 'topology-edge-normal',
};

const ServiceTopologySVG: React.FC<ServiceTopologySVGProps> = ({
  dependencies,
  patientZero,
  blastRadius,
  podStatuses = [],
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
      <div className="h-32 flex items-center justify-center text-[11px] text-slate-600">
        Topology will populate as dependencies are discovered
      </div>
    );
  }

  const nodeMap = new Map(nodes.map((n) => [n.id, n]));

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="w-full"
      style={{ maxHeight: '260px' }}
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

        const marker = edge.type === 'error' ? 'url(#arrowhead-red)' : 'url(#arrowhead)';
        return (
          <line
            key={i}
            x1={src.x}
            y1={src.y + NODE_RADIUS}
            x2={tgt.x}
            y2={tgt.y - NODE_RADIUS}
            className={edgeStyles[edge.type]}
            markerEnd={marker}
          />
        );
      })}

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
