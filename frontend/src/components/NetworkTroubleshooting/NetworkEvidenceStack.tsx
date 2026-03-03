import React from 'react';
import type { NetworkFindings } from '../../types';
import FirewallVerdictCard from './FirewallVerdictCard';
import AdapterHealthBadge from './AdapterHealthBadge';

interface NetworkEvidenceStackProps {
  findings: NetworkFindings;
  adapters?: Array<{ vendor: string; status: string }>;
}

const NetworkEvidenceStack: React.FC<NetworkEvidenceStackProps> = ({
  findings,
  adapters,
}) => {
  const state = findings.state;
  const firewallVerdicts = state.firewall_verdicts || [];
  const natTranslations = state.nat_translations || [];
  const traceHops = state.trace_hops || [];
  const contradictions = state.contradictions || [];
  const evidence = state.evidence || [];
  const naclVerdicts = state.nacl_verdicts || [];
  const vpcCrossings = state.vpc_boundary_crossings || [];
  const vpnSegments = state.vpn_segments || [];
  const lbsInPath = state.load_balancers_in_path || [];

  return (
    <div className="flex flex-col gap-4 h-full overflow-y-auto pr-1 custom-scrollbar">
      {/* Firewall Verdicts */}
      {firewallVerdicts.length > 0 && (
        <div>
          <div
            className="text-xs font-mono uppercase tracking-wider mb-2 flex items-center gap-1.5"
            style={{ color: '#64748b' }}
          >
            <span className="material-symbols-outlined text-sm" style={{ color: '#f59e0b' }}>
              security
            </span>
            Firewall Verdicts ({firewallVerdicts.length})
          </div>
          <div className="space-y-2">
            {firewallVerdicts.map((v, i) => (
              <FirewallVerdictCard key={`${v.device_id}-${i}`} verdict={v} />
            ))}
          </div>
        </div>
      )}

      {/* NACL Verdicts */}
      {naclVerdicts.length > 0 && (
        <div
          className="rounded-lg p-3"
          style={{ backgroundColor: '#0f2023', border: '1px solid #224349' }}
        >
          <div
            className="text-xs font-mono uppercase tracking-wider mb-2 flex items-center gap-1.5"
            style={{ color: '#64748b' }}
          >
            <span className="material-symbols-outlined text-sm" style={{ color: '#ef4444' }}>
              checklist
            </span>
            NACL Evaluation ({naclVerdicts.length})
          </div>
          <div className="space-y-2">
            {naclVerdicts.map((v, i) => (
              <div
                key={`${v.nacl_id}-${i}`}
                className="flex items-center justify-between rounded px-3 py-2"
                style={{ backgroundColor: '#0a0f13' }}
              >
                <span className="text-xs font-mono" style={{ color: '#e2e8f0' }}>{v.nacl_name}</span>
                <span
                  className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded uppercase"
                  style={{
                    backgroundColor: v.action === 'allow' ? '#052e16' : '#450a0a',
                    color: v.action === 'allow' ? '#22c55e' : '#ef4444',
                  }}
                >
                  {v.action}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* VPC Boundary Crossings */}
      {vpcCrossings.length > 0 && (
        <div
          className="rounded-lg p-3"
          style={{ backgroundColor: '#0f2023', border: '1px solid #224349' }}
        >
          <div
            className="text-xs font-mono uppercase tracking-wider mb-2 flex items-center gap-1.5"
            style={{ color: '#64748b' }}
          >
            <span className="material-symbols-outlined text-sm" style={{ color: '#3b82f6' }}>
              cloud_circle
            </span>
            VPC Boundary Crossings ({vpcCrossings.length})
          </div>
          <div className="space-y-2">
            {vpcCrossings.map((c, i) => (
              <div
                key={i}
                className="flex items-center gap-2 rounded px-3 py-2 font-mono text-xs"
                style={{ backgroundColor: '#0a0f13' }}
              >
                <span style={{ color: '#3b82f6' }}>{c.from_vpc}</span>
                <span className="material-symbols-outlined text-sm" style={{ color: '#64748b' }}>arrow_forward</span>
                <span style={{ color: '#3b82f6' }}>{c.to_vpc}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* VPN Tunnel Segments */}
      {vpnSegments.length > 0 && (
        <div
          className="rounded-lg p-3"
          style={{ backgroundColor: '#0f2023', border: '1px solid #224349' }}
        >
          <div
            className="text-xs font-mono uppercase tracking-wider mb-2 flex items-center gap-1.5"
            style={{ color: '#64748b' }}
          >
            <span className="material-symbols-outlined text-sm" style={{ color: '#f97316' }}>
              vpn_lock
            </span>
            VPN Tunnel Segments ({vpnSegments.length})
          </div>
          <div className="space-y-2">
            {vpnSegments.map((seg, i) => (
              <div
                key={`${seg.device_id}-${i}`}
                className="rounded px-3 py-2 font-mono text-xs"
                style={{ backgroundColor: '#0a0f13' }}
              >
                <div className="flex items-center justify-between mb-1">
                  <span style={{ color: '#e2e8f0' }}>{seg.name}</span>
                  <span
                    className="text-[10px] px-1.5 py-0.5 rounded uppercase"
                    style={{ color: '#f97316', backgroundColor: 'rgba(249,115,22,0.12)' }}
                  >
                    {seg.tunnel_type}
                  </span>
                </div>
                {seg.encryption && (
                  <div style={{ color: '#64748b' }}>Encryption: {seg.encryption}</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Load Balancers in Path */}
      {lbsInPath.length > 0 && (
        <div
          className="rounded-lg p-3"
          style={{ backgroundColor: '#0f2023', border: '1px solid #224349' }}
        >
          <div
            className="text-xs font-mono uppercase tracking-wider mb-2 flex items-center gap-1.5"
            style={{ color: '#64748b' }}
          >
            <span className="material-symbols-outlined text-sm" style={{ color: '#22c55e' }}>
              dns
            </span>
            Load Balancers ({lbsInPath.length})
          </div>
          <div className="space-y-2">
            {lbsInPath.map((lb, i) => (
              <div
                key={`${lb.device_id}-${i}`}
                className="flex items-center justify-between rounded px-3 py-2 font-mono text-xs"
                style={{ backgroundColor: '#0a0f13' }}
              >
                <span style={{ color: '#e2e8f0' }}>{lb.device_name}</span>
                <span
                  className="text-[10px] px-1.5 py-0.5 rounded uppercase"
                  style={{ color: '#22c55e', backgroundColor: 'rgba(34,197,94,0.12)' }}
                >
                  {lb.device_type}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* NAT Translations */}
      {natTranslations.length > 0 && (
        <div
          className="rounded-lg p-3"
          style={{ backgroundColor: '#0f2023', border: '1px solid #224349' }}
        >
          <div
            className="text-xs font-mono uppercase tracking-wider mb-2 flex items-center gap-1.5"
            style={{ color: '#64748b' }}
          >
            <span className="material-symbols-outlined text-sm" style={{ color: '#07b6d5' }}>
              swap_horiz
            </span>
            NAT Translations
          </div>
          <div className="space-y-2">
            {natTranslations.map((nat, i) => (
              <div
                key={i}
                className="rounded px-3 py-2 font-mono text-xs"
                style={{ backgroundColor: '#0a0f13' }}
              >
                <div className="flex items-center gap-2 mb-1">
                  <span style={{ color: '#f59e0b' }}>{nat.direction?.toUpperCase()}</span>
                  <span style={{ color: '#64748b' }}>on {nat.device_id}</span>
                </div>
                {nat.original_src && (
                  <div style={{ color: '#94a3b8' }}>
                    Src: {nat.original_src}{' '}
                    {nat.translated_src && (
                      <>
                        <span style={{ color: '#07b6d5' }}>&rarr;</span>{' '}
                        {nat.translated_src}
                      </>
                    )}
                  </div>
                )}
                {nat.original_dst && (
                  <div style={{ color: '#94a3b8' }}>
                    Dst: {nat.original_dst}{' '}
                    {nat.translated_dst && (
                      <>
                        <span style={{ color: '#07b6d5' }}>&rarr;</span>{' '}
                        {nat.translated_dst}
                      </>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Traceroute Hop Table */}
      {traceHops.length > 0 && (
        <div
          className="rounded-lg p-3"
          style={{ backgroundColor: '#0f2023', border: '1px solid #224349' }}
        >
          <div
            className="text-xs font-mono uppercase tracking-wider mb-2 flex items-center gap-1.5"
            style={{ color: '#64748b' }}
          >
            <span className="material-symbols-outlined text-sm" style={{ color: '#07b6d5' }}>
              timeline
            </span>
            Traceroute Raw
          </div>
          <table className="w-full font-mono text-xs">
            <thead>
              <tr style={{ color: '#64748b' }}>
                <th className="text-left py-1 pr-2">#</th>
                <th className="text-left py-1 pr-2">IP</th>
                <th className="text-left py-1 pr-2">Device</th>
                <th className="text-right py-1">RTT</th>
              </tr>
            </thead>
            <tbody>
              {traceHops.map((hop) => (
                <tr
                  key={hop.hop_number}
                  style={{ color: '#e2e8f0', borderTop: '1px solid #1a3a3f' }}
                >
                  <td className="py-1 pr-2" style={{ color: '#64748b' }}>
                    {hop.hop_number}
                  </td>
                  <td className="py-1 pr-2 tabular-nums">{hop.ip}</td>
                  <td className="py-1 pr-2" style={{ color: '#07b6d5' }}>
                    {hop.device_name || '-'}
                  </td>
                  <td className="py-1 text-right tabular-nums" style={{ color: '#94a3b8' }}>
                    {hop.rtt_ms > 0 ? `${hop.rtt_ms.toFixed(1)}ms` : '*'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Evidence */}
      {evidence.length > 0 && (
        <div
          className="rounded-lg p-3"
          style={{ backgroundColor: '#0f2023', border: '1px solid #224349' }}
        >
          <div
            className="text-xs font-mono uppercase tracking-wider mb-2 flex items-center gap-1.5"
            style={{ color: '#64748b' }}
          >
            <span className="material-symbols-outlined text-sm" style={{ color: '#22c55e' }}>
              fact_check
            </span>
            Evidence
          </div>
          <div className="space-y-1.5">
            {evidence.map((e, i) => (
              <div
                key={i}
                className="rounded px-2.5 py-1.5 font-mono text-xs"
                style={{ backgroundColor: '#0a0f13' }}
              >
                <span
                  className="inline-block px-1.5 py-0.5 rounded mr-2 text-[10px] uppercase"
                  style={{ color: '#07b6d5', backgroundColor: 'rgba(7,182,213,0.12)' }}
                >
                  {e.type}
                </span>
                <span style={{ color: '#e2e8f0' }}>{e.detail}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Contradiction Alerts */}
      {contradictions.length > 0 && (
        <div
          className="rounded-lg p-3"
          style={{ backgroundColor: '#0f2023', border: '1px solid rgba(239,68,68,0.3)' }}
        >
          <div
            className="text-xs font-mono uppercase tracking-wider mb-2 flex items-center gap-1.5"
            style={{ color: '#ef4444' }}
          >
            <span className="material-symbols-outlined text-sm">warning</span>
            Contradictions ({contradictions.length})
          </div>
          <div className="space-y-1.5">
            {contradictions.map((c, i) => (
              <div
                key={i}
                className="rounded px-2.5 py-1.5 font-mono text-xs"
                style={{
                  backgroundColor: 'rgba(239,68,68,0.06)',
                  color: '#e2e8f0',
                }}
              >
                <span className="font-bold mr-1" style={{ color: '#ef4444' }}>
                  {c.type}:
                </span>
                {c.detail}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Adapter Health */}
      {adapters && adapters.length > 0 && (
        <div
          className="rounded-lg p-3"
          style={{ backgroundColor: '#0f2023', border: '1px solid #224349' }}
        >
          <div
            className="text-xs font-mono uppercase tracking-wider mb-2"
            style={{ color: '#64748b' }}
          >
            Adapter Health
          </div>
          <div className="flex flex-wrap gap-2">
            {adapters.map((a, i) => (
              <AdapterHealthBadge key={i} vendor={a.vendor} status={a.status} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default NetworkEvidenceStack;
