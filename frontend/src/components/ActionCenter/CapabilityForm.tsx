import React, { useState } from 'react';
import { ArrowLeft, Rocket, Search, FileText, Bug, Container } from 'lucide-react';
import type {
  CapabilityType,
  CapabilityFormData,
  TroubleshootAppForm,
  PRReviewForm,
  GithubIssueFixForm,
  ClusterDiagnosticsForm,
} from '../../types';
import TroubleshootAppFields from './forms/TroubleshootAppFields';
import PRReviewFields from './forms/PRReviewFields';
import GithubIssueFixFields from './forms/GithubIssueFixFields';
import ClusterDiagnosticsFields from './forms/ClusterDiagnosticsFields';

interface CapabilityFormProps {
  capability: CapabilityType;
  onBack: () => void;
  onSubmit: (data: CapabilityFormData) => void;
}

const capabilityMeta: Record<
  CapabilityType,
  { title: string; subtitle: string; icon: typeof Search; color: string }
> = {
  troubleshoot_app: {
    title: 'Troubleshoot Application',
    subtitle: 'Configure log and metric analysis parameters',
    icon: Search,
    color: '#07b6d5',
  },
  pr_review: {
    title: 'PR Review',
    subtitle: 'Set up automated code review pipeline',
    icon: FileText,
    color: '#a78bfa',
  },
  github_issue_fix: {
    title: 'Issue Fixer',
    subtitle: 'Configure automated patch generation',
    icon: Bug,
    color: '#f97316',
  },
  cluster_diagnostics: {
    title: 'Cluster Diagnostics',
    subtitle: 'Set up cluster health check parameters',
    icon: Container,
    color: '#14b8a6',
  },
};

const getInitialData = (capability: CapabilityType): CapabilityFormData => {
  switch (capability) {
    case 'troubleshoot_app':
      return { capability: 'troubleshoot_app', service_name: '', time_window: '1h' };
    case 'pr_review':
      return { capability: 'pr_review', repo_url: '', pr_number: '', focus_areas: ['security'] };
    case 'github_issue_fix':
      return { capability: 'github_issue_fix', repo_url: '', issue_number: '', priority: 'medium' };
    case 'cluster_diagnostics':
      return { capability: 'cluster_diagnostics', cluster_url: '', auth_method: 'token' };
  }
};

const CapabilityForm: React.FC<CapabilityFormProps> = ({ capability, onBack, onSubmit }) => {
  const [formData, setFormData] = useState<CapabilityFormData>(getInitialData(capability));
  const meta = capabilityMeta[capability];
  const Icon = meta.icon;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(formData);
  };

  const isValid = (): boolean => {
    switch (formData.capability) {
      case 'troubleshoot_app':
        return formData.service_name.trim().length > 0;
      case 'pr_review':
        return formData.repo_url.trim().length > 0 && formData.pr_number.trim().length > 0;
      case 'github_issue_fix':
        return formData.repo_url.trim().length > 0 && formData.issue_number.trim().length > 0;
      case 'cluster_diagnostics':
        return formData.cluster_url.trim().length > 0;
    }
  };

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-lg mx-auto px-6 py-10">
        {/* Back button */}
        <button
          onClick={onBack}
          className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-white mb-6 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Launcher</span>
        </button>

        {/* Header */}
        <div className="flex items-center gap-3 mb-8">
          <div
            className="w-10 h-10 rounded-lg flex items-center justify-center"
            style={{ backgroundColor: `${meta.color}15`, border: `1px solid ${meta.color}30` }}
          >
            <Icon className="w-5 h-5" style={{ color: meta.color }} />
          </div>
          <div>
            <h1 className="text-xl font-bold text-white">{meta.title}</h1>
            <p className="text-xs text-gray-400">{meta.subtitle}</p>
          </div>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit}>
          <div className="bg-[#1e2f33]/50 border border-[#224349] rounded-xl p-5">
            {formData.capability === 'troubleshoot_app' && (
              <TroubleshootAppFields
                data={formData as TroubleshootAppForm}
                onChange={(d) => setFormData(d)}
              />
            )}
            {formData.capability === 'pr_review' && (
              <PRReviewFields
                data={formData as PRReviewForm}
                onChange={(d) => setFormData(d)}
              />
            )}
            {formData.capability === 'github_issue_fix' && (
              <GithubIssueFixFields
                data={formData as GithubIssueFixForm}
                onChange={(d) => setFormData(d)}
              />
            )}
            {formData.capability === 'cluster_diagnostics' && (
              <ClusterDiagnosticsFields
                data={formData as ClusterDiagnosticsForm}
                onChange={(d) => setFormData(d)}
              />
            )}
          </div>

          {/* Submit */}
          <button
            type="submit"
            disabled={!isValid()}
            className="mt-6 w-full flex items-center justify-center gap-2 px-6 py-3 bg-[#07b6d5] hover:bg-[#07b6d5]/90 disabled:bg-[#224349] disabled:text-gray-500 disabled:cursor-not-allowed text-[#0f2023] font-bold rounded-xl text-sm transition-colors"
          >
            <Rocket className="w-4 h-4" />
            <span>Deploy Mission</span>
          </button>
        </form>
      </div>
    </div>
  );
};

export default CapabilityForm;
