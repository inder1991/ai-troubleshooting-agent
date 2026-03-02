import React from 'react';

interface TraceHop {
  hop_number: number;
  ip: string;
  rtt_ms: number;
  status: string;
  device_id?: string;
  device_name?: string;
  attribution_confidence?: number;
}

interface PathHopListProps {
  hops: TraceHop[];
}

const STATUS_DOT: Record<string, string> = {
  success: '#22c55e',
  reachable: '#22c55e',
  timeout: '#f59e0b',
  unreachable: '#ef4444',
  blocked: '#ef4444',
};

const PathHopList: React.FC<PathHopListProps> = ({ hops }) => {
  if (!hops || hops.length === 0) {
    return (
      <div className="text-xs font-mono py-2" style={{ color: '#64748b' }}>
        No traceroute hops available.
      </div>
    );
  }

  return (
    <div className="space-y-1">
      <div className="text-xs font-mono mb-2 uppercase tracking-wider" style={{ color: '#64748b' }}>
        Traceroute Hops
      </div>
      {hops.map((hop) => {
        const dotColor = STATUS_DOT[hop.status?.toLowerCase()] || '#64748b';
        return (
          <div
            key={hop.hop_number}
            className="flex items-center gap-2 px-2 py-1.5 rounded font-mono text-xs"
            style={{ backgroundColor: '#0a0f13' }}
          >
            {/* Hop number */}
            <span
              className="w-5 text-right flex-shrink-0"
              style={{ color: '#64748b' }}
            >
              {hop.hop_number}
            </span>

            {/* Status dot */}
            <span
              className="w-2 h-2 rounded-full flex-shrink-0"
              style={{ backgroundColor: dotColor }}
            />

            {/* IP */}
            <span className="flex-1 truncate" style={{ color: '#e2e8f0' }}>
              {hop.ip}
            </span>

            {/* Device name */}
            {hop.device_name && (
              <span className="truncate max-w-[100px]" style={{ color: '#07b6d5' }}>
                {hop.device_name}
              </span>
            )}

            {/* RTT */}
            <span className="flex-shrink-0 tabular-nums" style={{ color: '#94a3b8' }}>
              {hop.rtt_ms > 0 ? `${hop.rtt_ms.toFixed(1)}ms` : '*'}
            </span>
          </div>
        );
      })}
    </div>
  );
};

export default PathHopList;
