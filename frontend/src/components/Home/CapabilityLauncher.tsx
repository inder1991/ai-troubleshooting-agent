import React from 'react';
import type { CapabilityType } from '../../types';
import { Badge, type BadgeType } from '../ui/Badge';

interface CapabilityLauncherProps {
  onSelectCapability: (capability: CapabilityType) => void;
}

const capabilities: {
  type: CapabilityType;
  title: string;
  description: string;
  icon: string;
  iconClasses: string;
  ctaText: string;
  ctaClasses: string;
  hasGlow?: boolean;
  badge?: BadgeType;
}[] = [
  {
    type: 'troubleshoot_app',
    title: 'Troubleshoot',
    description: 'Scan logs and metrics for anomalies across microservices.',
    icon: 'troubleshoot',
    iconClasses: 'text-duck-accent bg-duck-accent/10 border-duck-accent/20',
    ctaText: 'Initialize Scan',
    ctaClasses: 'text-duck-accent',
    hasGlow: true,
  },
  {
    type: 'pr_review',
    title: 'PR Review',
    description: 'Automated code quality & security audit for active pull requests.',
    icon: 'rate_review',
    iconClasses: 'text-indigo-400 bg-indigo-500/10 border-indigo-500/20',
    ctaText: 'Start Audit',
    ctaClasses: 'text-indigo-400',
  },
  {
    type: 'github_issue_fix',
    title: 'Issue Fixer',
    description: 'Generate and apply automated patches to known vulnerabilities.',
    icon: 'auto_fix_high',
    iconClasses: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
    ctaText: 'Generate Patch',
    ctaClasses: 'text-amber-400',
  },
  {
    type: 'cluster_diagnostics',
    title: 'Cluster Diag',
    description: 'Full-stack health check of Kubernetes cluster and node status.',
    icon: 'hub',
    iconClasses: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
    ctaText: 'Run Diagnostics',
    ctaClasses: 'text-emerald-400',
    badge: 'PREVIEW',
  },
  {
    type: 'network_troubleshooting' as CapabilityType,
    title: 'Network Path',
    description: 'Trace network paths across firewalls, NAT chains, and routing hops to diagnose connectivity issues',
    icon: 'route',
    iconClasses: 'text-amber-500 bg-amber-500/[0.08] border-amber-500/20',
    ctaText: 'Trace Path',
    ctaClasses: 'text-amber-500',
    badge: 'NEW',
  },
  {
    type: 'database_diagnostics',
    title: 'DB Diagnostics',
    description: 'AI-powered PostgreSQL investigation with query analysis and performance tuning.',
    icon: 'database',
    iconClasses: 'text-violet-400 bg-violet-500/10 border-violet-500/20',
    ctaText: 'Investigate DB',
    ctaClasses: 'text-violet-400',
    badge: 'NEW',
  },
];

const CapabilityLauncher: React.FC<CapabilityLauncherProps> = ({ onSelectCapability }) => {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
      {capabilities.map((cap) => (
        <button
          key={cap.type}
          onClick={() => onSelectCapability(cap.type)}
          className="group relative rounded-xl p-5 transition-all duration-200 ease-in-out hover:-translate-y-1 hover:shadow-2xl cursor-pointer overflow-hidden text-left border bg-duck-card/20 border-duck-border focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent"
        >
          {/* Glow effect for first card */}
          {cap.hasGlow && (
            <div className="absolute -right-4 -top-4 w-24 h-24 rounded-full blur-2xl transition-colors bg-duck-accent/5" />
          )}

          {/* Icon */}
          <div
            className={`w-10 h-10 rounded-lg flex items-center justify-center mb-4 border ${cap.iconClasses}`}
          >
            <span className="material-symbols-outlined" aria-hidden="true">{cap.icon}</span>
          </div>

          {/* Title & Description */}
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-white font-bold">{cap.title}</h3>
            {cap.badge && <Badge type={cap.badge} />}
          </div>
          <p className="text-xs text-slate-400 leading-relaxed">{cap.description}</p>

          {/* CTA - appears on hover */}
          <div
            className={`mt-4 flex items-center text-micro font-bold opacity-0 group-hover:opacity-100 transition-opacity uppercase tracking-widest ${cap.ctaClasses}`}
          >
            {cap.ctaText}
            <span className="material-symbols-outlined text-xs ml-1" aria-hidden="true">arrow_forward</span>
          </div>
        </button>
      ))}
    </div>
  );
};

export default CapabilityLauncher;
