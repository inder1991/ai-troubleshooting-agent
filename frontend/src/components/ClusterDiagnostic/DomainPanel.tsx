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
    case 'RUNNING': return { text: 'ACTIVE_TRACING', cls: 'text-wr-accent bg-wr-accent/10 border-wr-accent/20' };
    case 'PARTIAL': return { text: 'PARTIAL', cls: 'text-amber-400 bg-amber-400/10 border-amber-400/20' };
    case 'FAILED': return { text: 'FAILED', cls: 'text-red-400 bg-red-400/10 border-red-400/20' };
    default: return { text: 'PENDING', cls: 'text-slate-400 bg-slate-400/10 border-slate-400/20' };
  }
};

const DomainPanel: React.FC<DomainPanelProps> = ({ domain, report, namespaces }) => {
  const meta = DOMAIN_META[domain];
  const badge = statusBadge(report?.status);

  return (
    <div className="flex-1 flex flex-col h-full bg-wr-surface/20 transition-transform duration-300 hover:scale-[1.005] origin-center z-10 shadow-2xl">
      <div className="px-4 py-3 bg-wr-surface border-b border-wr-border flex items-center justify-between shrink-0">
        <h2 className="font-bold text-sm tracking-wide flex items-center gap-2">
          <span className="material-symbols-outlined text-base" style={{ color: meta.color }}>
            {meta.icon}
          </span>
          DOMAIN: {meta.label}
        </h2>
        <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${badge.cls}`}>
          {badge.text}
        </span>
      </div>

      {/* Failure reason banner */}
      {report?.status === 'FAILED' && report.failure_reason && (
        <div className="mx-4 mt-3 px-3 py-2 rounded border border-red-500/20 bg-red-500/5 text-[11px]">
          <span className="text-red-400 font-semibold">Agent failed: </span>
          <span className="text-red-300">{report.failure_reason.replace(/_/g, ' ').toLowerCase()}</span>
          {report.data_gathered_before_failure && report.data_gathered_before_failure.length > 0 && (
            <div className="mt-1 text-slate-500">
              Partial data collected: {report.data_gathered_before_failure.join(', ')}
            </div>
          )}
        </div>
      )}

      {/* Partial status info */}
      {report?.status === 'PARTIAL' && (
        <div className="mx-4 mt-3 px-3 py-2 rounded border border-amber-500/20 bg-amber-500/5 text-[11px]">
          <span className="text-amber-400 font-semibold">Partial results — </span>
          <span className="text-amber-300">{report.failure_reason ? report.failure_reason.replace(/_/g, ' ').toLowerCase() : 'some data missing'}</span>
          {report.data_gathered_before_failure && report.data_gathered_before_failure.length > 0 && (
            <div className="mt-1 text-slate-500">
              Data collected: {report.data_gathered_before_failure.join(', ')}
            </div>
          )}
        </div>
      )}

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
                  ? `border-wr-accent bg-wr-surface/40 rounded-r border-y border-r border-wr-border/50`
                  : `border-wr-border ${isHealthy ? 'opacity-40 hover:opacity-80 transition-opacity' : ''}`
              }`}
            >
              <h4 className={`text-xs font-mono flex items-center gap-2 ${hasTrigger ? 'text-wr-accent' : 'text-slate-500'}`}>
                <span className="material-symbols-outlined text-[14px]">grid_view</span>
                namespace: {ns.namespace}
              </h4>

              {hasTrigger && ns.workloads?.map(w => (
                <div key={w.name} className="mt-2">
                  <WorkloadCard workload={w} domainColor={meta.color} />
                </div>
              ))}

              {!hasTrigger && (
                <div className="mt-2 bg-wr-bg/30 p-2 rounded text-[10px] text-slate-600 font-mono">
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

        {/* Ruled out (healthy checks) */}
        {report && report.ruled_out.length > 0 && (
          <div className="mx-4 mt-2 mb-3 px-3 py-2 rounded border border-emerald-500/10 bg-emerald-500/5">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-emerald-600">Ruled Out ({report.ruled_out.length})</span>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {report.ruled_out.map((item, i) => (
                <span key={i} className="text-[10px] text-emerald-500/60 bg-emerald-500/5 px-1.5 py-0.5 rounded font-mono">
                  {item}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default DomainPanel;
