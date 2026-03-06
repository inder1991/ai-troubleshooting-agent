import React from 'react';
import { SparklineWidget } from '../shared';
import type { CapabilityType } from '../../types';

interface QuickActionsPanelProps {
  onSelectCapability: (capability: CapabilityType) => void;
  wsConnected: boolean;
}

const actions: { label: string; capability: CapabilityType; icon: string }[] = [
  { label: 'New Investigation', capability: 'troubleshoot_app', icon: 'troubleshoot' },
  { label: 'Network Scan', capability: 'network_troubleshooting', icon: 'lan' },
  { label: 'Cluster Check', capability: 'cluster_diagnostics', icon: 'deployed_code' },
  { label: 'PR Review', capability: 'pr_review', icon: 'code' },
];

export const QuickActionsPanel: React.FC<QuickActionsPanelProps> = ({ onSelectCapability, wsConnected }) => (
  <div className="flex flex-col gap-4">
    <div className="bg-[#0a1517] border border-[#224349] rounded-lg p-4">
      <h3 className="text-xs font-bold text-[#94a3b8] uppercase tracking-wider mb-3">Quick Actions</h3>
      <div className="flex flex-col gap-1.5">
        {actions.map((a) => (
          <button
            key={a.capability}
            onClick={() => onSelectCapability(a.capability)}
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-300 hover:text-white hover:bg-[#162a2e] transition-colors text-left group"
          >
            <span className="material-symbols-outlined text-[18px] text-[#07b6d5] group-hover:text-white transition-colors" style={{ fontFamily: 'Material Symbols Outlined' }}>
              {a.icon}
            </span>
            <span className="text-sm font-medium">{a.label}</span>
            <span className="material-symbols-outlined text-[14px] text-slate-600 ml-auto opacity-0 group-hover:opacity-100 transition-opacity" style={{ fontFamily: 'Material Symbols Outlined' }}>
              arrow_forward
            </span>
          </button>
        ))}
      </div>
    </div>

    <div className="bg-[#0a1517] border border-[#224349] rounded-lg p-4">
      <h3 className="text-xs font-bold text-[#94a3b8] uppercase tracking-wider mb-3">System Health</h3>
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
