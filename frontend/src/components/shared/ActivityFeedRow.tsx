import React from 'react';
import { StatusBadge, type SystemStatus } from './StatusBadge';
import { CAPABILITY_COLORS } from '../../constants/colors';

interface ActivityFeedRowProps {
  targetService: string;
  incidentId?: string;
  timestamp: string;
  status: SystemStatus;
  phase: string;
  confidenceScore: number;
  durationStr: string;
  onClick?: () => void;
  onViewReport?: () => void;
  isComplete?: boolean;
  capabilityIcon?: string;
  findingsCount?: number;
  criticalCount?: number;
  capability?: string;
}

export const ActivityFeedRow: React.FC<ActivityFeedRowProps> = ({
  targetService,
  incidentId,
  timestamp,
  status,
  phase,
  confidenceScore,
  durationStr,
  onClick,
  onViewReport,
  isComplete = false,
  capabilityIcon = 'memory',
  findingsCount,
  criticalCount,
  capability,
}) => {
  const barColor = confidenceScore >= 80 ? 'bg-emerald-500' : confidenceScore >= 50 ? 'bg-amber-500' : 'bg-red-500';
  const isRunning = !isComplete;

  const severityTint = status === 'critical' ? 'rgba(239, 68, 68, 0.06)'
    : (criticalCount ?? 0) > 0 ? 'rgba(239, 68, 68, 0.04)'
    : isRunning ? 'rgba(224, 159, 62, 0.03)'
    : 'transparent';

  return (
    <button
      onClick={onClick}
      className="w-full text-left px-4 py-3 border-b border-duck-border/30 hover:bg-duck-surface/30 transition-colors group focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent"
      style={{
        borderLeft: `3px solid ${CAPABILITY_COLORS[capability || ''] || '#3d3528'}`,
        backgroundColor: severityTint,
      }}
      aria-label={`${targetService} — ${phase}`}
    >
      {/* Row 1: Service + Incident ID + Status + Duration */}
      <div className="flex items-center gap-3 mb-1.5">
        <div className="w-7 h-7 rounded bg-duck-surface flex items-center justify-center border border-duck-border shrink-0">
          <span className="material-symbols-outlined text-[14px] text-duck-accent" aria-hidden="true">{capabilityIcon}</span>
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-display font-bold text-white truncate">{targetService}</span>
            {incidentId && <span className="text-duck-accent text-[9px] font-mono shrink-0">{incidentId}</span>}
          </div>
        </div>
        <StatusBadge status={status} label={phase} pulse={isRunning} />
        <span className="text-[10px] text-slate-400 font-mono shrink-0" style={{ fontVariantNumeric: 'tabular-nums' }}>{timestamp}</span>
        <span className="text-[10px] text-slate-400 shrink-0">{durationStr}</span>
      </div>

      {/* Row 2: Confidence bar + Findings + Actions */}
      <div className="flex items-center gap-3 ml-10">
        {/* Confidence bar — wider, more prominent */}
        <div className="flex-1 h-1.5 bg-duck-surface rounded-full overflow-hidden max-w-[200px]">
          <div
            className={`h-full ${barColor} rounded-full transition-all duration-700`}
            style={{ width: `${confidenceScore}%` }}
          />
        </div>
        <span className="text-[10px] text-slate-400 font-mono shrink-0" style={{ fontVariantNumeric: 'tabular-nums' }}>
          {confidenceScore}%
        </span>

        {/* Findings */}
        {findingsCount != null && findingsCount > 0 ? (
          <div className="flex items-center gap-1.5 shrink-0">
            {(criticalCount ?? 0) > 0 && (
              <span className="text-[10px] font-bold text-red-400">{criticalCount} crit</span>
            )}
            <span className="text-[10px] text-slate-400">{findingsCount} findings</span>
          </div>
        ) : findingsCount === 0 && isComplete ? (
          <span className="text-[10px] text-emerald-400 shrink-0">Clean</span>
        ) : null}

        {/* Actions — right-aligned */}
        <div className="ml-auto shrink-0">
          {isComplete && onViewReport ? (
            <span
              role="button"
              tabIndex={0}
              onClick={(e) => { e.stopPropagation(); onViewReport(); }}
              onKeyDown={(e) => { if (e.key === 'Enter') { e.stopPropagation(); onViewReport(); } }}
              className="flex items-center gap-1 text-duck-accent hover:text-amber-300 transition-colors cursor-pointer"
              aria-label={`Download report for ${targetService}`}
            >
              <span className="material-symbols-outlined text-[12px]" aria-hidden="true">download</span>
              <span className="text-[9px] font-display font-bold">Report</span>
            </span>
          ) : isRunning ? (
            <div className="flex items-center gap-1 text-amber-400/60">
              <span className="material-symbols-outlined text-[12px] animate-spin" aria-hidden="true">progress_activity</span>
              <span className="text-[9px]">Running</span>
            </div>
          ) : null}
        </div>
      </div>
    </button>
  );
};
