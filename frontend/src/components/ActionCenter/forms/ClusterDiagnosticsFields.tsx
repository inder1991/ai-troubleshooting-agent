import React from 'react';
import type { ClusterDiagnosticsForm } from '../../../types';

interface ClusterDiagnosticsFieldsProps {
  data: ClusterDiagnosticsForm;
  onChange: (data: ClusterDiagnosticsForm) => void;
}

const namespaces = ['default', 'kube-system', 'monitoring', 'production', 'staging'];
const resourceTypes = ['All Resources', 'Pods', 'Deployments', 'Services', 'StatefulSets', 'DaemonSets', 'Nodes'];

const ClusterDiagnosticsFields: React.FC<ClusterDiagnosticsFieldsProps> = ({ data, onChange }) => {
  const update = (field: Partial<ClusterDiagnosticsForm>) => {
    onChange({ ...data, ...field });
  };

  return (
    <div className="space-y-4">
      {/* Cluster API URL */}
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

      {/* Auth Token */}
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
      </div>

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
