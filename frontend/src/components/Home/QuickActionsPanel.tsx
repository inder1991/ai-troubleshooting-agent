import React from 'react';
import type { CapabilityType } from '../../types';
import { Badge, type BadgeType } from '../ui/Badge';

interface QuickActionsPanelProps {
  onSelectCapability: (capability: CapabilityType) => void;
}

const actions: { label: string; capability: CapabilityType; icon: string; badge?: BadgeType }[] = [
  { label: 'New Investigation', capability: 'troubleshoot_app', icon: 'troubleshoot' },
  { label: 'Network Scan', capability: 'network_troubleshooting', icon: 'lan', badge: 'NEW' },
  { label: 'Cluster Check', capability: 'cluster_diagnostics', icon: 'deployed_code', badge: 'PREVIEW' },
  { label: 'PR Review', capability: 'pr_review', icon: 'code', badge: 'NEW' },
];

export const QuickActionsPanel: React.FC<QuickActionsPanelProps> = ({ onSelectCapability }) => (
  <div className="bg-duck-panel border border-duck-border rounded-lg p-4 h-full flex flex-col">
    <h3 className="text-xs font-bold text-duck-muted font-display mb-3 shrink-0">
      Quick Actions
    </h3>

    <div className="flex flex-col gap-1.5 overflow-y-auto custom-scrollbar pr-1">
      {actions.map((a) => (
        <button
          key={a.capability}
          onClick={() => onSelectCapability(a.capability)}
          className="flex items-center justify-between px-3 py-2.5 bg-duck-surface border border-duck-border rounded hover:border-duck-accent transition-all duration-200 group focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent shrink-0"
        >
          <div className="flex items-center gap-3">
            <span className="material-symbols-outlined text-[18px] text-duck-muted group-hover:text-duck-accent transition-colors" aria-hidden="true">
              {a.icon}
            </span>
            <span className="text-sm font-medium text-slate-300 group-hover:text-white transition-colors">{a.label}</span>
          </div>
          {a.badge && <Badge type={a.badge} />}
        </button>
      ))}
    </div>
  </div>
);
