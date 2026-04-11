import React from 'react';

export type WorkflowTab = 'app_diagnostics' | 'cluster_diagnostics' | 'database_diagnostics' | 'assistant';

interface WorkflowTabsProps {
  activeTab: WorkflowTab;
  onTabChange: (tab: WorkflowTab) => void;
  appCount: number;
  clusterCount: number;
  dbCount: number;
  assistantCount: number;
  degradedByWorkflow?: Record<string, number>;
}

const WorkflowTabs: React.FC<WorkflowTabsProps> = ({ activeTab, onTabChange, appCount, clusterCount, dbCount, assistantCount, degradedByWorkflow }) => {
  const tabs: { id: WorkflowTab; label: string; icon: string; count: number }[] = [
    { id: 'app_diagnostics', label: 'App Diagnostics', icon: 'bug_report', count: appCount },
    { id: 'cluster_diagnostics', label: 'Cluster Diagnostics', icon: 'cloud_circle', count: clusterCount },
    { id: 'database_diagnostics', label: 'Database', icon: 'database', count: dbCount },
    { id: 'assistant', label: 'Assistant', icon: 'smart_toy', count: assistantCount },
  ];

  return (
    <div className="flex items-center gap-2 px-8 py-3">
      {tabs.map((tab) => {
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium border"
            style={{
              backgroundColor: isActive ? 'rgba(224,159,62,0.15)' : 'transparent',
              borderColor: isActive ? 'rgba(224,159,62,0.4)' : '#3d3528',
              color: isActive ? '#e09f3e' : '#8a7e6b',
              transition: 'background-color 200ms cubic-bezier(0.25, 1, 0.5, 1), border-color 200ms cubic-bezier(0.25, 1, 0.5, 1), color 200ms cubic-bezier(0.25, 1, 0.5, 1)',
            }}
          >
            <span className="material-symbols-outlined text-base">{tab.icon}</span>
            <span>{tab.label}</span>
            <span
              className="text-body-xs font-mono px-1.5 py-0.5 rounded"
              style={{
                backgroundColor: isActive ? 'rgba(224,159,62,0.2)' : 'rgba(100,116,139,0.2)',
                color: isActive ? '#e09f3e' : '#64748b',
              }}
            >
              {tab.count}
            </span>
            {(degradedByWorkflow?.[tab.id] ?? 0) > 0 && (
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500" title={`${degradedByWorkflow![tab.id]} degraded`} />
            )}
          </button>
        );
      })}
    </div>
  );
};

export default WorkflowTabs;
