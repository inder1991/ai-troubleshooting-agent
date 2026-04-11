import React from 'react';
import type { WorkloadDetail } from '../../types';

interface WorkloadCardProps {
  workload: WorkloadDetail;
  domainColor: string;
}

const statusIcon: Record<string, string> = {
  CrashLoopBackOff: 'restart_alt',
  Pending: 'hourglass_top',
  Failed: 'error',
  Running: 'check_circle',
  Completed: 'task_alt',
};

const WorkloadCard: React.FC<WorkloadCardProps> = ({ workload, domainColor }) => {
  const isTrigger = workload.is_trigger;
  const isCrashing = workload.status === 'CrashLoopBackOff' || workload.status === 'Failed';

  return (
    <div className={`bg-wr-bg/60 border border-l-2 rounded p-3 ${isTrigger ? 'border-red-500 shadow-lg' : 'border-wr-border'}`} style={{ borderLeftColor: domainColor }}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded border flex items-center justify-center ${
            isCrashing ? 'border-red-500 bg-red-500/10 text-red-500' : `border-wr-border text-slate-500`
          }`}>
            <span
              className={`material-symbols-outlined ${isCrashing ? 'animate-pulse' : ''}`}
            >
              {statusIcon[workload.status] || 'deployed_code'}
            </span>
          </div>
          <div>
            <div className="text-sm font-bold text-white">
              {workload.status === 'CrashLoopBackOff' ? 'Pod Restart Loop' : workload.status}
            </div>
            <div className="text-body-xs font-mono text-slate-500">{workload.name}</div>
          </div>
        </div>
        {isTrigger && (
          <div className="flex flex-col items-end gap-1">
            <span className="px-2 py-1 bg-red-500/20 text-red-500 text-body-xs font-bold border border-red-500 rounded tracking-tighter">TRIGGER</span>
            {workload.age && <span className="text-body-xs text-slate-500 font-mono">{workload.age}</span>}
          </div>
        )}
      </div>

      {(workload.cpu_usage || workload.memory_usage || workload.restarts != null) && (
        <div className="mt-3 grid grid-cols-2 sm:grid-cols-3 gap-2">
          {workload.cpu_usage && (
            <div className="bg-wr-bg p-2 rounded border border-wr-border/30">
              <div className="text-body-xs text-slate-500 uppercase">CPU Usage</div>
              <div className={`text-xs font-mono ${parseInt(workload.cpu_usage) > 80 ? 'text-amber-500' : 'text-slate-300'}`}>
                {workload.cpu_usage}
              </div>
            </div>
          )}
          {workload.memory_usage && (
            <div className="bg-wr-bg p-2 rounded border border-wr-border/30">
              <div className="text-body-xs text-slate-500 uppercase">Memory</div>
              <div className="text-xs font-mono text-slate-300">{workload.memory_usage}</div>
            </div>
          )}
          {workload.restarts != null && (
            <div className="bg-wr-bg p-2 rounded border border-wr-border/30">
              <div className="text-body-xs text-slate-500 uppercase">Restarts</div>
              <div className={`text-xs font-mono ${workload.restarts > 5 ? 'text-red-500' : 'text-slate-300'}`}>
                {workload.restarts}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default WorkloadCard;
