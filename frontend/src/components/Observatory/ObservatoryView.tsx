import React, { useState } from 'react';
import { useMonitorSnapshot } from './hooks/useMonitorSnapshot';
import NOCWallTab from './NOCWallTab';

type Tab = 'topology' | 'noc' | 'flows';

const ObservatoryView: React.FC = () => {
  const [activeTab, setActiveTab] = useState<Tab>('noc');
  const { snapshot, loading, lastUpdated } = useMonitorSnapshot(30_000);

  const upCount = snapshot.devices.filter((d) => d.status === 'up').length;
  const totalCount = snapshot.devices.length;
  const driftCount = snapshot.drifts.length;
  const discoveryCount = snapshot.candidates.length;

  const secondsAgo = lastUpdated
    ? Math.round((Date.now() - lastUpdated.getTime()) / 1000)
    : null;

  const tabs: { id: Tab; label: string }[] = [
    { id: 'topology', label: 'Live Topology' },
    { id: 'noc', label: 'NOC Wall' },
    { id: 'flows', label: 'Traffic Flows' },
  ];

  return (
    <div className="flex-1 flex flex-col overflow-hidden" style={{ backgroundColor: '#0f2023' }}>
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b" style={{ borderColor: '#224349' }}>
        <div className="flex items-center gap-3">
          <span className="material-symbols-outlined text-2xl" style={{ color: '#07b6d5' }}>
            monitoring
          </span>
          <h1 className="text-xl font-bold text-white">Network Observatory</h1>
        </div>
        <div className="flex items-center gap-4">
          {/* Tabs */}
          <div className="flex gap-1 rounded-lg p-0.5" style={{ backgroundColor: '#0a1a1e' }}>
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className="px-4 py-1.5 rounded-md text-sm font-medium transition-colors"
                style={activeTab === tab.id
                  ? { backgroundColor: 'rgba(7,182,213,0.15)', color: '#07b6d5' }
                  : { color: '#64748b' }
                }
              >
                {tab.label}
              </button>
            ))}
          </div>
          {/* Status badges */}
          <div className="flex items-center gap-3 text-xs font-mono">
            {secondsAgo !== null && (
              <span style={{ color: '#64748b' }}>Updated {secondsAgo}s ago</span>
            )}
            <span style={{ color: upCount === totalCount && totalCount > 0 ? '#22c55e' : '#f59e0b' }}>
              {upCount}/{totalCount} UP
            </span>
            {driftCount > 0 && (
              <span style={{ color: '#f59e0b' }}>{driftCount} drift</span>
            )}
            {discoveryCount > 0 && (
              <span style={{ color: '#07b6d5' }}>{discoveryCount} discovered</span>
            )}
          </div>
        </div>
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-auto">
        {loading ? (
          <div className="flex items-center justify-center h-40 text-slate-500 text-sm">Loading observatory data...</div>
        ) : activeTab === 'topology' ? (
          <div className="p-6 text-slate-500 text-sm">Live Topology — coming soon</div>
        ) : activeTab === 'noc' ? (
          <NOCWallTab
            devices={snapshot.devices}
            drifts={snapshot.drifts}
            onSelectDevice={() => { setActiveTab('topology'); }}
          />
        ) : (
          <div className="p-6 text-slate-500 text-sm">Traffic Flows — coming soon</div>
        )}
      </div>
    </div>
  );
};

export default ObservatoryView;
