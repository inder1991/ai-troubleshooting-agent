import React from 'react';

export type WorkflowTab = 'app_diagnostics' | 'cluster_diagnostics';

interface WorkflowTabsProps {
  activeTab: WorkflowTab;
  onTabChange: (tab: WorkflowTab) => void;
  appCount: number;
  clusterCount: number;
}

const WorkflowTabs: React.FC<WorkflowTabsProps> = ({ activeTab, onTabChange, appCount, clusterCount }) => {
  const tabs: { id: WorkflowTab; label: string; icon: string; count: number }[] = [
    { id: 'app_diagnostics', label: 'App Diagnostics', icon: 'bug_report', count: appCount },
    { id: 'cluster_diagnostics', label: 'Cluster Diagnostics', icon: 'cloud_circle', count: clusterCount },
  ];

  return (
    <div className="flex items-center gap-2 px-8 py-3">
      {tabs.map((tab) => {
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all border"
            style={{
              backgroundColor: isActive ? 'rgba(224,159,62,0.15)' : 'transparent',
              borderColor: isActive ? 'rgba(224,159,62,0.4)' : '#3d3528',
              color: isActive ? '#e09f3e' : '#8a7e6b',
            }}
          >
            <span className="material-symbols-outlined text-base">{tab.icon}</span>
            <span>{tab.label}</span>
            <span
              className="text-[10px] font-mono px-1.5 py-0.5 rounded"
              style={{
                backgroundColor: isActive ? 'rgba(224,159,62,0.2)' : 'rgba(100,116,139,0.2)',
                color: isActive ? '#e09f3e' : '#64748b',
              }}
            >
              {tab.count}
            </span>
          </button>
        );
      })}
    </div>
  );
};

export default WorkflowTabs;
