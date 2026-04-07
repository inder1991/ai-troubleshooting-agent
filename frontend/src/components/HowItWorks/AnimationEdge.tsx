import React, { useId } from 'react';
import { motion } from 'framer-motion';

export type EdgeStatus = 'pending' | 'active' | 'complete';

interface AnimationEdgeProps {
  fromX: number;
  fromY: number;
  toX: number;
  toY: number;
  status: EdgeStatus;
  color?: string;
  nodeHeight?: number; // to offset from node bottom to next node top
}

const AnimationEdge: React.FC<AnimationEdgeProps> = ({
  fromX, fromY, toX, toY, status, color = '#07b6d5', nodeHeight = 52,
}) => {
  const id = useId();

  // Start from bottom of source node, end at top of target node
  const startY = fromY + nodeHeight / 2;
  const endY = toY - nodeHeight / 2;
  const midY = (startY + endY) / 2;

  // Bezier curve for smooth path
  const pathD = `M ${fromX} ${startY} C ${fromX} ${midY}, ${toX} ${midY}, ${toX} ${endY}`;

  const strokeColor = status === 'pending' ? '#1e293b' : color;
  const strokeOpacity = status === 'pending' ? 0.3 : 0.6;

  return (
    <g>
      {/* Background path */}
      <path
        d={pathD}
        fill="none"
        stroke={strokeColor}
        strokeWidth={1.5}
        strokeOpacity={strokeOpacity}
      />

      {/* Animated particle (active only) */}
      {status === 'active' && (
        <>
          {/* Glow particle */}
          <motion.circle
            r={3}
            fill={color}
            filter={`url(#particle-glow-${id})`}
            initial={{ offsetDistance: '0%' }}
            animate={{ offsetDistance: '100%' }}
            transition={{
              duration: 1.2,
              repeat: Infinity,
              ease: 'linear',
            }}
            style={{
              offsetPath: `path("${pathD}")`,
            }}
          />
          {/* Trail particle (slightly behind) */}
          <motion.circle
            r={2}
            fill={color}
            opacity={0.5}
            initial={{ offsetDistance: '0%' }}
            animate={{ offsetDistance: '100%' }}
            transition={{
              duration: 1.2,
              repeat: Infinity,
              ease: 'linear',
              delay: 0.2,
            }}
            style={{
              offsetPath: `path("${pathD}")`,
            }}
          />
          {/* SVG filter for particle glow */}
          <defs>
            <filter id={`particle-glow-${id}`} x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur in="SourceGraphic" stdDeviation="2" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
        </>
      )}

      {/* Completion pulse (one-shot when transitioning to complete) */}
      {status === 'complete' && (
        <motion.path
          d={pathD}
          fill="none"
          stroke={color}
          strokeWidth={3}
          initial={{ pathLength: 0, opacity: 0.8 }}
          animate={{ pathLength: 1, opacity: 0 }}
          transition={{ duration: 0.8, ease: 'easeOut' }}
        />
      )}
    </g>
  );
};

export default AnimationEdge;
