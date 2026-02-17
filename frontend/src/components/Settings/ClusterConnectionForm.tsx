import React, { useState } from 'react';
import type { ClusterProfile, EndpointConfig } from '../../types/profiles';
import EndpointSection from './EndpointSection';

interface ClusterConnectionFormProps {
  profile?: ClusterProfile | null;
  onSave: (data: Record<string, unknown>) => Promise<void>;
  onCancel: () => void;
  onTestEndpoint: (profileId: string, endpointName: string) => Promise<void>;
  testingEndpoint: string | null;
}

const ClusterConnectionForm: React.FC<ClusterConnectionFormProps> = ({
  profile,
  onSave,
  onCancel,
  onTestEndpoint,
  testingEndpoint,
}) => {
  const [name, setName] = useState(profile?.name || '');
  const [displayName, setDisplayName] = useState(profile?.display_name || '');
  const [clusterType, setClusterType] = useState<'openshift' | 'kubernetes'>(
    profile?.cluster_type || 'openshift'
  );
  const [clusterUrl, setClusterUrl] = useState(profile?.cluster_url || '');
  const [environment, setEnvironment] = useState(profile?.environment || 'dev');
  const [authMethod, setAuthMethod] = useState(profile?.has_cluster_credentials ? 'token' : 'token');
  const [authData, setAuthData] = useState('');
  const [saving, setSaving] = useState(false);

  // Endpoint state
  const [endpointUpdates, setEndpointUpdates] = useState<Record<string, Record<string, unknown>>>({});

  const handleEndpointUpdate = (endpointName: string, data: Partial<EndpointConfig> & { auth_data?: string }) => {
    setEndpointUpdates((prev) => ({
      ...prev,
      [endpointName]: { ...(prev[endpointName] || {}), ...data },
    }));
  };

  const handleTestEndpoint = async (endpointName: string) => {
    if (profile?.id) {
      await onTestEndpoint(profile.id, endpointName);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave({
        name,
        display_name: displayName || null,
        cluster_type: clusterType,
        cluster_url: clusterUrl,
        environment,
        auth_method: authMethod,
        auth_data: authData || undefined,
        endpoints: Object.keys(endpointUpdates).length > 0 ? endpointUpdates : undefined,
      });
    } finally {
      setSaving(false);
    }
  };

  const inputClass =
    'w-full px-3 py-2 bg-[#0f2023] border border-[#224349] rounded-lg text-sm text-white placeholder-gray-600 focus:border-[#07b6d5] focus:outline-none focus:ring-1 focus:ring-[#07b6d5]/30 transition-colors';

  return (
    <div className="bg-[#0a1a1d] border border-[#224349] rounded-xl p-5 space-y-5">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold text-white">
          {profile ? 'Edit Cluster Connection' : 'Add Cluster Connection'}
        </h3>
        <button
          onClick={onCancel}
          className="text-gray-500 hover:text-white transition-colors"
        >
          <span
            className="material-symbols-outlined text-lg"
            style={{ fontFamily: 'Material Symbols Outlined' }}
          >
            close
          </span>
        </button>
      </div>

      {/* Profile identity */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-[10px] text-gray-500 mb-1 uppercase tracking-wider font-medium">
            Cluster Profile Name <span className="text-red-400">*</span>
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={inputClass}
            placeholder="e.g. Production-US"
          />
        </div>
        <div>
          <label className="block text-[10px] text-gray-500 mb-1 uppercase tracking-wider font-medium">
            Display Name
          </label>
          <input
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            className={inputClass}
            placeholder="Optional display name"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <label className="block text-[10px] text-gray-500 mb-1 uppercase tracking-wider font-medium">
            Cluster URL <span className="text-red-400">*</span>
          </label>
          <input
            type="text"
            value={clusterUrl}
            onChange={(e) => setClusterUrl(e.target.value)}
            className={inputClass}
            placeholder="https://api.cluster.example.com:6443"
          />
        </div>
        <div>
          <label className="block text-[10px] text-gray-500 mb-1 uppercase tracking-wider font-medium">
            Cluster Type
          </label>
          <select
            value={clusterType}
            onChange={(e) => setClusterType(e.target.value as 'openshift' | 'kubernetes')}
            className={inputClass}
          >
            <option value="openshift">OpenShift</option>
            <option value="kubernetes">Kubernetes</option>
          </select>
        </div>
        <div>
          <label className="block text-[10px] text-gray-500 mb-1 uppercase tracking-wider font-medium">
            Environment
          </label>
          <select
            value={environment}
            onChange={(e) => setEnvironment(e.target.value as 'prod' | 'staging' | 'dev')}
            className={inputClass}
          >
            <option value="prod">Production</option>
            <option value="staging">Staging</option>
            <option value="dev">Development</option>
          </select>
        </div>
      </div>

      {/* Cluster auth */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-[10px] text-gray-500 mb-1 uppercase tracking-wider font-medium">
            Auth Method
          </label>
          <select
            value={authMethod}
            onChange={(e) => setAuthMethod(e.target.value)}
            className={inputClass}
          >
            <option value="token">Token</option>
            <option value="kubeconfig">Kubeconfig</option>
            <option value="service_account">Service Account</option>
          </select>
        </div>
        <div>
          <label className="block text-[10px] text-gray-500 mb-1 uppercase tracking-wider font-medium">
            Credentials {profile?.has_cluster_credentials && <span className="text-gray-600">(leave blank to keep existing)</span>}
          </label>
          <input
            type="password"
            value={authData}
            onChange={(e) => setAuthData(e.target.value)}
            className={inputClass}
            placeholder={profile?.has_cluster_credentials ? '••••••••' : 'sha256~...'}
          />
        </div>
      </div>

      {/* Endpoint sections */}
      <div className="space-y-3 pt-2">
        <EndpointSection
          icon="settings_input_component"
          label="OpenShift API"
          endpointName="openshift_api"
          endpoint={profile?.endpoints?.openshift_api ?? null}
          authOptions={[
            { value: 'bearer_token', label: 'Bearer Token' },
            { value: 'certificate', label: 'Certificate' },
          ]}
          onTest={handleTestEndpoint}
          onUpdate={handleEndpointUpdate}
          testing={testingEndpoint === 'openshift_api'}
        />

        <EndpointSection
          icon="monitoring"
          label="Prometheus Endpoint"
          endpointName="prometheus"
          endpoint={profile?.endpoints?.prometheus ?? null}
          authOptions={[
            { value: 'bearer_token', label: 'Bearer Token' },
            { value: 'basic_auth', label: 'Basic Auth' },
          ]}
          onTest={handleTestEndpoint}
          onUpdate={handleEndpointUpdate}
          testing={testingEndpoint === 'prometheus'}
        />

        <EndpointSection
          icon="account_tree"
          label="Jaeger / Tracing"
          endpointName="jaeger"
          endpoint={profile?.endpoints?.jaeger ?? null}
          authOptions={[
            { value: 'bearer_token', label: 'Bearer Token' },
            { value: 'tls_cert', label: 'TLS Certificate' },
          ]}
          onTest={handleTestEndpoint}
          onUpdate={handleEndpointUpdate}
          testing={testingEndpoint === 'jaeger'}
        />
      </div>

      {/* Form actions */}
      <div className="flex gap-3 pt-2">
        <button
          onClick={handleSave}
          disabled={!name.trim() || saving}
          className="px-5 py-2 bg-[#07b6d5] hover:bg-[#07b6d5]/90 text-[#0f2023] rounded-lg text-sm font-bold transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {saving ? 'Saving...' : profile ? 'Update Profile' : 'Create Profile'}
        </button>
        <button
          onClick={onCancel}
          className="px-4 py-2 bg-[#1e2f33] hover:bg-[#1e2f33]/80 text-gray-400 rounded-lg text-sm transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  );
};

export default ClusterConnectionForm;
