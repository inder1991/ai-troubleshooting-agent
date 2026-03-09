/**
 * RemediationCard — Inline approval card for a remediation plan.
 * Shows action, status, SQL preview, impact, rollback, and action buttons.
 */
import React from 'react';

interface RemediationPlan {
  plan_id: string;
  profile_id: string;
  finding_id?: string;
  action: string;
  params: Record<string, unknown>;
  sql_preview: string;
  impact_assessment: string;
  rollback_sql?: string;
  requires_downtime: boolean;
  status: string;
  created_at: string;
  approved_at?: string;
  executed_at?: string;
  completed_at?: string;
  result_summary?: string;
}

interface RemediationCardProps {
  plan: RemediationPlan;
  onApprove?: (planId: string) => void;
  onReject?: (planId: string) => void;
  onExecute?: (planId: string) => void;
}

const statusStyles: Record<string, string> = {
  pending: 'bg-yellow-500/20 text-yellow-400',
  approved: 'bg-blue-500/20 text-blue-400',
  executing: 'bg-cyan-500/20 text-cyan-400 animate-pulse',
  completed: 'bg-green-500/20 text-green-400',
  failed: 'bg-red-500/20 text-red-400',
  rejected: 'bg-slate-500/20 text-slate-400',
};

const RemediationCard: React.FC<RemediationCardProps> = ({ plan, onApprove, onReject, onExecute }) => {
  const statusClass = statusStyles[plan.status] || 'bg-slate-500/20 text-slate-400';
  const source = plan.finding_id ? 'AI' : 'Manual';

  return (
    <div className="bg-[#0d2329] border border-slate-700/50 rounded-lg p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className="material-symbols-outlined text-cyan-400 text-[18px]">build</span>
          <span className="text-sm font-semibold text-slate-200 truncate">
            {plan.action.replace(/_/g, ' ').toUpperCase()}
            {plan.params.table ? ` on ${plan.params.table}` : ''}
          </span>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-700/60 text-slate-400">{source}</span>
          <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${statusClass}`}>
            {plan.status.toUpperCase()}
          </span>
          {plan.requires_downtime && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-500/20 text-red-400 font-medium">
              DOWNTIME
            </span>
          )}
        </div>
      </div>

      {/* SQL Preview */}
      <div className="rounded bg-[#081418] border border-slate-700/30 p-3 overflow-x-auto">
        <pre className="text-xs font-mono text-slate-300 whitespace-pre-wrap break-all">{plan.sql_preview}</pre>
      </div>

      {/* Impact */}
      <p className="text-xs text-slate-400">{plan.impact_assessment}</p>

      {/* Rollback SQL */}
      {plan.rollback_sql && (
        <details className="group">
          <summary className="text-xs text-slate-500 cursor-pointer hover:text-slate-300 transition-colors">
            <span className="material-symbols-outlined text-[14px] align-middle mr-1">undo</span>
            Rollback SQL
          </summary>
          <div className="mt-1 rounded bg-[#081418] border border-slate-700/30 p-2 overflow-x-auto">
            <pre className="text-xs font-mono text-slate-400 whitespace-pre-wrap break-all">{plan.rollback_sql}</pre>
          </div>
        </details>
      )}

      {/* Result summary for completed/failed */}
      {(plan.status === 'completed' || plan.status === 'failed') && plan.result_summary && (
        <div className={`text-xs rounded px-3 py-2 ${plan.status === 'completed' ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
          {plan.result_summary}
        </div>
      )}

      {/* Timestamps */}
      <div className="flex flex-wrap gap-3 text-[10px] text-slate-500">
        <span>Created: {new Date(plan.created_at).toLocaleString()}</span>
        {plan.approved_at && <span>Approved: {new Date(plan.approved_at).toLocaleString()}</span>}
        {plan.executed_at && <span>Executed: {new Date(plan.executed_at).toLocaleString()}</span>}
        {plan.completed_at && <span>Completed: {new Date(plan.completed_at).toLocaleString()}</span>}
      </div>

      {/* Action buttons */}
      {plan.status === 'pending' && (
        <div className="flex items-center gap-2 pt-1">
          <button
            onClick={() => onReject?.(plan.plan_id)}
            className="flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg bg-slate-700/50 hover:bg-slate-600/60 text-slate-300 transition-colors"
          >
            <span className="material-symbols-outlined text-[14px]">close</span>
            Reject
          </button>
          <button
            onClick={() => onApprove?.(plan.plan_id)}
            className="flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white transition-colors"
          >
            <span className="material-symbols-outlined text-[14px]">check</span>
            Approve &amp; Run
          </button>
        </div>
      )}

      {plan.status === 'approved' && (
        <div className="flex items-center gap-2 pt-1">
          <button
            onClick={() => onExecute?.(plan.plan_id)}
            className="flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg bg-green-600 hover:bg-green-500 text-white transition-colors"
          >
            <span className="material-symbols-outlined text-[14px]">play_arrow</span>
            Execute
          </button>
        </div>
      )}
    </div>
  );
};

export default RemediationCard;
