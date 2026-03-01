import React from 'react';
import type { ClusterDomainReport } from '../../../types';

// Map domain to display label and short code
const DOMAIN_META: Record<string, { label: string; code: string }> = {
  ctrl_plane: { label: 'Control Plane', code: 'CP' },
  node: { label: 'Node Health', code: 'ND' },
  network: { label: 'Network & DNS', code: 'NW' },
  storage: { label: 'Storage & PVCs', code: 'ST' },
};

const STATUS_BORDER: Record<string, string> = {
  SUCCESS: 'border-l-emerald-500',
  PARTIAL: 'border-l-amber-500',
  FAILED: 'border-l-red-500',
  RUNNING: 'border-l-cyan-500',
  PENDING: 'border-l-slate-600',
};

interface DomainAgentStatusProps {
  reports: ClusterDomainReport[];
}

export default function DomainAgentStatus({ reports }: DomainAgentStatusProps) {
  // Use the DOMAIN_META order, fill in with report data when available
  const domains = ['ctrl_plane', 'node', 'network', 'storage'];

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 mb-1">
        <span className="material-symbols-outlined text-cyan-400 text-base">monitor_heart</span>
        <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Domain Agents</span>
      </div>
      {domains.map((domain) => {
        const report = reports.find((r) => r.domain === domain);
        const meta = DOMAIN_META[domain] || { label: domain, code: domain.slice(0, 2).toUpperCase() };
        const status = report?.status || 'PENDING';
        const borderClass = STATUS_BORDER[status] || STATUS_BORDER.PENDING;
        const anomalyCount = report?.anomalies?.length || 0;
        const confidence = report?.confidence || 0;

        return (
          <div
            key={domain}
            className={`bg-slate-900/40 border border-slate-700/30 border-l-2 ${borderClass} rounded px-3 py-2 flex items-center justify-between`}
          >
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-mono text-slate-500 w-5">{meta.code}</span>
              <span className="text-xs text-slate-300">{meta.label}</span>
            </div>
            <div className="flex items-center gap-3">
              {anomalyCount > 0 && (
                <span className="text-[9px] font-mono px-1.5 py-0.5 rounded-full bg-red-500/10 text-red-400 border border-red-500/30">
                  {anomalyCount}
                </span>
              )}
              <span className="text-[10px] text-slate-500 font-mono">{confidence}%</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
