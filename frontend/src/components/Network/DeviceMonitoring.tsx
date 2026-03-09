import React, { useState, useEffect, useCallback, useMemo } from 'react';
import type { MonitoredDevice, DiscoveryConfig, DeviceProfileSummary, CollectorHealthStatus, NDMTabType } from '../../types';
import { listMonitoredDevices, listDiscoveryConfigs, listDeviceProfiles, getCollectorHealth } from '../../services/api';
import NDMOverviewTab from './NDMOverviewTab';
import NDMDevicesTab from './NDMDevicesTab';
import NDMInterfacesTab from './NDMInterfacesTab';
import NDMNetFlowTab from './NDMNetFlowTab';
import NDMSyslogTab from './NDMSyslogTab';
import NDMTrapsTab from './NDMTrapsTab';
import NDMTopologyTab from './NDMTopologyTab';
import DeviceDetailPanel from './DeviceDetailPanel';

const TABS: { key: NDMTabType; label: string; icon: string }[] = [
  { key: 'overview', label: 'Overview', icon: 'dashboard' },
  { key: 'devices', label: 'Devices', icon: 'router' },
  { key: 'interfaces', label: 'Interfaces', icon: 'settings_ethernet' },
  { key: 'netflow', label: 'NetFlow', icon: 'hub' },
  { key: 'syslog', label: 'Syslog', icon: 'article' },
  { key: 'traps', label: 'Traps', icon: 'notification_important' },
  { key: 'topology', label: 'Topology', icon: 'lan' },
];

