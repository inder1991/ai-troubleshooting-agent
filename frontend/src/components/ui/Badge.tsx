import React from 'react';

export type BadgeType = 'NEW' | 'PREVIEW' | 'BETA';

interface BadgeProps {
  type: BadgeType;
  className?: string;
}

const styleMap: Record<BadgeType, string> = {
  NEW: 'bg-duck-accent/15 text-duck-accent border-duck-accent/30',
  PREVIEW: 'bg-purple-500/15 text-purple-400 border-purple-500/30',
  BETA: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
};

export const Badge: React.FC<BadgeProps> = ({ type, className = '' }) => (
  <span
    className={`inline-flex items-center justify-center px-1.5 py-0.5 rounded border text-nano font-black uppercase tracking-widest ${styleMap[type]} ${className}`}
  >
    {type}
  </span>
);

export default Badge;
