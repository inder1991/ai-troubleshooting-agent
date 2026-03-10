import React from 'react';
import { SparklineWidget } from '../shared';
import type { CapabilityType } from '../../types';
import { Badge, type BadgeType } from '../ui/Badge';

interface QuickActionsPanelProps {
  onSelectCapability: (capability: CapabilityType) => void;
  wsConnected: boolean;
}

const actions: { label: string; capability: CapabilityType; icon: string; badge?: BadgeType }[] = [
  { label: 'New Investigation', capability: 'troubleshoot_app', icon: 'troubleshoot' },
  { label: 'Network Scan', capability: 'network_troubleshooting', icon: 'lan', badge: 'NEW' },
  { label: 'Cluster Check', capability: 'cluster_diagnostics', icon: 'deployed_code', badge: 'PREVIEW' },
  { label: 'PR Review', capability: 'pr_review', icon: 'code', badge: 'NEW' },
];

export const QuickActionsPanel: React.FC<QuickActionsPanelProps> = ({ onSelectCapability, wsConnected }) => (
  <div className="flex flex-col gap-4">
    <div className="bg-duck-panel border border-duck-border rounded-lg p-4">
      <h3 className="text-xs font-bold text-duck-muted uppercase tracking-wider mb-3">Quick Actions</h3>
      <div className="flex flex-col gap-1.5">
        {actions.map((a) => (
          <button
            key={a.capability}
            onClick={() => onSelectCapability(a.capability)}
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-300 hover:text-white hover:bg-duck-surface transition-all duration-200 ease-in-out text-left group focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent"
          >
            <span className="material-symbols-outlined text-[18px] text-duck-accent group-hover:text-white transition-colors" aria-hidden="true">
              {a.icon}
            </span>
            <span className="text-sm font-medium">{a.label}</span>
            {a.badge && <Badge type={a.badge} className="ml-2" />}
            <span className="material-symbols-outlined text-[14px] text-slate-600 ml-auto opacity-0 group-hover:opacity-100 transition-opacity" aria-hidden="true">
              arrow_forward
            </span>
          </button>
        ))}
      </div>
    </div>

    <div className="bg-duck-panel border border-duck-border rounded-lg p-4">
      <h3 className="text-xs font-bold text-duck-muted uppercase tracking-wider mb-3">System Health</h3>
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-400">WebSocket</span>
          <div className="flex items-center gap-1.5">
            <span className={`w-1.5 h-1.5 rounded-full ${wsConnected ? 'bg-green-500' : 'bg-red-500'}`} />
            <span className={`text-[10px] font-mono ${wsConnected ? 'text-green-500' : 'text-red-500'}`}>
              {wsConnected ? 'Connected' : 'Disconnected'}
            </span>
          </div>
        </div>
        {[
          { label: 'CPU', value: '23%', data: [20, 22, 25, 23, 21, 24, 23] },
          { label: 'Memory', value: '61%', data: [58, 59, 62, 60, 63, 61, 61] },
          { label: 'API Latency', value: '12ms', data: [14, 12, 13, 11, 12, 15, 12] },
        ].map((m) => (
          <div key={m.label} className="flex items-center justify-between gap-3">
            <span className="text-xs text-slate-400 w-16">{m.label}</span>
            <div className="flex-1 max-w-[60px]">
              <SparklineWidget data={m.data} color="cyan" height={16} strokeWidth={1.5} />
            </div>
            <span className="text-xs font-mono text-slate-300 w-10 text-right">{m.value}</span>
          </div>
        ))}
      </div>
    </div>
  </div>
);
