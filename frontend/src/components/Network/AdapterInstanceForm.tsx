import React, { useState, useEffect } from 'react';
import type { AdapterInstanceStatus, DeviceGroupInfo } from '../../types';
import {
  createAdapterInstance,
  updateAdapterInstance,
  testNewAdapter,
  testAdapterInstance,
  discoverDeviceGroups,
} from '../../services/api';

const VENDORS = [
  { value: 'cisco', label: 'Cisco IOS-XE' },
  { value: 'palo_alto', label: 'Palo Alto' },
  { value: 'aws_sg', label: 'AWS Security Group' },
  { value: 'azure_nsg', label: 'Azure NSG' },
  { value: 'oracle_nsg', label: 'Oracle NSG' },
  { value: 'zscaler', label: 'Zscaler' },
  { value: 'f5', label: 'F5 Load Balancer' },
  { value: 'checkpoint', label: 'Checkpoint' },
];

interface Props {
  instance: AdapterInstanceStatus | null;
  onClose: () => void;
}

const AdapterInstanceForm: React.FC<Props> = ({ instance, onClose }) => {
  const isEditing = !!instance;

  const [label, setLabel] = useState(instance?.label || '');
  const [vendor, setVendor] = useState(instance?.vendor || 'cisco');
  const [apiEndpoint, setApiEndpoint] = useState(instance?.api_endpoint || '');
  const [apiKey, setApiKey] = useState('');
  const [extraConfig, setExtraConfig] = useState<Record<string, unknown>>(instance?.extra_config || {});
  const [deviceGroups, setDeviceGroups] = useState<string[]>(instance?.device_groups || []);

  // Vendor-specific fields
  const [panoMode, setPanoMode] = useState<'panorama' | 'standalone'>(
    (instance?.extra_config?.device_group as string) ? 'panorama' : 'standalone'
  );
  const [vsys, setVsys] = useState((instance?.extra_config?.vsys as string) || 'vsys1');

  // AWS
  const [awsRegion, setAwsRegion] = useState((instance?.extra_config?.region as string) || 'us-east-1');
  const [sgId, setSgId] = useState((instance?.extra_config?.security_group_id as string) || '');
  const [awsAccessKey, setAwsAccessKey] = useState('');
  const [awsSecretKey, setAwsSecretKey] = useState('');

  // Azure
  const [subscriptionId, setSubscriptionId] = useState((instance?.extra_config?.subscription_id as string) || '');
  const [resourceGroup, setResourceGroup] = useState((instance?.extra_config?.resource_group as string) || '');
  const [nsgName, setNsgName] = useState((instance?.extra_config?.nsg_name as string) || '');

  // Oracle
  const [compartmentId, setCompartmentId] = useState((instance?.extra_config?.compartment_id as string) || '');
  const [oracleNsgId, setOracleNsgId] = useState((instance?.extra_config?.nsg_id as string) || '');

  // Cisco
  const [ciscoUsername, setCiscoUsername] = useState((instance?.extra_config?.username as string) || '');
  const [ciscoPassword, setCiscoPassword] = useState('');
  const [verifySsl, setVerifySsl] = useState((instance?.extra_config?.verify_ssl as boolean) ?? false);

  // F5
  const [f5Username, setF5Username] = useState((instance?.extra_config?.username as string) || '');
  const [f5Password, setF5Password] = useState('');
  const [f5Partition, setF5Partition] = useState((instance?.extra_config?.partition as string) || 'Common');

  // Checkpoint
  const [cpUsername, setCpUsername] = useState((instance?.extra_config?.username as string) || '');
  const [cpPassword, setCpPassword] = useState('');
  const [cpDomain, setCpDomain] = useState((instance?.extra_config?.domain as string) || '');

  // Zscaler
  const [cloudName, setCloudName] = useState((instance?.extra_config?.cloud_name as string) || '');
  const [zscalerUsername, setZscalerUsername] = useState((instance?.extra_config?.username as string) || '');
  const [zscalerPassword, setZscalerPassword] = useState('');

  // Panorama DG discovery
  const [discoveredDGs, setDiscoveredDGs] = useState<DeviceGroupInfo[]>([]);
  const [discovering, setDiscovering] = useState(false);

  // Test/Save state
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const buildExtraConfig = (): Record<string, unknown> => {
    switch (vendor) {
      case 'cisco':
        return {
          username: ciscoUsername,
          ...(ciscoPassword ? { password: ciscoPassword } : {}),
          verify_ssl: verifySsl,
        };
      case 'palo_alto':
        return panoMode === 'panorama'
          ? { device_group: deviceGroups[0] || '', vsys }
          : { vsys };
      case 'aws_sg':
        return {
          region: awsRegion,
          security_group_id: sgId,
          ...(awsAccessKey ? { aws_access_key: awsAccessKey } : {}),
          ...(awsSecretKey ? { aws_secret_key: awsSecretKey } : {}),
        };
      case 'azure_nsg':
        return { subscription_id: subscriptionId, resource_group: resourceGroup, nsg_name: nsgName };
      case 'oracle_nsg':
        return { compartment_id: compartmentId, nsg_id: oracleNsgId };
      case 'zscaler':
        return {
          cloud_name: cloudName,
          username: zscalerUsername,
          ...(zscalerPassword ? { password: zscalerPassword } : {}),
        };
      case 'f5':
        return {
          username: f5Username,
          ...(f5Password ? { password: f5Password } : {}),
          partition: f5Partition,
        };
      case 'checkpoint':
        return {
          username: cpUsername,
          ...(cpPassword ? { password: cpPassword } : {}),
          domain: cpDomain,
        };
      default:
        return extraConfig;
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const config = buildExtraConfig();
      if (isEditing && instance) {
        const result = await testAdapterInstance(instance.instance_id);
        setTestResult(result);
      } else {
        const result = await testNewAdapter({
          label: label || 'test',
          vendor,
          api_endpoint: apiEndpoint,
          api_key: apiKey,
          extra_config: config,
        });
        setTestResult(result);
      }
    } catch (err) {
      setTestResult({ success: false, message: err instanceof Error ? err.message : 'Test failed' });
    } finally {
      setTesting(false);
    }
  };

  const handleDiscover = async () => {
    if (!instance) return;
    setDiscovering(true);
    try {
      const result = await discoverDeviceGroups(instance.instance_id);
      setDiscoveredDGs(result.device_groups || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Discovery failed');
    } finally {
      setDiscovering(false);
    }
  };

  const handleSave = async () => {
    if (!label.trim()) {
      setError('Label is required');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const config = buildExtraConfig();
      if (isEditing && instance) {
        await updateAdapterInstance(instance.instance_id, {
          label,
          api_endpoint: apiEndpoint,
          ...(apiKey ? { api_key: apiKey } : {}),
          extra_config: config,
          device_groups: deviceGroups,
        });
      } else {
        await createAdapterInstance({
          label,
          vendor,
          api_endpoint: apiEndpoint,
          api_key: apiKey,
          extra_config: config,
        });
      }
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const toggleDG = (name: string) => {
    setDeviceGroups((prev) =>
      prev.includes(name) ? prev.filter((g) => g !== name) : [...prev, name]
    );
  };

  const inputClass = 'w-full px-3 py-2 rounded-lg border text-sm font-mono text-white placeholder-slate-500 focus:outline-none focus:border-[#e09f3e]';
  const inputStyle = { backgroundColor: '#0a1214', borderColor: '#3d3528' };
  const labelClass = 'block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div
        className="w-full max-w-lg max-h-[85vh] overflow-auto rounded-xl border shadow-2xl"
        style={{ backgroundColor: '#1a1814', borderColor: '#3d3528' }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b" style={{ borderColor: '#3d3528' }}>
          <h2 className="text-lg font-bold text-white">
            {isEditing ? 'Edit Adapter Instance' : 'New Adapter Instance'}
          </h2>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors">
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        <div className="px-6 py-4 space-y-4">
          {/* Label */}
          <div>
            <label className={labelClass}>Instance Label</label>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g. US-East Panorama"
              className={inputClass}
              style={inputStyle}
            />
          </div>

          {/* Vendor */}
          <div>
            <label className={labelClass}>Vendor</label>
            <select
              value={vendor}
              onChange={(e) => setVendor(e.target.value)}
              disabled={isEditing}
              className={inputClass}
              style={inputStyle}
            >
              {VENDORS.map((v) => (
                <option key={v.value} value={v.value}>{v.label}</option>
              ))}
            </select>
          </div>

          {/* API Endpoint */}
          <div>
            <label className={labelClass}>API Endpoint</label>
            <input
              type="text"
              value={apiEndpoint}
              onChange={(e) => setApiEndpoint(e.target.value)}
              placeholder="https://panorama.example.com"
              className={inputClass}
              style={inputStyle}
            />
          </div>

          {/* API Key */}
          <div>
            <label className={labelClass}>API Key {isEditing && <span className="text-slate-500 normal-case">(leave blank to keep current)</span>}</label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={isEditing ? '••••••••' : 'Enter API key'}
              className={inputClass}
              style={inputStyle}
            />
          </div>

          {/* Vendor-specific fields */}
          {vendor === 'cisco' && (
            <div className="space-y-3 p-3 rounded-lg border" style={{ borderColor: '#3d3528', backgroundColor: '#0a1214' }}>
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Cisco IOS-XE Configuration (RESTCONF)</p>
              <div>
                <label className={labelClass}>Username</label>
                <input type="text" value={ciscoUsername} onChange={(e) => setCiscoUsername(e.target.value)} placeholder="admin" className={inputClass} style={inputStyle} />
              </div>
              <div>
                <label className={labelClass}>Password {isEditing && <span className="text-slate-500 normal-case">(leave blank to keep current)</span>}</label>
                <input type="password" value={ciscoPassword} onChange={(e) => setCiscoPassword(e.target.value)} placeholder={isEditing ? '••••••••' : 'RESTCONF password'} className={inputClass} style={inputStyle} />
              </div>
              <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
                <input type="checkbox" checked={verifySsl} onChange={(e) => setVerifySsl(e.target.checked)} className="accent-[#e09f3e]" />
                Verify SSL Certificate
                <span className="text-xs text-slate-500">(disable for self-signed certs)</span>
              </label>
            </div>
          )}

          {vendor === 'palo_alto' && (
            <div className="space-y-3 p-3 rounded-lg border" style={{ borderColor: '#3d3528', backgroundColor: '#0a1214' }}>
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Palo Alto Configuration</p>
              <div className="flex gap-2">
                {(['panorama', 'standalone'] as const).map((mode) => (
                  <button
                    key={mode}
                    onClick={() => setPanoMode(mode)}
                    className={`px-3 py-1 text-xs font-mono rounded border transition-colors ${
                      panoMode === mode ? 'border-[#e09f3e] text-[#e09f3e]' : 'border-[#3d3528] text-slate-400'
                    }`}
                    style={{ backgroundColor: panoMode === mode ? 'rgba(224,159,62,0.1)' : 'transparent' }}
                  >
                    {mode === 'panorama' ? 'Panorama' : 'Standalone'}
                  </button>
                ))}
              </div>
              {panoMode === 'standalone' && (
                <div>
                  <label className={labelClass}>Vsys</label>
                  <input
                    type="text"
                    value={vsys}
                    onChange={(e) => setVsys(e.target.value)}
                    placeholder="vsys1"
                    className={inputClass}
                    style={inputStyle}
                  />
                </div>
              )}
              {panoMode === 'panorama' && (
                <div>
                  {isEditing && instance && (
                    <button
                      onClick={handleDiscover}
                      disabled={discovering}
                      className="text-xs font-mono px-3 py-1.5 rounded border transition-colors mb-2"
                      style={{ borderColor: '#e09f3e', color: '#e09f3e', backgroundColor: 'rgba(224,159,62,0.1)' }}
                    >
                      {discovering ? 'Discovering...' : 'Discover Device Groups'}
                    </button>
                  )}
                  {discoveredDGs.length > 0 && (
                    <div className="space-y-1 mt-2">
                      <p className="text-xs text-slate-400">Select device groups to monitor:</p>
                      {discoveredDGs.map((dg) => (
                        <label key={dg.name} className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={deviceGroups.includes(dg.name)}
                            onChange={() => toggleDG(dg.name)}
                            className="accent-[#e09f3e]"
                          />
                          <span className="font-mono">{dg.name}</span>
                          <span className="text-xs text-slate-500">({dg.connected_devices} devices)</span>
                        </label>
                      ))}
                    </div>
                  )}
                  {deviceGroups.length > 0 && discoveredDGs.length === 0 && (
                    <p className="text-xs text-slate-400 mt-1">Device Groups: {deviceGroups.join(', ')}</p>
                  )}
                </div>
              )}
            </div>
          )}

          {vendor === 'aws_sg' && (
            <div className="space-y-3 p-3 rounded-lg border" style={{ borderColor: '#3d3528', backgroundColor: '#0a1214' }}>
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">AWS Configuration</p>
              <div>
                <label className={labelClass}>Region</label>
                <input type="text" value={awsRegion} onChange={(e) => setAwsRegion(e.target.value)} placeholder="us-east-1" className={inputClass} style={inputStyle} />
              </div>
              <div>
                <label className={labelClass}>Security Group ID</label>
                <input type="text" value={sgId} onChange={(e) => setSgId(e.target.value)} placeholder="sg-0123456789abcdef0" className={inputClass} style={inputStyle} />
              </div>
              <div>
                <label className={labelClass}>Access Key</label>
                <input type="password" value={awsAccessKey} onChange={(e) => setAwsAccessKey(e.target.value)} placeholder="AKIA..." className={inputClass} style={inputStyle} />
              </div>
              <div>
                <label className={labelClass}>Secret Key</label>
                <input type="password" value={awsSecretKey} onChange={(e) => setAwsSecretKey(e.target.value)} placeholder="Secret key" className={inputClass} style={inputStyle} />
              </div>
            </div>
          )}

          {vendor === 'azure_nsg' && (
            <div className="space-y-3 p-3 rounded-lg border" style={{ borderColor: '#3d3528', backgroundColor: '#0a1214' }}>
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Azure Configuration</p>
              <div>
                <label className={labelClass}>Subscription ID</label>
                <input type="text" value={subscriptionId} onChange={(e) => setSubscriptionId(e.target.value)} className={inputClass} style={inputStyle} />
              </div>
              <div>
                <label className={labelClass}>Resource Group</label>
                <input type="text" value={resourceGroup} onChange={(e) => setResourceGroup(e.target.value)} className={inputClass} style={inputStyle} />
              </div>
              <div>
                <label className={labelClass}>NSG Name</label>
                <input type="text" value={nsgName} onChange={(e) => setNsgName(e.target.value)} className={inputClass} style={inputStyle} />
              </div>
            </div>
          )}

          {vendor === 'oracle_nsg' && (
            <div className="space-y-3 p-3 rounded-lg border" style={{ borderColor: '#3d3528', backgroundColor: '#0a1214' }}>
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Oracle Configuration</p>
              <div>
                <label className={labelClass}>Compartment ID</label>
                <input type="text" value={compartmentId} onChange={(e) => setCompartmentId(e.target.value)} className={inputClass} style={inputStyle} />
              </div>
              <div>
                <label className={labelClass}>NSG ID</label>
                <input type="text" value={oracleNsgId} onChange={(e) => setOracleNsgId(e.target.value)} className={inputClass} style={inputStyle} />
              </div>
            </div>
          )}

          {vendor === 'zscaler' && (
            <div className="space-y-3 p-3 rounded-lg border" style={{ borderColor: '#3d3528', backgroundColor: '#0a1214' }}>
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Zscaler Configuration</p>
              <div>
                <label className={labelClass}>Cloud Name</label>
                <input type="text" value={cloudName} onChange={(e) => setCloudName(e.target.value)} placeholder="zscaler.net" className={inputClass} style={inputStyle} />
              </div>
              <div>
                <label className={labelClass}>Username</label>
                <input type="text" value={zscalerUsername} onChange={(e) => setZscalerUsername(e.target.value)} className={inputClass} style={inputStyle} />
              </div>
              <div>
                <label className={labelClass}>Password</label>
                <input type="password" value={zscalerPassword} onChange={(e) => setZscalerPassword(e.target.value)} className={inputClass} style={inputStyle} />
              </div>
            </div>
          )}

          {vendor === 'f5' && (
            <div className="space-y-3 p-3 rounded-lg border" style={{ borderColor: '#3d3528', backgroundColor: '#0a1214' }}>
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">F5 Configuration</p>
              <div>
                <label className={labelClass}>Username</label>
                <input type="text" value={f5Username} onChange={(e) => setF5Username(e.target.value)} placeholder="admin" className={inputClass} style={inputStyle} />
              </div>
              <div>
                <label className={labelClass}>Password {isEditing && <span className="text-slate-500 normal-case">(leave blank to keep current)</span>}</label>
                <input type="password" value={f5Password} onChange={(e) => setF5Password(e.target.value)} placeholder={isEditing ? '••••••••' : 'Password'} className={inputClass} style={inputStyle} />
              </div>
              <div>
                <label className={labelClass}>Partition</label>
                <input type="text" value={f5Partition} onChange={(e) => setF5Partition(e.target.value)} placeholder="Common" className={inputClass} style={inputStyle} />
              </div>
            </div>
          )}

          {vendor === 'checkpoint' && (
            <div className="space-y-3 p-3 rounded-lg border" style={{ borderColor: '#3d3528', backgroundColor: '#0a1214' }}>
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Checkpoint Configuration</p>
              <div>
                <label className={labelClass}>Username</label>
                <input type="text" value={cpUsername} onChange={(e) => setCpUsername(e.target.value)} placeholder="admin" className={inputClass} style={inputStyle} />
              </div>
              <div>
                <label className={labelClass}>Password {isEditing && <span className="text-slate-500 normal-case">(leave blank to keep current)</span>}</label>
                <input type="password" value={cpPassword} onChange={(e) => setCpPassword(e.target.value)} placeholder={isEditing ? '••••••••' : 'Password'} className={inputClass} style={inputStyle} />
              </div>
              <div>
                <label className={labelClass}>Domain <span className="text-slate-500 normal-case">(optional)</span></label>
                <input type="text" value={cpDomain} onChange={(e) => setCpDomain(e.target.value)} placeholder="e.g. SMC User" className={inputClass} style={inputStyle} />
              </div>
            </div>
          )}

          {/* Test Result */}
          {testResult && (
            <div
              className="px-3 py-2 rounded border text-sm font-mono"
              style={{
                backgroundColor: testResult.success ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)',
                borderColor: testResult.success ? '#22c55e' : '#ef4444',
                color: testResult.success ? '#22c55e' : '#ef4444',
              }}
            >
              {testResult.success ? 'Connection successful' : testResult.message}
            </div>
          )}

          {error && (
            <div className="px-3 py-2 rounded border text-sm" style={{ backgroundColor: 'rgba(239,68,68,0.1)', borderColor: '#ef4444', color: '#ef4444' }}>
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t" style={{ borderColor: '#3d3528' }}>
          <button
            onClick={handleTest}
            disabled={testing}
            className="text-sm font-mono px-4 py-2 rounded border transition-colors"
            style={{ borderColor: '#3d3528', color: '#e09f3e', backgroundColor: 'transparent' }}
          >
            {testing ? 'Testing...' : 'Test Connection'}
          </button>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="text-sm font-mono px-4 py-2 rounded border transition-colors text-slate-400 hover:text-white"
              style={{ borderColor: '#3d3528', backgroundColor: 'transparent' }}
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={saving || !label.trim()}
              className="text-sm font-mono font-semibold px-4 py-2 rounded transition-colors disabled:opacity-40"
              style={{ backgroundColor: '#e09f3e', color: '#1a1814' }}
            >
              {saving ? 'Saving...' : isEditing ? 'Update' : 'Create'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AdapterInstanceForm;
