import React from 'react';
import type { InferredDependency, PatientZero, BlastRadiusData } from '../../../types';
import { useTopologyLayout, type TopologyNode, type TopologyEdge } from './useTopologyLayout';

interface ServiceTopologySVGProps {
  dependencies: InferredDependency[];
  patientZero: PatientZero | null;
  blastRadius: BlastRadiusData | null;
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
}) => {
  const { nodes, edges, width, height } = useTopologyLayout(dependencies, patientZero, blastRadius);

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
        return (
          <g key={node.id} className={style.className}>
            <circle
              cx={node.x}
              cy={node.y}
              r={NODE_RADIUS}
              fill={style.fill}
              stroke={style.stroke}
              strokeWidth={node.role === 'patient_zero' ? 2.5 : 1.5}
              filter={node.role === 'patient_zero' ? 'url(#glow-red)' : undefined}
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
