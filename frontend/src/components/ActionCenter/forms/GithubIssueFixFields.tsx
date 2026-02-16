import React from 'react';
import type { GithubIssueFixForm } from '../../../types';

interface GithubIssueFixFieldsProps {
  data: GithubIssueFixForm;
  onChange: (data: GithubIssueFixForm) => void;
}

const priorities: { value: GithubIssueFixForm['priority']; label: string; color: string }[] = [
  { value: 'low', label: 'LOW', color: '#22c55e' },
  { value: 'medium', label: 'MEDIUM', color: '#f59e0b' },
  { value: 'high', label: 'HIGH', color: '#f97316' },
  { value: 'critical', label: 'CRITICAL', color: '#ef4444' },
];

const GithubIssueFixFields: React.FC<GithubIssueFixFieldsProps> = ({ data, onChange }) => {
  const update = (field: Partial<GithubIssueFixForm>) => {
    onChange({ ...data, ...field });
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

      {/* Issue Number */}
      <div>
        <label className="block text-xs text-gray-400 mb-1.5 font-medium">
          Issue ID <span className="text-red-400">*</span>
        </label>
        <input
          type="text"
          value={data.issue_number}
          onChange={(e) => update({ issue_number: e.target.value })}
          className="w-full px-3 py-2.5 bg-[#0f2023] border border-[#224349] rounded-lg text-sm text-white placeholder-gray-600 focus:border-[#07b6d5] focus:outline-none focus:ring-1 focus:ring-[#07b6d5]/30 transition-colors font-mono"
          placeholder="#87"
          required
        />
      </div>

      {/* Target Branch */}
      <div>
        <label className="block text-xs text-gray-400 mb-1.5 font-medium">Target Branch</label>
        <input
          type="text"
          value={data.target_branch || ''}
          onChange={(e) => update({ target_branch: e.target.value || undefined })}
          className="w-full px-3 py-2.5 bg-[#0f2023] border border-[#224349] rounded-lg text-sm text-white placeholder-gray-600 focus:border-[#07b6d5] focus:outline-none focus:ring-1 focus:ring-[#07b6d5]/30 transition-colors font-mono"
          placeholder="main"
        />
      </div>

      {/* Priority Level */}
      <div>
        <label className="block text-xs text-gray-400 mb-2 font-medium">Priority Level</label>
        <div className="grid grid-cols-4 gap-2">
          {priorities.map((p) => {
            const active = data.priority === p.value;
            return (
              <button
                key={p.value}
                type="button"
                onClick={() => update({ priority: p.value })}
                className={`px-2 py-2 rounded-lg border text-xs font-bold transition-all ${
                  active
                    ? 'border-opacity-50 text-white'
                    : 'bg-[#0f2023] border-[#224349] text-gray-500 hover:text-gray-300'
                }`}
                style={
                  active
                    ? {
                        backgroundColor: `${p.color}15`,
                        borderColor: `${p.color}40`,
                        color: p.color,
                      }
                    : undefined
                }
              >
                {p.label}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default GithubIssueFixFields;
