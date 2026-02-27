import React, { useState, useEffect, useCallback } from 'react';
import type {
  V4Session, ClusterHealthReport, ClusterDomainReport,
  ClusterCausalChain, TaskEvent,
} from '../../types';

interface ClusterWarRoomProps {
  session: V4Session;
  events: TaskEvent[];
  wsConnected: boolean;
  phase: string | null;
  confidence: number;
  onGoHome: () => void;
}

const DOMAIN_COLORS: Record<string, string> = {
  ctrl_plane: '#ef4444',
  node: '#07b6d5',
  network: '#f97316',
  storage: '#10b981',
};

const DOMAIN_LABELS: Record<string, string> = {
  ctrl_plane: 'Control Plane & Etcd',
  node: 'Node & Capacity',
  network: 'Network & Ingress',
  storage: 'Storage & Persistence',
};

const ClusterWarRoom: React.FC<ClusterWarRoomProps> = ({
  session, events, wsConnected, phase, confidence, onGoHome,
}) => {
  const [findings, setFindings] = useState<ClusterHealthReport | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchFindings = useCallback(async () => {
    try {
      const res = await fetch(`/api/v4/session/${session.session_id}/findings`);
      if (res.ok) {
        const data = await res.json();
        if (data.platform_health && data.platform_health !== 'PENDING') {
          setFindings(data as ClusterHealthReport);
        }
      }
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [session.session_id]);

  useEffect(() => {
    fetchFindings();
    const interval = setInterval(fetchFindings, 5000);
    return () => clearInterval(interval);
  }, [fetchFindings]);

  const healthColor = findings?.platform_health === 'HEALTHY' ? '#10b981'
    : findings?.platform_health === 'DEGRADED' ? '#f59e0b'
    : findings?.platform_health === 'CRITICAL' ? '#ef4444'
    : '#6b7280';

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ backgroundColor: '#0f2023' }}>
      {/* Header */}
      <header className="h-14 border-b border-[#224349] flex items-center justify-between px-6 shrink-0">
        <div className="flex items-center gap-4">
          <button onClick={onGoHome} className="text-slate-400 hover:text-white transition-colors">
            <span className="material-symbols-outlined" style={{ fontFamily: 'Material Symbols Outlined' }}>arrow_back</span>
          </button>
          <div>
            <h1 className="text-white font-bold text-lg">Cluster Diagnostics</h1>
            <p className="text-xs text-slate-500">{session.session_id.slice(0, 8)}</p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 px-3 py-1 rounded-full" style={{ backgroundColor: `${healthColor}20`, border: `1px solid ${healthColor}40` }}>
            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: healthColor }} />
            <span className="text-xs font-bold uppercase tracking-wider" style={{ color: healthColor }}>
              {findings?.platform_health || 'Analyzing...'}
            </span>
          </div>
          {findings && (
            <span className="text-xs text-slate-500">
              Data: {Math.round((findings.data_completeness || 0) * 100)}%
            </span>
          )}
        </div>
      </header>

      {/* Main content grid */}
      <div className="flex-1 overflow-y-auto p-6 custom-scrollbar">
        {loading && !findings && (
          <div className="flex items-center justify-center h-64 text-slate-500">
            <span className="material-symbols-outlined animate-spin mr-2" style={{ fontFamily: 'Material Symbols Outlined' }}>progress_activity</span>
            Running cluster diagnostics...
          </div>
        )}

        {findings && (
          <div className="grid grid-cols-12 gap-4">
            {/* Domain panels — 4 columns, 3 cols each */}
            {(['ctrl_plane', 'node', 'network', 'storage'] as const).map(domain => {
              const report = findings.domain_reports?.find(r => r.domain === domain);
              return (
                <div key={domain} className="col-span-3 rounded-lg border p-4" style={{ borderColor: '#224349', backgroundColor: 'rgba(15,32,35,0.6)' }}>
                  <div className="flex items-center gap-2 mb-3">
                    <div className="w-1 h-6 rounded-full" style={{ backgroundColor: DOMAIN_COLORS[domain] }} />
                    <h3 className="text-sm font-bold text-white">{DOMAIN_LABELS[domain]}</h3>
                  </div>
                  {report ? (
                    <>
                      <div className="flex items-center gap-2 mb-2">
                        <span className={`text-xs font-bold uppercase ${report.status === 'SUCCESS' ? 'text-emerald-400' : report.status === 'FAILED' ? 'text-red-400' : 'text-amber-400'}`}>
                          {report.status}
                        </span>
                        <span className="text-xs text-slate-500">
                          {report.confidence}% confidence
                        </span>
                      </div>
                      {report.anomalies?.map((a, i) => (
                        <div key={i} className="text-xs text-slate-300 mb-1 pl-3 border-l-2" style={{ borderColor: DOMAIN_COLORS[domain] + '60' }}>
                          {a.description}
                        </div>
                      ))}
                      {report.ruled_out?.length > 0 && (
                        <div className="mt-2 text-[10px] text-slate-600">
                          Ruled out: {report.ruled_out.join(', ')}
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="text-xs text-slate-600 animate-pulse">Analyzing...</div>
                  )}
                </div>
              );
            })}

            {/* Causal chains — full width */}
            {findings.causal_chains?.length > 0 && (
              <div className="col-span-12 rounded-lg border p-4" style={{ borderColor: '#224349', backgroundColor: 'rgba(15,32,35,0.6)' }}>
                <h3 className="text-sm font-bold text-white mb-3">Causal Chains</h3>
                {findings.causal_chains.map(chain => (
                  <div key={chain.chain_id} className="mb-3 p-3 rounded border" style={{ borderColor: '#224349' }}>
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-xs font-bold text-red-400 uppercase">Root Cause</span>
                      <span className="text-xs text-slate-500">{Math.round(chain.confidence * 100)}% confidence</span>
                    </div>
                    <p className="text-sm text-white mb-2">{chain.root_cause.description}</p>
                    {chain.cascading_effects.map(effect => (
                      <div key={effect.order} className="flex items-center gap-2 ml-4 mb-1">
                        <span className="text-slate-600">&rarr;</span>
                        <span className="text-xs text-slate-300">{effect.description}</span>
                        <span className="text-[10px] text-slate-600">({effect.link_type})</span>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            )}

            {/* Blast radius */}
            {findings.blast_radius?.summary && (
              <div className="col-span-6 rounded-lg border p-4" style={{ borderColor: '#224349', backgroundColor: 'rgba(15,32,35,0.6)' }}>
                <h3 className="text-sm font-bold text-white mb-2">Blast Radius</h3>
                <p className="text-sm text-slate-300 mb-2">{findings.blast_radius.summary}</p>
                <div className="flex gap-4 text-xs text-slate-500">
                  <span>{findings.blast_radius.affected_nodes} nodes</span>
                  <span>{findings.blast_radius.affected_pods} pods</span>
                  <span>{findings.blast_radius.affected_namespaces} namespaces</span>
                </div>
              </div>
            )}

            {/* Remediation */}
            {(findings.remediation?.immediate?.length > 0 || findings.remediation?.long_term?.length > 0) && (
              <div className="col-span-6 rounded-lg border p-4" style={{ borderColor: '#224349', backgroundColor: 'rgba(15,32,35,0.6)' }}>
                <h3 className="text-sm font-bold text-white mb-2">Remediation</h3>
                {findings.remediation.immediate?.map((step, i) => (
                  <div key={i} className="mb-2">
                    <p className="text-xs text-slate-300">{step.description}</p>
                    {step.command && (
                      <code className="text-[10px] text-cyan-400 block mt-1 font-mono">{step.command}</code>
                    )}
                  </div>
                ))}
                {findings.remediation.long_term?.length > 0 && (
                  <>
                    <h4 className="text-xs font-bold text-slate-400 mt-3 mb-1">Long Term</h4>
                    {findings.remediation.long_term.map((step, i) => (
                      <div key={i} className="mb-2">
                        <p className="text-xs text-slate-300">{step.description}</p>
                      </div>
                    ))}
                  </>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default ClusterWarRoom;
