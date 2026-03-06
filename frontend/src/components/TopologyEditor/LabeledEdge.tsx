import React from 'react';
import { getBezierPath, EdgeLabelRenderer, type EdgeProps } from 'reactflow';

const edgeColors: Record<string, string> = {
  connected_to: '#07b6d5',
  vpc_contains: '#3b82f6',
  load_balances: '#22c55e',
  routes_to: '#a855f7',
  tunnel_to: '#f97316',
  nacl_guards: '#ef4444',
  attached_to: '#eab308',
};

const LabeledEdge: React.FC<EdgeProps> = ({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  sourceHandleId,
  style = {},
  selected,
}) => {
  const edgeType = (data?.label as string) || 'connected_to';
  const color = edgeColors[edgeType] || '#07b6d5';
  const interfaceName = sourceHandleId?.startsWith('iface-')
    ? (data?.interface as string) || sourceHandleId.replace('iface-', '')
    : null;

  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const markerId = `arrow-${id}`;

  return (
    <>
      <defs>
        <marker
          id={markerId}
          markerWidth="12"
          markerHeight="12"
          refX="10"
          refY="6"
          orient="auto"
        >
          <path d="M2,2 L10,6 L2,10" fill="none" stroke={color} strokeWidth="1.5" />
        </marker>
      </defs>
      {/* Invisible fat interaction path for easier click targeting */}
      <path
        d={edgePath}
        style={{ stroke: 'transparent', strokeWidth: 15, fill: 'none', cursor: 'pointer' }}
      />
      <path
        id={id}
        className="react-flow__edge-path"
        d={edgePath}
        style={{ ...style, stroke: color, strokeWidth: selected ? 3 : 2 }}
        markerEnd={`url(#${markerId})`}
      />
      {selected && (
        <path
          d={edgePath}
          style={{ stroke: color, strokeWidth: 6, strokeOpacity: 0.2, fill: 'none' }}
        />
      )}
      <EdgeLabelRenderer>
        <div
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            pointerEvents: 'all',
          }}
          className="nodrag nopan"
        >
          <span
            className="text-[9px] font-mono px-2 py-1 rounded-full"
            style={{
              backgroundColor: selected ? color + '20' : '#0a0f13e6',
              color,
              border: `1px solid ${selected ? color : color + '40'}`,
            }}
          >
            {interfaceName || edgeType.replace(/_/g, ' ')}
          </span>
        </div>
      </EdgeLabelRenderer>
    </>
  );
};

export default LabeledEdge;
