import React from 'react';
import type { ClusterDomainKey, ClusterDomainReport } from '../../types';

interface VerticalRibbonProps {
  domain: ClusterDomainKey;
  report?: ClusterDomainReport;
  onClick: () => void;
}

const DOMAIN_META: Record<ClusterDomainKey, { icon: string; label: string; color: string }> = {
  ctrl_plane: { icon: 'settings_system_daydream', label: 'CONTROL PLANE', color: '#f59e0b' },
  node: { icon: 'memory', label: 'COMPUTE', color: '#13b6ec' },
  network: { icon: 'network_check', label: 'NETWORK', color: '#10b981' },
  storage: { icon: 'database', label: 'STORAGE', color: '#10b981' },
};

const VerticalRibbon: React.FC<VerticalRibbonProps> = ({ domain, report, onClick }) => {
  const meta = DOMAIN_META[domain];
  const hasAnomaly = report && report.anomalies.length > 0;
  const isRunning = report?.status === 'RUNNING';
  const iconColor = hasAnomaly ? '#f59e0b' : report?.status === 'SUCCESS' ? '#10b981' : '#64748b';

  return (
    <div
      className={`
        flex-1 border-b border-[#1f3b42] last:border-b-0 relative group cursor-pointer
        hover:bg-[#152a2f]/80 transition-colors flex flex-col items-center py-2 gap-2 overflow-hidden
        ${hasAnomaly ? 'bg-amber-500/5' : ''}
      `}
      onClick={onClick}
    >
      <span
        className={`material-symbols-outlined text-sm ${isRunning ? 'animate-pulse' : ''}`}
        style={{ fontFamily: 'Material Symbols Outlined', color: iconColor }}
      >
        {meta.icon}
      </span>

      <svg className="w-full h-12 fill-none" preserveAspectRatio="none" viewBox="0 0 40 100" style={{ stroke: iconColor }}>
        <path d="M20 100 L20 60 L35 50 L5 40 L20 30 L20 0" strokeWidth="1.5" />
      </svg>

      <div className="vertical-label text-[10px] font-bold tracking-widest text-slate-400 whitespace-nowrap py-2 flex-1 text-center">
        {meta.label}
      </div>
    </div>
  );
};

export default VerticalRibbon;
