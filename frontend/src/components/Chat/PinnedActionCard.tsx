import React, { useEffect, useState } from 'react';
import type { PendingAction } from '../../types';

interface PinnedActionCardProps {
  pendingAction: PendingAction;
  onAction: (action: string) => void;
}

const typeConfig: Record<string, { icon: string; title: string; borderColor: string }> = {
  attestation_required: {
    icon: 'verified_user',
    title: 'Findings Review Required',
    borderColor: 'border-amber-500',
  },
  fix_approval: {
    icon: 'build',
    title: 'Fix Ready for Review',
    borderColor: 'border-violet-500',
  },
  campaign_execute_confirm: {
    icon: 'rocket_launch',
    title: 'Campaign Execution Confirmation',
    borderColor: 'border-emerald-500',
  },
  repo_confirm: {
    icon: 'folder_open',
    title: 'Repository Confirmation',
    borderColor: 'border-blue-500',
  },
  code_agent_question: {
    icon: 'help',
    title: 'Agent Question',
    borderColor: 'border-cyan-500',
  },
};

const actionStyles: Record<string, string> = {
  approve: 'bg-green-500/20 text-green-400 border-green-500/30 hover:bg-green-500/30',
  reject: 'bg-red-500/20 text-red-400 border-red-500/30 hover:bg-red-500/30',
  details: 'bg-slate-500/20 text-slate-300 border-slate-500/30 hover:bg-slate-500/30',
  confirm: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/30',
  cancel: 'bg-red-500/20 text-red-400 border-red-500/30 hover:bg-red-500/30',
  feedback: 'bg-violet-500/20 text-violet-400 border-violet-500/30 hover:bg-violet-500/30',
};

const PinnedActionCard: React.FC<PinnedActionCardProps> = ({ pendingAction, onAction }) => {
  const config = typeConfig[pendingAction.type] || typeConfig.attestation_required;
  const [countdown, setCountdown] = useState<number | null>(null);

  useEffect(() => {
    if (!pendingAction.expires_at) return;
    const tick = () => {
      const remaining = Math.max(0, Math.floor((new Date(pendingAction.expires_at!).getTime() - Date.now()) / 1000));
      setCountdown(remaining);
    };
    tick();
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, [pendingAction.expires_at]);

  const ctx = pendingAction.context;

  return (
    <div className={`sticky top-0 z-10 mx-3 mt-2 mb-1 rounded-lg border-l-4 ${config.borderColor} bg-wr-surface/95 backdrop-blur-sm shadow-lg`}>
      <div className="px-4 py-3">
        <div className="flex items-center gap-2 mb-2">
          <span className="material-symbols-outlined text-base text-amber-400 animate-pulse">
            {config.icon}
          </span>
          <span className="text-body-xs font-bold uppercase tracking-wider text-slate-200">
            {config.title}
          </span>
          {countdown !== null && countdown > 0 && (
            <span className="ml-auto text-body-xs text-slate-500 font-mono">
              {Math.floor(countdown / 60)}:{String(countdown % 60).padStart(2, '0')}
            </span>
          )}
        </div>

        {ctx.findings_count != null && (
          <p className="text-body-xs text-slate-400 mb-2">
            {ctx.findings_count as number} findings at {((ctx.confidence as number) * 100).toFixed(0)}% confidence
          </p>
        )}
        {ctx.diff_summary && (
          <p className="text-body-xs text-slate-400 mb-2">{ctx.diff_summary as string}</p>
        )}
        {ctx.repo_count != null && (
          <p className="text-body-xs text-slate-400 mb-2">
            {ctx.repo_count as number} repositories ready for PR creation
          </p>
        )}

        <div className="flex items-center gap-2 flex-wrap">
          {pendingAction.actions.map((action) => (
            <button
              key={action}
              onClick={() => onAction(`__intent:${action}_${pendingAction.type.replace('_required', '').replace('_confirm', '')}`)}
              className={`text-body-xs font-bold px-3 py-1.5 rounded border transition-colors ${actionStyles[action] || actionStyles.details}`}
            >
              {action.charAt(0).toUpperCase() + action.slice(1)}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};

export default PinnedActionCard;
