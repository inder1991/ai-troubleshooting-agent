import React, { useState, useEffect } from 'react';
import type { ClusterDiagnosticsForm } from '../../../types';
import type { ClusterProfile } from '../../../types/profiles';
import { listProfiles } from '../../../services/profileApi';

interface ClusterDiagnosticsFieldsProps {
  data: ClusterDiagnosticsForm;
  onChange: (data: ClusterDiagnosticsForm) => void;
}

const namespaces = ['default', 'kube-system', 'monitoring', 'production', 'staging'];
const resourceTypes = ['All Resources', 'Pods', 'Deployments', 'Services', 'StatefulSets', 'DaemonSets', 'Nodes'];

const envBadge: Record<string, string> = {
  prod: 'text-red-400',
  staging: 'text-[#07b6d5]',
  dev: 'text-emerald-400',
};

const statusDot: Record<string, string> = {
  connected: 'bg-green-500',
  warning: 'bg-amber-500',
  unreachable: 'bg-red-500',
  pending_setup: 'bg-gray-500',
};

const ClusterDiagnosticsFields: React.FC<ClusterDiagnosticsFieldsProps> = ({ data, onChange }) => {
  const [profiles, setProfiles] = useState<ClusterProfile[]>([]);
  const [selectedProfile, setSelectedProfile] = useState<string>(data.profile_id || '');
  const [overrideAuth, setOverrideAuth] = useState(false);

  useEffect(() => {
    listProfiles()
      .then(setProfiles)
      .catch(() => {});
  }, []);

  const activeProfile = profiles.find((p) => p.id === selectedProfile);
  const hasStoredCreds = activeProfile?.has_cluster_credentials ?? false;
  const showAuthSection = !selectedProfile || overrideAuth || !hasStoredCreds;

  const handleProfileSelect = (profileId: string) => {
    setSelectedProfile(profileId);
    setOverrideAuth(false);
    if (profileId) {
      const profile = profiles.find((p) => p.id === profileId);
      if (profile) {
        onChange({
          ...data,
          profile_id: profileId,
          cluster_url: profile.cluster_url,
          auth_method: 'token',
          auth_token: undefined,
        });
      }
    } else {
      onChange({ ...data, profile_id: undefined });
    }
  };

  const update = (field: Partial<ClusterDiagnosticsForm>) => {
    onChange({ ...data, ...field });
  };

  return (
    <div className="space-y-4">
      {/* Select Cluster Profile */}
      {profiles.length > 0 && (
        <div>
          <label className="block text-xs text-gray-400 mb-1.5 font-medium">Select Cluster Profile</label>
          <select
            value={selectedProfile}
            onChange={(e) => handleProfileSelect(e.target.value)}
            className="w-full px-3 py-2.5 bg-[#0f2023] border border-[#224349] rounded-lg text-sm text-white focus:border-[#07b6d5] focus:outline-none focus:ring-1 focus:ring-[#07b6d5]/30 transition-colors"
          >
            <option value="">-- Manual Entry --</option>
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} [{p.environment}] {p.status === 'connected' ? '' : `(${p.status})`}
              </option>
            ))}
          </select>
          {selectedProfile && activeProfile && (
            <div className="flex items-center gap-2 mt-1.5 text-[10px]">
              <span className={`w-1.5 h-1.5 rounded-full ${statusDot[activeProfile.status] || 'bg-gray-500'}`} />
              <span className={envBadge[activeProfile.environment] || 'text-gray-400'}>{activeProfile.environment}</span>
              <span className="text-gray-600 font-mono">{activeProfile.cluster_url}</span>
              {hasStoredCreds && !overrideAuth && (
                <>
                  <span className="material-symbols-outlined text-green-500 text-[12px]">shield</span>
                  <span className="text-green-500">Credentials stored</span>
                  <button
                    type="button"
                    onClick={() => setOverrideAuth(true)}
                    className="text-[#07b6d5] hover:underline ml-1"
                  >
                    Override
                  </button>
                </>
              )}
              {overrideAuth && (
                <>
                  <span className="text-amber-400">Using manual credentials</span>
                  <button
                    type="button"
                    onClick={() => {
                      setOverrideAuth(false);
                      update({ auth_token: undefined });
                    }}
                    className="text-[#07b6d5] hover:underline ml-1"
                  >
                    Use stored
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      )}

      {/* Auth Section — hidden when profile has stored credentials (unless override) */}
      {showAuthSection && (
        <>
          {/* Cluster API URL */}
          {!selectedProfile && (
            <div>
              <label className="block text-xs text-gray-400 mb-1.5 font-medium">
                Cluster API URL <span className="text-red-400">*</span>
              </label>
              <input
                type="text"
                value={data.cluster_url}
                onChange={(e) => update({ cluster_url: e.target.value })}
                className="w-full px-3 py-2.5 bg-[#0f2023] border border-[#224349] rounded-lg text-sm text-white placeholder-gray-600 focus:border-[#07b6d5] focus:outline-none focus:ring-1 focus:ring-[#07b6d5]/30 transition-colors"
                placeholder="https://api.cluster.example.com:6443"
                required
              />
            </div>
          )}

          {/* Auth Method Toggle */}
          <div>
            <label className="block text-xs text-gray-400 mb-2 font-medium">Auth Method</label>
            <div className="grid grid-cols-2 gap-2">
              {(['token', 'kubeconfig'] as const).map((method) => {
                const active = (data.auth_method || 'token') === method;
                return (
                  <button
                    key={method}
                    type="button"
                    onClick={() => update({ auth_method: method })}
                    className={`px-3 py-2 rounded-lg border text-xs font-medium transition-all ${
                      active
                        ? 'bg-[#07b6d5]/10 border-[#07b6d5]/30 text-[#07b6d5]'
                        : 'bg-[#0f2023] border-[#224349] text-gray-400 hover:text-gray-300'
                    }`}
                  >
                    {method === 'token' ? 'Auth Token' : 'Kubeconfig'}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Auth Token / Kubeconfig */}
          <div>
            <label className="block text-xs text-gray-400 mb-1.5 font-medium">
              {(data.auth_method || 'token') === 'token' ? 'Bearer Token' : 'Kubeconfig Contents'}
            </label>
            <textarea
              value={data.auth_token || ''}
              onChange={(e) => update({ auth_token: e.target.value || undefined })}
              rows={3}
              className="w-full px-3 py-2.5 bg-[#0f2023] border border-[#224349] rounded-lg text-sm text-white placeholder-gray-600 focus:border-[#07b6d5] focus:outline-none focus:ring-1 focus:ring-[#07b6d5]/30 transition-colors font-mono resize-none"
              placeholder={
                (data.auth_method || 'token') === 'token'
                  ? 'eyJhbGciOi...'
                  : 'Paste kubeconfig YAML...'
              }
            />
            {/* Kubeconfig file upload */}
            {(data.auth_method || 'token') === 'kubeconfig' && (
              <label className="flex items-center gap-1.5 mt-1.5 cursor-pointer text-[10px] text-[#07b6d5] hover:text-[#07b6d5]/80 transition-colors">
                <span className="material-symbols-outlined text-[14px]">upload_file</span>
                <span>Upload .kubeconfig</span>
                <input
                  type="file"
                  accept=".yaml,.yml,.kubeconfig"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) {
                      const reader = new FileReader();
                      reader.onload = (ev) => {
                        const contents = ev.target?.result as string;
                        if (contents) update({ auth_token: contents });
                      };
                      reader.readAsText(file);
                    }
                    e.target.value = '';
                  }}
                />
              </label>
            )}
          </div>
        </>
      )}

      {/* Save This Cluster — only shown in manual entry mode (no profile selected) */}
      {!selectedProfile && (
        <div className="border border-[#224349] rounded-lg p-3 bg-[#0f2023]/50">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={data.save_cluster ?? true}
              onChange={(e) => update({ save_cluster: e.target.checked })}
              className="w-3.5 h-3.5 rounded border-[#224349] bg-[#0f2023] text-[#07b6d5] focus:ring-[#07b6d5]/30"
            />
            <span className="text-xs text-gray-300">Save this cluster for future diagnostics</span>
          </label>
          {(data.save_cluster ?? true) && (
            <input
              type="text"
              value={data.cluster_name || ''}
              onChange={(e) => update({ cluster_name: e.target.value })}
              className="w-full mt-2 px-3 py-2 bg-[#0f2023] border border-[#224349] rounded-lg text-sm text-white placeholder-gray-600 focus:border-[#07b6d5] focus:outline-none focus:ring-1 focus:ring-[#07b6d5]/30 transition-colors"
              placeholder="Cluster name (e.g. prod-east-1)"
            />
          )}
        </div>
      )}

      {/* Target Namespace */}
      <div>
        <label className="block text-xs text-gray-400 mb-1.5 font-medium">Target Namespace</label>
        <select
          value={data.namespace || ''}
          onChange={(e) => update({ namespace: e.target.value || undefined })}
          className="w-full px-3 py-2.5 bg-[#0f2023] border border-[#224349] rounded-lg text-sm text-white focus:border-[#07b6d5] focus:outline-none focus:ring-1 focus:ring-[#07b6d5]/30 transition-colors"
        >
          <option value="">All Namespaces</option>
          {namespaces.map((ns) => (
            <option key={ns} value={ns}>
              {ns}
            </option>
          ))}
        </select>
      </div>

      {/* Resource Type */}
      <div>
        <label className="block text-xs text-gray-400 mb-1.5 font-medium">Resource Type</label>
        <select
          value={data.resource_type || ''}
          onChange={(e) => update({ resource_type: e.target.value || undefined })}
          className="w-full px-3 py-2.5 bg-[#0f2023] border border-[#224349] rounded-lg text-sm text-white focus:border-[#07b6d5] focus:outline-none focus:ring-1 focus:ring-[#07b6d5]/30 transition-colors"
        >
          <option value="">All Resources</option>
          {resourceTypes.filter((r) => r !== 'All Resources').map((rt) => (
            <option key={rt} value={rt.toLowerCase()}>
              {rt}
            </option>
          ))}
        </select>
      </div>

      {/* Symptoms */}
      <div>
        <label className="block text-xs text-gray-400 mb-1.5 font-medium">Symptoms Description</label>
        <textarea
          value={data.symptoms || ''}
          onChange={(e) => update({ symptoms: e.target.value || undefined })}
          rows={2}
          className="w-full px-3 py-2.5 bg-[#0f2023] border border-[#224349] rounded-lg text-sm text-white placeholder-gray-600 focus:border-[#07b6d5] focus:outline-none focus:ring-1 focus:ring-[#07b6d5]/30 transition-colors resize-none"
          placeholder="Describe the observed symptoms..."
        />
      </div>
    </div>
  );
};

export default ClusterDiagnosticsFields;
