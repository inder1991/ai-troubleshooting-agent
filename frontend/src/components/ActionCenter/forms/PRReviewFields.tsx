import React from 'react';
import { Shield, Gauge } from 'lucide-react';
import type { PRReviewForm } from '../../../types';

interface PRReviewFieldsProps {
  data: PRReviewForm;
  onChange: (data: PRReviewForm) => void;
}

const analysisModules = [
  { id: 'security', label: 'Security Scan', icon: Shield, color: '#ef4444' },
  { id: 'performance', label: 'Performance Analysis', icon: Gauge, color: '#f59e0b' },
];

const PRReviewFields: React.FC<PRReviewFieldsProps> = ({ data, onChange }) => {
  const update = (field: Partial<PRReviewForm>) => {
    onChange({ ...data, ...field });
  };

  const toggleFocusArea = (area: string) => {
    const areas = data.focus_areas || [];
    if (areas.includes(area)) {
      update({ focus_areas: areas.filter((a) => a !== area) });
    } else {
      update({ focus_areas: [...areas, area] });
    }
  };

  return (
    <div className="space-y-4">
      {/* Repo URL */}
      <div>
        <label className="block text-xs text-gray-400 mb-1.5 font-medium">
          Repository URL <span className="text-red-400">*</span>
        </label>
        <input
          type="text"
          value={data.repo_url}
          onChange={(e) => update({ repo_url: e.target.value })}
          className="w-full px-3 py-2.5 bg-[#0f2023] border border-[#224349] rounded-lg text-sm text-white placeholder-gray-600 focus:border-[#07b6d5] focus:outline-none focus:ring-1 focus:ring-[#07b6d5]/30 transition-colors"
          placeholder="https://github.com/org/repo"
          required
        />
      </div>

      {/* PR Number */}
      <div>
        <label className="block text-xs text-gray-400 mb-1.5 font-medium">
          PR Number <span className="text-red-400">*</span>
        </label>
        <input
          type="text"
          value={data.pr_number}
          onChange={(e) => update({ pr_number: e.target.value })}
          className="w-full px-3 py-2.5 bg-[#0f2023] border border-[#224349] rounded-lg text-sm text-white placeholder-gray-600 focus:border-[#07b6d5] focus:outline-none focus:ring-1 focus:ring-[#07b6d5]/30 transition-colors font-mono"
          placeholder="#142"
          required
        />
      </div>

      {/* Branch Name */}
      <div>
        <label className="block text-xs text-gray-400 mb-1.5 font-medium">Branch Name</label>
        <input
          type="text"
          value={data.branch_name || ''}
          onChange={(e) => update({ branch_name: e.target.value || undefined })}
          className="w-full px-3 py-2.5 bg-[#0f2023] border border-[#224349] rounded-lg text-sm text-white placeholder-gray-600 focus:border-[#07b6d5] focus:outline-none focus:ring-1 focus:ring-[#07b6d5]/30 transition-colors font-mono"
          placeholder="feature/my-branch"
        />
      </div>

      {/* Analysis Modules */}
      <div>
        <label className="block text-xs text-gray-400 mb-2 font-medium">Analysis Modules</label>
        <div className="space-y-2">
          {analysisModules.map((mod) => {
            const active = (data.focus_areas || []).includes(mod.id);
            return (
              <button
                key={mod.id}
                type="button"
                onClick={() => toggleFocusArea(mod.id)}
                className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg border text-sm transition-all ${
                  active
                    ? 'bg-[#07b6d5]/10 border-[#07b6d5]/30 text-white'
                    : 'bg-[#0f2023] border-[#224349] text-gray-400 hover:border-[#224349]/80'
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <mod.icon className="w-4 h-4" style={{ color: active ? mod.color : undefined }} />
                  <span>{mod.label}</span>
                </div>
                <div
                  className={`w-8 h-4 rounded-full relative transition-colors ${
                    active ? 'bg-[#07b6d5]' : 'bg-[#224349]'
                  }`}
                >
                  <div
                    className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition-transform ${
                      active ? 'translate-x-4' : 'translate-x-0.5'
                    }`}
                  />
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default PRReviewFields;
