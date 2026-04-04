import React from 'react';
import type { WorkflowRun } from './useWorkflowRuns';
import { t } from '../../../styles/tokens';

const STATUS_CONFIG: Record<WorkflowRun['status'], { color: string; icon: string; label: string }> = {
  completed:        { color: t.green, icon: 'check_circle',      label: 'Completed' },
  failed:           { color: t.red,   icon: 'error',             label: 'Failed' },
  running:          { color: t.cyan,  icon: 'progress_activity', label: 'Running' },
  waiting_approval: { color: t.amber, icon: 'pending_actions',   label: 'Awaiting Approval' },
};

function elapsed(start: string, end?: string) {
  const ms = new Date(end || Date.now()).getTime() - new Date(start).getTime();
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

interface Props { run: WorkflowRun; selected: boolean; onClick: () => void; }

const WorkflowRunCard: React.FC<Props> = ({ run, selected, onClick }) => {
  const cfg = STATUS_CONFIG[run.status];
  const total = run.agents_completed.length + run.agents_pending.length;
  const progress = total > 0 ? Math.round((run.agents_completed.length / total) * 100) : 0;

  return (
    <button
      onClick={onClick}
      className="w-full text-left px-4 py-3 border-b"
      style={{
        borderColor: t.borderDefault,
        background: selected ? t.cyanSelected : 'transparent',
        borderLeft: selected ? `2px solid ${t.cyan}` : '2px solid transparent',
      }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-xs font-display font-semibold truncate" style={{ color: t.textPrimary }}>
            {run.workflow_name}
          </div>
          <div className="text-[10px] font-sans mt-0.5 truncate" style={{ color: t.textMuted }}>
            {run.service_name}
          </div>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          <span className="material-symbols-outlined" style={{ fontSize: 14, color: cfg.color }}>
            {cfg.icon}
          </span>
          <span className="text-[10px] font-sans" style={{ color: cfg.color }}>{cfg.label}</span>
        </div>
      </div>

      <div className="mt-2 flex items-center gap-3 text-[10px] font-sans" style={{ color: t.textFaint }}>
        <span>{new Date(run.started_at).toLocaleString()}</span>
        <span>·</span>
        <span>{elapsed(run.started_at, run.finished_at)}</span>
        {run.overall_confidence !== undefined && (
          <>
            <span>·</span>
            <span style={{ color: run.overall_confidence > 0.8 ? t.green : t.amber }}>
              {Math.round(run.overall_confidence * 100)}% conf
            </span>
          </>
        )}
      </div>

      {total > 0 && (
        <div
          className="mt-2 h-1 rounded-full overflow-hidden"
          style={{ background: t.bgTrack }}
          role="progressbar"
          aria-valuenow={progress}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`${progress}% complete`}
        >
          <div
            className="h-full rounded-full transition-all"
            style={{ width: `${progress}%`, background: cfg.color }}
          />
        </div>
      )}
    </button>
  );
};

export default WorkflowRunCard;
