import React from 'react';
import type { ClusterDomainKey, ClusterDomainReport, NamespaceWorkload } from '../../types';
import WorkloadCard from './WorkloadCard';
import { DOMAIN_META } from './domainMeta';

interface DomainPanelProps {
  domain: ClusterDomainKey;
  report?: ClusterDomainReport;
  namespaces: NamespaceWorkload[];
}

const statusBadge = (status?: string) => {
  switch (status) {
    case 'SUCCESS': return { text: 'HEALTHY', cls: 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20' };
    case 'RUNNING': return { text: 'ACTIVE_TRACING', cls: 'text-[#13b6ec] bg-[#13b6ec]/10 border-[#13b6ec]/20' };
    case 'PARTIAL': return { text: 'PARTIAL', cls: 'text-amber-400 bg-amber-400/10 border-amber-400/20' };
    case 'FAILED': return { text: 'FAILED', cls: 'text-red-400 bg-red-400/10 border-red-400/20' };
    default: return { text: 'PENDING', cls: 'text-slate-400 bg-slate-400/10 border-slate-400/20' };
  }
};

const DomainPanel: React.FC<DomainPanelProps> = ({ domain, report, namespaces }) => {
  const meta = DOMAIN_META[domain];
  const badge = statusBadge(report?.status);

  return (
    <div className="flex-1 flex flex-col h-full bg-[#152a2f]/20 transition-transform duration-300 hover:scale-[1.005] origin-center z-10 shadow-2xl">
      <div className="px-4 py-3 bg-[#152a2f] border-b border-[#1f3b42] flex items-center justify-between shrink-0">
        <h2 className="font-bold text-sm tracking-wide flex items-center gap-2">
          <span className="material-symbols-outlined text-base" style={{ fontFamily: 'Material Symbols Outlined', color: meta.color }}>
            {meta.icon}
          </span>
          DOMAIN: {meta.label}
        </h2>
        <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${badge.cls}`}>
          {badge.text}
        </span>
      </div>

      <div className="p-4 space-y-4 overflow-y-auto flex-1 custom-scrollbar">
        {namespaces.length === 0 && !report && (
          <div className="text-xs text-slate-600 animate-pulse">Scanning namespaces...</div>
        )}

        {namespaces.map(ns => {
          const isHealthy = ns.status === 'Healthy';
          const hasTrigger = ns.workloads?.some(w => w.is_trigger);

          return (
            <div
              key={ns.namespace}
              className={`border-l-2 pl-4 py-2 ${
                hasTrigger
                  ? `border-[#13b6ec] bg-[#152a2f]/40 rounded-r border-y border-r border-[#1f3b42]/50`
                  : `border-[#1f3b42] ${isHealthy ? 'opacity-40 hover:opacity-80 transition-opacity' : ''}`
              }`}
            >
              <h4 className={`text-xs font-mono flex items-center gap-2 ${hasTrigger ? 'text-[#13b6ec]' : 'text-slate-500'}`}>
                <span className="material-symbols-outlined text-[14px]" style={{ fontFamily: 'Material Symbols Outlined' }}>grid_view</span>
                namespace: {ns.namespace}
              </h4>

              {hasTrigger && ns.workloads?.map(w => (
                <div key={w.name} className="mt-2">
                  <WorkloadCard workload={w} domainColor={meta.color} />
                </div>
              ))}

              {!hasTrigger && (
                <div className="mt-2 bg-[#0f2023]/30 p-2 rounded text-[10px] text-slate-600 font-mono">
                  Status: {ns.status} | {ns.replica_status || '—'} | Last Deploy: {ns.last_deploy || '—'}
                </div>
              )}
            </div>
          );
        })}

        {namespaces.length === 0 && report?.anomalies?.map((a, i) => (
          <div key={a.anomaly_id || i} className="text-xs text-slate-300 mb-1 pl-3 border-l-2" style={{ borderColor: meta.color + '60' }}>
            {a.description}
          </div>
        ))}
      </div>
    </div>
  );
};

export default DomainPanel;
