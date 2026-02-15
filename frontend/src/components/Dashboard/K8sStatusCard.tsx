import React from 'react';
import type { PodHealthStatus, K8sEvent } from '../../types';

interface K8sStatusCardProps {
  pods: PodHealthStatus[];
  events: K8sEvent[];
}

const podStatusColor = (status: string, crashLoop: boolean, oomKilled: boolean): string => {
  if (crashLoop) return 'text-red-400';
  if (oomKilled) return 'text-orange-400';
  if (status === 'Running') return 'text-green-400';
  if (status === 'Pending') return 'text-yellow-400';
  return 'text-gray-400';
};

const K8sStatusCard: React.FC<K8sStatusCardProps> = ({ pods, events }) => {
  if (pods.length === 0 && events.length === 0) return null;

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
      <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-blue-500" />
        Kubernetes Status
      </h3>

      {pods.length > 0 && (
        <div className="mb-4">
          <h4 className="text-xs text-gray-400 mb-2 uppercase tracking-wide">Pod Health</h4>
          <div className="space-y-2">
            {pods.map((pod, i) => (
              <div
                key={i}
                className="flex items-center justify-between bg-gray-900/50 rounded px-3 py-2"
              >
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-gray-200 truncate font-mono">{pod.pod_name}</div>
                  <div className="text-xs text-gray-500">{pod.namespace}</div>
                </div>
                <div className="flex items-center gap-2 ml-3">
                  {pod.crash_loop && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-red-900 text-red-300">
                      CrashLoopBackOff
                    </span>
                  )}
                  {pod.oom_killed && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-orange-900 text-orange-300">
                      OOMKilled
                    </span>
                  )}
                  <span className={`text-xs font-medium ${podStatusColor(pod.status, pod.crash_loop, pod.oom_killed)}`}>
                    {pod.status}
                  </span>
                  {pod.restart_count > 0 && (
                    <span className="text-xs text-gray-500">
                      {pod.restart_count} restarts
                    </span>
                  )}
                  <span
                    className={`w-2 h-2 rounded-full ${pod.ready ? 'bg-green-500' : 'bg-red-500'}`}
                    title={pod.ready ? 'Ready' : 'Not Ready'}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {events.length > 0 && (
        <div>
          <h4 className="text-xs text-gray-400 mb-2 uppercase tracking-wide">Events</h4>
          <div className="space-y-1 max-h-48 overflow-y-auto">
            {events.map((evt, i) => (
              <div
                key={i}
                className={`text-xs px-3 py-1.5 rounded ${
                  evt.type === 'Warning'
                    ? 'bg-yellow-900/30 text-yellow-300'
                    : 'bg-gray-900/30 text-gray-400'
                }`}
              >
                <span className="font-medium">{evt.reason}</span>
                <span className="mx-1 opacity-50">|</span>
                <span>{evt.message}</span>
                {evt.count > 1 && (
                  <span className="ml-1 opacity-50">(x{evt.count})</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default K8sStatusCard;
