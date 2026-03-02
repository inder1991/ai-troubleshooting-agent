import React, { useState, useCallback } from 'react';
import { API_BASE_URL } from '../../services/api';

interface AdapterConfigDialogProps {
  open: boolean;
  onClose: () => void;
  nodeId: string | null;
  nodeName?: string;
}

type VendorType = 'palo_alto' | 'azure_nsg' | 'aws_sg' | 'oracle_nsg' | 'zscaler';

const vendorOptions: { value: VendorType; label: string }[] = [
  { value: 'palo_alto', label: 'Palo Alto' },
  { value: 'azure_nsg', label: 'Azure NSG' },
  { value: 'aws_sg', label: 'AWS Security Group' },
  { value: 'oracle_nsg', label: 'Oracle NSG' },
  { value: 'zscaler', label: 'Zscaler' },
];

const AdapterConfigDialog: React.FC<AdapterConfigDialogProps> = ({
  open,
  onClose,
  nodeId,
  nodeName,
}) => {
  const [vendor, setVendor] = useState<VendorType>('palo_alto');
  const [apiEndpoint, setApiEndpoint] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [extraConfig, setExtraConfig] = useState('{}');
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

  const handleTestConnection = useCallback(async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v4/network/adapters/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          node_id: nodeId,
          vendor,
          api_endpoint: apiEndpoint,
          api_key: apiKey,
          extra_config: JSON.parse(extraConfig),
        }),
      });
      const data = await response.json();
      setTestResult({
        success: response.ok,
        message: data.message || (response.ok ? 'Connection successful' : 'Connection failed'),
      });
    } catch (err) {
      setTestResult({
        success: false,
        message: err instanceof Error ? err.message : 'Test failed',
      });
    } finally {
      setTesting(false);
    }
  }, [nodeId, vendor, apiEndpoint, apiKey, extraConfig]);

  const handleSave = useCallback(async () => {
    try {
      await fetch(`${API_BASE_URL}/api/v4/network/adapters/configure`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          node_id: nodeId,
          vendor,
          api_endpoint: apiEndpoint,
          api_key: apiKey,
          extra_config: JSON.parse(extraConfig),
        }),
      });
      onClose();
    } catch {
      // handle error silently
    }
  }, [nodeId, vendor, apiEndpoint, apiKey, extraConfig, onClose]);

  if (!open) return null;

  const inputStyle: React.CSSProperties = {
    backgroundColor: '#0a0f13',
    borderColor: '#224349',
    color: '#e2e8f0',
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Overlay */}
      <div
        className="absolute inset-0"
        style={{ backgroundColor: 'rgba(0,0,0,0.7)' }}
        onClick={onClose}
      />

      {/* Dialog */}
      <div
        className="relative w-full max-w-lg rounded-xl border p-6 shadow-2xl"
        style={{ backgroundColor: '#0f2023', borderColor: '#224349' }}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <div>
            <h3 className="text-sm font-mono font-semibold" style={{ color: '#e2e8f0' }}>
              Configure Adapter
            </h3>
            {nodeName && (
              <p className="text-[10px] font-mono mt-0.5" style={{ color: '#64748b' }}>
                {nodeName}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded transition-colors hover:bg-white/5"
          >
            <span
              className="material-symbols-outlined text-lg"
              style={{ fontFamily: 'Material Symbols Outlined', color: '#64748b' }}
            >
              close
            </span>
          </button>
        </div>

        <div className="flex flex-col gap-4">
          {/* Vendor */}
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>
              Vendor
            </label>
            <select
              value={vendor}
              onChange={(e) => setVendor(e.target.value as VendorType)}
              className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#07b6d5]"
              style={inputStyle}
            >
              {vendorOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* API Endpoint */}
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>
              API Endpoint
            </label>
            <input
              type="text"
              value={apiEndpoint}
              onChange={(e) => setApiEndpoint(e.target.value)}
              placeholder="https://firewall.example.com/api"
              className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#07b6d5]"
              style={inputStyle}
            />
          </div>

          {/* API Key */}
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>
              API Key
            </label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="Enter API key"
              className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#07b6d5]"
              style={inputStyle}
            />
          </div>

          {/* Extra Config */}
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>
              Extra Config (JSON)
            </label>
            <textarea
              value={extraConfig}
              onChange={(e) => setExtraConfig(e.target.value)}
              rows={3}
              className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#07b6d5] resize-none"
              style={inputStyle}
            />
          </div>

          {/* Test Result */}
          {testResult && (
            <div
              className="p-3 rounded border text-xs font-mono"
              style={{
                backgroundColor: testResult.success ? '#0f2023' : '#1a0f0f',
                borderColor: testResult.success ? '#224349' : '#7f1d1d',
                color: testResult.success ? '#22c55e' : '#ef4444',
              }}
            >
              {testResult.message}
            </div>
          )}

          {/* Actions */}
          <div className="flex justify-between mt-2">
            <button
              onClick={handleTestConnection}
              disabled={testing || !apiEndpoint}
              className="flex items-center gap-1.5 px-4 py-2 rounded text-xs font-mono border transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              style={{ borderColor: '#224349', color: '#f59e0b', backgroundColor: 'transparent' }}
            >
              <span
                className="material-symbols-outlined text-sm"
                style={{ fontFamily: 'Material Symbols Outlined' }}
              >
                electrical_services
              </span>
              {testing ? 'Testing...' : 'Test Connection'}
            </button>

            <div className="flex gap-2">
              <button
                onClick={onClose}
                className="px-4 py-2 rounded text-xs font-mono border transition-colors"
                style={{ borderColor: '#224349', color: '#64748b', backgroundColor: 'transparent' }}
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                className="px-4 py-2 rounded text-xs font-mono font-semibold transition-colors"
                style={{ backgroundColor: '#07b6d5', color: '#0a0f13' }}
              >
                Save
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AdapterConfigDialog;
