import React, { useState, useRef, useEffect } from 'react';
import { useMonitorSnapshot } from './hooks/useMonitorSnapshot';
import NOCWallTab from './NOCWallTab';
import LiveTopologyTab from './LiveTopologyTab';
import TrafficFlowsTab from './TrafficFlowsTab';
import AlertsTab from './AlertsTab';
import { MetricCard } from '../shared/MetricCard';

type Tab = 'topology' | 'noc' | 'flows' | 'alerts';

const ObservatoryView: React.FC = () => {
  const [activeTab, setActiveTab] = useState<Tab>('noc');
  const [bellOpen, setBellOpen] = useState(false);
  const bellRef = useRef<HTMLDivElement>(null);
  const { snapshot, loading, lastUpdated, refresh } = useMonitorSnapshot(30_000);

  const upCount = snapshot.devices.filter((d) => d.status === 'up').length;
  const totalCount = snapshot.devices.length;
  const driftCount = snapshot.drifts.length;
  const discoveryCount = snapshot.candidates.length;
  const alertCount = (snapshot.alerts || []).filter((a) => !a.acknowledged).length;

  // Golden Signals computation
  const activeDevices = snapshot.devices.filter(d => d.status !== 'down');
  const avgLatency = activeDevices.length > 0
    ? activeDevices.reduce((sum, d) => sum + d.latency_ms, 0) / activeDevices.length
    : 0;
  const avgPacketLoss = snapshot.devices.length > 0
    ? snapshot.devices.reduce((sum, d) => sum + d.packet_loss, 0) / snapshot.devices.length
    : 0;
  const avgUtilization = snapshot.links.length > 0
    ? snapshot.links.reduce((sum, l) => sum + l.utilization, 0) / snapshot.links.length
    : 0;

  const secondsAgo = lastUpdated
    ? Math.round((Date.now() - lastUpdated.getTime()) / 1000)
    : null;

  const tabs: { id: Tab; label: string }[] = [
    { id: 'topology', label: 'Live Topology' },
    { id: 'noc', label: 'Device Health' },
    { id: 'flows', label: 'Traffic Flows' },
    { id: 'alerts', label: 'Alerts' },
  ];

  // Close bell dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (bellRef.current && !bellRef.current.contains(e.target as Node)) {
        setBellOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

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
                className="px-4 py-1.5 rounded-md text-sm font-medium transition-colors relative"
                style={activeTab === tab.id
                  ? { backgroundColor: 'rgba(7,182,213,0.15)', color: '#07b6d5' }
                  : { color: '#64748b' }
                }
              >
                {tab.label}
                {tab.id === 'alerts' && alertCount > 0 && (
                  <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full text-[9px] font-bold flex items-center justify-center"
                    style={{ backgroundColor: '#ef4444', color: 'white' }}>
                    {alertCount > 9 ? '9+' : alertCount}
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Alert Bell */}
          <div className="relative" ref={bellRef}>
            <button
              onClick={() => setBellOpen(!bellOpen)}
              className="relative p-1.5 rounded transition-colors"
              style={{ color: alertCount > 0 ? '#f59e0b' : '#64748b' }}
            >
              <span className="material-symbols-outlined text-xl">notifications</span>
              {alertCount > 0 && (
                <span className="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full text-[9px] font-bold flex items-center justify-center"
                  style={{ backgroundColor: '#ef4444', color: 'white' }}>
                  {alertCount > 9 ? '9+' : alertCount}
                </span>
              )}
            </button>
            {bellOpen && (
              <div className="absolute right-0 top-full mt-2 w-80 rounded-lg border shadow-xl z-50 overflow-hidden"
                style={{ backgroundColor: '#0a1a1e', borderColor: '#224349' }}>
                <div className="px-3 py-2 border-b text-xs font-mono font-bold" style={{ borderColor: '#224349', color: '#07b6d5' }}>
                  Recent Alerts
                </div>
                {(snapshot.alerts || []).length === 0 ? (
                  <div className="px-3 py-4 text-xs font-mono text-center" style={{ color: '#64748b' }}>
                    No alerts
                  </div>
                ) : (
                  (snapshot.alerts || []).slice(0, 5).map((alert) => (
                    <div key={alert.key} className="px-3 py-2 border-b text-xs font-mono"
                      style={{
                        borderColor: '#224349',
                        opacity: alert.acknowledged ? 0.5 : 1,
                      }}>
                      <div className="flex items-center gap-2">
                        <span className="w-1.5 h-1.5 rounded-full inline-block"
                          style={{ backgroundColor: alert.severity === 'critical' ? '#ef4444' : alert.severity === 'warning' ? '#f59e0b' : '#07b6d5' }} />
                        <span style={{ color: '#e2e8f0' }}>{alert.rule_name}</span>
                      </div>
                      <div className="mt-0.5 pl-3.5" style={{ color: '#64748b' }}>
                        {alert.entity_id}: {alert.metric}={alert.value.toFixed(1)}
                      </div>
                    </div>
                  ))
                )}
                <button
                  onClick={() => { setActiveTab('alerts'); setBellOpen(false); }}
                  className="w-full px-3 py-2 text-xs font-mono text-center transition-colors"
                  style={{ color: '#07b6d5' }}
                >
                  View all alerts
                </button>
              </div>
            )}
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

      {/* Golden Signals Ribbon */}
      {!loading && (
        <div className="grid grid-cols-4 gap-4 px-6 py-4">
          <MetricCard
            title="AVG LATENCY"
            value={`${avgLatency.toFixed(1)}ms`}
            trendValue={avgLatency < 50 ? 'Normal' : avgLatency < 100 ? 'Elevated' : 'High'}
            trendDirection={avgLatency < 50 ? 'down' : 'up'}
            trendType={avgLatency < 50 ? 'good' : avgLatency < 100 ? 'neutral' : 'bad'}
            sparklineData={activeDevices.map(d => d.latency_ms)}
          />
          <MetricCard
            title="PACKET LOSS"
            value={`${(avgPacketLoss * 100).toFixed(1)}%`}
            trendValue={avgPacketLoss === 0 ? '0% loss' : `${(avgPacketLoss * 100).toFixed(1)}%`}
            trendDirection={avgPacketLoss === 0 ? 'down' : 'up'}
            trendType={avgPacketLoss < 0.01 ? 'good' : avgPacketLoss < 0.05 ? 'neutral' : 'bad'}
            sparklineData={snapshot.devices.map(d => d.packet_loss * 100)}
          />
          <MetricCard
            title="LINK UTILIZATION"
            value={`${(avgUtilization * 100).toFixed(0)}%`}
            trendValue={avgUtilization < 0.5 ? 'Healthy' : avgUtilization < 0.8 ? 'Moderate' : 'Saturated'}
            trendDirection={avgUtilization < 0.5 ? 'down' : 'up'}
            trendType={avgUtilization < 0.5 ? 'good' : avgUtilization < 0.8 ? 'neutral' : 'bad'}
            sparklineData={snapshot.links.map(l => l.utilization * 100)}
          />
          <MetricCard
            title="ACTIVE ALERTS"
            value={alertCount}
            trendValue={alertCount === 0 ? 'Clear' : `${alertCount} active`}
            trendDirection={alertCount === 0 ? 'down' : 'up'}
            trendType={alertCount === 0 ? 'good' : alertCount > 5 ? 'bad' : 'neutral'}
            sparklineData={[alertCount, alertCount]}
          />
        </div>
      )}

      {/* Tab content */}
      <div className="flex-1 overflow-auto">
        {loading ? (
          <div className="flex items-center justify-center h-40 text-slate-500 text-sm">Loading observatory data...</div>
        ) : activeTab === 'topology' ? (
          <LiveTopologyTab
            devices={snapshot.devices}
            links={snapshot.links}
            drifts={snapshot.drifts}
            candidates={snapshot.candidates}
          />
        ) : activeTab === 'noc' ? (
          <NOCWallTab
            devices={snapshot.devices}
            drifts={snapshot.drifts}
            onSelectDevice={() => { setActiveTab('topology'); }}
          />
        ) : activeTab === 'alerts' ? (
          <AlertsTab alerts={snapshot.alerts || []} onRefresh={refresh} />
        ) : (
          <TrafficFlowsTab links={snapshot.links} />
        )}
      </div>
    </div>
  );
};

export default ObservatoryView;
