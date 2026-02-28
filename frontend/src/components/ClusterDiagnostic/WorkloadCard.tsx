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
    <div className={`bg-[#0f2023]/60 border rounded p-3 ${isTrigger ? 'border-red-500 shadow-lg' : 'border-[#1f3b42]'}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded border flex items-center justify-center ${
            isCrashing ? 'border-red-500 bg-red-500/10 text-red-500' : `border-[#1f3b42] text-slate-500`
          }`}>
            <span
              className={`material-symbols-outlined ${isCrashing ? 'animate-pulse' : ''}`}
              style={{ fontFamily: 'Material Symbols Outlined' }}
            >
              {statusIcon[workload.status] || 'deployed_code'}
            </span>
          </div>
          <div>
            <div className="text-sm font-bold text-white">
              {workload.status === 'CrashLoopBackOff' ? 'Pod Restart Loop' : workload.status}
            </div>
            <div className="text-[10px] font-mono text-slate-500">{workload.name}</div>
          </div>
        </div>
        {isTrigger && (
          <div className="flex flex-col items-end gap-1">
            <span className="px-2 py-1 bg-red-500/20 text-red-500 text-[10px] font-bold border border-red-500 rounded tracking-tighter">TRIGGER</span>
            {workload.age && <span className="text-[9px] text-slate-500 font-mono">{workload.age}</span>}
          </div>
        )}
      </div>

      {(workload.cpu_usage || workload.memory_usage || workload.restarts != null) && (
        <div className="mt-3 grid grid-cols-3 gap-2">
          {workload.cpu_usage && (
            <div className="bg-[#0f2023] p-2 rounded border border-[#1f3b42]/30">
              <div className="text-[9px] text-slate-500 uppercase">CPU Usage</div>
              <div className={`text-xs font-mono ${parseInt(workload.cpu_usage) > 80 ? 'text-amber-500' : 'text-slate-300'}`}>
                {workload.cpu_usage}
              </div>
            </div>
          )}
          {workload.memory_usage && (
            <div className="bg-[#0f2023] p-2 rounded border border-[#1f3b42]/30">
              <div className="text-[9px] text-slate-500 uppercase">Memory</div>
              <div className="text-xs font-mono text-slate-300">{workload.memory_usage}</div>
            </div>
          )}
          {workload.restarts != null && (
            <div className="bg-[#0f2023] p-2 rounded border border-[#1f3b42]/30">
              <div className="text-[9px] text-slate-500 uppercase">Restarts</div>
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
