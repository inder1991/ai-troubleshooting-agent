import React, { useState } from 'react';
import { AlertEvent } from './hooks/useMonitorSnapshot';
import { acknowledgeAlert } from '../../services/api';

interface Props {
  alerts: AlertEvent[];
  onRefresh: () => void;
}

const severityColors: Record<string, string> = {
  critical: '#ef4444',
  warning: '#f59e0b',
  info: '#07b6d5',
};

const AlertsTab: React.FC<Props> = ({ alerts, onRefresh }) => {
  const [filter, setFilter] = useState<string>('all');

  const filtered = filter === 'all'
    ? alerts
    : alerts.filter(a => a.severity === filter);

  const handleAck = async (key: string) => {
    try {
      await acknowledgeAlert(key);
      onRefresh();
    } catch {
      // Toast would be nice here
    }
  };

  return (
    <div className="p-6 space-y-4">
      {/* Filter buttons */}
      <div className="flex gap-2">
        {['all', 'critical', 'warning', 'info'].map(s => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className="px-3 py-1 rounded text-xs font-mono transition-colors"
            style={{
              backgroundColor: filter === s ? '#1a3a40' : 'transparent',
              color: s === 'all' ? '#e2e8f0' : severityColors[s] || '#e2e8f0',
              border: `1px solid ${filter === s ? '#07b6d5' : '#224349'}`,
            }}
          >
            {s.toUpperCase()}
            {s !== 'all' && ` (${alerts.filter(a => a.severity === s).length})`}
          </button>
        ))}
      </div>

      {/* Alert list */}
      {filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16">
          <span className="material-symbols-outlined text-4xl mb-3" style={{ color: '#224349' }}>
            check_circle
          </span>
          <span className="text-sm font-mono" style={{ color: '#64748b' }}>
            No active alerts
          </span>
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map(alert => (
            <div
              key={alert.key}
              className="rounded border p-3 flex items-center justify-between"
              style={{
                backgroundColor: '#0a1a1e',
                borderColor: (severityColors[alert.severity] || '#224349') + '40',
                borderLeftWidth: '3px',
                borderLeftColor: severityColors[alert.severity] || '#224349',
                opacity: alert.acknowledged ? 0.5 : 1,
              }}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span
                    className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded"
                    style={{
                      backgroundColor: (severityColors[alert.severity] || '#224349') + '20',
                      color: severityColors[alert.severity] || '#e2e8f0',
                    }}
                  >
                    {alert.severity.toUpperCase()}
                  </span>
                  <span className="text-sm font-mono" style={{ color: '#e2e8f0' }}>
                    {alert.rule_name}
                  </span>
                  {alert.acknowledged && (
                    <span className="text-[9px] font-mono px-1.5 py-0.5 rounded"
                      style={{ backgroundColor: '#22432920', color: '#64748b' }}>
                      ACK
                    </span>
                  )}
                </div>
                <div className="text-xs font-mono mt-1" style={{ color: '#64748b' }}>
                  {alert.entity_id} — {alert.metric}: {alert.value.toFixed(1)} ({alert.condition} {alert.threshold})
                </div>
                <div className="text-[10px] font-mono mt-0.5" style={{ color: '#4a5568' }}>
                  {new Date(alert.fired_at * 1000).toLocaleString()}
                </div>
              </div>
              {!alert.acknowledged && (
                <button
                  onClick={() => handleAck(alert.key)}
                  className="text-xs font-mono px-3 py-1.5 rounded border transition-colors hover:border-[#07b6d5]"
                  style={{ borderColor: '#224349', color: '#64748b' }}
                >
                  Acknowledge
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default AlertsTab;
