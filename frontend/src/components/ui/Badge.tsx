import React from 'react';

export type BadgeType = 'NEW' | 'PREVIEW' | 'BETA';

interface BadgeProps {
  type: BadgeType;
  className?: string;
}

const styleMap: Record<BadgeType, string> = {
  NEW: 'bg-duck-accent/10 text-duck-accent border-duck-accent/20',
  PREVIEW: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
  BETA: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
};

export const Badge: React.FC<BadgeProps> = ({ type, className = '' }) => (
  <span
    className={`inline-flex items-center justify-center px-1 py-[1px] rounded border text-body-xs leading-none font-bold uppercase tracking-wider ${styleMap[type]} ${className}`}
  >
    {type}
  </span>
);

export default Badge;
