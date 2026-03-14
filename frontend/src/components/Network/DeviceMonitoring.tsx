import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import type { MonitoredDevice, DiscoveryConfig, DeviceProfileSummary, CollectorHealthStatus, NDMTabType } from '../../types';
import { listMonitoredDevices, listDiscoveryConfigs, listDeviceProfiles, getCollectorHealth, searchDevices } from '../../services/api';
import NDMOverviewTab from './NDMOverviewTab';
import NDMDevicesTab from './NDMDevicesTab';
import NDMInterfacesTab from './NDMInterfacesTab';
import NDMNetFlowTab from './NDMNetFlowTab';
import NDMSyslogTab from './NDMSyslogTab';
import NDMTrapsTab from './NDMTrapsTab';
import NDMTopologyTab from './NDMTopologyTab';
import DeviceDetailPanel from './DeviceDetailPanel';
import NDMErrorBoundary from './NDMErrorBoundary';
import { ToastContainer } from './Toast';
import NetworkChatDrawer from '../NetworkChat/NetworkChatDrawer';

const TABS: { key: NDMTabType; label: string; icon: string }[] = [
  { key: 'overview', label: 'Overview', icon: 'dashboard' },
  { key: 'devices', label: 'Devices', icon: 'router' },
  { key: 'interfaces', label: 'Interfaces', icon: 'settings_ethernet' },
  { key: 'netflow', label: 'NetFlow', icon: 'hub' },
  { key: 'syslog', label: 'Syslog', icon: 'article' },
  { key: 'traps', label: 'Traps', icon: 'notification_important' },
  { key: 'topology', label: 'Topology', icon: 'lan' },
];

// --- Filter Presets (localStorage) ---
const PRESETS_KEY = 'ndm-filter-presets';

interface FilterPreset {
  name: string;
  tags: string[];
}

const loadPresets = (): FilterPreset[] => {
  try { return JSON.parse(localStorage.getItem(PRESETS_KEY) || '[]'); }
  catch { return []; }
};

