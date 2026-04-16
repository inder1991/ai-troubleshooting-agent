import type { PositionedEdge } from './dagTypes';
import type { EdgeStatus } from './dagHelpers';

/* ── Edge status color map ────────────────────────────────────── */
const EDGE_STROKE: Record<EdgeStatus, string> = {
  pending:   '#525252',
  active:    '#d97706',
  completed: '#059669',
  failed:    '#dc2626',
};

function pointsToPath(points: Array<{ x: number; y: number }>): string {
  if (points.length === 0) return '';
  const [first, ...rest] = points;
  return `M ${first.x} ${first.y}` + rest.map((p) => ` L ${p.x} ${p.y}`).join('');
}

interface DagEdgeProps {
  edge: PositionedEdge;
  edgeStatus: EdgeStatus;
  dimmed?: boolean;
  onFailurePath?: boolean;
}

export default function DagEdge({ edge, edgeStatus, dimmed, onFailurePath }: DagEdgeProps) {
  const d = pointsToPath(edge.points);
  const stroke = EDGE_STROKE[edgeStatus];
  const baseStrokeWidth = onFailurePath ? 3 : 2;

  return (
    <g
      data-testid={`edge-${edge.source}-${edge.target}`}
      opacity={dimmed ? 0.1 : 1}
    >
      {/* Base path */}
      <path
        d={d}
        fill="none"
        stroke={stroke}
        strokeWidth={baseStrokeWidth}
        markerEnd="url(#arrowhead)"
      />

      {/* Flow particles — active edges only */}
      {edgeStatus === 'active' && (
        <path
          className="dag-flow-particle"
          d={d}
          fill="none"
          stroke="white"
          strokeWidth={2}
          strokeDasharray="4 8"
          strokeOpacity={0.6}
        />
      )}

      {/* Completed glow */}
      {edgeStatus === 'completed' && (
        <path
          d={d}
          fill="none"
          stroke="#059669"
          strokeWidth="4"
          strokeOpacity="0.3"
        />
      )}
    </g>
  );
}
