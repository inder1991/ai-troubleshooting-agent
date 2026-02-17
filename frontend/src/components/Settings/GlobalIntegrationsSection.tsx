import React, { useState } from 'react';
import type { GlobalIntegration, GlobalIntegrationStatus } from '../../types/profiles';

interface GlobalIntegrationsSectionProps {
  integrations: GlobalIntegration[];
  onUpdate: (id: string, data: Record<string, unknown>) => void;
  onTest: (id: string) => Promise<void>;
  testingId: string | null;
  onAdd?: (data: Record<string, unknown>) => Promise<void>;
  onDelete?: (id: string) => Promise<void>;
  showAddForm?: boolean;
  onShowAddForm?: (show: boolean) => void;
  testResults?: Record<string, { reachable: boolean; latency_ms: number | null; error: string | null }>;
}

const serviceConfig: Record<string, { icon: string; bgColor: string; borderColor: string; textColor: string; displayName: string; subtitle: string }> = {
  elk: {
    icon: 'analytics',
    bgColor: 'bg-[#07b6d5]/10',
    borderColor: 'border-[#07b6d5]/20',
    textColor: 'text-[#07b6d5]',
    displayName: 'ELK / Log Stack',
    subtitle: 'Log Aggregation',
  },
  jira: {
    icon: 'task',
    bgColor: 'bg-blue-600/10',
    borderColor: 'border-blue-500/20',
    textColor: 'text-blue-400',
    displayName: 'Atlassian Jira',
    subtitle: 'Ticketing System',
  },
  confluence: {
    icon: 'menu_book',
    bgColor: 'bg-indigo-600/10',
    borderColor: 'border-indigo-500/20',
    textColor: 'text-indigo-400',
    displayName: 'Confluence',
    subtitle: 'Documentation',
  },
  remedy: {
    icon: 'corporate_fare',
    bgColor: 'bg-orange-600/10',
    borderColor: 'border-orange-500/20',
    textColor: 'text-orange-400',
    displayName: 'BMC Remedy',
    subtitle: 'Change Management',
  },
  github: {
    icon: 'code',
    bgColor: 'bg-slate-600/10',
    borderColor: 'border-slate-500/20',
    textColor: 'text-slate-400',
    displayName: 'GitHub Enterprise',
    subtitle: 'Version Control',
  },
};

const statusDisplay: Record<GlobalIntegrationStatus, { text: string; classes: string; dot?: boolean }> = {
  connected: { text: 'Connected', classes: 'text-green-500', dot: true },
  not_validated: { text: 'Not Validated', classes: 'text-[#8fc3cc]' },
  not_linked: { text: 'Not Linked', classes: 'text-[#8fc3cc]' },
  conn_error: { text: 'Conn. Error', classes: 'text-red-400' },
};

const inputClass = 'bg-[#0f2023] border border-[#224349] rounded-lg text-sm text-white focus:ring-1 focus:ring-[#07b6d5] placeholder-[#8fc3cc]/50';

/** Render auth credential fields based on the selected auth method */
function AuthFields({
  authMethod,
  username,
  password,
  token,
  onUsernameChange,
  onPasswordChange,
  onTokenChange,
  hasExistingCredentials,
}: {
  authMethod: string;
  username: string;
  password: string;
  token: string;
  onUsernameChange: (v: string) => void;
  onPasswordChange: (v: string) => void;
  onTokenChange: (v: string) => void;
  hasExistingCredentials?: boolean;
}) {
  if (authMethod === 'none') return null;

  if (authMethod === 'basic_auth') {
    return (
      <div className="flex items-center gap-2 flex-1 min-w-0 basis-[200px]">
        <input
          type="text"
          value={username}
          onChange={(e) => onUsernameChange(e.target.value)}
          className={`${inputClass} px-3 py-2 flex-1 min-w-0`}
          placeholder={hasExistingCredentials ? '••••••' : 'Username'}
        />
        <input
          type="password"
          value={password}
          onChange={(e) => onPasswordChange(e.target.value)}
          className={`${inputClass} px-3 py-2 flex-1 min-w-0`}
          placeholder={hasExistingCredentials ? '••••••' : 'Password'}
        />
      </div>
    );
  }

  // Bearer Token or API Key — single field
  const placeholder = authMethod === 'bearer_token' ? 'Bearer Token' : 'API Key';
  return (
    <input
      type="password"
      value={token}
      onChange={(e) => onTokenChange(e.target.value)}
      className={`${inputClass} px-4 py-2 flex-1 min-w-0 basis-[200px]`}
      placeholder={hasExistingCredentials ? '••••••••' : placeholder}
    />
  );
}

