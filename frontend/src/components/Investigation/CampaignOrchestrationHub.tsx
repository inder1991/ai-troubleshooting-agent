import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { RemediationCampaign } from '../../types/campaign';
import { useCampaignContext } from '../../contexts/CampaignContext';
import CampaignRepoNode from './CampaignRepoNode';
import { masterGateVariants } from '../../styles/campaign-animations';

interface CampaignOrchestrationHubProps {
  campaign: RemediationCampaign;
}

const CampaignOrchestrationHub: React.FC<CampaignOrchestrationHubProps> = ({ campaign }) => {
  const {
    approveRepo, rejectRepo, executeCampaign, openTelescope, setHoveredRepo, isLoading,
  } = useCampaignContext();
  const [selectedRepo, setSelectedRepo] = useState<string | null>(null);

  // Order repos: root_cause first, then cascading, then correlated
  const rolePriority: Record<string, number> = { root_cause: 0, cascading: 1, correlated: 2 };
  const sortedRepos = [...campaign.repos].sort(
    (a, b) => (rolePriority[a.causal_role] ?? 2) - (rolePriority[b.causal_role] ?? 2)
  );

  const allApproved = campaign.approved_count === campaign.total_count && campaign.total_count > 0;

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800/50">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-cyan-400 text-[18px]">hub</span>
          <span className="text-[11px] font-black text-slate-300 tracking-[0.15em] uppercase">
            Remediation Campaign
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono text-slate-500">
            {campaign.approved_count}/{campaign.total_count} approved
          </span>
          <div className="w-16 h-1.5 rounded-full bg-slate-800 overflow-hidden">
            <div
              className="h-full rounded-full bg-emerald-500 transition-all duration-500"
              style={{ width: `${campaign.total_count ? (campaign.approved_count / campaign.total_count) * 100 : 0}%` }}
            />
          </div>
        </div>
      </div>

      {/* Repo node chain */}
      <div className="flex-1 overflow-auto p-4 space-y-3">
        {/* Horizontal chain indicators + vertical list */}
        <div className="flex items-center gap-1 mb-4 overflow-x-auto">
          {sortedRepos.map((repo, i) => (
            <React.Fragment key={repo.repo_url}>
              <div
                className={`px-2 py-1 rounded text-[9px] font-bold tracking-wider whitespace-nowrap
                  ${repo.status === 'approved' || repo.status === 'pr_created'
                    ? 'bg-emerald-950/40 text-emerald-400 border border-emerald-700/40'
                    : repo.status === 'rejected'
                      ? 'bg-red-950/30 text-red-400 border border-red-700/40'
                      : repo.status === 'error'
                        ? 'bg-red-950/30 text-red-500 border border-red-700/40'
                        : 'bg-slate-900/60 text-slate-400 border border-slate-700/40'}
                `}
              >
                {repo.service_name}
              </div>
              {i < sortedRepos.length - 1 && (
                <span className="material-symbols-outlined text-[12px] text-slate-700">
                  arrow_forward
                </span>
              )}
            </React.Fragment>
          ))}
        </div>

        {/* Repo detail cards */}
        {sortedRepos.map((repo, i) => (
          <CampaignRepoNode
            key={repo.repo_url}
            repoFix={repo}
            index={i}
            isSelected={selectedRepo === repo.repo_url}
            onSelect={() => setSelectedRepo(prev => prev === repo.repo_url ? null : repo.repo_url)}
            onApprove={() => approveRepo(repo.repo_url)}
            onReject={() => rejectRepo(repo.repo_url)}
            onTelescope={() => openTelescope(repo.repo_url)}
            onHover={setHoveredRepo}
          />
        ))}
      </div>

      {/* Campaign Readiness Footer */}
      <div className="px-4 py-3 border-t border-slate-800/50">
        <div className="flex items-center justify-between mb-3">
          <span className="text-[10px] text-slate-500 uppercase tracking-widest">Campaign Readiness</span>
          <span className="text-xs font-mono font-bold text-slate-300">
            {campaign.approved_count} / {campaign.total_count} Attested
          </span>
        </div>

        <AnimatePresence mode="wait">
          {allApproved ? (
            <motion.button
              key="execute"
              variants={masterGateVariants}
              initial="hidden"
              animate="visible"
              exit="hidden"
              onClick={executeCampaign}
              disabled={isLoading}
              className="w-full py-3 rounded-lg bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-black font-black text-[11px] tracking-[0.2em] uppercase shadow-[0_0_15px_rgba(16,185,129,0.3)] flex items-center justify-center gap-2"
            >
              <span className="material-symbols-outlined text-sm">rocket_launch</span>
              Execute Coordinated Deployment
            </motion.button>
          ) : (
            <motion.div
              key="waiting"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="w-full py-3 rounded-lg bg-slate-900/50 border border-slate-800 text-slate-600 font-bold text-[10px] tracking-widest uppercase text-center flex items-center justify-center gap-2"
            >
              <span className="material-symbols-outlined text-sm animate-spin">sync</span>
              Awaiting Local Attestations...
            </motion.div>
          )}
        </AnimatePresence>

        {/* Partial Execution Failure Banner */}
        {campaign.overall_status === 'partial_failure' && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            className="mt-3 p-3 rounded-lg bg-amber-950/30 border border-amber-700/50"
          >
            <div className="flex items-center gap-2 text-amber-400 text-[11px] font-bold uppercase tracking-wider mb-2">
              <span className="material-symbols-outlined text-sm">warning</span>
              Partial Deployment — Manual Intervention Required
            </div>
            <div className="space-y-1">
              {sortedRepos.map(repo => (
                <div key={repo.repo_url} className="flex items-center gap-2 text-[10px]">
                  {repo.status === 'pr_created' ? (
                    <>
                      <span className="material-symbols-outlined text-[12px] text-emerald-400">check_circle</span>
                      <span className="text-slate-400">{repo.service_name}</span>
                      {repo.pr_url && (
                        <a href={repo.pr_url} target="_blank" rel="noopener noreferrer" className="text-cyan-400 hover:underline">
                          PR #{repo.pr_number}
                        </a>
                      )}
                    </>
                  ) : repo.status === 'error' ? (
                    <>
                      <span className="material-symbols-outlined text-[12px] text-red-400">error</span>
                      <span className="text-red-400">{repo.service_name}: {repo.error_message}</span>
                    </>
                  ) : null}
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
};

export default CampaignOrchestrationHub;