const savePresetsToStorage = (presets: FilterPreset[]) => {
  localStorage.setItem(PRESETS_KEY, JSON.stringify(presets));
};

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
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [searchOpen, setSearchOpen] = useState(false);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Preset state
  const [presets, setPresets] = useState<FilterPreset[]>(loadPresets);
  const [showPresetDropdown, setShowPresetDropdown] = useState(false);

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

  // Preset handlers
  const handleSavePreset = () => {
    if (selectedTags.length === 0) return;
    const name = prompt('Enter a name for this filter preset:');
    if (!name || !name.trim()) return;
    const updated = [...presets, { name: name.trim(), tags: [...selectedTags] }];
    setPresets(updated);
    savePresetsToStorage(updated);
  };

  const handleLoadPreset = (preset: FilterPreset) => {
    setSelectedTags(preset.tags);
    setShowPresetDropdown(false);
  };

  const handleDeletePreset = (index: number, e: React.MouseEvent) => {
    e.stopPropagation();
    const updated = presets.filter((_, i) => i !== index);
    setPresets(updated);
    savePresetsToStorage(updated);
  };

  const handleSearch = (query: string) => {
    setSearchQuery(query);
    if (searchTimer.current) clearTimeout(searchTimer.current);
    if (!query.trim()) {
      setSearchResults([]);
      setSearchOpen(false);
      return;
    }
    searchTimer.current = setTimeout(async () => {
      try {
        const results = await searchDevices({ name: query });
        setSearchResults(Array.isArray(results) ? results : results.devices || []);
        setSearchOpen(true);
      } catch {
        setSearchResults([]);
      }
    }, 300);
  };

  const cardStyle: React.CSSProperties = {
    background: 'rgba(224,159,62,0.04)', border: '1px solid rgba(224,159,62,0.12)',
    borderRadius: 10, padding: 20,
  };

  if (loading) {
    return (
      <div style={{ padding: 32, color: '#8a7e6b', display: 'flex', alignItems: 'center', gap: 8 }}>
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
            onReload={reload}
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
          <h1 style={{ fontSize: 22, fontWeight: 700, color: '#e8e0d4', margin: 0, display: 'flex', alignItems: 'center', gap: 10 }}>
            <span className="material-symbols-outlined" style={{ fontSize: 26, color: '#e09f3e' }}>device_hub</span>
            Network Device Monitoring
          </h1>
          <p style={{ fontSize: 13, color: '#64748b', margin: '4px 0 0' }}>
            Protocol-first SNMP monitoring with autodiscovery
          </p>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          {/* Device Search Bar */}
          <div style={{ position: 'relative' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'rgba(224,159,62,0.06)', border: '1px solid rgba(224,159,62,0.15)', borderRadius: 8, padding: '6px 12px' }}>
              <span className="material-symbols-outlined" style={{ fontSize: 18, color: '#64748b' }}>search</span>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => handleSearch(e.target.value)}
                onFocus={() => searchResults.length > 0 && setSearchOpen(true)}
                onBlur={() => setTimeout(() => setSearchOpen(false), 200)}
                placeholder="Search devices..."
                style={{ background: 'transparent', border: 'none', outline: 'none', color: '#e8e0d4', fontSize: 13, width: 200 }}
              />
            </div>
            {searchOpen && searchResults.length > 0 && (
              <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, marginTop: 4, background: '#0a1a1e', border: '1px solid #3d3528', borderRadius: 8, maxHeight: 240, overflowY: 'auto', zIndex: 50 }}>
                {searchResults.map((d: any, i: number) => (
                  <button
                    key={d.id || d.device_id || i}
                    onClick={() => { setSelectedDeviceId(d.id || d.device_id); setSearchOpen(false); setSearchQuery(''); }}
                    style={{ display: 'block', width: '100%', textAlign: 'left', padding: '8px 12px', background: 'transparent', border: 'none', borderBottom: '1px solid #3d3528', color: '#e8e0d4', fontSize: 12, cursor: 'pointer' }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(224,159,62,0.08)')}
                    onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                  >
                    <div style={{ fontWeight: 600 }}>{d.hostname || d.name || d.ip_address}</div>
                    <div style={{ fontSize: 11, color: '#64748b' }}>{d.ip_address} {d.device_type ? `• ${d.device_type}` : ''}</div>
                  </button>
                ))}
              </div>
            )}
          </div>
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
            background: 'rgba(224,159,62,0.1)', color: '#e09f3e',
          }}>
            {profiles.length} profiles
          </span>
          <span style={{
            fontSize: 11, padding: '4px 10px', borderRadius: 4,
            background: 'rgba(224,159,62,0.1)', color: '#e09f3e',
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
                  border: active ? '1px solid #e09f3e' : '1px solid rgba(148,163,184,0.2)',
                  background: active ? 'rgba(224,159,62,0.2)' : 'transparent',
                  color: active ? '#e09f3e' : '#8a7e6b',
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

          {/* Divider */}
          <div style={{ width: 1, height: 20, background: 'rgba(148,163,184,0.15)', marginLeft: 4, marginRight: 4 }} />

          {/* Save Filter button */}
          <button
            onClick={handleSavePreset}
            disabled={selectedTags.length === 0}
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '3px 10px', borderRadius: 12, fontSize: 11, fontWeight: 500,
              border: '1px solid rgba(224,159,62,0.25)',
              background: selectedTags.length > 0 ? 'rgba(224,159,62,0.08)' : 'transparent',
              color: selectedTags.length > 0 ? '#e09f3e' : '#475569',
              cursor: selectedTags.length > 0 ? 'pointer' : 'default',
              opacity: selectedTags.length > 0 ? 1 : 0.5,
            }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 14 }}>save</span>
            Save
          </button>

          {/* Presets dropdown */}
          <div style={{ position: 'relative' }}>
            <button
              onClick={() => setShowPresetDropdown(prev => !prev)}
              style={{
                display: 'flex', alignItems: 'center', gap: 4,
                padding: '3px 10px', borderRadius: 12, fontSize: 11, fontWeight: 500,
                border: '1px solid rgba(148,163,184,0.2)',
                background: showPresetDropdown ? 'rgba(224,159,62,0.1)' : 'transparent',
                color: showPresetDropdown ? '#e09f3e' : '#8a7e6b',
                cursor: 'pointer',
              }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 14 }}>bookmark</span>
              Presets
              {presets.length > 0 && (
                <span style={{
                  fontSize: 9, fontWeight: 700, padding: '0 4px', borderRadius: 6,
                  background: 'rgba(224,159,62,0.2)', color: '#e09f3e',
                }}>
                  {presets.length}
                </span>
              )}
              <span className="material-symbols-outlined" style={{ fontSize: 12 }}>
                {showPresetDropdown ? 'expand_less' : 'expand_more'}
              </span>
            </button>

            {showPresetDropdown && (
              <div style={{
                position: 'absolute', top: '100%', left: 0, marginTop: 4, zIndex: 100,
                minWidth: 200, maxHeight: 240, overflowY: 'auto',
                background: '#0a1a1f', border: '1px solid rgba(224,159,62,0.2)',
                borderRadius: 8, boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
              }}>
                {presets.length === 0 ? (
                  <div style={{ padding: '12px 16px', fontSize: 12, color: '#64748b', textAlign: 'center' }}>
                    No saved presets
                  </div>
                ) : (
                  presets.map((preset, idx) => (
                    <div
                      key={`${preset.name}-${idx}`}
                      onClick={() => handleLoadPreset(preset)}
                      style={{
                        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                        padding: '8px 12px', cursor: 'pointer',
                        borderBottom: idx < presets.length - 1 ? '1px solid rgba(148,163,184,0.08)' : undefined,
                        transition: 'background 0.1s',
                      }}
                      onMouseEnter={e => { e.currentTarget.style.background = 'rgba(224,159,62,0.06)'; }}
                      onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; }}
                    >
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 12, fontWeight: 600, color: '#e8e0d4', marginBottom: 2 }}>
                          {preset.name}
                        </div>
                        <div style={{ fontSize: 10, color: '#64748b', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {preset.tags.join(', ')}
                        </div>
                      </div>
                      <button
                        onClick={(e) => handleDeletePreset(idx, e)}
                        style={{
                          background: 'none', border: 'none', cursor: 'pointer',
                          color: '#64748b', padding: 2, display: 'flex', alignItems: 'center',
                          marginLeft: 8, flexShrink: 0,
                        }}
                        title="Delete preset"
                        onMouseEnter={e => { e.currentTarget.style.color = '#ef4444'; }}
                        onMouseLeave={e => { e.currentTarget.style.color = '#64748b'; }}
                      >
                        <span className="material-symbols-outlined" style={{ fontSize: 14 }}>delete</span>
                      </button>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tab Bar */}
      <div
        role="tablist"
        aria-label="NDM dashboard tabs"
        style={{
          display: 'flex', gap: 0, marginBottom: 20,
          borderBottom: '1px solid rgba(148,163,184,0.12)',
        }}
      >
        {TABS.map(tab => {
          const isActive = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              role="tab"
              aria-selected={isActive}
              aria-controls={`ndm-tabpanel-${tab.key}`}
              id={`ndm-tab-${tab.key}`}
              onClick={() => setActiveTab(tab.key)}
              onKeyDown={(e) => {
                const idx = TABS.findIndex(t => t.key === tab.key);
                if (e.key === 'ArrowRight' && idx < TABS.length - 1) {
                  setActiveTab(TABS[idx + 1].key);
                  (document.getElementById(`ndm-tab-${TABS[idx + 1].key}`) as HTMLElement)?.focus();
                } else if (e.key === 'ArrowLeft' && idx > 0) {
                  setActiveTab(TABS[idx - 1].key);
                  (document.getElementById(`ndm-tab-${TABS[idx - 1].key}`) as HTMLElement)?.focus();
                }
              }}
              tabIndex={isActive ? 0 : -1}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '10px 18px', border: 'none', background: 'transparent',
                color: isActive ? '#e09f3e' : '#64748b',
                fontSize: 13, fontWeight: isActive ? 600 : 400,
                cursor: 'pointer', position: 'relative',
                borderBottom: isActive ? '2px solid #e09f3e' : '2px solid transparent',
                transition: 'all 0.15s ease',
              }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 18 }} aria-hidden="true">{tab.icon}</span>
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Active Tab Content */}
      <div
        role="tabpanel"
        id={`ndm-tabpanel-${activeTab}`}
        aria-labelledby={`ndm-tab-${activeTab}`}
      >
        <NDMErrorBoundary tabName={TABS.find(t => t.key === activeTab)?.label || activeTab}>
          {renderTab()}
        </NDMErrorBoundary>
      </div>

      {/* Device Detail Slide-out Panel */}
      {selectedDeviceId && selectedDevice && (
        <DeviceDetailPanel
          device={selectedDevice}
          onClose={() => setSelectedDeviceId(null)}
          onSelectDevice={setSelectedDeviceId}
        />
      )}

      <ToastContainer />
      <NetworkChatDrawer view="device-monitoring" />
    </div>
  );
};

export default DeviceMonitoring;
