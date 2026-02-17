import React from 'react';
import type { CapabilityType } from '../../types';

interface CapabilityLauncherProps {
  onSelectCapability: (capability: CapabilityType) => void;
}

const capabilities: {
  type: CapabilityType;
  title: string;
  description: string;
  icon: string;
  iconColor: string;
  iconBg: string;
  iconBorder: string;
  ctaText: string;
  ctaColor: string;
  hasGlow?: boolean;
}[] = [
  {
    type: 'troubleshoot_app',
    title: 'Troubleshoot',
    description: 'Scan logs and metrics for anomalies across microservices.',
    icon: 'troubleshoot',
    iconColor: '#07b6d5',
    iconBg: 'rgba(7,182,213,0.1)',
    iconBorder: 'rgba(7,182,213,0.2)',
    ctaText: 'Initialize Scan',
    ctaColor: '#07b6d5',
    hasGlow: true,
  },
  {
    type: 'pr_review',
    title: 'PR Review',
    description: 'Automated code quality & security audit for active pull requests.',
    icon: 'rate_review',
    iconColor: '#818cf8',
    iconBg: 'rgba(99,102,241,0.1)',
    iconBorder: 'rgba(99,102,241,0.2)',
    ctaText: 'Start Audit',
    ctaColor: '#818cf8',
  },
  {
    type: 'github_issue_fix',
    title: 'Issue Fixer',
    description: 'Generate and apply automated patches to known vulnerabilities.',
    icon: 'auto_fix_high',
    iconColor: '#fbbf24',
    iconBg: 'rgba(245,158,11,0.1)',
    iconBorder: 'rgba(245,158,11,0.2)',
    ctaText: 'Generate Patch',
    ctaColor: '#fbbf24',
  },
  {
    type: 'cluster_diagnostics',
    title: 'Cluster Diag',
    description: 'Full-stack health check of Kubernetes cluster and node status.',
    icon: 'hub',
    iconColor: '#34d399',
    iconBg: 'rgba(16,185,129,0.1)',
    iconBorder: 'rgba(16,185,129,0.2)',
    ctaText: 'Run Diagnostics',
    ctaColor: '#34d399',
  },
];

const CapabilityLauncher: React.FC<CapabilityLauncherProps> = ({ onSelectCapability }) => {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {capabilities.map((cap) => (
        <button
          key={cap.type}
          onClick={() => onSelectCapability(cap.type)}
          className="group relative rounded-xl p-5 transition-all hover:-translate-y-1 hover:shadow-2xl cursor-pointer overflow-hidden text-left border"
          style={{
            backgroundColor: 'rgba(30,47,51,0.2)',
            borderColor: '#224349',
          }}
        >
          {/* Glow effect for first card */}
          {cap.hasGlow && (
            <div className="absolute -right-4 -top-4 w-24 h-24 rounded-full blur-2xl transition-colors" style={{ backgroundColor: 'rgba(7,182,213,0.05)' }} />
          )}

          {/* Icon */}
          <div
            className="w-10 h-10 rounded-lg flex items-center justify-center mb-4 border"
            style={{ backgroundColor: cap.iconBg, borderColor: cap.iconBorder }}
          >
            <span className="material-symbols-outlined" style={{ fontFamily: 'Material Symbols Outlined', color: cap.iconColor }}>{cap.icon}</span>
          </div>

          {/* Title & Description */}
          <h3 className="text-white font-bold mb-1">{cap.title}</h3>
          <p className="text-xs text-slate-400 leading-relaxed">{cap.description}</p>

          {/* CTA - appears on hover */}
          <div
            className="mt-4 flex items-center text-[10px] font-bold opacity-0 group-hover:opacity-100 transition-opacity uppercase tracking-widest"
            style={{ color: cap.ctaColor }}
          >
            {cap.ctaText}
            <span className="material-symbols-outlined text-xs ml-1" style={{ fontFamily: 'Material Symbols Outlined' }}>arrow_forward</span>
          </div>
        </button>
      ))}
    </div>
  );
};

export default CapabilityLauncher;
