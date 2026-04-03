import React from 'react';
import type { WorkflowRun } from './useWorkflowRuns';

const STATUS_CONFIG: Record<WorkflowRun['status'], { color: string; icon: string; label: string }> = {
  completed:        { color: '#22c55e', icon: 'check_circle',      label: 'Completed' },
  failed:           { color: '#ef4444', icon: 'error',             label: 'Failed' },
  running:          { color: '#07b6d5', icon: 'progress_activity', label: 'Running' },
  waiting_approval: { color: '#f59e0b', icon: 'pending_actions',   label: 'Awaiting Approval' },
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
  return (
    <div
      onClick={onClick}
      className="px-4 py-3 cursor-pointer border-b"
      style={{
        borderColor: '#1e2a2e',
        background: selected ? 'rgba(7,182,213,0.06)' : 'transparent',
        borderLeft: selected ? '2px solid #07b6d5' : '2px solid transparent',
      }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-xs font-mono font-semibold truncate" style={{ color: '#e8e0d4' }}>
            {run.workflow_name}
          </div>
          <div className="text-[10px] font-mono mt-0.5 truncate" style={{ color: '#64748b' }}>
            {run.service_name}
          </div>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          <span className="material-symbols-outlined" style={{ fontSize: 14, color: cfg.color }}>
            {cfg.icon}
          </span>
          <span className="text-[10px] font-mono" style={{ color: cfg.color }}>{cfg.label}</span>
        </div>
      </div>

      <div className="mt-2 flex items-center gap-3 text-[10px] font-mono" style={{ color: '#3d4a50' }}>
        <span>{new Date(run.started_at).toLocaleString()}</span>
        <span>·</span>
        <span>{elapsed(run.started_at, run.finished_at)}</span>
        {run.overall_confidence !== undefined && (
          <>
            <span>·</span>
            <span style={{ color: run.overall_confidence > 0.8 ? '#22c55e' : '#f59e0b' }}>
              {Math.round(run.overall_confidence * 100)}% conf
            </span>
          </>
        )}
      </div>

      {total > 0 && (
        <div className="mt-2 h-1 rounded-full overflow-hidden" style={{ background: '#1e2a2e' }}>
          <div
            className="h-full rounded-full transition-all"
            style={{
              width: `${(run.agents_completed.length / total) * 100}%`,
              background: cfg.color,
            }}
          />
        </div>
      )}
    </div>
  );
};

export default WorkflowRunCard;
