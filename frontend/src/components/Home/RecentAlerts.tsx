import React, { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { V4Session } from '../../types';
import { listSessionsV4 } from '../../services/api';

interface Alert {
  id: string;
  message: string;
  severity: 'critical' | 'warning' | 'info';
  age: string;
}

const severityStyles: Record<string, { icon: string; cls: string }> = {
  critical: { icon: 'error', cls: 'text-red-400' },
  warning: { icon: 'warning', cls: 'text-amber-400' },
  info: { icon: 'info', cls: 'text-slate-400' },
};

function timeAgo(dateStr: string): string {
  const ms = Date.now() - new Date(dateStr).getTime();
  if (ms < 60000) return 'just now';
  if (ms < 3600000) return `${Math.floor(ms / 60000)}m ago`;
  if (ms < 86400000) return `${Math.floor(ms / 3600000)}h ago`;
  return `${Math.floor(ms / 86400000)}d ago`;
}

export const RecentAlerts: React.FC = () => {
  const { data: sessions = [] } = useQuery({
    queryKey: ['live-sessions'],
    queryFn: listSessionsV4,
    refetchInterval: 15000,
    staleTime: 8000,
  });

  const alerts = useMemo<Alert[]>(() => {
    const result: Alert[] = [];

    // Derive alerts from recent session data
    const completed = sessions.filter(s =>
      ['complete', 'diagnosis_complete'].includes(s.status)
    );

    for (const s of completed.slice(0, 10)) {
      const critCount = s.critical_count ?? 0;
      const findCount = s.findings_count ?? 0;

      if (critCount > 0) {
        result.push({
          id: `${s.session_id}-crit`,
          message: `${critCount} critical issue${critCount > 1 ? 's' : ''} in ${s.service_name}`,
          severity: 'critical',
          age: timeAgo(s.updated_at),
        });
      } else if (findCount > 3) {
        result.push({
          id: `${s.session_id}-warn`,
          message: `${findCount} findings in ${s.service_name}`,
          severity: 'warning',
          age: timeAgo(s.updated_at),
        });
      }
    }

    // Check for currently running sessions (long-running = warning)
    const running = sessions.filter(s => !['complete', 'diagnosis_complete', 'error', 'cancelled'].includes(s.status));
    for (const s of running) {
      const elapsed = Date.now() - new Date(s.created_at).getTime();
      if (elapsed > 300000) { // > 5 minutes
        result.push({
          id: `${s.session_id}-long`,
          message: `${s.service_name} investigation running ${Math.floor(elapsed / 60000)}m`,
          severity: 'info',
          age: timeAgo(s.created_at),
        });
      }
    }

    return result.slice(0, 5);
  }, [sessions]);

  return (
    <div>
      <h3 className="text-[10px] font-display font-bold text-slate-400 mb-1.5">Recent Alerts</h3>
      {alerts.length === 0 ? (
        <div className="flex items-center gap-2 py-1">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500/40" aria-hidden="true" />
          <span className="text-[10px] text-slate-400">All clear — no alerts</span>
        </div>
      ) : (
        <div className="space-y-1.5">
          {alerts.map((alert) => {
            const sev = severityStyles[alert.severity] || severityStyles.info;
            return (
              <div key={alert.id} className="flex items-start gap-1.5">
                <span className={`material-symbols-outlined text-[12px] mt-0.5 shrink-0 ${sev.cls}`} aria-hidden="true">
                  {sev.icon}
                </span>
                <span className="text-[10px] text-slate-300 flex-1">{alert.message}</span>
                <span className="text-[9px] text-slate-500 shrink-0">{alert.age}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
