// Campaign types for multi-repo remediation orchestration

export type CampaignRepoStatus =
  | 'pending' | 'cloning' | 'generating'
  | 'awaiting_review' | 'approved' | 'rejected'
  | 'pr_created' | 'error';

export interface CampaignRepoFix {
  repo_url: string;
  service_name: string;
  status: CampaignRepoStatus;
  causal_role: 'root_cause' | 'cascading' | 'correlated';
  diff: string;
  fix_explanation: string;
  fixed_files: { file_path: string; diff: string }[];
  pr_url: string | null;
  pr_number: number | null;
  error_message: string;
}

export interface RemediationCampaign {
  campaign_id: string;
  overall_status: string;
  approved_count: number;
  total_count: number;
  repos: CampaignRepoFix[];
}

export interface TelescopeData {
  repo_url: string;
  service_name: string;
  files: {
    file_path: string;
    original_code: string;
    fixed_code: string;
    diff: string;
  }[];
}
