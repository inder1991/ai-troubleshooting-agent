import React from 'react';
import type { PipelineCapabilityForm } from '../../../types';

interface Props {
  data: PipelineCapabilityForm;
  onChange: (data: PipelineCapabilityForm) => void;
}

const PipelineTroubleshootingFields: React.FC<Props> = ({ data, onChange }) => {
  const update = (patch: Partial<PipelineCapabilityForm>) =>
    onChange({ ...data, ...patch });

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-xs font-semibold text-gray-300 mb-1.5">
          Cluster ID <span className="text-red-400">*</span>
        </label>
        <input
          type="text"
          value={data.cluster_id}
          onChange={(e) => update({ cluster_id: e.target.value })}
          placeholder="prod-us-east-1"
          className="w-full bg-[#1a1814] border border-[#3d3528] rounded-lg px-3 py-2 text-sm text-white placeholder:text-gray-600 focus:outline-none focus:border-[#06b6d4]"
          required
        />
        <p className="mt-1 text-body-xs text-gray-500">
          Resolves linked Jenkins / ArgoCD instances and recent commits.
        </p>
      </div>

      <div>
        <label className="block text-xs font-semibold text-gray-300 mb-1.5">
          Time window (minutes)
        </label>
        <input
          type="number"
          min={1}
          max={1440}
          value={data.time_window_minutes}
          onChange={(e) =>
            update({ time_window_minutes: Math.max(1, parseInt(e.target.value) || 60) })
          }
          className="w-full bg-[#1a1814] border border-[#3d3528] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-[#06b6d4]"
        />
      </div>

      <div>
        <label className="block text-xs font-semibold text-gray-300 mb-1.5">
          Git repo <span className="text-gray-500 font-normal">(owner/repo, optional)</span>
        </label>
        <input
          type="text"
          value={data.git_repo ?? ''}
          onChange={(e) => update({ git_repo: e.target.value })}
          placeholder="acme/payments-api"
          className="w-full bg-[#1a1814] border border-[#3d3528] rounded-lg px-3 py-2 text-sm text-white placeholder:text-gray-600 focus:outline-none focus:border-[#06b6d4]"
        />
      </div>

      <div>
        <label className="block text-xs font-semibold text-gray-300 mb-1.5">
          Service hint <span className="text-gray-500 font-normal">(optional)</span>
        </label>
        <input
          type="text"
          value={data.service_hint ?? ''}
          onChange={(e) => update({ service_hint: e.target.value })}
          placeholder="payments-api"
          className="w-full bg-[#1a1814] border border-[#3d3528] rounded-lg px-3 py-2 text-sm text-white placeholder:text-gray-600 focus:outline-none focus:border-[#06b6d4]"
        />
      </div>

      <div>
        <label className="block text-xs font-semibold text-gray-300 mb-1.5">
          Profile ID <span className="text-gray-500 font-normal">(optional)</span>
        </label>
        <input
          type="text"
          value={data.profile_id ?? ''}
          onChange={(e) => update({ profile_id: e.target.value })}
          placeholder="global-integration-uuid"
          className="w-full bg-[#1a1814] border border-[#3d3528] rounded-lg px-3 py-2 text-sm text-white placeholder:text-gray-600 focus:outline-none focus:border-[#06b6d4]"
        />
      </div>
    </div>
  );
};

export default PipelineTroubleshootingFields;
