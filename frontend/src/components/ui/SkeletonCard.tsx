import React from 'react';

interface SkeletonCardProps {
  variant?: 'card' | 'inline' | 'metric';
}

const shimmerClass = 'animate-pulse bg-slate-800/60 rounded';

const SkeletonCard: React.FC<SkeletonCardProps> = ({ variant = 'card' }) => {
  if (variant === 'inline') {
    return (
      <div className="flex items-center gap-3 py-2">
        <div className={`w-5 h-5 rounded-full ${shimmerClass}`} />
        <div className={`h-3 flex-1 max-w-[200px] ${shimmerClass}`} />
        <div className={`h-3 w-16 ${shimmerClass}`} />
      </div>
    );
  }

  if (variant === 'metric') {
    return (
      <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-4">
        <div className="flex items-center gap-2 mb-3">
          <div className={`w-5 h-5 rounded-full ${shimmerClass}`} />
          <div className={`h-3 w-24 ${shimmerClass}`} />
        </div>
        <div className={`h-8 w-20 mb-2 ${shimmerClass}`} />
        <div className={`h-12 w-full ${shimmerClass}`} />
      </div>
    );
  }

  // Default: full card
  return (
    <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-4 space-y-3">
      <div className="flex items-center gap-2">
        <div className={`w-5 h-5 rounded-full ${shimmerClass}`} />
        <div className={`h-3 w-32 ${shimmerClass}`} />
        <div className={`h-3 w-16 ml-auto ${shimmerClass}`} />
      </div>
      <div className={`h-3 w-full ${shimmerClass}`} />
      <div className={`h-3 w-3/4 ${shimmerClass}`} />
      <div className="flex gap-2">
        <div className={`h-5 w-16 rounded-full ${shimmerClass}`} />
        <div className={`h-5 w-20 rounded-full ${shimmerClass}`} />
      </div>
    </div>
  );
};

/** Multiple skeleton cards for loading states */
export const SkeletonStack: React.FC<{ count?: number; variant?: SkeletonCardProps['variant'] }> = ({
  count = 3,
  variant = 'card',
}) => (
  <div className="space-y-3">
    {Array.from({ length: count }).map((_, i) => (
      <SkeletonCard key={i} variant={variant} />
    ))}
  </div>
);

export default SkeletonCard;