const DeviceMonitoring: React.FC = () => {
  const [devices, setDevices] = useState<MonitoredDevice[]>([]);
  const [configs, setConfigs] = useState<DiscoveryConfig[]>([]);
  const [profiles, setProfiles] = useState<DeviceProfileSummary[]>([]);
  const [health, setHealth] = useState<CollectorHealthStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState<NDMTabType>('overview');
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const [devRes, cfgRes, profRes, hRes] = await Promise.all([
        listMonitoredDevices(), listDiscoveryConfigs(), listDeviceProfiles(), getCollectorHealth(),
      ]);
      setDevices(devRes.devices || []);
      setConfigs(cfgRes.configs || []);
      setProfiles(profRes.profiles || []);
      setHealth(hRes);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { reload(); }, [reload]);

  // Auto-refresh every 30s
  useEffect(() => {
    const interval = setInterval(reload, 30000);
    return () => clearInterval(interval);
  }, [reload]);

  // Derive all unique tags from devices
  const allTags = useMemo(() => {
    const tagSet = new Set<string>();
    devices.forEach(d => d.tags.forEach(t => tagSet.add(t)));
    return Array.from(tagSet).sort();
  }, [devices]);

  // Filter devices by selected tags
  const filteredDevices = useMemo(() => {
    if (selectedTags.length === 0) return devices;
    return devices.filter(d => selectedTags.every(tag => d.tags.includes(tag)));
  }, [devices, selectedTags]);

  const toggleTag = (tag: string) => {
    setSelectedTags(prev =>
      prev.includes(tag) ? prev.filter(t => t !== tag) : [...prev, tag]
    );
  };

  const selectedDevice = useMemo(
    () => devices.find(d => d.device_id === selectedDeviceId) || null,
    [devices, selectedDeviceId]
  );

  const cardStyle: React.CSSProperties = {
    background: 'rgba(7,182,213,0.04)', border: '1px solid rgba(7,182,213,0.12)',
    borderRadius: 10, padding: 20,
  };

  if (loading) {
    return (
      <div style={{ padding: 32, color: '#94a3b8', display: 'flex', alignItems: 'center', gap: 8 }}>
        <span className="material-symbols-outlined" style={{ animation: 'spin 1s linear infinite' }}>progress_activity</span>
        Loading device monitoring...
      </div>
    );
  }

  const renderTab = () => {
    switch (activeTab) {
      case 'overview':
        return (
          <NDMOverviewTab
            devices={filteredDevices}
            configs={configs}
            profiles={profiles}
            health={health}
            onSelectDevice={setSelectedDeviceId}
          />
        );
      case 'devices':
        return (
          <NDMDevicesTab
            devices={filteredDevices}
            onSelectDevice={setSelectedDeviceId}
            onReload={reload}
          />
        );
      case 'interfaces':
        return <NDMInterfacesTab devices={filteredDevices} />;
      case 'netflow':
        return <NDMNetFlowTab />;
      case 'syslog':
        return <NDMSyslogTab devices={filteredDevices} />;
      case 'traps':
        return <NDMTrapsTab devices={filteredDevices} />;
      case 'topology':
        return <NDMTopologyTab devices={filteredDevices} onSelectDevice={setSelectedDeviceId} />;
      default:
        return null;
    }
  };

  return (
    <div style={{ padding: '24px 32px', maxWidth: 1600, margin: '0 auto', position: 'relative' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: '#e2e8f0', margin: 0, display: 'flex', alignItems: 'center', gap: 10 }}>
            <span className="material-symbols-outlined" style={{ fontSize: 26, color: '#07b6d5' }}>device_hub</span>
            Network Device Monitoring
          </h1>
          <p style={{ fontSize: 13, color: '#64748b', margin: '4px 0 0' }}>
            Protocol-first SNMP monitoring with autodiscovery
          </p>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          {health && (
            <span style={{
              fontSize: 11, padding: '4px 10px', borderRadius: 4,
              background: health.pysnmp_available ? 'rgba(34,197,94,0.12)' : 'rgba(245,158,11,0.12)',
              color: health.pysnmp_available ? '#22c55e' : '#f59e0b',
            }}>
              {health.pysnmp_available ? 'pysnmp active' : 'simulated mode'}
            </span>
          )}
          <span style={{
            fontSize: 11, padding: '4px 10px', borderRadius: 4,
            background: 'rgba(7,182,213,0.1)', color: '#07b6d5',
          }}>
            {profiles.length} profiles
          </span>
          <span style={{
            fontSize: 11, padding: '4px 10px', borderRadius: 4,
            background: 'rgba(7,182,213,0.1)', color: '#07b6d5',
          }}>
            {filteredDevices.length}/{devices.length} devices
          </span>
        </div>
      </div>

      {error && <div style={{ color: '#ef4444', marginBottom: 12, fontSize: 13 }}>{error}</div>}

      {/* Tag Filter Bar */}
      {allTags.length > 0 && (
        <div style={{ ...cardStyle, padding: '10px 16px', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span className="material-symbols-outlined" style={{ fontSize: 16, color: '#64748b' }}>label</span>
          <span style={{ fontSize: 11, color: '#64748b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', marginRight: 4 }}>
            Filter by tag:
          </span>
          {allTags.map(tag => {
            const active = selectedTags.includes(tag);
            return (
              <button
                key={tag}
                onClick={() => toggleTag(tag)}
                style={{
                  padding: '3px 10px', borderRadius: 12, fontSize: 11, fontWeight: 500,
                  border: active ? '1px solid #07b6d5' : '1px solid rgba(148,163,184,0.2)',
                  background: active ? 'rgba(7,182,213,0.2)' : 'transparent',
                  color: active ? '#07b6d5' : '#94a3b8',
                  cursor: 'pointer', transition: 'all 0.15s ease',
                }}
              >
                {tag}
              </button>
            );
          })}
          {selectedTags.length > 0 && (
            <button
              onClick={() => setSelectedTags([])}
              style={{
                padding: '3px 8px', borderRadius: 12, fontSize: 11, fontWeight: 500,
                border: '1px solid rgba(239,68,68,0.3)', background: 'transparent',
                color: '#ef4444', cursor: 'pointer', marginLeft: 4,
              }}
            >
              Clear
            </button>
          )}
        </div>
      )}

      {/* Tab Bar */}
      <div style={{
        display: 'flex', gap: 0, marginBottom: 20,
        borderBottom: '1px solid rgba(148,163,184,0.12)',
      }}>
        {TABS.map(tab => {
          const isActive = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '10px 18px', border: 'none', background: 'transparent',
                color: isActive ? '#07b6d5' : '#64748b',
                fontSize: 13, fontWeight: isActive ? 600 : 400,
                cursor: 'pointer', position: 'relative',
                borderBottom: isActive ? '2px solid #07b6d5' : '2px solid transparent',
                transition: 'all 0.15s ease',
              }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 18 }}>{tab.icon}</span>
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Active Tab Content */}
      {renderTab()}

      {/* Device Detail Slide-out Panel */}
      {selectedDeviceId && selectedDevice && (
        <DeviceDetailPanel
          device={selectedDevice}
          onClose={() => setSelectedDeviceId(null)}
        />
      )}
    </div>
  );
};

export default DeviceMonitoring;
