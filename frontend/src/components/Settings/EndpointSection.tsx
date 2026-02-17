import React, { useState } from 'react';
import type { EndpointConfig, EndpointStatus } from '../../types/profiles';

interface EndpointSectionProps {
  icon: string;
  label: string;
  endpointName: string;
  endpoint: EndpointConfig | null;
  authOptions: { value: string; label: string }[];
  onTest: (endpointName: string) => Promise<void>;
  onUpdate: (endpointName: string, data: Partial<EndpointConfig> & { auth_data?: string }) => void;
  testing?: boolean;
}

const statusBadge: Record<EndpointStatus, { text: string; icon: string; classes: string }> = {
  unknown: { text: 'Not Tested', icon: 'help_outline', classes: 'text-gray-500 bg-gray-500/10 border-gray-500/20' },
  healthy: { text: 'Verified', icon: 'check_circle', classes: 'text-green-500 bg-green-500/10 border-green-500/20' },
  testing: { text: 'Testing...', icon: 'pending', classes: 'text-amber-500 bg-amber-500/10 border-amber-500/20' },
  degraded: { text: 'Degraded', icon: 'warning', classes: 'text-amber-500 bg-amber-500/10 border-amber-500/20' },
  unreachable: { text: 'Unreachable', icon: 'cloud_off', classes: 'text-red-500 bg-red-500/10 border-red-500/20' },
  connection_failed: { text: 'Connection Failed', icon: 'error', classes: 'text-red-500 bg-red-500/10 border-red-500/20' },
};

const EndpointSection: React.FC<EndpointSectionProps> = ({
  icon,
  label,
  endpointName,
  endpoint,
  authOptions,
  onTest,
  onUpdate,
  testing = false,
}) => {
  const [url, setUrl] = useState(endpoint?.url || '');
  const [authMethod, setAuthMethod] = useState(endpoint?.auth_method || 'none');
  const [authData, setAuthData] = useState('');

  const status = testing ? 'testing' : (endpoint?.status || 'unknown');
  const badge = statusBadge[status];

  const inputClass =
    'w-full px-3 py-2 bg-[#0f2023] border border-[#224349] rounded-lg text-sm text-white placeholder-gray-600 focus:border-[#07b6d5] focus:outline-none focus:ring-1 focus:ring-[#07b6d5]/30 transition-colors';

  const handleUrlChange = (val: string) => {
    setUrl(val);
    onUpdate(endpointName, { url: val } as Partial<EndpointConfig>);
  };

  const handleAuthChange = (val: string) => {
    setAuthMethod(val);
    onUpdate(endpointName, { auth_method: val } as Partial<EndpointConfig>);
  };

  const handleCredentialChange = (val: string) => {
    setAuthData(val);
    onUpdate(endpointName, { auth_data: val });
  };

  return (
    <div className="p-4 rounded-lg bg-[#0a1a1d]/40 border border-[#224349]/50">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span
            className="material-symbols-outlined text-[#07b6d5] text-lg"
            style={{ fontFamily: 'Material Symbols Outlined' }}
          >
            {icon}
          </span>
          <span className="text-xs font-bold text-white uppercase tracking-wider">{label}</span>
        </div>
        <span
          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium border ${badge.classes}`}
        >
          <span
            className="material-symbols-outlined text-xs"
            style={{ fontFamily: 'Material Symbols Outlined' }}
          >
            {badge.icon}
          </span>
          {badge.text}
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="relative">
          <label className="block text-[10px] text-gray-500 mb-1 uppercase tracking-wider">Endpoint URL</label>
          <div className="relative">
            <input
              type="text"
              value={url}
              onChange={(e) => handleUrlChange(e.target.value)}
              className={`${inputClass} pr-14`}
              placeholder="https://..."
            />
            <button
              onClick={() => onTest(endpointName)}
              disabled={!url || testing}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] font-bold text-[#07b6d5] hover:text-[#07b6d5]/80 disabled:text-gray-600 disabled:cursor-not-allowed transition-colors"
            >
              {testing ? 'Testing...' : 'Test'}
            </button>
          </div>
        </div>

        <div>
          <label className="block text-[10px] text-gray-500 mb-1 uppercase tracking-wider">Authentication</label>
          <div className="flex gap-2">
            <select
              value={authMethod}
              onChange={(e) => handleAuthChange(e.target.value)}
              className={`${inputClass} w-36 shrink-0`}
            >
              <option value="none">None</option>
              {authOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            {authMethod !== 'none' && (
              <input
                type="password"
                value={authData}
                onChange={(e) => handleCredentialChange(e.target.value)}
                className={inputClass}
                placeholder={endpoint?.has_credentials ? '••••••••' : 'Enter credentials'}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default EndpointSection;
