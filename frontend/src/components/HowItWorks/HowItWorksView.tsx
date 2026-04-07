import React, { useState } from 'react';
import WorkflowAnimation from './WorkflowAnimation';
import { clusterConfig, appConfig, WF_COLORS } from './workflowConfigs';

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
    <div className="flex flex-col h-full" style={{ backgroundColor: WF_COLORS.pageBg, color: WF_COLORS.labelText }}>
      {/* Header */}
      <header
        className="h-14 flex items-center justify-between px-6 shrink-0 border-b"
        style={{ backgroundColor: WF_COLORS.panelBg, borderColor: WF_COLORS.border }}
      >
        <div className="flex items-center gap-4">
          <button
            onClick={onGoHome}
            className="hover:opacity-80 transition-opacity"
            style={{ color: WF_COLORS.mutedText }}
            aria-label="Back to home"
          >
            <span className="material-symbols-outlined">arrow_back</span>
          </button>
          <h1
            className="text-xl font-bold text-white"
            style={{ fontFamily: 'DM Sans, Inter, system-ui, sans-serif' }}
          >
            How It Works
          </h1>
        </div>

        {/* Tabs */}
        <div
          className="flex gap-1 rounded-lg p-1 border"
          style={{ backgroundColor: WF_COLORS.pageBg, borderColor: WF_COLORS.border }}
        >
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className="flex items-center gap-2 px-4 py-1.5 rounded-md text-xs font-bold transition-all"
              style={activeTab === tab.id
                ? { backgroundColor: `${WF_COLORS.amber}15`, color: WF_COLORS.amber, border: `1px solid ${WF_COLORS.amber}4d` }
                : { color: WF_COLORS.mutedText, border: '1px solid transparent' }
              }
            >
              <span className="material-symbols-outlined text-sm">{tab.icon}</span>
              {tab.label}
            </button>
          ))}
        </div>

        <div className="w-24" />
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
