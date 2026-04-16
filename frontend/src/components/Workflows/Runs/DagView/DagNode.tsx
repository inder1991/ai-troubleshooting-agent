import type { PositionedNode } from './dagTypes';
import type { StepRunStatus } from '../../../../types';

/* ── Status color map ─────────────────────────────────────────── */
const STATUS_FILL: Record<StepRunStatus, string> = {
  pending:   '#525252',
  running:   '#d97706',
  success:   '#059669',
  failed:    '#dc2626',
  skipped:   '#6b7280',
  cancelled: '#64748b',
};

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

interface DagNodeProps {
  node: PositionedNode;
  dimmed?: boolean;
  highlighted?: boolean;
  selected?: boolean;
  onClick?: (nodeId: string) => void;
}

export default function DagNode({ node, dimmed, highlighted, selected, onClick }: DagNodeProps) {
  const fill = STATUS_FILL[node.status];
  const stroke = selected ? '#e09f3e' : fill;
  const strokeWidth = selected ? 3 : 1;

  const handleClick = () => onClick?.(node.id);
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onClick?.(node.id);
    }
  };

  const statusText = node.duration_ms != null
    ? `${node.status} · ${formatDuration(node.duration_ms)}`
    : node.status;

  return (
    <g
      data-testid={`dag-node-${node.id}`}
      transform={`translate(${node.x}, ${node.y})`}
      opacity={dimmed ? 0.2 : 1}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      role="button"
      tabIndex={0}
      aria-label={`Step ${node.id}, status ${node.status}`}
      style={{ cursor: 'pointer' }}
    >
      {/* Base rectangle */}
      <rect
        width={node.width}
        height={node.height}
        rx={8}
        fill={fill}
        stroke={stroke}
        strokeWidth={strokeWidth}
      />

      {/* Running pulse overlay */}
      {node.status === 'running' && (
        <rect
          className="animate-pulse"
          width={node.width}
          height={node.height}
          rx={8}
          fill={fill}
          opacity={0.4}
        />
      )}

      {/* Failure path glow — dashed outline */}
      {highlighted && (
        <rect
          width={node.width}
          height={node.height}
          rx={8}
          fill="none"
          stroke={node.status === 'failed' ? '#dc2626' : '#e09f3e'}
          strokeWidth={2}
          strokeDasharray="6 3"
        />
      )}

      {/* Step ID label */}
      <text x={10} y={22} fill="white" fontSize={13} fontWeight="bold">
        {node.id}
      </text>

      {/* Agent@version label */}
      <text x={10} y={40} fill="#a1a1aa" fontSize={11}>
        {node.agent}@{node.agentVersion}
      </text>

      {/* Status + duration */}
      <text x={10} y={58} fill="#d4d4d8" fontSize={11}>
        {statusText}
      </text>

      {/* Error indicator for failed nodes */}
      {node.status === 'failed' && (
        <text
          data-testid={`dag-node-error-${node.id}`}
          x={node.width - 20}
          y={18}
          fill="#fca5a5"
          fontSize={16}
        >
          ⚠
        </text>
      )}
    </g>
  );
}
