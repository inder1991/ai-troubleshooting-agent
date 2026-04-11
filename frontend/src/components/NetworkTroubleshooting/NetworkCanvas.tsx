import React from 'react';
import type { NetworkFindings } from '../../types';

interface NetworkCanvasProps {
  findings: NetworkFindings;
  direction: 'forward' | 'return';
}

interface HopNode {
  hop_number: number;
  ip: string;
  device_name?: string;
  device_id?: string;
  status: string;
  type: 'source' | 'hop' | 'firewall' | 'destination';
  firewallAction?: string;
}

const STATUS_COLORS: Record<string, string> = {
  success: '#22c55e',
  reachable: '#22c55e',
  allow: '#22c55e',
  ALLOW: '#22c55e',
  deny: '#ef4444',
  DENY: '#ef4444',
  drop: '#ef4444',
  DROP: '#ef4444',
  timeout: '#f59e0b',
  unreachable: '#ef4444',
  blocked: '#ef4444',
};

const ICON_MAP: Record<string, string> = {
  source: 'dns',
  hop: 'router',
  firewall: 'security',
  destination: 'cloud',
};

const NetworkCanvas: React.FC<NetworkCanvasProps> = ({ findings, direction }) => {
  const state = direction === 'return' && findings.return_state ? findings.return_state : findings.state;
  const traceHops = state.trace_hops || [];
  const firewallVerdicts = state.firewall_verdicts || [];
  const finalPath = state.final_path;

  // Build a map of device_id -> firewall verdict for quick lookup
  const fwMap = new Map<string, { action: string; device_name: string }>();
  for (const fv of firewallVerdicts) {
    fwMap.set(fv.device_id, { action: fv.action, device_name: fv.device_name });
  }

  // Build hop nodes from trace_hops
  const nodes: HopNode[] = traceHops.map((hop, idx) => {
    const fw = hop.device_id ? fwMap.get(hop.device_id) : undefined;
    let type: HopNode['type'] = 'hop';
    if (idx === 0) type = 'source';
    else if (idx === traceHops.length - 1) type = 'destination';
    if (fw) type = 'firewall';

    return {
      hop_number: hop.hop_number,
      ip: hop.ip,
      device_name: hop.device_name || fw?.device_name,
      device_id: hop.device_id,
      status: fw ? fw.action : hop.status,
      type,
      firewallAction: fw?.action,
    };
  });

  // If no trace_hops but we have final_path, build minimal nodes
  if (nodes.length === 0 && finalPath) {
    const pathHops = finalPath.hops || [];
    pathHops.forEach((hopStr, idx) => {
      nodes.push({
        hop_number: idx + 1,
        ip: hopStr,
        status: idx === pathHops.length - 1 && finalPath.blocked ? 'blocked' : 'success',
        type: idx === 0 ? 'source' : idx === pathHops.length - 1 ? 'destination' : 'hop',
      });
    });
  }

  if (nodes.length === 0) {
    return (
      <div
        className="flex-1 flex items-center justify-center rounded-lg"
        style={{ backgroundColor: '#1a1814', border: '1px solid #3d3528' }}
      >
        <div className="text-center font-mono">
          <span
            className="material-symbols-outlined text-3xl block mb-2"
            style={{ color: '#3d3528' }}
          >
            route
          </span>
          <span className="text-xs" style={{ color: '#64748b' }}>
            Network path will appear here
          </span>
        </div>
      </div>
    );
  }

  return (
    <div
      className="flex-1 rounded-lg p-4 overflow-auto"
      style={{ backgroundColor: '#1a1814', border: '1px solid #3d3528' }}
    >
      <div
        className="text-xs font-mono uppercase tracking-wider mb-4"
        style={{ color: '#64748b' }}
      >
        Network Path
      </div>

      {/* Vertical path layout */}
      <div className="flex flex-col items-center gap-0">
        {nodes.map((node, idx) => {
          const statusColor =
            STATUS_COLORS[node.status?.toLowerCase()] || '#64748b';
          const isBlocked =
            node.firewallAction?.toUpperCase() === 'DENY' ||
            node.firewallAction?.toUpperCase() === 'DROP' ||
            node.status?.toLowerCase() === 'blocked';
          const icon = ICON_MAP[node.type] || 'router';

          return (
            <React.Fragment key={node.hop_number}>
              {/* Connection line from previous node */}
              {idx > 0 && (
                <div className="flex flex-col items-center">
                  <div
                    className="w-0.5 h-6"
                    style={{
                      backgroundColor: isBlocked ? '#ef4444' : '#3d3528',
                      ...(isBlocked
                        ? {}
                        : {
                            backgroundImage:
                              'repeating-linear-gradient(to bottom, #e09f3e 0, #e09f3e 4px, transparent 4px, transparent 8px)',
                            backgroundSize: '2px 8px',
                          }),
                    }}
                  />
                  {isBlocked && (
                    <div
                      className="flex items-center gap-1 text-body-xs font-mono font-bold px-2 py-0.5 rounded"
                      style={{ color: '#ef4444', backgroundColor: 'rgba(239,68,68,0.12)' }}
                    >
                      <span className="material-symbols-outlined text-xs">block</span>
                      BLOCKED
                    </div>
                  )}
                  <div
                    className="w-0.5 h-6"
                    style={{
                      backgroundColor: isBlocked ? '#ef4444' : '#3d3528',
                      ...(isBlocked
                        ? {}
                        : {
                            backgroundImage:
                              'repeating-linear-gradient(to bottom, #e09f3e 0, #e09f3e 4px, transparent 4px, transparent 8px)',
                            backgroundSize: '2px 8px',
                          }),
                    }}
                  />
                </div>
              )}

              {/* Node card */}
              <div
                className="flex items-center gap-3 px-4 py-2.5 rounded-lg w-full max-w-xs"
                style={{
                  backgroundColor: '#0a0f13',
                  border: `1px solid ${isBlocked ? '#ef4444' : '#3d3528'}`,
                  boxShadow: isBlocked ? '0 0 12px rgba(239,68,68,0.15)' : undefined,
                }}
              >
                {/* Icon */}
                <span
                  className="material-symbols-outlined text-lg flex-shrink-0"
                  style={{ color: statusColor }}
                >
                  {icon}
                </span>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    {node.device_name && (
                      <span
                        className="text-xs font-mono font-bold truncate"
                        style={{ color: '#e8e0d4' }}
                      >
                        {node.device_name}
                      </span>
                    )}
                    {node.firewallAction && (
                      <span
                        className="text-body-xs font-mono font-bold px-1.5 py-0.5 rounded"
                        style={{
                          color: statusColor,
                          backgroundColor: `${statusColor}1a`,
                        }}
                      >
                        {node.firewallAction.toUpperCase()}
                      </span>
                    )}
                  </div>
                  <div
                    className="text-xs font-mono tabular-nums"
                    style={{ color: '#8a7e6b' }}
                  >
                    {node.ip}
                  </div>
                </div>

                {/* Status dot */}
                <span
                  className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                  style={{ backgroundColor: statusColor }}
                />
              </div>
            </React.Fragment>
          );
        })}
      </div>

      {/* Path summary */}
      {finalPath && (
        <div
          className="mt-4 pt-3 flex items-center justify-between text-xs font-mono"
          style={{ borderTop: '1px solid #3d3528', color: '#64748b' }}
        >
          <span>
            {finalPath.hop_count} hops &middot;{' '}
            {finalPath.has_nat ? 'NAT detected' : 'No NAT'}
          </span>
          <span style={{ color: finalPath.blocked ? '#ef4444' : '#22c55e' }}>
            {finalPath.blocked ? 'Path Blocked' : 'Path Clear'}
          </span>
        </div>
      )}
    </div>
  );
};

export default NetworkCanvas;
