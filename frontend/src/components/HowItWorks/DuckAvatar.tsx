import React from 'react';
import { motion } from 'framer-motion';

export type DuckVariant =
  | 'supervisor'    // headset
  | 'log'           // magnifying glass
  | 'metrics'       // chart
  | 'k8s'           // hard hat
  | 'network'       // antenna
  | 'storage'       // wrench
  | 'code'          // glasses
  | 'critic'        // gavel
  | 'rbac'          // shield
  | 'ctrl_plane'    // radar
  | 'compute'       // cpu chip
  | 'change'        // git branch
  | 'generic';      // no accessory

export type DuckState = 'idle' | 'working' | 'done';

interface DuckAvatarProps {
  variant: DuckVariant;
  state: DuckState;
  size?: number;
}

// Base duck body path (simple silhouette: round head, beak, body)
const DUCK_BODY = "M12 4c-2 0-3.5 1.5-3.5 3.5 0 1 .4 1.9 1 2.5C7.5 11 6 13 6 15.5c0 2.5 2.7 4.5 6 4.5s6-2 6-4.5c0-2.5-1.5-4.5-3.5-5.5.6-.6 1-1.5 1-2.5C15.5 5.5 14 4 12 4z";
const DUCK_BEAK = "M15.5 7.5l2 .5-2 .5z";
const DUCK_EYE = { cx: 13.5, cy: 6.5, r: 0.7 };

// Accessory SVG elements per variant
function Accessory({ variant }: { variant: DuckVariant }) {
  switch (variant) {
    case 'supervisor':
      // Headset: arc over head + small mic
      return (
        <g stroke="#e09f3e" strokeWidth="1" fill="none">
          <path d="M8 5.5 Q8 2 12 2 Q16 2 16 5.5" />
          <circle cx="7.5" cy="5.5" r="1.2" fill="#e09f3e" />
          <circle cx="16.5" cy="5.5" r="1.2" fill="#e09f3e" />
          <line x1="7.5" y1="6.7" x2="7.5" y2="8.5" />
          <circle cx="7.5" cy="9" r="0.6" fill="#e09f3e" />
        </g>
      );
    case 'log':
      // Magnifying glass
      return (
        <g stroke="#fbbf24" strokeWidth="0.8" fill="none">
          <circle cx="17" cy="4" r="2.2" />
          <line x1="18.5" y1="5.5" x2="20" y2="7" strokeWidth="1.2" />
        </g>
      );
    case 'metrics':
      // Small bar chart
      return (
        <g fill="#10b981">
          <rect x="16" y="5" width="1.2" height="4" rx="0.3" />
          <rect x="18" y="3" width="1.2" height="6" rx="0.3" />
          <rect x="20" y="4.5" width="1.2" height="4.5" rx="0.3" />
        </g>
      );
    case 'k8s':
      // Hard hat
      return (
        <g>
          <path d="M8.5 5 Q12 1.5 15.5 5" fill="#f59e0b" stroke="#d97706" strokeWidth="0.5" />
          <rect x="8" y="4.8" width="8" height="1" rx="0.3" fill="#d97706" />
        </g>
      );
    case 'network':
      // Antenna on head
      return (
        <g stroke="#e09f3e" strokeWidth="0.8">
          <line x1="12" y1="4" x2="12" y2="0.5" />
          <circle cx="12" cy="0" r="1" fill="#e09f3e" />
          <path d="M9.5 1.5 Q12 -0.5 14.5 1.5" fill="none" strokeWidth="0.6" opacity="0.5" />
          <path d="M8 2.5 Q12 -1.5 16 2.5" fill="none" strokeWidth="0.5" opacity="0.3" />
        </g>
      );
    case 'storage':
      // Wrench
      return (
        <g stroke="#a78bfa" strokeWidth="0.8" fill="none">
          <path d="M17 3l3 3" strokeWidth="1.2" />
          <circle cx="20.5" cy="6.5" r="1.5" />
          <path d="M16.5 2.5l1-1 1 1" fill="#a78bfa" />
        </g>
      );
    case 'code':
      // Glasses
      return (
        <g stroke="#60a5fa" strokeWidth="0.7" fill="none">
          <circle cx="10.5" cy="6.5" r="1.8" />
          <circle cx="14.5" cy="6.5" r="1.8" />
          <line x1="12.3" y1="6.5" x2="12.7" y2="6.5" />
          <line x1="8.7" y1="6.5" x2="7.5" y2="5.5" />
          <line x1="16.3" y1="6.5" x2="17.5" y2="5.5" />
        </g>
      );
    case 'critic':
      // Gavel
      return (
        <g fill="#f87171" stroke="#f87171" strokeWidth="0.5">
          <rect x="17" y="2" width="4" height="2" rx="0.5" />
          <line x1="19" y1="4" x2="19" y2="7.5" strokeWidth="1" />
          <rect x="17.5" y="7" width="3" height="0.8" rx="0.3" />
        </g>
      );
    case 'rbac':
      // Shield
      return (
        <g>
          <path d="M17 3l3 1v2.5c0 2-1.5 3.5-3 4.5-1.5-1-3-2.5-3-4.5V4l3-1z" fill="#10b981" opacity="0.8" stroke="#059669" strokeWidth="0.5" />
          <path d="M17 5.5l1.2 1-1.2 1-1.2-1z" fill="white" opacity="0.6" />
        </g>
      );
    case 'ctrl_plane':
      // Radar dish
      return (
        <g stroke="#f59e0b" strokeWidth="0.7" fill="none">
          <path d="M16 2 Q19 2 20 5" />
          <path d="M16.5 3.5 Q18 3.5 18.5 5" />
          <circle cx="17" cy="5.5" r="0.6" fill="#f59e0b" />
          <line x1="17" y1="5.5" x2="20" y2="2" strokeWidth="0.5" />
        </g>
      );
    case 'compute':
      // CPU chip
      return (
        <g>
          <rect x="16.5" y="3" width="4" height="4" rx="0.5" fill="#38bdf8" stroke="#0ea5e9" strokeWidth="0.5" />
          {/* Pins */}
          <line x1="17.5" y1="2.5" x2="17.5" y2="3" stroke="#0ea5e9" strokeWidth="0.5" />
          <line x1="19.5" y1="2.5" x2="19.5" y2="3" stroke="#0ea5e9" strokeWidth="0.5" />
          <line x1="17.5" y1="7" x2="17.5" y2="7.5" stroke="#0ea5e9" strokeWidth="0.5" />
          <line x1="19.5" y1="7" x2="19.5" y2="7.5" stroke="#0ea5e9" strokeWidth="0.5" />
        </g>
      );
    case 'change':
      // Git branch icon
      return (
        <g stroke="#c084fc" strokeWidth="0.8" fill="none">
          <circle cx="18" cy="3" r="1" fill="#c084fc" />
          <circle cx="18" cy="8" r="1" fill="#c084fc" />
          <circle cx="21" cy="5" r="1" fill="#c084fc" />
          <line x1="18" y1="4" x2="18" y2="7" />
          <path d="M18 5.5 Q18 5 21 4" />
        </g>
      );
    default:
      return null;
  }
}

