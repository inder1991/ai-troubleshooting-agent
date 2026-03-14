import React from 'react';

interface SectionHeaderProps {
  title: string;
  count?: number;
  action?: React.ReactNode;
  children?: React.ReactNode;
}

export const SectionHeader: React.FC<SectionHeaderProps> = ({ title, count, action, children }) => (
  <div className="flex items-center justify-between mb-4">
    <div className="flex items-center gap-3">
      <h2 className="text-base font-bold text-white tracking-tight font-display">{title}</h2>
      {count !== undefined && (
        <span className="px-2 py-0.5 bg-[#e09f3e]/10 text-[#e09f3e] text-[10px] font-black uppercase rounded tracking-widest border border-[#e09f3e]/20">
          {count}
        </span>
      )}
      {children}
    </div>
    {action && <div>{action}</div>}
  </div>
);
