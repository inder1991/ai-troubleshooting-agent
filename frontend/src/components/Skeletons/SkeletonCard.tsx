import React from 'react';

const SkeletonCard: React.FC = () => {
  return (
    <div className="space-y-2">
      {[0, 1, 2, 3].map((row) => (
        <div
          key={row}
          className="flex items-center gap-3 p-3 bg-[#12110e] border border-[#3d3528] rounded-xl"
        >
          <div className="flex items-center gap-2 w-40 shrink-0">
            <div className="h-5 w-5 bg-[#252118] rounded animate-pulse" />
            <div className="flex flex-col gap-1">
              <div className="h-3 bg-[#252118] rounded animate-pulse w-20" />
              <div className="h-2 bg-[#252118] rounded animate-pulse w-16" />
            </div>
          </div>
          <div className="h-8 bg-[#252118] rounded-lg animate-pulse flex-1 min-w-[200px]" />
          <div className="h-8 bg-[#252118] rounded-lg animate-pulse w-32 shrink-0" />
          <div className="h-6 bg-[#252118] rounded-lg animate-pulse w-14 shrink-0" />
          <div className="h-3 bg-[#252118] rounded animate-pulse w-16 shrink-0" />
        </div>
      ))}
    </div>
  );
};

export default SkeletonCard;