const DuckAvatar: React.FC<DuckAvatarProps> = ({ variant, state, size = 24 }) => {
  // Working animation: gentle bounce
  const bounceVariants = {
    idle: { y: 0 },
    working: {
      y: [0, -2, 0],
      transition: { duration: 0.6, repeat: Infinity, ease: 'easeInOut' },
    },
    done: { y: 0 },
  };

  // Color based on state
  const bodyFill = state === 'done' ? '#10b981' : state === 'working' ? '#fbbf24' : '#475569';
  const bodyStroke = state === 'done' ? '#059669' : state === 'working' ? '#d97706' : '#334155';

  return (
    <motion.svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      variants={bounceVariants}
      animate={state}
      style={{ overflow: 'visible' }}
    >
      {/* Body */}
      <path d={DUCK_BODY} fill={bodyFill} stroke={bodyStroke} strokeWidth="0.5" />
      {/* Beak */}
      <path d={DUCK_BEAK} fill="#f59e0b" />
      {/* Eye */}
      <circle cx={DUCK_EYE.cx} cy={DUCK_EYE.cy} r={DUCK_EYE.r} fill="white" />

      {/* Accessory */}
      <Accessory variant={variant} />

      {/* Done checkmark */}
      {state === 'done' && (
        <motion.g
          initial={{ scale: 0, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: 'spring', stiffness: 300 }}
        >
          <circle cx="19" cy="16" r="3.5" fill="#059669" />
          <path d="M17.5 16l1 1 2-2.5" stroke="white" strokeWidth="1" fill="none" strokeLinecap="round" />
        </motion.g>
      )}
    </motion.svg>
  );
};

/**
 * Pure SVG content — no <svg> wrapper.
 * Renders in a 24x24 coordinate system.
 * Parent must provide transform for positioning and scaling.
 */
export const DuckSVGContent: React.FC<{ variant: DuckVariant; state: DuckState }> = ({ variant, state }) => {
  const bodyFill = state === 'done' ? '#10b981' : state === 'working' ? '#fbbf24' : '#475569';
  const bodyStroke = state === 'done' ? '#059669' : state === 'working' ? '#d97706' : '#334155';

  return (
    <g>
      <path d={DUCK_BODY} fill={bodyFill} stroke={bodyStroke} strokeWidth="0.5" />
      <path d={DUCK_BEAK} fill="#f59e0b" />
      <circle cx={DUCK_EYE.cx} cy={DUCK_EYE.cy} r={DUCK_EYE.r} fill="white" />
      <Accessory variant={variant} />
      {state === 'done' && (
        <g>
          <circle cx="19" cy="16" r="3.5" fill="#059669" />
          <path d="M17.5 16l1 1 2-2.5" stroke="white" strokeWidth="1" fill="none" strokeLinecap="round" />
        </g>
      )}
    </g>
  );
};

export default DuckAvatar;
