import React, { useState } from 'react';

type TabId = 'chat' | 'dashboard' | 'activity';

interface TabLayoutProps {
  chatContent: React.ReactNode;
  dashboardContent: React.ReactNode;
  activityContent: React.ReactNode;
}

const tabs: { id: TabId; label: string }[] = [
  { id: 'chat', label: 'Chat' },
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'activity', label: 'Activity Log' },
];

const TabLayout: React.FC<TabLayoutProps> = ({
  chatContent,
  dashboardContent,
  activityContent,
}) => {
  const [activeTab, setActiveTab] = useState<TabId>('chat');

  const contentMap: Record<TabId, React.ReactNode> = {
    chat: chatContent,
    dashboard: dashboardContent,
    activity: activityContent,
  };

  return (
    <div className="flex flex-col h-full">
      {/* Tab bar */}
      <div className="flex border-b border-gray-700 bg-gray-900">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-6 py-3 text-sm font-medium transition-colors relative ${
              activeTab === tab.id
                ? 'text-blue-400'
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            {tab.label}
            {activeTab === tab.id && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-blue-500" />
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-hidden">
        {contentMap[activeTab]}
      </div>
    </div>
  );
};

export default TabLayout;
