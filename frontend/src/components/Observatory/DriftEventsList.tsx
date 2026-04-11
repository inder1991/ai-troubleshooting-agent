import React, { useState } from 'react';
import type { DriftEvent } from './hooks/useMonitorSnapshot';

interface Props {
  drifts: DriftEvent[];
}

const severityColor: Record<string, string> = {
  critical: '#ef4444',
  warning: '#f59e0b',
  info: '#e09f3e',
};

const DriftEventsList: React.FC<Props> = ({ drifts }) => {
  const [expanded, setExpanded] = useState<string | null>(null);

  if (drifts.length === 0) return null;

  const criticalCount = drifts.filter((d) => d.severity === 'critical').length;
  const warningCount = drifts.filter((d) => d.severity === 'warning').length;
  const infoCount = drifts.filter((d) => d.severity === 'info').length;

  return (
    <div className="rounded-lg border" style={{ backgroundColor: '#0a1a1e', borderColor: '#3d3528' }}>
      <div className="flex items-center justify-between px-3 py-2 border-b" style={{ borderColor: '#3d3528' }}>
        <span className="text-xs font-semibold text-white">Drift Events</span>
        <div className="flex gap-2 text-body-xs font-mono">
          {criticalCount > 0 && <span style={{ color: '#ef4444' }}>{criticalCount} critical</span>}
          {warningCount > 0 && <span style={{ color: '#f59e0b' }}>{warningCount} warning</span>}
          {infoCount > 0 && <span style={{ color: '#e09f3e' }}>{infoCount} info</span>}
        </div>
      </div>
      <div className="max-h-48 overflow-y-auto">
        {drifts.map((d) => (
          <div
            key={d.id}
            className="px-3 py-1.5 border-b cursor-pointer hover:bg-[#1e1b15]"
            style={{ borderColor: '#1a3038' }}
            onClick={() => setExpanded(expanded === d.id ? null : d.id)}
          >
            <div className="flex items-center gap-2 text-xs">
              <span
                className="inline-block w-1.5 h-1.5 rounded-full flex-shrink-0"
                style={{ backgroundColor: severityColor[d.severity] }}
              />
              <span style={{ color: '#e8e0d4' }}>{d.entity_type}</span>
              <span style={{ color: '#64748b' }}>{d.drift_type}</span>
              <span className="font-mono" style={{ color: '#8a7e6b' }}>{d.field}</span>
            </div>
            {expanded === d.id && (
              <div className="mt-1 pl-4 text-body-xs font-mono space-y-0.5">
                <div><span style={{ color: '#64748b' }}>Expected: </span><span style={{ color: '#22c55e' }}>{d.expected}</span></div>
                <div><span style={{ color: '#64748b' }}>Actual: </span><span style={{ color: '#ef4444' }}>{d.actual}</span></div>
                <div style={{ color: '#64748b' }}>Detected: {new Date(d.detected_at).toLocaleString()}</div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default DriftEventsList;
