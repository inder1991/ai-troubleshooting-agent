import React from 'react';
import type { ClusterDomainKey, ClusterDomainReport } from '../../types';
import { DOMAIN_META } from './domainMeta';

interface VerticalRibbonProps {
  domain: ClusterDomainKey;
  report?: ClusterDomainReport;
  onClick: () => void;
  onPriorityClick?: () => void;
  isPriority?: boolean;
  isActive?: boolean;
}

const VerticalRibbon: React.FC<VerticalRibbonProps> = ({ domain, report, onClick, onPriorityClick, isPriority, isActive }) => {
  // Priority tab at position 0
  if (isPriority) {
    return (
      <button
        type="button"
        className={`
          flex-1 border-b border-[#1f3b42] last:border-b-0 relative group cursor-pointer
          hover:bg-[#152a2f]/80 transition-colors flex flex-col items-center py-2 gap-2 overflow-hidden
          ${isActive ? 'bg-[#e09f3e]/10 border-l-2 border-l-[#e09f3e]' : ''}
          focus:outline-none focus:ring-1 focus:ring-inset focus:ring-[#e09f3e]
        `}
        onClick={onPriorityClick || onClick}
        aria-label="Priority findings tab"
        aria-pressed={isActive}
      >
        <span
          className="material-symbols-outlined text-sm"
          style={{ color: isActive ? '#e09f3e' : '#64748b' }}
        >
          priority_high
        </span>

        <div className="vertical-label text-[10px] font-bold tracking-widest whitespace-nowrap py-2 flex-1 text-center"
          style={{ color: isActive ? '#e09f3e' : '#64748b' }}
        >
          PRIORITY
        </div>
      </button>
    );
  }

  const meta = DOMAIN_META[domain];
  const hasAnomaly = report && report.anomalies.length > 0;
  const isRunning = report?.status === 'RUNNING';
  const iconColor = hasAnomaly ? '#f59e0b' : report?.status === 'SUCCESS' ? '#10b981' : '#64748b';

  return (
    <button
      type="button"
      className={`
        flex-1 border-b border-[#1f3b42] last:border-b-0 relative group cursor-pointer
        hover:bg-[#152a2f]/80 transition-colors flex flex-col items-center py-2 gap-2 overflow-hidden
        ${hasAnomaly ? 'bg-amber-500/5' : ''}
        ${isActive ? 'bg-[#e09f3e]/10 border-l-2 border-l-[#e09f3e]' : ''}
        focus:outline-none focus:ring-1 focus:ring-inset focus:ring-[#e09f3e]
      `}
      onClick={onClick}
      aria-label={`${meta.label} domain tab`}
      aria-pressed={isActive}
    >
      <span
        className={`material-symbols-outlined text-sm ${isRunning ? 'animate-pulse' : ''}`}
        style={{ color: isActive ? '#e09f3e' : iconColor }}
      >
        {meta.icon}
      </span>

      <svg className="w-full h-12 fill-none" preserveAspectRatio="none" viewBox="0 0 40 100" style={{ stroke: isActive ? '#e09f3e' : iconColor }}>
        <path d="M20 100 L20 60 L35 50 L5 40 L20 30 L20 0" strokeWidth="1.5" />
      </svg>

      <div className="vertical-label text-[10px] font-bold tracking-widest text-slate-400 whitespace-nowrap py-2 flex-1 text-center"
        style={{ color: isActive ? '#e09f3e' : undefined }}
      >
        {meta.label}
      </div>
    </button>
  );
};

export default VerticalRibbon;
