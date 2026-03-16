import React, { useState, useRef, useEffect } from 'react';
import { useMonitorSnapshot } from './hooks/useMonitorSnapshot';
import NOCWallTab from './NOCWallTab';
import LiveTopologyTab from './LiveTopologyTab';
import LiveTopologyView from './topology/LiveTopologyViewV2';
import TrafficFlowsTab from './TrafficFlowsTab';
import AlertsTab from './AlertsTab';
import AlertHistoryTab from './AlertHistoryTab';
import DNSMonitoringTab from './DNSMonitoringTab';
import { MetricCard } from '../shared/MetricCard';
import { StatusBadge } from '../shared/StatusBadge';
import { SkeletonLoader } from '../shared/SkeletonLoader';
import NetworkChatDrawer from '../NetworkChat/NetworkChatDrawer';

type Tab = 'topology' | 'noc' | 'flows' | 'alerts' | 'history' | 'dns';

interface ObservatoryViewProps {
  onOpenEditor?: () => void;
  onOpenTopology?: () => void;
}

const ObservatoryView: React.FC<ObservatoryViewProps> = ({ onOpenEditor, onOpenTopology }) => {
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

  // Live-ticking "Updated Xs ago" counter
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const secondsAgo = lastUpdated
    ? Math.round((now - lastUpdated.getTime()) / 1000)
    : null;

  const tabs: { id: Tab; label: string }[] = [
    { id: 'topology', label: 'Live Topology' },
    { id: 'noc', label: 'Device Health' },
    { id: 'flows', label: 'Traffic Flows' },
    { id: 'alerts', label: 'Alerts' },
    { id: 'history', label: 'Alert History' },
    { id: 'dns', label: 'DNS' },
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
    <div className="flex-1 flex flex-col overflow-hidden" style={{ backgroundColor: '#1a1814' }}>
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b" style={{ borderColor: '#3d3528' }}>
        <div className="flex items-center gap-3">
          <span className="material-symbols-outlined text-2xl" style={{ color: '#e09f3e' }}>
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
                  ? { backgroundColor: 'rgba(224,159,62,0.15)', color: '#e09f3e' }
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
                style={{ backgroundColor: '#0a1a1e', borderColor: '#3d3528' }}>
                <div className="px-3 py-2 border-b text-xs font-mono font-bold" style={{ borderColor: '#3d3528', color: '#e09f3e' }}>
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
                        borderColor: '#3d3528',
                        opacity: alert.acknowledged ? 0.5 : 1,
                      }}>
                      <div className="flex items-center gap-2">
                        <span className="w-1.5 h-1.5 rounded-full inline-block"
                          style={{ backgroundColor: alert.severity === 'critical' ? '#ef4444' : alert.severity === 'warning' ? '#f59e0b' : '#e09f3e' }} />
                        <span style={{ color: '#e8e0d4' }}>{alert.rule_name}</span>
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
                  style={{ color: '#e09f3e' }}
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
            <StatusBadge
              status={upCount === totalCount && totalCount > 0 ? 'healthy' : 'degraded'}
              label={`${upCount}/${totalCount} UP`}
              pulse={upCount < totalCount}
            />
            {driftCount > 0 && (
              <StatusBadge status="degraded" label="Drift" count={driftCount} />
            )}
            {discoveryCount > 0 && (
              <StatusBadge status="in_progress" label="Discovered" count={discoveryCount} />
            )}
          </div>
        </div>
      </div>

      {/* Golden Signals Ribbon */}
      {loading && (
        <div className="grid grid-cols-4 gap-4 px-6 py-4">
          {[1, 2, 3, 4].map(i => (
            <SkeletonLoader key={i} type="card" />
          ))}
        </div>
      )}
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
          <div className="p-6">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
              {[1, 2, 3, 4, 5, 6, 7, 8].map(i => (
                <SkeletonLoader key={i} type="card" />
              ))}
            </div>
          </div>
        ) : activeTab === 'topology' ? (
          <div className="flex flex-col items-center justify-center h-full gap-4 p-8">
            <span className="material-symbols-outlined" style={{ fontSize: 48, color: '#e09f3e' }}>device_hub</span>
            <h2 style={{ color: 'white', fontSize: 18, fontWeight: 600 }}>Live Network Topology</h2>
            <p style={{ color: '#8a7e6b', fontSize: 13, textAlign: 'center', maxWidth: 400 }}>
              View your full network diagram with hierarchical layout, device health status, and link monitoring.
            </p>
            <button
              onClick={() => onOpenTopology?.()}
              style={{
                background: 'rgba(224,159,62,0.15)',
                border: '1px solid rgba(224,159,62,0.4)',
                color: '#e09f3e',
                borderRadius: 8,
                padding: '10px 24px',
                fontSize: 13,
                fontWeight: 600,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                transition: 'background 200ms',
              }}
              onMouseEnter={e => { e.currentTarget.style.background = 'rgba(224,159,62,0.25)'; }}
              onMouseLeave={e => { e.currentTarget.style.background = 'rgba(224,159,62,0.15)'; }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 18 }}>open_in_full</span>
              Open Full Screen
            </button>
          </div>
        ) : activeTab === 'noc' ? (
          <NOCWallTab
            devices={snapshot.devices}
            drifts={snapshot.drifts}
            onSelectDevice={() => { setActiveTab('topology'); }}
          />
        ) : activeTab === 'alerts' ? (
          <AlertsTab alerts={snapshot.alerts || []} onRefresh={refresh} />
        ) : activeTab === 'history' ? (
          <AlertHistoryTab />
        ) : activeTab === 'dns' ? (
          <DNSMonitoringTab />
        ) : (
          <TrafficFlowsTab links={snapshot.links} />
        )}
      </div>
      <NetworkChatDrawer view="observatory" />
    </div>
  );
};

export default ObservatoryView;
