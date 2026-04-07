import React, { useState } from 'react';
import WorkflowAnimation from './WorkflowAnimation';
import { clusterConfig, appConfig } from './workflowConfigs';

interface HowItWorksViewProps {
  onGoHome: () => void;
}

type Tab = 'cluster' | 'app';

const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: 'cluster', label: 'Cluster Diagnostics', icon: 'deployed_code' },
  { id: 'app',     label: 'App Diagnostics',     icon: 'bug_report' },
];

const HowItWorksView: React.FC<HowItWorksViewProps> = ({ onGoHome }) => {
  const [activeTab, setActiveTab] = useState<Tab>('cluster');

  return (
    <div className="flex flex-col h-full bg-[#0f2023] text-slate-300">
      {/* Header */}
      <header className="h-14 border-b border-slate-800 bg-[#0a1a1f] flex items-center justify-between px-6 shrink-0">
        <div className="flex items-center gap-4">
          <button
            onClick={onGoHome}
            className="text-slate-400 hover:text-white transition-colors"
            aria-label="Back to home"
          >
            <span className="material-symbols-outlined">arrow_back</span>
          </button>
          <h1 className="text-xl font-bold text-white">
            How It <span className="text-[#07b6d5]">Works</span>
          </h1>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 bg-[#0f2023] rounded-lg p-1 border border-slate-800">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-1.5 rounded-md text-xs font-bold transition-all ${
                activeTab === tab.id
                  ? 'bg-[#07b6d5]/10 text-[#07b6d5] border border-[#07b6d5]/30'
                  : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              <span className="material-symbols-outlined text-sm">{tab.icon}</span>
              {tab.label}
            </button>
          ))}
        </div>

        <div className="w-24" /> {/* Spacer for balance */}
      </header>

      {/* Animation canvas */}
      <div className="flex-1 overflow-hidden">
        {activeTab === 'cluster' && <WorkflowAnimation key="cluster" config={clusterConfig} />}
        {activeTab === 'app' && <WorkflowAnimation key="app" config={appConfig} />}
      </div>
    </div>
  );
};

export default HowItWorksView;
