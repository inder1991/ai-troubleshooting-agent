import React, { useState, useEffect } from 'react';
import type { TroubleshootAppForm, Integration } from '../../../types';
import { listIntegrations } from '../../../services/api';

interface TroubleshootAppFieldsProps {
  data: TroubleshootAppForm;
  onChange: (data: TroubleshootAppForm) => void;
}

const TroubleshootAppFields: React.FC<TroubleshootAppFieldsProps> = ({ data, onChange }) => {
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [selectedIntegration, setSelectedIntegration] = useState<string>('');

  useEffect(() => {
    listIntegrations()
      .then(setIntegrations)
      .catch(() => {});
  }, []);

  const handleIntegrationSelect = (integrationId: string) => {
    setSelectedIntegration(integrationId);
    if (integrationId) {
      const integration = integrations.find((i) => i.id === integrationId);
      if (integration) {
        onChange({ ...data, namespace: integration.cluster_url });
      }
    }
  };

  const update = (field: Partial<TroubleshootAppForm>) => {
    onChange({ ...data, ...field });
  };

  return (
    <div className="space-y-4">
      {/* Select Cluster */}
      {integrations.length > 0 && (
        <div>
          <label className="block text-xs text-gray-400 mb-1.5 font-medium">Select Cluster</label>
          <select
            value={selectedIntegration}
            onChange={(e) => handleIntegrationSelect(e.target.value)}
            className="w-full px-3 py-2.5 bg-[#0f2023] border border-[#224349] rounded-lg text-sm text-white focus:border-[#07b6d5] focus:outline-none focus:ring-1 focus:ring-[#07b6d5]/30 transition-colors"
          >
            <option value="">-- Manual Entry --</option>
            {integrations.map((i) => (
              <option key={i.id} value={i.id}>
                {i.name} ({i.cluster_type})
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Service Name */}
      <div>
        <label className="block text-xs text-gray-400 mb-1.5 font-medium">
          Service Name <span className="text-red-400">*</span>
        </label>
        <input
          type="text"
          value={data.service_name}
          onChange={(e) => update({ service_name: e.target.value })}
          className="w-full px-3 py-2.5 bg-[#0f2023] border border-[#224349] rounded-lg text-sm text-white placeholder-gray-600 focus:border-[#07b6d5] focus:outline-none focus:ring-1 focus:ring-[#07b6d5]/30 transition-colors"
          placeholder="e.g. payment-service"
          required
        />
      </div>

      {/* Time Window */}
      <div>
        <label className="block text-xs text-gray-400 mb-1.5 font-medium">Time Window</label>
        <select
          value={data.time_window}
          onChange={(e) => update({ time_window: e.target.value })}
          className="w-full px-3 py-2.5 bg-[#0f2023] border border-[#224349] rounded-lg text-sm text-white focus:border-[#07b6d5] focus:outline-none focus:ring-1 focus:ring-[#07b6d5]/30 transition-colors"
        >
          <option value="15m">15 minutes</option>
          <option value="30m">30 minutes</option>
          <option value="1h">1 hour</option>
          <option value="3h">3 hours</option>
          <option value="6h">6 hours</option>
          <option value="24h">24 hours</option>
        </select>
      </div>

      {/* Trace ID */}
      <div>
        <label className="block text-xs text-gray-400 mb-1.5 font-medium">Trace ID</label>
        <input
          type="text"
          value={data.trace_id || ''}
          onChange={(e) => update({ trace_id: e.target.value || undefined })}
          className="w-full px-3 py-2.5 bg-[#0f2023] border border-[#224349] rounded-lg text-sm text-white placeholder-gray-600 focus:border-[#07b6d5] focus:outline-none focus:ring-1 focus:ring-[#07b6d5]/30 transition-colors font-mono"
          placeholder="abc123def456..."
        />
      </div>

      {/* Namespace */}
      <div>
        <label className="block text-xs text-gray-400 mb-1.5 font-medium">Namespace</label>
        <input
          type="text"
          value={data.namespace || ''}
          onChange={(e) => update({ namespace: e.target.value || undefined })}
          className="w-full px-3 py-2.5 bg-[#0f2023] border border-[#224349] rounded-lg text-sm text-white placeholder-gray-600 focus:border-[#07b6d5] focus:outline-none focus:ring-1 focus:ring-[#07b6d5]/30 transition-colors"
          placeholder="production"
        />
      </div>

      {/* ELK Index */}
      <div>
        <label className="block text-xs text-gray-400 mb-1.5 font-medium">ELK Index</label>
        <input
          type="text"
          value={data.elk_index || ''}
          onChange={(e) => update({ elk_index: e.target.value || undefined })}
          className="w-full px-3 py-2.5 bg-[#0f2023] border border-[#224349] rounded-lg text-sm text-white placeholder-gray-600 focus:border-[#07b6d5] focus:outline-none focus:ring-1 focus:ring-[#07b6d5]/30 transition-colors font-mono"
          placeholder="app-logs-*"
        />
      </div>

      {/* Repo URL */}
      <div>
        <label className="block text-xs text-gray-400 mb-1.5 font-medium">Repository URL</label>
        <input
          type="text"
          value={data.repo_url || ''}
          onChange={(e) => update({ repo_url: e.target.value || undefined })}
          className="w-full px-3 py-2.5 bg-[#0f2023] border border-[#224349] rounded-lg text-sm text-white placeholder-gray-600 focus:border-[#07b6d5] focus:outline-none focus:ring-1 focus:ring-[#07b6d5]/30 transition-colors"
          placeholder="https://github.com/org/repo"
        />
      </div>
    </div>
  );
};

export default TroubleshootAppFields;
