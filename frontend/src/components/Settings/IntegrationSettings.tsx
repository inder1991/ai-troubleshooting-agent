import React, { useState, useEffect, useCallback } from 'react';
import { ArrowLeft, Plus, Trash2, RefreshCw, Server, Activity } from 'lucide-react';
import type { Integration } from '../../types';
import {
  listIntegrations,
  addIntegration,
  deleteIntegration,
  probeIntegration,
} from '../../services/api';

interface IntegrationSettingsProps {
  onBack: () => void;
}

const statusColors: Record<string, string> = {
  active: 'bg-green-500',
  unreachable: 'bg-red-500',
  expired: 'bg-yellow-500',
};

const statusLabels: Record<string, string> = {
  active: 'Active',
  unreachable: 'Unreachable',
  expired: 'Expired',
};

const IntegrationSettings: React.FC<IntegrationSettingsProps> = ({ onBack }) => {
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [probing, setProbing] = useState<string | null>(null);

  // Form state
  const [formName, setFormName] = useState('');
  const [formClusterUrl, setFormClusterUrl] = useState('');
  const [formClusterType, setFormClusterType] = useState<'openshift' | 'kubernetes'>('openshift');
  const [formAuthMethod, setFormAuthMethod] = useState<'token' | 'kubeconfig'>('token');
  const [formAuthData, setFormAuthData] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  const loadIntegrations = useCallback(async () => {
    try {
      setLoading(true);
      const data = await listIntegrations();
      setIntegrations(data);
    } catch (err) {
      console.error('Failed to load integrations:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadIntegrations();
  }, [loadIntegrations]);

  const handleAdd = async () => {
    if (!formName.trim() || !formClusterUrl.trim() || !formAuthData.trim()) {
      setFormError('Name, Cluster URL, and Auth Data are required.');
      return;
    }
    setFormError(null);
    try {
      await addIntegration({
        name: formName,
        cluster_type: formClusterType,
        cluster_url: formClusterUrl,
        auth_method: formAuthMethod,
        auth_data: formAuthData,
      });
      setShowForm(false);
      setFormName('');
      setFormClusterUrl('');
      setFormAuthData('');
      await loadIntegrations();
    } catch (err) {
      setFormError('Failed to add integration.');
      console.error(err);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteIntegration(id);
      setIntegrations((prev) => prev.filter((i) => i.id !== id));
    } catch (err) {
      console.error('Failed to delete integration:', err);
    }
  };

  const handleProbe = async (id: string) => {
    try {
      setProbing(id);
      await probeIntegration(id);
      await loadIntegrations();
    } catch (err) {
      console.error('Failed to probe integration:', err);
    } finally {
      setProbing(null);
    }
  };

  const inputClass =
    'w-full px-3 py-2.5 bg-[#0f2023] border border-[#224349] rounded-lg text-sm text-white placeholder-gray-600 focus:border-[#07b6d5] focus:outline-none focus:ring-1 focus:ring-[#07b6d5]/30 transition-colors';

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="h-12 bg-[#1e2f33]/50 border-b border-[#224349] flex items-center px-4">
        <button
          onClick={onBack}
          className="text-gray-400 hover:text-white text-xs mr-3 transition-colors flex items-center gap-1"
        >
          <ArrowLeft className="w-3 h-3" />
          Home
        </button>
        <Server className="w-4 h-4 text-[#07b6d5] mr-2" />
        <h1 className="text-sm font-semibold text-white">Integration Settings</h1>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-3xl mx-auto space-y-6">
          {/* Header row */}
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-bold text-white">Cluster Integrations</h2>
              <p className="text-xs text-gray-500 mt-1">
                Connect your OpenShift or Kubernetes clusters for automated diagnostics.
              </p>
            </div>
            <button
              onClick={() => setShowForm(!showForm)}
              className="flex items-center gap-2 px-4 py-2 bg-[#07b6d5] hover:bg-[#07b6d5]/90 text-[#0f2023] rounded-lg text-sm font-bold transition-colors"
            >
              <Plus className="w-4 h-4" />
              Add Integration
            </button>
          </div>

          {/* Add form */}
          {showForm && (
            <div className="bg-[#0a1a1d] border border-[#224349] rounded-xl p-5 space-y-4">
              <h3 className="text-sm font-semibold text-white">New Integration</h3>

              <div>
                <label className="block text-xs text-gray-400 mb-1.5 font-medium">
                  Name <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  className={inputClass}
                  placeholder="e.g. Production OpenShift"
                />
              </div>

              <div>
                <label className="block text-xs text-gray-400 mb-1.5 font-medium">
                  Cluster URL <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  value={formClusterUrl}
                  onChange={(e) => setFormClusterUrl(e.target.value)}
                  className={inputClass}
                  placeholder="https://api.cluster.example.com:6443"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs text-gray-400 mb-1.5 font-medium">
                    Cluster Type
                  </label>
                  <select
                    value={formClusterType}
                    onChange={(e) =>
                      setFormClusterType(e.target.value as 'openshift' | 'kubernetes')
                    }
                    className={inputClass}
                  >
                    <option value="openshift">OpenShift</option>
                    <option value="kubernetes">Kubernetes</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1.5 font-medium">
                    Auth Method
                  </label>
                  <select
                    value={formAuthMethod}
                    onChange={(e) =>
                      setFormAuthMethod(e.target.value as 'token' | 'kubeconfig')
                    }
                    className={inputClass}
                  >
                    <option value="token">Token</option>
                    <option value="kubeconfig">Kubeconfig</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs text-gray-400 mb-1.5 font-medium">
                  {formAuthMethod === 'token' ? 'Auth Token' : 'Kubeconfig YAML'}{' '}
                  <span className="text-red-400">*</span>
                </label>
                <textarea
                  value={formAuthData}
                  onChange={(e) => setFormAuthData(e.target.value)}
                  rows={3}
                  className={`${inputClass} font-mono resize-none`}
                  placeholder={
                    formAuthMethod === 'token'
                      ? 'sha256~your-token-here...'
                      : 'Paste kubeconfig YAML...'
                  }
                />
              </div>

              {formError && (
                <p className="text-xs text-red-400">{formError}</p>
              )}

              <div className="flex gap-3 pt-1">
                <button
                  onClick={handleAdd}
                  className="px-4 py-2 bg-[#07b6d5] hover:bg-[#07b6d5]/90 text-[#0f2023] rounded-lg text-sm font-bold transition-colors"
                >
                  Save Integration
                </button>
                <button
                  onClick={() => {
                    setShowForm(false);
                    setFormError(null);
                  }}
                  className="px-4 py-2 bg-[#1e2f33] hover:bg-[#1e2f33]/80 text-gray-400 rounded-lg text-sm transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* Integration list */}
          {loading ? (
            <div className="text-center text-gray-500 text-sm py-8">Loading integrations...</div>
          ) : integrations.length === 0 ? (
            <div className="text-center text-gray-600 text-sm py-12 border border-dashed border-[#224349] rounded-xl">
              No integrations configured yet. Add one to get started.
            </div>
          ) : (
            <div className="space-y-3">
              {integrations.map((integration) => (
                <div
                  key={integration.id}
                  className="bg-[#0a1a1d] border border-[#224349] rounded-xl p-4"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <h3 className="text-sm font-semibold text-white truncate">
                          {integration.name}
                        </h3>
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium text-white ${statusColors[integration.status] || 'bg-gray-500'}`}
                        >
                          {statusLabels[integration.status] || integration.status}
                        </span>
                        <span className="text-[10px] text-gray-600 bg-[#1e2f33] px-2 py-0.5 rounded">
                          {integration.cluster_type}
                        </span>
                      </div>
                      <p className="text-xs text-gray-500 mt-1 font-mono truncate">
                        {integration.cluster_url}
                      </p>
                      {/* Discovered URLs */}
                      <div className="flex flex-wrap gap-3 mt-2">
                        {integration.prometheus_url && (
                          <span className="text-[10px] text-[#07b6d5] flex items-center gap-1">
                            <Activity className="w-3 h-3" />
                            Prometheus: {integration.prometheus_url}
                          </span>
                        )}
                        {integration.elasticsearch_url && (
                          <span className="text-[10px] text-[#07b6d5] flex items-center gap-1">
                            <Activity className="w-3 h-3" />
                            ELK: {integration.elasticsearch_url}
                          </span>
                        )}
                      </div>
                      {integration.last_verified && (
                        <p className="text-[10px] text-gray-600 mt-1">
                          Last verified: {new Date(integration.last_verified).toLocaleString()}
                        </p>
                      )}
                    </div>

                    <div className="flex items-center gap-2 ml-4 shrink-0">
                      <button
                        onClick={() => handleProbe(integration.id)}
                        disabled={probing === integration.id}
                        className="p-2 text-gray-400 hover:text-[#07b6d5] hover:bg-[#1e2f33] rounded-lg transition-colors disabled:opacity-50"
                        title="Re-probe cluster"
                      >
                        <RefreshCw
                          className={`w-4 h-4 ${probing === integration.id ? 'animate-spin' : ''}`}
                        />
                      </button>
                      <button
                        onClick={() => handleDelete(integration.id)}
                        className="p-2 text-gray-400 hover:text-red-400 hover:bg-[#1e2f33] rounded-lg transition-colors"
                        title="Delete integration"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default IntegrationSettings;
