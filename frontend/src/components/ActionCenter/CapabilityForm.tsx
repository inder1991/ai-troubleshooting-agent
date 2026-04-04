import React, { useState } from 'react';
import type {
  CapabilityType,
  CapabilityFormData,
  TroubleshootAppForm,
  PRReviewForm,
  GithubIssueFixForm,
  ClusterDiagnosticsForm,
  NetworkTroubleshootingForm,
  DatabaseDiagnosticsForm,
} from '../../types';
import TroubleshootAppFields from './forms/TroubleshootAppFields';
import PRReviewFields from './forms/PRReviewFields';
import GithubIssueFixFields from './forms/GithubIssueFixFields';
import ClusterDiagnosticsFields from './forms/ClusterDiagnosticsFields';
import NetworkTroubleshootingFields from './forms/NetworkTroubleshootingFields';
import DatabaseDiagnosticsFields from './forms/DatabaseDiagnosticsFields';

interface CapabilityFormProps {
  capability: CapabilityType;
  onBack: () => void;
  onSubmit: (data: CapabilityFormData) => void;
}

const capabilityMeta: Record<
  CapabilityType,
  { title: string; subtitle: string; icon: string; color: string }
> = {
  troubleshoot_app: {
    title: 'Troubleshoot Application',
    subtitle: 'Configure log and metric analysis parameters',
    icon: 'troubleshoot',
    color: '#e09f3e',
  },
  pr_review: {
    title: 'PR Review',
    subtitle: 'Set up automated code review pipeline',
    icon: 'rate_review',
    color: '#a78bfa',
  },
  github_issue_fix: {
    title: 'Issue Fixer',
    subtitle: 'Configure automated patch generation',
    icon: 'auto_fix_high',
    color: '#f97316',
  },
  cluster_diagnostics: {
    title: 'Cluster Diagnostics',
    subtitle: 'Set up cluster health check parameters',
    icon: 'hub',
    color: '#14b8a6',
  },
  network_troubleshooting: {
    title: 'Network Path Troubleshooting',
    subtitle: 'Trace and diagnose network path issues across firewalls and NAT',
    icon: 'route',
    color: '#f59e0b',
  },
  database_diagnostics: {
    title: 'Database Diagnostics',
    subtitle: 'AI-powered PostgreSQL investigation with query analysis and performance tuning',
    icon: 'database',
    color: '#8b5cf6',
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
    case 'network_troubleshooting':
      return { capability: 'network_troubleshooting', src_ip: '', dst_ip: '', port: '443', protocol: 'tcp' as const };
    case 'database_diagnostics':
      return {
        capability: 'database_diagnostics',
        profile_id: '',
        time_window: '1h' as const,
        focus: ['queries', 'connections', 'storage'],
        database_type: 'postgres' as const,
        sampling_mode: 'standard' as const,
        include_explain_plans: false,
      };
  }
};

const CapabilityForm: React.FC<CapabilityFormProps> = ({ capability, onBack, onSubmit }) => {
  const [formData, setFormData] = useState<CapabilityFormData>(getInitialData(capability));
  const meta = capabilityMeta[capability];

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
      case 'cluster_diagnostics': {
        const cd = formData as ClusterDiagnosticsForm;
        const hasProfile = !!cd.profile_id;
        // When a saved profile is selected, cluster_url and auth come from the profile
        if (hasProfile) return true;
        // When using a temporary cluster, require a successful Test Connection
        // (signalled by cluster_url being populated AND use_temp_cluster=true with auth set)
        if (cd.use_temp_cluster) {
          return (
            cd.cluster_url.trim().length > 0 &&
            (!!cd.auth_token || !!cd.kubeconfig_content) &&
            // use_temp_cluster is only true once test passes and onChange is called with cluster_url
            cd.cluster_url.trim().length > 0
          );
        }
        const hasUrl = cd.cluster_url.trim().length > 0 && /^https?:\/\/.+/.test(cd.cluster_url.trim());
        const hasAuth = !!cd.auth_token;
        const hasName = !(cd.save_cluster ?? true) || !!cd.cluster_name?.trim();
        return hasUrl && hasAuth && hasName;
      }
      case 'network_troubleshooting': {
        const nd = formData as NetworkTroubleshootingForm;
        return nd.src_ip.trim() !== '' && nd.dst_ip.trim() !== '' && parseInt(nd.port) > 0;
      }
      case 'database_diagnostics': {
        const dd = formData as DatabaseDiagnosticsForm;
        return dd.profile_id.trim().length > 0;
      }
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
          <span className="material-symbols-outlined text-base">arrow_back</span>
          <span>Back to Launcher</span>
        </button>

        {/* Header */}
        <div className="flex items-center gap-3 mb-8">
          <div
            className="w-10 h-10 rounded-lg flex items-center justify-center"
            style={{ backgroundColor: `${meta.color}15`, border: `1px solid ${meta.color}30` }}
          >
            <span className="material-symbols-outlined" style={{ color: meta.color }}>{meta.icon}</span>
          </div>
          <div>
            <h1 className="text-xl font-bold text-white">{meta.title}</h1>
            <p className="text-xs text-gray-400">{meta.subtitle}</p>
          </div>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit}>
          <div className="bg-[#252118]/50 border border-[#3d3528] rounded-xl p-5">
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
            {formData.capability === 'network_troubleshooting' && (
              <NetworkTroubleshootingFields
                data={formData as NetworkTroubleshootingForm}
                onChange={(d) => setFormData(d)}
              />
            )}
            {formData.capability === 'database_diagnostics' && (
              <DatabaseDiagnosticsFields
                data={formData as DatabaseDiagnosticsForm}
                onChange={(d) => setFormData(d)}
              />
            )}
          </div>

          {/* Submit */}
          <button
            type="submit"
            disabled={!isValid()}
            className="mt-6 w-full flex items-center justify-center gap-2 px-6 py-3 bg-[#e09f3e] hover:bg-[#e09f3e]/90 disabled:bg-[#3d3528] disabled:text-gray-500 disabled:cursor-not-allowed text-[#1a1814] font-bold rounded-xl text-sm transition-colors"
          >
            <span className="material-symbols-outlined text-lg">rocket_launch</span>
            <span>Deploy Mission</span>
          </button>
        </form>
      </div>
    </div>
  );
};

export default CapabilityForm;
