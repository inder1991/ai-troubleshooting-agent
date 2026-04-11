import React from 'react';
import type { CapabilityType } from '../../types';

interface HeroCapabilitiesProps {
  onSelectCapability: (capability: CapabilityType) => void;
}

const caps: { type: CapabilityType; label: string; verb: string; icon: string; accent: string }[] = [
  { type: 'troubleshoot_app', label: 'Application', verb: 'Diagnose logs, metrics & traces', icon: 'troubleshoot', accent: 'border-duck-accent/40 hover:border-duck-accent text-duck-accent' },
  { type: 'database_diagnostics', label: 'Database', verb: 'Scan queries, health & schema', icon: 'database', accent: 'border-violet-400/40 hover:border-violet-400 text-violet-400' },
  { type: 'network_troubleshooting', label: 'Network', verb: 'Trace path & firewall rules', icon: 'route', accent: 'border-amber-400/40 hover:border-amber-400 text-amber-400' },
  { type: 'cluster_diagnostics', label: 'Cluster', verb: 'Check K8s nodes & pods', icon: 'deployed_code', accent: 'border-emerald-400/40 hover:border-emerald-400 text-emerald-400' },
  { type: 'pr_review', label: 'PR Review', verb: 'Audit code quality & security', icon: 'rate_review', accent: 'border-blue-400/40 hover:border-blue-400 text-blue-400' },
  { type: 'github_issue_fix', label: 'Issue Fix', verb: 'Auto-generate patches', icon: 'auto_fix_high', accent: 'border-pink-400/40 hover:border-pink-400 text-pink-400' },
];

const HeroCapabilities: React.FC<HeroCapabilitiesProps> = ({ onSelectCapability }) => (
  <div className="px-6 py-3 border-b border-duck-border/30">
    <div className="flex items-center gap-2 mb-2">
      <span className="material-symbols-outlined text-duck-accent text-[16px]" aria-hidden="true">rocket_launch</span>
      <span className="text-xs font-display font-bold text-white">Start Investigation</span>
    </div>
    <div className="grid grid-cols-3 lg:grid-cols-6 gap-2">
      {caps.map((cap, index) => (
        <button
          key={cap.type}
          onClick={() => onSelectCapability(cap.type)}
          className={`flex flex-col items-start px-3 py-2.5 rounded-lg bg-duck-card/30 border group focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent ${cap.accent}`}
          style={{
            transition: 'transform 200ms cubic-bezier(0.25, 1, 0.5, 1), box-shadow 200ms cubic-bezier(0.25, 1, 0.5, 1), border-color 200ms cubic-bezier(0.25, 1, 0.5, 1), background-color 200ms cubic-bezier(0.25, 1, 0.5, 1)',
            animation: `fadeSlideUp 300ms cubic-bezier(0.25, 1, 0.5, 1) ${index * 40}ms both`,
          }}
          onMouseEnter={e => {
            e.currentTarget.style.transform = 'translateY(-2px)';
            e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.3)';
          }}
          onMouseLeave={e => {
            e.currentTarget.style.transform = 'translateY(0)';
            e.currentTarget.style.boxShadow = 'none';
          }}
          onMouseDown={e => { e.currentTarget.style.transform = 'scale(0.97)'; }}
          onMouseUp={e => { e.currentTarget.style.transform = 'translateY(-2px)'; }}
        >
          <div className="flex items-center gap-2 mb-1">
            <span className="material-symbols-outlined text-[18px] opacity-70 group-hover:opacity-100 transition-opacity" aria-hidden="true">{cap.icon}</span>
            <span className="text-sm font-display font-bold text-white">{cap.label}</span>
          </div>
          <span className="text-body-xs text-slate-400 group-hover:text-slate-300 transition-colors leading-tight">{cap.verb}</span>
        </button>
      ))}
    </div>
  </div>
);

export default HeroCapabilities;
