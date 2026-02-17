import React, { useState } from 'react';
import type { GlobalIntegration, GlobalIntegrationStatus } from '../../types/profiles';

interface GlobalIntegrationsSectionProps {
  integrations: GlobalIntegration[];
  onUpdate: (id: string, data: Record<string, unknown>) => void;
  onTest: (id: string) => Promise<void>;
  testingId: string | null;
}

const serviceIcons: Record<string, { icon: string; color: string }> = {
  elk: { icon: 'search', color: 'text-[#07b6d5]' },
  jira: { icon: 'bug_report', color: 'text-blue-400' },
  confluence: { icon: 'article', color: 'text-indigo-400' },
  remedy: { icon: 'build', color: 'text-orange-400' },
};

const authOptionsByService: Record<string, { value: string; label: string }[]> = {
  elk: [
    { value: 'basic_auth', label: 'Basic Auth' },
    { value: 'cloud_id', label: 'Cloud ID' },
    { value: 'bearer_token', label: 'Bearer Token' },
  ],
  jira: [
    { value: 'basic_auth', label: 'Basic Auth' },
    { value: 'api_token', label: 'API Token' },
    { value: 'oauth2', label: 'OAuth 2.0' },
  ],
  confluence: [
    { value: 'basic_auth', label: 'Basic Auth' },
    { value: 'api_token', label: 'API Token' },
    { value: 'oauth2', label: 'OAuth 2.0' },
  ],
  remedy: [
    { value: 'basic_auth', label: 'Basic Auth' },
    { value: 'bearer_token', label: 'Bearer Token' },
    { value: 'certificate', label: 'Certificate' },
  ],
};

const statusText: Record<GlobalIntegrationStatus, { text: string; classes: string }> = {
  connected: { text: 'Connected', classes: 'text-green-400' },
  not_validated: { text: 'Not Validated', classes: 'text-amber-400' },
  not_linked: { text: 'Not Linked', classes: 'text-gray-500' },
  conn_error: { text: 'Conn. Error', classes: 'text-red-400' },
};

const GlobalIntegrationsSection: React.FC<GlobalIntegrationsSectionProps> = ({
  integrations,
  onUpdate,
  onTest,
  testingId,
}) => {
  const [localUpdates, setLocalUpdates] = useState<Record<string, Record<string, string>>>({});

  const inputClass =
    'px-3 py-2 bg-[#0f2023] border border-[#224349] rounded-lg text-sm text-white placeholder-gray-600 focus:border-[#07b6d5] focus:outline-none focus:ring-1 focus:ring-[#07b6d5]/30 transition-colors';

  const getLocal = (id: string, field: string, fallback: string) => {
    return localUpdates[id]?.[field] ?? fallback;
  };

  const setLocal = (id: string, field: string, value: string) => {
    setLocalUpdates((prev) => ({
      ...prev,
      [id]: { ...(prev[id] || {}), [field]: value },
    }));
    onUpdate(id, { [field]: value });
  };

  return (
    <div>
      <h2 className="text-sm font-bold text-white uppercase tracking-wider mb-3">
        Global Ecosystem Integrations
      </h2>

      <div className="space-y-2">
        {integrations.map((gi) => {
          const svc = serviceIcons[gi.service_type] || { icon: 'extension', color: 'text-gray-400' };
          const status = statusText[gi.status];
          const authOpts = authOptionsByService[gi.service_type] || [];
          const isTesting = testingId === gi.id;

          return (
            <div
              key={gi.id}
              className="flex items-center gap-3 p-3 bg-[#0a1a1d] border border-[#224349] rounded-xl"
            >
              {/* Service icon + name */}
              <div className="flex items-center gap-2 w-40 shrink-0">
                <span
                  className={`material-symbols-outlined text-lg ${svc.color}`}
                  style={{ fontFamily: 'Material Symbols Outlined' }}
                >
                  {svc.icon}
                </span>
                <div>
                  <span className="text-xs font-semibold text-white block">{gi.name}</span>
                  <span className="text-[9px] text-gray-600 uppercase tracking-widest">
                    {gi.category}
                  </span>
                </div>
              </div>

              {/* URL */}
              <input
                type="text"
                value={getLocal(gi.id, 'url', gi.url)}
                onChange={(e) => setLocal(gi.id, 'url', e.target.value)}
                className={`${inputClass} flex-1 min-w-[200px]`}
                placeholder={`https://${gi.service_type}.example.com`}
              />

              {/* Auth dropdown */}
              <select
                value={getLocal(gi.id, 'auth_method', gi.auth_method)}
                onChange={(e) => setLocal(gi.id, 'auth_method', e.target.value)}
                className={`${inputClass} w-32 shrink-0`}
              >
                <option value="none">None</option>
                {authOpts.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>

              {/* Credentials (if auth != none) */}
              {getLocal(gi.id, 'auth_method', gi.auth_method) !== 'none' && (
                <input
                  type="password"
                  value={getLocal(gi.id, 'auth_data', '')}
                  onChange={(e) => setLocal(gi.id, 'auth_data', e.target.value)}
                  className={`${inputClass} w-36 shrink-0`}
                  placeholder={gi.has_credentials ? '••••••' : 'Credentials'}
                />
              )}

              {/* Test button */}
              <button
                onClick={() => onTest(gi.id)}
                disabled={isTesting}
                className="px-3 py-1.5 text-[10px] font-bold text-[#07b6d5] border border-[#07b6d5]/20 rounded-lg hover:bg-[#07b6d5]/10 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shrink-0"
              >
                {isTesting ? 'Testing...' : 'Test'}
              </button>

              {/* Status */}
              <span className={`text-[10px] font-medium w-20 text-right shrink-0 ${status.classes}`}>
                {status.text}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default GlobalIntegrationsSection;