const GlobalIntegrationsSection: React.FC<GlobalIntegrationsSectionProps> = ({
  integrations,
  onUpdate,
  onTest,
  testingId,
  onAdd,
  onDelete,
  showAddForm,
  onShowAddForm,
  testResults,
}) => {
  const [localUpdates, setLocalUpdates] = useState<Record<string, Record<string, string>>>({});

  // Add form state
  const [newServiceType, setNewServiceType] = useState<string>('elk');
  const [newName, setNewName] = useState('');
  const [newUrl, setNewUrl] = useState('');
  const [newAuthMethod, setNewAuthMethod] = useState('none');
  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newToken, setNewToken] = useState('');
  const [newOrgs, setNewOrgs] = useState('');

  const getLocal = (id: string, field: string, fallback: string) => {
    return localUpdates[id]?.[field] ?? fallback;
  };

  const setLocal = (id: string, field: string, value: string) => {
    setLocalUpdates((prev) => ({
      ...prev,
      [id]: { ...(prev[id] || {}), [field]: value },
    }));
    // For auth credential fields, combine and send as auth_data
    if (field === '_username' || field === '_password') {
      const updates = { ...(localUpdates[id] || {}), [field]: value };
      const user = updates['_username'] || '';
      const pass = updates['_password'] || '';
      if (user || pass) {
        onUpdate(id, { auth_data: `${user}:${pass}` });
      }
    } else if (field === '_token') {
      onUpdate(id, { auth_data: value });
    } else {
      onUpdate(id, { [field]: value });
    }
  };

  /** Build auth_data from form fields */
  const buildAuthData = (method: string, username: string, password: string, token: string): string | undefined => {
    if (method === 'basic_auth') {
      return (username || password) ? `${username}:${password}` : undefined;
    }
    if (method === 'bearer_token' || method === 'api_key') {
      return token || undefined;
    }
    return undefined;
  };

  const handleAddSubmit = () => {
    if (!newName.trim() || !onAdd) return;
    const data: Record<string, unknown> = {
      service_type: newServiceType,
      name: newName.trim(),
      url: newUrl.trim(),
      auth_method: newAuthMethod,
      auth_data: buildAuthData(newAuthMethod, newUsername, newPassword, newToken),
    };
    if (newServiceType === 'github' && newOrgs.trim()) {
      data.config = { orgs: newOrgs.split(',').map((s) => s.trim()).filter(Boolean) };
    }
    onAdd(data);
    setNewName('');
    setNewUrl('');
    setNewAuthMethod('none');
    setNewUsername('');
    setNewPassword('');
    setNewToken('');
    setNewOrgs('');
    setNewServiceType('elk');
  };

  const addConfig = serviceConfig[newServiceType] || serviceConfig.elk;

  return (
    <section>
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-lg font-bold text-white">Global Ecosystem Integrations</h3>
        {onAdd && (
          <button
            onClick={() => onShowAddForm?.(!showAddForm)}
            className="flex items-center gap-2 bg-[#224349] text-white px-4 py-2 rounded-lg text-sm font-bold hover:bg-[#224349]/80 transition-colors border border-[#07b6d5]/20"
          >
            <span
              className="material-symbols-outlined text-[18px]"
              style={{ fontFamily: 'Material Symbols Outlined' }}
            >
              add_circle
            </span>
            Add Integration
          </button>
        )}
      </div>
      <p className="text-[#8fc3cc] text-sm mb-6">
        Manage shared services and enterprise ecosystem tools used across the global infrastructure.
      </p>

      {/* Add Integration Form */}
      {showAddForm && (
        <div className="p-5 bg-[#183034]/30 border border-[#07b6d5]/30 rounded-xl mb-4">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-3 min-w-[200px]">
              <div className={`w-10 h-10 ${addConfig.bgColor} rounded flex items-center justify-center border ${addConfig.borderColor} ${addConfig.textColor}`}>
                <span className="material-symbols-outlined" style={{ fontFamily: 'Material Symbols Outlined' }}>{addConfig.icon}</span>
              </div>
              <div>
                <select
                  value={newServiceType}
                  onChange={(e) => {
                    setNewServiceType(e.target.value);
                    if (e.target.value === 'github') {
                      setNewAuthMethod('bearer_token');
                    }
                  }}
                  className={`${inputClass} px-3 py-1.5 font-bold`}
                >
                  <option value="elk">ELK / Log Stack</option>
                  <option value="jira">Atlassian Jira</option>
                  <option value="confluence">Confluence</option>
                  <option value="remedy">BMC Remedy</option>
                  <option value="github">GitHub Enterprise</option>
                </select>
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className={`block mt-1 ${inputClass} px-3 py-1 text-xs w-full`}
                  placeholder="Display name"
                />
              </div>
            </div>

            <div className="flex-1 min-w-[300px]">
              <input
                type="url"
                value={newUrl}
                onChange={(e) => setNewUrl(e.target.value)}
                className={`w-full ${inputClass} px-4 py-2`}
                placeholder={`Endpoint URL (e.g., https://${newServiceType}.corp.net)`}
              />
              {newServiceType === 'github' && (
                <input
                  type="text"
                  value={newOrgs}
                  onChange={(e) => setNewOrgs(e.target.value)}
                  className={`w-full mt-2 ${inputClass} px-4 py-2 text-xs`}
                  placeholder="GitHub Orgs (comma-separated, e.g. org-a, org-b, org-c)"
                />
              )}
            </div>

            <div className="w-40">
              <select
                value={newAuthMethod}
                onChange={(e) => {
                  setNewAuthMethod(e.target.value);
                  setNewUsername('');
                  setNewPassword('');
                  setNewToken('');
                }}
                className={`w-full ${inputClass} px-3 py-2 text-xs text-[#8fc3cc]`}
              >
                <option value="none">No Auth</option>
                <option value="basic_auth">Basic Auth</option>
                <option value="bearer_token">Bearer Token</option>
                <option value="api_key">API Key</option>
              </select>
            </div>

            <AuthFields
              authMethod={newAuthMethod}
              username={newUsername}
              password={newPassword}
              token={newToken}
              onUsernameChange={setNewUsername}
              onPasswordChange={setNewPassword}
              onTokenChange={setNewToken}
            />

            <div className="flex items-center gap-2">
              <button
                onClick={handleAddSubmit}
                disabled={!newName.trim()}
                className="px-4 py-2 bg-[#07b6d5] text-[#0f2023] rounded-lg text-xs font-bold hover:bg-[#07b6d5]/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                Add
              </button>
              <button
                onClick={() => onShowAddForm?.(false)}
                className="px-4 py-2 text-[#8fc3cc] hover:text-white text-xs font-bold transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Integration Cards */}
      <div className="space-y-4">
        {integrations.map((gi) => {
          const config = serviceConfig[gi.service_type] || {
            icon: 'extension',
            bgColor: 'bg-gray-600/10',
            borderColor: 'border-gray-500/20',
            textColor: 'text-gray-400',
            displayName: gi.name,
            subtitle: gi.category || gi.service_type,
          };
          const status = statusDisplay[gi.status];
          const isTesting = testingId === gi.id;
          const testResult = testResults?.[gi.id];
          const currentAuth = getLocal(gi.id, 'auth_method', gi.auth_method);

          return (
            <div
              key={gi.id}
              className="p-5 bg-[#183034]/30 border border-[#224349] rounded-xl"
            >
              <div className="flex flex-wrap items-center gap-4">
                {/* Icon + Name */}
                <div className="flex items-center gap-3 min-w-[200px]">
                  <div className={`w-10 h-10 ${config.bgColor} rounded flex items-center justify-center border ${config.borderColor} ${config.textColor}`}>
                    <span className="material-symbols-outlined" style={{ fontFamily: 'Material Symbols Outlined' }}>{config.icon}</span>
                  </div>
                  <div>
                    <h4 className="font-bold text-sm text-white">{gi.name || config.displayName}</h4>
                    <span className="text-[10px] text-[#8fc3cc] uppercase tracking-widest">
                      {gi.category || config.subtitle}
                    </span>
                  </div>
                </div>

                {/* URL Input */}
                <div className="flex-1 min-w-[300px]">
                  <input
                    type="url"
                    value={getLocal(gi.id, 'url', gi.url)}
                    onChange={(e) => setLocal(gi.id, 'url', e.target.value)}
                    className={`w-full ${inputClass} px-4 py-2`}
                    placeholder={`${config.displayName} Endpoint URL (e.g., https://${gi.service_type}.corp.net)`}
                  />
                  {gi.service_type === 'github' && (
                    <div className="mt-2">
                      {(() => {
                        const orgs = (gi.config?.orgs as string[] | undefined) || [];
                        return orgs.length > 0 && (
                          <div className="flex flex-wrap gap-1 mb-1.5">
                            {orgs.map((org) => (
                              <span key={org} className="inline-flex items-center px-2 py-0.5 rounded bg-slate-600/20 border border-slate-500/20 text-[10px] text-slate-300 font-mono">
                                {org}
                              </span>
                            ))}
                          </div>
                        );
                      })()}
                      <input
                        type="text"
                        value={getLocal(gi.id, '_orgs', ((gi.config?.orgs as string[] | undefined) || []).join(', '))}
                        onChange={(e) => {
                          setLocal(gi.id, '_orgs', e.target.value);
                          const orgs = e.target.value.split(',').map((s) => s.trim()).filter(Boolean);
                          onUpdate(gi.id, { config: { orgs } });
                        }}
                        className={`w-full ${inputClass} px-4 py-1.5 text-xs`}
                        placeholder="GitHub Orgs (comma-separated, e.g. org-a, org-b)"
                      />
                    </div>
                  )}
                </div>

                {/* Auth Dropdown */}
                <div className="w-40">
                  <select
                    value={currentAuth}
                    onChange={(e) => {
                      setLocal(gi.id, 'auth_method', e.target.value);
                      // Clear credential fields when switching auth method
                      setLocalUpdates((prev) => ({
                        ...prev,
                        [gi.id]: {
                          ...(prev[gi.id] || {}),
                          auth_method: e.target.value,
                          _username: '',
                          _password: '',
                          _token: '',
                        },
                      }));
                    }}
                    className={`w-full ${inputClass} px-3 py-2 text-xs text-[#8fc3cc]`}
                  >
                    <option value="none">No Auth</option>
                    <option value="basic_auth">Basic Auth</option>
                    <option value="bearer_token">Bearer Token</option>
                    <option value="api_key">API Key</option>
                  </select>
                </div>

                {/* Auth Credential Fields */}
                <AuthFields
                  authMethod={currentAuth}
                  username={getLocal(gi.id, '_username', '')}
                  password={getLocal(gi.id, '_password', '')}
                  token={getLocal(gi.id, '_token', '')}
                  onUsernameChange={(v) => setLocal(gi.id, '_username', v)}
                  onPasswordChange={(v) => setLocal(gi.id, '_password', v)}
                  onTokenChange={(v) => setLocal(gi.id, '_token', v)}
                  hasExistingCredentials={gi.has_credentials}
                />

                {/* Test Connection + Status */}
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => onTest(gi.id)}
                    disabled={isTesting}
                    className="px-4 py-2 bg-[#07b6d5]/10 text-[#07b6d5] border border-[#07b6d5]/20 rounded-lg text-xs font-bold hover:bg-[#07b6d5]/20 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isTesting ? 'Testing...' : 'Test Connection'}
                  </button>

                  <span className={`text-[10px] font-bold uppercase flex items-center gap-1 ${status.classes}`}>
                    {status.dot && <span className="w-1.5 h-1.5 bg-green-500 rounded-full" />}
                    {status.text}
                  </span>

                  {testResult && (
                    <span className={`text-[9px] font-mono ${testResult.reachable ? 'text-green-400' : 'text-red-400'}`}>
                      {testResult.reachable
                        ? `${testResult.latency_ms}ms`
                        : testResult.error?.substring(0, 25)}
                    </span>
                  )}

                  {onDelete && (
                    <button
                      onClick={() => onDelete(gi.id)}
                      className="p-1.5 hover:bg-red-500/20 text-[#8fc3cc] hover:text-red-400 rounded transition-colors"
                      title="Delete integration"
                    >
                      <span
                        className="material-symbols-outlined text-[18px]"
                        style={{ fontFamily: 'Material Symbols Outlined' }}
                      >
                        delete
                      </span>
                    </button>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
};

export default GlobalIntegrationsSection;
