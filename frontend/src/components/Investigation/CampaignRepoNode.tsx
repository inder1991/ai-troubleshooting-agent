import React from 'react';
import { motion } from 'framer-motion';
import type { CampaignRepoFix } from '../../types/campaign';
import CausalRoleBadge from './cards/CausalRoleBadge';
import VSCodeLink from './VSCodeLink';
import { repoNodeVariants } from '../../styles/campaign-animations';

const causalRoleBorderColor: Record<string, string> = {
  root_cause: 'border-l-red-500',
  cascading: 'border-l-amber-500',
  correlated: 'border-l-cyan-500',
};

const causalRoleToBadge: Record<string, 'root_cause' | 'cascading_failure' | 'correlated_anomaly'> = {
  root_cause: 'root_cause',
  cascading: 'cascading_failure',
  correlated: 'correlated_anomaly',
};

const statusIcon: Record<string, { icon: string; className: string }> = {
  pending: { icon: 'schedule', className: 'text-slate-500' },
  cloning: { icon: 'cloud_download', className: 'text-cyan-400 animate-pulse' },
  generating: { icon: 'auto_fix_high', className: 'text-cyan-400 campaign-node-generating' },
  awaiting_review: { icon: 'visibility', className: 'text-amber-400' },
  approved: { icon: 'check_circle', className: 'text-emerald-400' },
  rejected: { icon: 'cancel', className: 'text-red-400' },
  pr_created: { icon: 'merge_type', className: 'text-emerald-400' },
  error: { icon: 'error', className: 'text-red-500' },
};

interface CampaignRepoNodeProps {
  repoFix: CampaignRepoFix;
  index: number;
  isSelected: boolean;
  onSelect: () => void;
  onApprove: () => void;
  onReject: () => void;
  onTelescope: () => void;
  onHover: (service: string | null) => void;
}

const CampaignRepoNode: React.FC<CampaignRepoNodeProps> = ({
  repoFix, index, isSelected, onSelect, onApprove, onReject, onTelescope, onHover,
}) => {
  const borderClass = causalRoleBorderColor[repoFix.causal_role] || 'border-l-slate-600';
  const badgeRole = causalRoleToBadge[repoFix.causal_role] || 'correlated_anomaly';
  const status = statusIcon[repoFix.status] || statusIcon.pending;

  return (
    <motion.div
      custom={index}
      variants={repoNodeVariants}
      initial="hidden"
      animate="visible"
      onMouseEnter={() => onHover(repoFix.service_name)}
      onMouseLeave={() => onHover(null)}
      onClick={onSelect}
      className={`
        relative border-l-4 ${borderClass} rounded-lg bg-slate-900/60 border border-slate-800/50
        cursor-pointer transition-all hover:bg-slate-800/40
        ${isSelected ? 'ring-1 ring-cyan-500/40 bg-slate-800/50' : ''}
        ${repoFix.status === 'generating' ? 'campaign-node-generating' : ''}
      `}
    >
      {/* Header */}
      <div className="p-3">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-[11px] font-bold text-slate-200 tracking-wide truncate">
            {repoFix.service_name}
          </span>
          <span className={`material-symbols-outlined text-[16px] ${status.className}`}>
            {status.icon}
          </span>
        </div>
        <CausalRoleBadge role={badgeRole} />

        {/* PR badge */}
        {repoFix.pr_url && (
          <a
            href={repoFix.pr_url}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-2 inline-flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-950/40 border border-emerald-700/40 text-[9px] text-emerald-400 font-mono hover:bg-emerald-900/40"
            onClick={e => e.stopPropagation()}
          >
            <span className="material-symbols-outlined text-[10px]">merge_type</span>
            PR #{repoFix.pr_number}
          </a>
        )}

        {/* Error message */}
        {repoFix.status === 'error' && repoFix.error_message && (
          <p className="mt-2 text-[9px] text-red-400/80 truncate">{repoFix.error_message}</p>
        )}
      </div>

      {/* Expanded detail area */}
      {isSelected && repoFix.status !== 'pending' && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          className="border-t border-slate-800/50 p-3"
        >
          {repoFix.fix_explanation && (
            <p className="text-[10px] text-slate-400 mb-2">{repoFix.fix_explanation}</p>
          )}

          {/* File list */}
          {repoFix.fixed_files.length > 0 && (
            <div className="mb-3 space-y-1">
              {repoFix.fixed_files.map((f) => (
                <div key={f.file_path} className="flex items-center gap-2">
                  <span className="text-[9px] font-mono text-slate-500 truncate flex-1">
                    {f.file_path}
                  </span>
                  <VSCodeLink filePath={f.file_path} repoName={repoFix.service_name} />
                </div>
              ))}
            </div>
          )}

          {/* Diff preview */}
          {repoFix.diff && (
            <pre className="text-[9px] font-mono text-slate-500 bg-black/30 rounded p-2 max-h-24 overflow-auto mb-3">
              {repoFix.diff.slice(0, 500)}
            </pre>
          )}

          {/* Action buttons */}
          {repoFix.status === 'awaiting_review' && (
            <div className="flex items-center gap-2">
              <button
                onClick={e => { e.stopPropagation(); onTelescope(); }}
                className="flex-1 py-1.5 rounded bg-slate-800/80 border border-slate-700 hover:bg-slate-700 text-[10px] text-cyan-400 font-bold tracking-wider"
              >
                VIEW DIFF
              </button>
              <button
                onClick={e => { e.stopPropagation(); onApprove(); }}
                className="flex-1 py-1.5 rounded bg-emerald-950/40 border border-emerald-700/50 hover:bg-emerald-900/40 text-[10px] text-emerald-400 font-bold tracking-wider"
              >
                APPROVE
              </button>
              <button
                onClick={e => { e.stopPropagation(); onReject(); }}
                className="flex-1 py-1.5 rounded bg-red-950/30 border border-red-700/40 hover:bg-red-900/30 text-[10px] text-red-400 font-bold tracking-wider"
              >
                REJECT
              </button>
            </div>
          )}
        </motion.div>
      )}
    </motion.div>
  );
};

export default CampaignRepoNode;
