import React from 'react';
import { motion } from 'framer-motion';
import DuckAvatar, { type DuckVariant, type DuckState } from './DuckAvatar';

export type NodeStatus = 'pending' | 'active' | 'complete';

interface AnimationNodeProps {
  id: string;
  label: string;
  duck: DuckVariant;
  x: number;
  y: number;
  status: NodeStatus;
  progress?: number; // 0-1, shown as ring
  subtitle?: string; // e.g. "Analyzing operators..."
  badge?: string;    // e.g. "3 anomalies"
}

const STATUS_COLORS = {
  pending: { fill: '#1e293b', stroke: '#334155', glow: 'none' },
  active:  { fill: '#0c2d3f', stroke: '#07b6d5', glow: '#07b6d5' },
  complete:{ fill: '#0c2d1f', stroke: '#10b981', glow: '#10b981' },
};

const NODE_WIDTH = 140;
const NODE_HEIGHT = 52;
const RING_RADIUS = 14;

const AnimationNode: React.FC<AnimationNodeProps> = ({
  id, label, duck, x, y, status, progress = 0, subtitle, badge,
}) => {
  const colors = STATUS_COLORS[status];
  const duckState: DuckState = status === 'active' ? 'working' : status === 'complete' ? 'done' : 'idle';

  // Progress ring math
  const circumference = 2 * Math.PI * RING_RADIUS;
  const dashOffset = circumference * (1 - progress);

  return (
    <motion.g
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ type: 'spring', stiffness: 200, damping: 20 }}
    >
      {/* Glow filter */}
      {status !== 'pending' && (
        <motion.ellipse
          cx={x}
          cy={y}
          rx={NODE_WIDTH / 2 + 8}
          ry={NODE_HEIGHT / 2 + 8}
          fill={colors.glow}
          initial={{ opacity: 0 }}
          animate={{ opacity: [0.05, 0.15, 0.05] }}
          transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
        />
      )}

      {/* Node background */}
      <motion.rect
        x={x - NODE_WIDTH / 2}
        y={y - NODE_HEIGHT / 2}
        width={NODE_WIDTH}
        height={NODE_HEIGHT}
        rx={10}
        fill={colors.fill}
        stroke={colors.stroke}
        strokeWidth={status === 'active' ? 1.5 : 1}
        animate={{
          stroke: colors.stroke,
          fill: colors.fill,
        }}
        transition={{ duration: 0.5 }}
      />

      {/* Duck avatar */}
      <foreignObject
        x={x - NODE_WIDTH / 2 + 8}
        y={y - 12}
        width={24}
        height={24}
      >
        <DuckAvatar variant={duck} state={duckState} size={24} />
      </foreignObject>

      {/* Progress ring (only when active and progress > 0) */}
      {status === 'active' && progress > 0 && (
        <g transform={`translate(${x - NODE_WIDTH / 2 + 20}, ${y})`}>
          <circle
            r={RING_RADIUS}
            fill="none"
            stroke="#334155"
            strokeWidth="2"
          />
          <motion.circle
            r={RING_RADIUS}
            fill="none"
            stroke="#07b6d5"
            strokeWidth="2"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            strokeLinecap="round"
            transform="rotate(-90)"
            animate={{ strokeDashoffset: dashOffset }}
            transition={{ duration: 0.3 }}
          />
        </g>
      )}

      {/* Label */}
      <text
        x={x + 6}
        y={y - 4}
        textAnchor="middle"
        fill={status === 'pending' ? '#64748b' : '#e2e8f0'}
        fontSize="11"
        fontWeight="600"
        fontFamily="system-ui, sans-serif"
      >
        {label}
      </text>

      {/* Subtitle */}
      {subtitle && status === 'active' && (
        <motion.text
          x={x + 6}
          y={y + 10}
          textAnchor="middle"
          fill="#94a3b8"
          fontSize="8"
          fontFamily="system-ui, sans-serif"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
        >
          {subtitle}
        </motion.text>
      )}

      {/* Badge */}
      {badge && status === 'complete' && (
        <motion.g
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ type: 'spring', stiffness: 300, delay: 0.2 }}
        >
          <rect
            x={x + NODE_WIDTH / 2 - 40}
            y={y + NODE_HEIGHT / 2 - 6}
            width={36}
            height={14}
            rx={7}
            fill="#059669"
          />
          <text
            x={x + NODE_WIDTH / 2 - 22}
            y={y + NODE_HEIGHT / 2 + 4}
            textAnchor="middle"
            fill="white"
            fontSize="7"
            fontWeight="600"
          >
            {badge}
          </text>
        </motion.g>
      )}

      {/* Burst effect for report/final nodes — key ensures one-shot animation */}
      {status === 'complete' && id.includes('report') && (
        <motion.circle
          key={`${id}-burst`}
          cx={x}
          cy={y}
          r={NODE_WIDTH / 2}
          fill="none"
          stroke="#07b6d5"
          strokeWidth={2}
          initial={{ r: 10, opacity: 0.8 }}
          animate={{ r: NODE_WIDTH, opacity: 0 }}
          transition={{ duration: 1.5, ease: 'easeOut' }}
        />
      )}
    </motion.g>
  );
};

export default AnimationNode;
