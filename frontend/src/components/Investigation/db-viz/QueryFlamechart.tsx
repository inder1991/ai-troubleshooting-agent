import React, { useState } from 'react';
import { VIZ_COLORS } from '../db-board/constants';

interface PlanStep {
  label: string;
  time_ms: number;
  children?: PlanStep[];
}

interface QueryFlamechartProps {
  planSteps: PlanStep[];
}

function stepColor(time_ms: number, maxTime: number): string {
  const ratio = maxTime > 0 ? Math.min(time_ms / maxTime, 1) : 0;
  if (ratio > 0.7) return VIZ_COLORS.critical;
  if (ratio > 0.4) return VIZ_COLORS.warning;
  if (ratio > 0.15) return VIZ_COLORS.good;
  return VIZ_COLORS.excellent;
}

function collectMaxTime(steps: PlanStep[]): number {
  let max = 0;
  for (const s of steps) {
    if (s.time_ms > max) max = s.time_ms;
    if (s.children) {
      const childMax = collectMaxTime(s.children);
      if (childMax > max) max = childMax;
    }
  }
  return max;
}

function collectTotalTime(steps: PlanStep[]): number {
  let total = 0;
  for (const s of steps) {
    total += s.time_ms;
    if (s.children) total += collectTotalTime(s.children);
  }
  return total;
}

const FlameBar: React.FC<{
  step: PlanStep;
  maxTime: number;
  rootTotal: number;
  depth: number;
}> = ({ step, maxTime, rootTotal, depth }) => {
  const [expanded, setExpanded] = useState(depth < 4);
  const hasChildren = step.children && step.children.length > 0;
  const color = stepColor(step.time_ms, maxTime);
  const widthPct = rootTotal > 0 ? Math.max((step.time_ms / rootTotal) * 100, 8) : 100;

  return (
    <div style={{ marginLeft: depth > 0 ? 12 : 0 }}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="group relative flex items-center w-full text-left mb-0.5"
      >
        <div
          className="flex items-center gap-2 px-2 py-1 rounded transition-opacity hover:opacity-90 cursor-pointer"
          style={{
            width: `${widthPct}%`,
            minWidth: '80px',
            backgroundColor: `${color}20`,
            border: `1px solid ${color}40`,
          }}
        >
          {hasChildren && (
            <span
              className={`material-symbols-outlined text-[10px] text-slate-500 transition-transform ${expanded ? 'rotate-90' : ''}`}
            >
              chevron_right
            </span>
          )}
          <span className="text-[10px] text-slate-200 truncate flex-1 font-mono">
            {step.label}
          </span>
          <span
            className="text-[9px] font-bold font-mono whitespace-nowrap"
            style={{ color }}
          >
            {step.time_ms.toFixed(1)}ms
          </span>
        </div>

        {/* Tooltip */}
        <div className="absolute left-0 bottom-full mb-1 hidden group-hover:block z-10">
          <div className="bg-slate-900 border border-slate-700 rounded px-2 py-1 shadow-lg whitespace-nowrap">
            <p className="text-[10px] text-white font-mono">{step.label}</p>
            <p className="text-[9px] text-slate-400">
              {step.time_ms.toFixed(2)}ms
              {rootTotal > 0 && ` (${((step.time_ms / rootTotal) * 100).toFixed(1)}%)`}
            </p>
          </div>
        </div>
      </button>

      {expanded && hasChildren && (
        <div className="border-l border-slate-800 ml-1">
          {step.children!.map((child, i) => (
            <FlameBar
              key={i}
              step={child}
              maxTime={maxTime}
              rootTotal={rootTotal}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
};

const QueryFlamechart: React.FC<QueryFlamechartProps> = ({ planSteps }) => {
  if (planSteps.length === 0) {
    return (
      <div className="text-center py-4">
        <span className="material-symbols-outlined text-2xl text-slate-700 block mb-1">local_fire_department</span>
        <p className="text-[10px] text-slate-400">No plan steps available</p>
      </div>
    );
  }

  const maxTime = collectMaxTime(planSteps);
  const totalTime = collectTotalTime(planSteps);

  return (
    <div className="bg-duck-card/30 border border-duck-border rounded-lg p-3 overflow-x-auto">
      {/* Header */}
      <div className="flex items-center gap-2 mb-2 pb-2 border-b border-slate-800">
        <span className="material-symbols-outlined text-orange-400 text-sm">local_fire_department</span>
        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Query Flamechart</span>
        <span className="text-[9px] text-slate-400 ml-auto font-mono">total {totalTime.toFixed(1)}ms</span>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-3 mb-2">
        {[
          { label: 'Hot (>70%)', color: VIZ_COLORS.critical },
          { label: 'Warm (>40%)', color: VIZ_COLORS.warning },
          { label: 'Moderate', color: VIZ_COLORS.good },
          { label: 'Fast', color: VIZ_COLORS.excellent },
        ].map(({ label, color }) => (
          <div key={label} className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-sm" style={{ backgroundColor: color }} />
            <span className="text-[9px] text-slate-400">{label}</span>
          </div>
        ))}
      </div>

      {/* Flame bars */}
      <div className="space-y-0.5">
        {planSteps.map((step, i) => (
          <FlameBar
            key={i}
            step={step}
            maxTime={maxTime}
            rootTotal={totalTime}
            depth={0}
          />
        ))}
      </div>
    </div>
  );
};

export default QueryFlamechart;
