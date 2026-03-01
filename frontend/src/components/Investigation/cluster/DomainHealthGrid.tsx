import React from 'react';
import type { ClusterDomainReport } from '../../../types';

interface DomainHealthGridProps {
  domains: ClusterDomainReport[];
}

const DOMAIN_LABELS: Record<string, string> = {
  ctrl_plane: 'CP',
  node: 'ND',
  network: 'NW',
  storage: 'ST',
};

const STATUS_DOT: Record<string, string> = {
  SUCCESS: 'bg-emerald-500',
  PARTIAL: 'bg-amber-500',
  FAILED: 'bg-red-500',
  PENDING: 'bg-slate-600',
};

export default function DomainHealthGrid({ domains }: DomainHealthGridProps) {
  const defaultDomains = ['ctrl_plane', 'node', 'network', 'storage'].map(d => {
    const found = domains.find(dd => dd.domain === d);
    return found || { domain: d, status: 'PENDING' as const, confidence: 0, anomalies: [], ruled_out: [], evidence_refs: [], truncation_flags: {}, duration_ms: 0 };
  });

  return (
    <div className="mb-3">
      <div className="flex items-center gap-2 mb-2">
        <span className="material-symbols-outlined text-cyan-400 text-base">dashboard</span>
        <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Domain Health</span>
      </div>
      <div className="grid grid-cols-2 gap-1.5">
        {defaultDomains.map(d => {
          const label = DOMAIN_LABELS[d.domain] || d.domain.slice(0, 2).toUpperCase();
          const dotClass = STATUS_DOT[d.status] || STATUS_DOT.PENDING;
          return (
            <div key={d.domain} className="bg-slate-900/40 border border-slate-700/30 rounded px-2 py-1.5 flex items-center gap-2">
              <span className={`w-1.5 h-1.5 rounded-full ${dotClass}`} />
              <span className="text-[10px] font-mono text-slate-400">{label}</span>
              <div className="ml-auto flex items-center gap-1.5">
                {d.anomalies.length > 0 && (
                  <span className="text-[9px] font-mono text-red-400">{d.anomalies.length}</span>
                )}
                <div className="w-8 h-1 bg-slate-800 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-cyan-500 rounded-full transition-all"
                    style={{ width: `${Math.min(d.confidence, 100)}%` }}
                  />
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
