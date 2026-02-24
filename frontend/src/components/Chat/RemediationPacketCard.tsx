import React from 'react';
import { motion } from 'framer-motion';
import type { ChatMessage } from '../../types';
import { useCampaignContext } from '../../contexts/CampaignContext';
import CausalRoleBadge from '../Investigation/cards/CausalRoleBadge';
import { packetCardVariants, approvalTransition } from '../../styles/campaign-animations';

const causalRoleToBadge: Record<string, 'root_cause' | 'cascading_failure' | 'correlated_anomaly'> = {
  root_cause: 'root_cause',
  cascading: 'cascading_failure',
  correlated: 'correlated_anomaly',
};

interface RemediationPacketCardProps {
  message: ChatMessage;
}

const RemediationPacketCard: React.FC<RemediationPacketCardProps> = ({ message }) => {
  const {
    campaign, approveRepo, rejectRepo, revokeRepo, openTelescope, setHoveredRepo,
  } = useCampaignContext();

  const meta = message.metadata;
  if (!meta) return null;

  const repoUrl = meta.repo_url || '';
  const serviceName = meta.service_name || '';
  const causalRole = meta.causal_role || 'correlated';
  const fixExplanation = meta.fix_explanation || '';
  const fixedFiles = meta.fixed_files || [];

  // Get live status from campaign context
  const repoStatus = campaign?.repos.find(r => r.repo_url === repoUrl)?.status;
  const isApproved = repoStatus === 'approved' || repoStatus === 'pr_created';
  const isRejected = repoStatus === 'rejected';
  const canRevoke = isApproved && campaign?.overall_status !== 'completed';

  const badgeRole = causalRoleToBadge[causalRole] || 'correlated_anomaly';

  // Border color based on status
  const borderStyle = isApproved
    ? approvalTransition.approved
    : isRejected
      ? approvalTransition.rejected
      : {};

  return (
    <motion.div
      variants={packetCardVariants}
      initial="hidden"
      animate="visible"
      style={borderStyle}
      onMouseEnter={() => setHoveredRepo(serviceName)}
      onMouseLeave={() => setHoveredRepo(null)}
      className={`
        rounded-lg border bg-slate-900/70 backdrop-blur-sm overflow-hidden
        ${isApproved ? 'border-emerald-600/50' : isRejected ? 'border-red-600/50' : 'border-slate-700/50'}
      `}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-800/50">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-[14px] text-cyan-400">build</span>
          <span className="text-[11px] font-bold text-slate-200">{serviceName}</span>
        </div>
        <CausalRoleBadge role={badgeRole} />
      </div>

      {/* Body */}
      <div className="px-3 py-2">
        {fixExplanation && (
          <p className="text-[10px] text-slate-400 mb-1.5">{fixExplanation}</p>
        )}
        {fixedFiles.length > 0 && (
          <p className="text-[9px] text-slate-500 font-mono">
            Files: {fixedFiles.join(', ')}
          </p>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 px-3 py-2 border-t border-slate-800/50">
        {!isApproved && !isRejected && (
          <>
            <button
              onClick={() => openTelescope(repoUrl)}
              className="px-3 py-1 rounded bg-slate-800/80 border border-slate-700 hover:bg-slate-700 text-[10px] text-cyan-400 font-bold tracking-wider transition-colors"
            >
              View Diff
            </button>
            <button
              onClick={() => approveRepo(repoUrl)}
              className="px-3 py-1 rounded bg-emerald-950/40 border border-emerald-700/50 hover:bg-emerald-900/40 text-[10px] text-emerald-400 font-bold tracking-wider transition-colors flex items-center gap-1"
            >
              <span className="material-symbols-outlined text-[12px]">check</span>
              Approve
            </button>
            <button
              onClick={() => rejectRepo(repoUrl)}
              className="px-3 py-1 rounded bg-red-950/30 border border-red-700/40 hover:bg-red-900/30 text-[10px] text-red-400 font-bold tracking-wider transition-colors flex items-center gap-1"
            >
              <span className="material-symbols-outlined text-[12px]">close</span>
              Reject
            </button>
          </>
        )}

        {isApproved && (
          <div className="flex items-center gap-2 w-full">
            <span className="flex items-center gap-1 text-[10px] text-emerald-400 font-bold">
              <span className="material-symbols-outlined text-[14px]">verified</span>
              Approved
            </span>
            {canRevoke && (
              <button
                onClick={() => revokeRepo(repoUrl)}
                className="ml-auto text-[9px] text-slate-500 hover:text-amber-400 transition-colors underline"
              >
                Revoke
              </button>
            )}
          </div>
        )}

        {isRejected && (
          <span className="flex items-center gap-1 text-[10px] text-red-400 font-bold">
            <span className="material-symbols-outlined text-[14px]">block</span>
            Rejected
          </span>
        )}
      </div>
    </motion.div>
  );
};

export default RemediationPacketCard;
