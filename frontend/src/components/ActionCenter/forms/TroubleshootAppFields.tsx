import React, { useState, useEffect } from 'react';
import type { TroubleshootAppForm } from '../../../types';
import type { ClusterProfile } from '../../../types/profiles';
import { listProfiles } from '../../../services/profileApi';

interface TroubleshootAppFieldsProps {
  data: TroubleshootAppForm;
  onChange: (data: TroubleshootAppForm) => void;
}

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

const TroubleshootAppFields: React.FC<TroubleshootAppFieldsProps> = ({ data, onChange }) => {
  const [profiles, setProfiles] = useState<ClusterProfile[]>([]);
  const [selectedProfile, setSelectedProfile] = useState<string>(data.profile_id || '');

  useEffect(() => {
    listProfiles()
      .then(setProfiles)
      .catch(() => {});
  }, []);

  const handleProfileSelect = (profileId: string) => {
    setSelectedProfile(profileId);
    if (profileId) {
      const profile = profiles.find((p) => p.id === profileId);
      if (profile) {
        onChange({ ...data, profile_id: profileId, namespace: profile.cluster_url });
      }
    } else {
      onChange({ ...data, profile_id: undefined });
    }
  };

  const update = (field: Partial<TroubleshootAppForm>) => {
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
          {selectedProfile && (() => {
            const p = profiles.find((pr) => pr.id === selectedProfile);
            if (!p) return null;
            return (
              <div className="flex items-center gap-2 mt-1.5 text-[10px]">
                <span className={`w-1.5 h-1.5 rounded-full ${statusDot[p.status] || 'bg-gray-500'}`} />
                <span className={envBadge[p.environment] || 'text-gray-400'}>{p.environment}</span>
                <span className="text-gray-600 font-mono">{p.cluster_url}</span>
              </div>
            );
          })()}
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
