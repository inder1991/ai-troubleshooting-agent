import React from 'react';

interface ClusterInfoBannerProps {
  platform: string;
  platformVersion: string;
  namespaceCount: number;
  scanMode: 'diagnostic' | 'guard';
}

export default function ClusterInfoBanner({ platform, platformVersion, namespaceCount, scanMode }: ClusterInfoBannerProps) {
  return (
    <div className="bg-slate-900/60 border border-slate-700/40 rounded-lg p-3 mb-3">
      <div className="flex items-center gap-2 mb-2">
        <span className="material-symbols-outlined text-cyan-400 text-lg">deployed_code_account</span>
        <span className="text-sm font-semibold text-slate-200">
          {platform === 'openshift' ? 'OpenShift' : 'Kubernetes'} {platformVersion}
        </span>
        <span className={`ml-auto px-2 py-0.5 text-[9px] font-mono uppercase tracking-wider rounded-full border ${
          scanMode === 'guard'
            ? 'text-amber-400 border-amber-500/40 bg-amber-500/10'
            : 'text-cyan-400 border-cyan-500/40 bg-cyan-500/10'
        }`}>
          {scanMode}
        </span>
      </div>
      <div className="flex items-center gap-3 text-xs text-slate-400">
        <span>{namespaceCount} namespaces</span>
      </div>
    </div>
  );
}
