import React from 'react';

const SkeletonTable: React.FC = () => {
  return (
    <div className="border border-[#224349] rounded-xl overflow-hidden">
      {/* Header */}
      <div className="bg-[#1e2f33]/50 px-4 py-2.5 flex gap-4">
        {[120, 80, 90, 70, 80, 60].map((w, i) => (
          <div key={i} className="h-3 bg-[#1e2f33] rounded animate-pulse" style={{ width: w }} />
        ))}
      </div>
      {/* Rows */}
      {[0, 1, 2].map((row) => (
        <div key={row} className="bg-[#0a1a1d] px-4 py-3 border-t border-[#224349]/50 flex items-center gap-4">
          <div className="flex flex-col gap-1.5 w-40">
            <div className="h-3 bg-[#1e2f33] rounded animate-pulse w-28" />
            <div className="h-2 bg-[#1e2f33] rounded animate-pulse w-36" />
          </div>
          <div className="h-4 bg-[#1e2f33] rounded animate-pulse w-16" />
          <div className="h-3 bg-[#1e2f33] rounded animate-pulse w-20" />
          <div className="flex items-center gap-2">
            <div className="h-2 w-2 bg-[#1e2f33] rounded-full animate-pulse" />
            <div className="h-3 bg-[#1e2f33] rounded animate-pulse w-16" />
          </div>
          <div className="h-3 bg-[#1e2f33] rounded animate-pulse w-14" />
          <div className="ml-auto flex gap-1">
            <div className="h-6 w-6 bg-[#1e2f33] rounded animate-pulse" />
            <div className="h-6 w-6 bg-[#1e2f33] rounded animate-pulse" />
          </div>
        </div>
      ))}
    </div>
  );
};

export default SkeletonTable;
