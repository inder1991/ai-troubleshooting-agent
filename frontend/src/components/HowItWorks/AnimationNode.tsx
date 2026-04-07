import React from 'react';
import { motion } from 'framer-motion';
import type { DuckVariant, DuckState } from './DuckAvatar';
import { DuckSVGContent } from './DuckAvatar';
import type { NodeTier } from './workflowConfigs';
import { WF_COLORS } from './workflowConfigs';

export type NodeStatus = 'pending' | 'active' | 'complete';

interface AnimationNodeProps {
  id: string;
  label: string;
  duck: DuckVariant;
  x: number;
  y: number;
  tier: NodeTier;
  status: NodeStatus;
  progress?: number;
  subtitle?: string;
  badge?: string;
  accentColor?: string;
  dimmed?: boolean;
  dimDelay?: number; // seconds, for staggered left-to-right dimming
}

const TIER_SIZES = {
  landmark: { width: 180, height: 64, radius: 12, fontSize: 13, duckSize: 32, strokeWidth: 2 },
  agent:    { width: 150, height: 56, radius: 10, fontSize: 11, duckSize: 28, strokeWidth: 1.5 },
  pipeline: { width: 130, height: 44, radius: 8,  fontSize: 10, duckSize: 0,  strokeWidth: 1 },
};

const STATUS_COLORS = {
  pending:  { fill: WF_COLORS.pendingFill, stroke: WF_COLORS.pendingStroke, glow: 'none' },
  active:   { fill: WF_COLORS.activeFill,  stroke: WF_COLORS.activeStroke,  glow: WF_COLORS.amber },
  complete: { fill: WF_COLORS.completeFill, stroke: WF_COLORS.completeStroke, glow: WF_COLORS.green },
};

const RING_RADIUS = 14;

const AnimationNode: React.FC<AnimationNodeProps> = ({
  id, label, duck, x, y, tier, status, progress = 0, subtitle, badge, accentColor, dimmed, dimDelay = 0,
}) => {
  const colors = STATUS_COLORS[status];
  const size = TIER_SIZES[tier];
  const duckState: DuckState = status === 'active' ? 'working' : status === 'complete' ? 'done' : 'idle';
  const showDuck = tier !== 'pipeline';

  const circumference = 2 * Math.PI * RING_RADIUS;
  const dashOffset = circumference * (1 - progress);

  const halfW = size.width / 2;
  const halfH = size.height / 2;

  return (
    <motion.g
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: dimmed ? 0.4 : 1, scale: 1 }}
      transition={{ type: 'spring', stiffness: 200, damping: 20, delay: dimmed ? dimDelay : 0 }}
    >
      {/* Glow */}
      {status !== 'pending' && !dimmed && (
        <motion.ellipse
          cx={x}
          cy={y}
          rx={halfW + 8}
          ry={halfH + 8}
          fill={colors.glow}
          initial={{ opacity: 0 }}
          animate={{ opacity: [0.05, 0.15, 0.05] }}
          transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
        />
      )}

      {/* Node background */}
      <motion.rect
        x={x - halfW}
        y={y - halfH}
        width={size.width}
        height={size.height}
        rx={size.radius}
        fill={colors.fill}
        stroke={colors.stroke}
        strokeWidth={size.strokeWidth}
        animate={{ stroke: colors.stroke, fill: colors.fill }}
        transition={{ duration: 0.5 }}
      />

      {/* Left accent bar for agent tier */}
      {tier === 'agent' && accentColor && (
        <rect
          x={x - halfW}
          y={y - halfH + 4}
          width={4}
          height={size.height - 8}
          rx={2}
          fill={accentColor}
        />
      )}

      {/* Duck avatar — pure SVG, no foreignObject */}
      {showDuck && (
        <g transform={`translate(${x - halfW + 10}, ${y - size.duckSize / 2}) scale(${size.duckSize / 24})`}>
          <DuckSVGContent variant={duck} state={duckState} />
        </g>
      )}

      {/* Label */}
      <text
        x={showDuck ? x + (tier === 'landmark' ? 12 : 8) : x}
        y={subtitle && status === 'active' ? y - 3 : y + 1}
        textAnchor="middle"
        fill={status === 'pending' ? WF_COLORS.dimText : WF_COLORS.labelText}
        fontSize={size.fontSize}
        fontWeight="600"
        fontFamily="DM Sans, Inter, system-ui, sans-serif"
      >
        {label}
      </text>

      {/* Subtitle */}
      {subtitle && status === 'active' && (
        <motion.text
          x={showDuck ? x + (tier === 'landmark' ? 12 : 8) : x}
          y={y + 10}
          textAnchor="middle"
          fill={WF_COLORS.mutedText}
          fontSize="8"
          fontFamily="Inter, system-ui, sans-serif"
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
            x={x + halfW - 40}
            y={y + halfH - 6}
            width={36}
            height={14}
            rx={7}
            fill="#059669"
          />
          <text
            x={x + halfW - 22}
            y={y + halfH + 4}
            textAnchor="middle"
            fill="white"
            fontSize="7"
            fontWeight="600"
          >
            {badge}
          </text>
        </motion.g>
      )}

      {/* Progress ring (active agents/landmarks only) */}
      {status === 'active' && progress > 0 && tier !== 'pipeline' && (
        <g transform={`translate(${x + halfW - 20}, ${y})`}>
          <circle r={RING_RADIUS} fill="none" stroke={WF_COLORS.pendingStroke} strokeWidth="2" />
          <motion.circle
            r={RING_RADIUS}
            fill="none"
            stroke={WF_COLORS.amber}
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

      {/* Burst effect for report/final nodes */}
      {status === 'complete' && id.includes('report') && (
        <motion.circle
          key={`${id}-burst`}
          cx={x}
          cy={y}
          r={halfW}
          fill="none"
          stroke={WF_COLORS.amber}
          strokeWidth={2}
          initial={{ r: 10, opacity: 0.8 }}
          animate={{ r: halfW * 2, opacity: 0 }}
          transition={{ duration: 1.5, ease: 'easeOut' }}
        />
      )}
    </motion.g>
  );
};

export default AnimationNode;
