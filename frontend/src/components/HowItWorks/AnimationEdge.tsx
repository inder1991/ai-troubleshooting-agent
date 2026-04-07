import React, { useId } from 'react';
import { motion } from 'framer-motion';
import { WF_COLORS } from './workflowConfigs';

export type EdgeStatus = 'pending' | 'active' | 'complete';

interface AnimationEdgeProps {
  fromX: number;
  fromY: number;
  toX: number;
  toY: number;
  status: EdgeStatus;
  color?: string;
  fromWidth?: number;
  fromHeight?: number;
  toWidth?: number;
  toHeight?: number;
}

const AnimationEdge: React.FC<AnimationEdgeProps> = ({
  fromX, fromY, toX, toY, status,
  color = WF_COLORS.amber,
  fromWidth = 150, fromHeight = 56,
  toWidth = 150, toHeight = 56,
}) => {
  const id = useId();

  // Determine if edge is primarily horizontal or vertical
  const dx = Math.abs(toX - fromX);
  const dy = Math.abs(toY - fromY);
  const horizontal = dx > dy;

  let pathD: string;

  if (horizontal) {
    // Horizontal: exit right side of source, enter left side of target
    const startX = fromX + fromWidth / 2;
    const startY = fromY;
    const endX = toX - toWidth / 2;
    const endY = toY;
    const cpOffset = (endX - startX) * 0.4;
    pathD = `M ${startX} ${startY} C ${startX + cpOffset} ${startY}, ${endX - cpOffset} ${endY}, ${endX} ${endY}`;
  } else {
    // Vertical: exit bottom of source, enter top of target
    const startX = fromX;
    const startY = fromY + fromHeight / 2;
    const endX = toX;
    const endY = toY - toHeight / 2;
    const cpOffset = (endY - startY) * 0.4;
    pathD = `M ${startX} ${startY} C ${startX} ${startY + cpOffset}, ${endX} ${endY - cpOffset}, ${endX} ${endY}`;
  }

  const strokeColor = status === 'pending' ? WF_COLORS.pendingStroke : color;
  const strokeOpacity = status === 'pending' ? 0.3 : 0.6;

  return (
    <g>
      <path
        d={pathD}
        fill="none"
        stroke={strokeColor}
        strokeWidth={1.5}
        strokeOpacity={strokeOpacity}
      />

      {status === 'active' && (
        <>
          <motion.circle
            r={3}
            fill={color}
            filter={`url(#particle-glow-${id})`}
            initial={{ offsetDistance: '0%' }}
            animate={{ offsetDistance: '100%' }}
            transition={{ duration: 1.2, repeat: Infinity, ease: 'linear' }}
            style={{ offsetPath: `path("${pathD}")` }}
          />
          <motion.circle
            r={2}
            fill={color}
            opacity={0.5}
            initial={{ offsetDistance: '0%' }}
            animate={{ offsetDistance: '100%' }}
            transition={{ duration: 1.2, repeat: Infinity, ease: 'linear', delay: 0.2 }}
            style={{ offsetPath: `path("${pathD}")` }}
          />
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
