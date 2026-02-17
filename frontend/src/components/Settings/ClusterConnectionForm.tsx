import React, { useState } from 'react';
import type { ClusterProfile, EndpointConfig } from '../../types/profiles';
import EndpointSection from './EndpointSection';

interface ClusterConnectionFormProps {
  profile?: ClusterProfile | null;
  onSave: (data: Record<string, unknown>) => Promise<void>;
  onCancel: () => void;
  onTestEndpoint: (profileId: string, endpointName: string) => Promise<void>;
  onProbe?: (profileId: string) => Promise<void>;
  testingEndpoint: string | null;
  probingId?: string | null;
}

const ClusterConnectionForm: React.FC<ClusterConnectionFormProps> = ({
  profile,
  onSave,
  onCancel,
  onTestEndpoint,
  onProbe,
  testingEndpoint,
  probingId,
}) => {
  const [name, setName] = useState(profile?.name || '');
  const [clusterType, setClusterType] = useState<'openshift' | 'kubernetes'>(
    profile?.cluster_type || 'openshift'
  );
  const [clusterUrl, setClusterUrl] = useState(profile?.cluster_url || '');
  const [environment, setEnvironment] = useState(profile?.environment || 'dev');
  const [authMethod, setAuthMethod] = useState(
    profile?.has_cluster_credentials ? 'token' : 'token'
  );
  const [authToken, setAuthToken] = useState('');
  const [kubeconfigData, setKubeconfigData] = useState('');
  const [saving, setSaving] = useState(false);

  // Endpoint state
  const [endpointUpdates, setEndpointUpdates] = useState<
    Record<string, Record<string, unknown>>
  >({});

  const handleEndpointUpdate = (
    endpointName: string,
    data: Partial<EndpointConfig> & { auth_data?: string }
  ) => {
    setEndpointUpdates((prev) => ({
      ...prev,
      [endpointName]: { ...(prev[endpointName] || {}), ...data },
    }));
  };

  const [unsavedTestWarning, setUnsavedTestWarning] = useState('');

  const handleTestEndpoint = async (endpointName: string) => {
    if (!profile?.id) {
      setUnsavedTestWarning('Save the profile first to test endpoints');
      setTimeout(() => setUnsavedTestWarning(''), 3000);
      return;
    }
    setUnsavedTestWarning('');
    await onTestEndpoint(profile.id, endpointName);
  };

  const handleProbeCluster = async () => {
    if (!profile?.id || !onProbe) return;
    await onProbe(profile.id);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const credentialData =
        authMethod === 'kubeconfig' ? kubeconfigData : authToken;
      await onSave({
        name,
        cluster_type: clusterType,
        cluster_url: clusterUrl,
        environment,
        auth_method: authMethod,
        auth_data: credentialData || undefined,
        endpoints:
          Object.keys(endpointUpdates).length > 0
            ? endpointUpdates
            : undefined,
      });
    } finally {
      setSaving(false);
    }
  };

  const inputClass =
    'w-full px-3 py-2 bg-[#0f2023] border border-[#224349] rounded-lg text-sm text-white placeholder-gray-600 focus:border-[#07b6d5] focus:outline-none focus:ring-1 focus:ring-[#07b6d5]/30 transition-colors';

  const openshiftApiEndpoint = profile?.endpoints?.openshift_api ?? null;
  const openshiftStatus = openshiftApiEndpoint?.status || 'unknown';

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
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <label className="block text-[10px] text-gray-500 mb-1 uppercase tracking-wider font-medium">
            Profile Name <span className="text-red-400">*</span>
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
            Cluster Type
          </label>
          <select
            value={clusterType}
            onChange={(e) =>
              setClusterType(e.target.value as 'openshift' | 'kubernetes')
            }
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
            onChange={(e) =>
              setEnvironment(e.target.value as 'prod' | 'staging' | 'dev')
            }
            className={inputClass}
          >
            <option value="prod">Production</option>
            <option value="staging">Staging</option>
            <option value="dev">Development</option>
          </select>
        </div>
      </div>

      {/* Cluster URL */}
      <div>
        <label className="block text-[10px] text-gray-500 mb-1 uppercase tracking-wider font-medium">
          Cluster API URL <span className="text-red-400">*</span>
        </label>
        <input
          type="text"
          value={clusterUrl}
          onChange={(e) => setClusterUrl(e.target.value)}
          className={inputClass}
          placeholder="https://api.cluster.example.com:6443"
        />
      </div>

      {/* Cluster auth */}
      <div>
        <label className="block text-[10px] text-gray-500 mb-1 uppercase tracking-wider font-medium">
          Authentication Method
        </label>
        <select
          value={authMethod}
          onChange={(e) => {
            setAuthMethod(e.target.value);
            setAuthToken('');
            setKubeconfigData('');
          }}
          className={`${inputClass} md:w-64`}
        >
          <option value="token">Bearer Token</option>
          <option value="kubeconfig">Kubeconfig</option>
          <option value="service_account">Service Account</option>
        </select>
      </div>

      {/* Credential input — varies by auth method */}
      {authMethod === 'kubeconfig' ? (
        <div>
          <label className="block text-[10px] text-gray-500 mb-1 uppercase tracking-wider font-medium">
            Kubeconfig{' '}
            {profile?.has_cluster_credentials && (
              <span className="text-gray-600 normal-case tracking-normal">
                (leave blank to keep existing)
              </span>
            )}
          </label>
          <textarea
            value={kubeconfigData}
            onChange={(e) => setKubeconfigData(e.target.value)}
            className={`${inputClass} h-32 font-mono text-xs`}
            placeholder={
              profile?.has_cluster_credentials
                ? '••••••••  (existing kubeconfig stored)'
                : 'Paste kubeconfig YAML contents here...'
            }
          />
        </div>
      ) : (
        <div>
          <label className="block text-[10px] text-gray-500 mb-1 uppercase tracking-wider font-medium">
            {authMethod === 'service_account'
              ? 'Service Account Token'
              : 'Bearer Token'}{' '}
            {profile?.has_cluster_credentials && (
              <span className="text-gray-600 normal-case tracking-normal">
                (leave blank to keep existing)
              </span>
            )}
          </label>
          <input
            type="password"
            value={authToken}
            onChange={(e) => setAuthToken(e.target.value)}
            className={inputClass}
            placeholder={
              profile?.has_cluster_credentials ? '••••••••' : 'sha256~...'
            }
          />
        </div>
      )}

      {/* Cluster API — summary with test button */}
      <div className="p-4 rounded-lg bg-[#0a1a1d]/40 border border-[#224349]/50">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <span
              className="material-symbols-outlined text-[#07b6d5] text-lg"
              style={{ fontFamily: 'Material Symbols Outlined' }}
            >
              settings_input_component
            </span>
            <span className="text-xs font-bold text-white uppercase tracking-wider">
              {clusterType === 'openshift' ? 'OpenShift' : 'Kubernetes'} API
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span
              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium border ${
                openshiftStatus === 'healthy'
                  ? 'text-green-500 bg-green-500/10 border-green-500/20'
                  : openshiftStatus === 'unreachable' ||
                      openshiftStatus === 'connection_failed'
                    ? 'text-red-500 bg-red-500/10 border-red-500/20'
                    : 'text-gray-500 bg-gray-500/10 border-gray-500/20'
              }`}
            >
              {openshiftStatus === 'healthy'
                ? 'Connected'
                : openshiftStatus === 'unknown'
                  ? 'Not Tested'
                  : openshiftStatus.replace(/_/g, ' ')}
            </span>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className="block text-[10px] text-gray-500 mb-1 uppercase tracking-wider">
              Endpoint
            </label>
            <div className="px-3 py-2 bg-[#0f2023]/50 border border-[#224349]/30 rounded-lg text-sm text-gray-400 truncate">
              {clusterUrl || 'Not configured'}
            </div>
          </div>
          <div>
            <label className="block text-[10px] text-gray-500 mb-1 uppercase tracking-wider">
              Authentication
            </label>
            <div className="px-3 py-2 bg-[#0f2023]/50 border border-[#224349]/30 rounded-lg text-sm text-gray-400">
              {authMethod === 'kubeconfig'
                ? 'Kubeconfig'
                : authMethod === 'service_account'
                  ? 'Service Account'
                  : 'Bearer Token'}
            </div>
          </div>
          <div>
            <label className="block text-[10px] text-gray-500 mb-1 uppercase tracking-wider">
              &nbsp;
            </label>
            <button
              onClick={handleProbeCluster}
              disabled={!profile?.id || !clusterUrl || probingId === profile?.id}
              className="w-full px-4 py-2 text-xs font-bold text-[#07b6d5] bg-[#07b6d5]/10 border border-[#07b6d5]/20 rounded-lg hover:bg-[#07b6d5]/20 disabled:text-gray-600 disabled:bg-transparent disabled:border-[#224349] disabled:cursor-not-allowed transition-colors"
              title={!profile?.id ? 'Save profile first to test connection' : 'Test cluster connectivity and auto-discover endpoints'}
            >
              {probingId === profile?.id ? (
                <span className="flex items-center justify-center gap-1.5">
                  <span
                    className="material-symbols-outlined text-sm animate-spin"
                    style={{ fontFamily: 'Material Symbols Outlined' }}
                  >
                    progress_activity
                  </span>
                  Testing...
                </span>
              ) : (
                <span className="flex items-center justify-center gap-1.5">
                  <span
                    className="material-symbols-outlined text-sm"
                    style={{ fontFamily: 'Material Symbols Outlined' }}
                  >
                    cable
                  </span>
                  Test Connection
                </span>
              )}
            </button>
          </div>
        </div>
        {!profile?.id && clusterUrl && (
          <p className="mt-2 text-[10px] text-amber-500/80">
            Save the profile first, then test connection
          </p>
        )}
      </div>

      {/* Unsaved warning for endpoint tests */}
      {unsavedTestWarning && (
        <div className="px-3 py-2 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 text-[11px] font-medium">
          {unsavedTestWarning}
        </div>
      )}

      {/* Observability endpoints */}
      <div className="space-y-3">
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
            { value: 'basic_auth', label: 'Basic Auth' },
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
