import React from 'react';

interface ReplicaNode {
  host: string;
  lag_ms: number;
  status: string;
}

interface ReplicationTopologySVGProps {
  primary: { host: string; lag_ms: number };
  replicas: ReplicaNode[];
}

function statusColor(status: string): string {
  switch (status.toLowerCase()) {
    case 'healthy':
    case 'streaming':
    case 'active':
      return '#10b981';
    case 'lagging':
    case 'behind':
      return '#f59e0b';
    case 'down':
    case 'error':
    case 'disconnected':
      return '#ef4444';
    default:
      return '#64748b';
  }
}

function lagLabel(lag_ms: number): string {
  if (lag_ms >= 1000) return `${(lag_ms / 1000).toFixed(1)}s`;
  return `${Math.round(lag_ms)}ms`;
}

const NODE_RADIUS = 22;
const SVG_PADDING = 24;
const PRIMARY_Y = 50;
const REPLICA_Y = 150;

const ReplicationTopologySVG: React.FC<ReplicationTopologySVGProps> = ({
  primary,
  replicas,
}) => {
  if (replicas.length === 0) {
    return (
      <div className="text-center py-4">
        <span className="material-symbols-outlined text-2xl text-slate-700 block mb-1">share</span>
        <p className="text-body-xs text-slate-400">No replication topology data</p>
      </div>
    );
  }

  const replicaSpacing = 110;
  const totalReplicaWidth = replicas.length * replicaSpacing;
  const svgWidth = Math.max(totalReplicaWidth, 180) + SVG_PADDING * 2;
  const svgHeight = 210;

  const primaryX = svgWidth / 2;

  return (
    <div className="bg-duck-card/30 border border-duck-border rounded-lg p-3 overflow-x-auto">
      {/* Header */}
      <div className="flex items-center gap-2 mb-2 pb-2 border-b border-slate-800">
        <span className="material-symbols-outlined text-amber-400 text-sm">share</span>
        <span className="text-body-xs font-bold text-slate-400 uppercase tracking-wider">Replication Topology</span>
        <span className="text-body-xs text-slate-400 ml-auto font-mono">
          {replicas.length} replica{replicas.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-3 mb-2">
        {[
          { label: 'Healthy', color: '#10b981' },
          { label: 'Lagging', color: '#f59e0b' },
          { label: 'Down', color: '#ef4444' },
        ].map(({ label, color }) => (
          <div key={label} className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
            <span className="text-body-xs text-slate-400">{label}</span>
          </div>
        ))}
      </div>

      <svg
        viewBox={`0 0 ${svgWidth} ${svgHeight}`}
        className="w-full"
        style={{ minWidth: `${Math.min(svgWidth, 300)}px`, maxHeight: '220px' }}
        role="img"
        aria-label={`Replication topology: primary to ${replicas.length} replicas`}
      >
        <title>Replication Topology</title>
        {/* Connection lines from primary to replicas */}
        {replicas.map((replica, i) => {
          const rx = SVG_PADDING + (i + 0.5) * replicaSpacing;
          const color = statusColor(replica.status);
          const midY = (PRIMARY_Y + REPLICA_Y) / 2;
          return (
            <g key={`line-${i}`}>
              <path
                d={`M ${primaryX} ${PRIMARY_Y + NODE_RADIUS} Q ${primaryX} ${midY} ${rx} ${REPLICA_Y - NODE_RADIUS}`}
                fill="none"
                stroke={color}
                strokeWidth="1.5"
                strokeDasharray={replica.status.toLowerCase() === 'down' ? '4 3' : 'none'}
                opacity={0.5}
              />
              {/* Arrow head */}
              <polygon
                points={`${rx},${REPLICA_Y - NODE_RADIUS} ${rx - 4},${REPLICA_Y - NODE_RADIUS - 8} ${rx + 4},${REPLICA_Y - NODE_RADIUS - 8}`}
                fill={color}
                opacity={0.6}
              />
              {/* Lag label on line */}
              <text
                x={(primaryX + rx) / 2}
                y={midY - 4}
                textAnchor="middle"
                fill="#d4922e"
                fontSize="8"
                fontFamily="monospace"
              >
                {lagLabel(replica.lag_ms)} lag
              </text>
            </g>
          );
        })}

        {/* Primary node */}
        <g>
          <circle
            cx={primaryX}
            cy={PRIMARY_Y}
            r={NODE_RADIUS}
            fill="#d4922e15"
            stroke="#d4922e"
            strokeWidth="2"
          />
          <text
            x={primaryX}
            y={PRIMARY_Y - 2}
            textAnchor="middle"
            fill="#d4922e"
            fontSize="8"
            fontWeight="bold"
          >
            PRIMARY
          </text>
          <text
            x={primaryX}
            y={PRIMARY_Y + 9}
            textAnchor="middle"
            fill="#e8e0d4"
            fontSize="7"
            fontFamily="monospace"
          >
            {primary.host.length > 14 ? primary.host.slice(0, 14) + '...' : primary.host}
          </text>
        </g>

        {/* Replica nodes */}
        {replicas.map((replica, i) => {
          const rx = SVG_PADDING + (i + 0.5) * replicaSpacing;
          const color = statusColor(replica.status);
          return (
            <g key={`replica-${i}`}>
              <circle
                cx={rx}
                cy={REPLICA_Y}
                r={NODE_RADIUS}
                fill={`${color}15`}
                stroke={color}
                strokeWidth="1.5"
              />
              <text
                x={rx}
                y={REPLICA_Y - 2}
                textAnchor="middle"
                fill={color}
                fontSize="7"
                fontWeight="bold"
              >
                {replica.status.toUpperCase()}
              </text>
              <text
                x={rx}
                y={REPLICA_Y + 9}
                textAnchor="middle"
                fill="#e8e0d4"
                fontSize="7"
                fontFamily="monospace"
              >
                {replica.host.length > 14 ? replica.host.slice(0, 14) + '...' : replica.host}
              </text>
              {/* Host label below */}
              <text
                x={rx}
                y={REPLICA_Y + NODE_RADIUS + 14}
                textAnchor="middle"
                fill="#d4922e"
                fontSize="7"
                fontFamily="monospace"
              >
                lag: {lagLabel(replica.lag_ms)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
};

export default ReplicationTopologySVG;
