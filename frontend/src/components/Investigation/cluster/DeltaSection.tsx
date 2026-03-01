import React from 'react';
import type { ScanDelta } from '../../../types';

interface DeltaSectionProps {
  delta: ScanDelta;
}

export default function DeltaSection({ delta }: DeltaSectionProps) {
  const hasChanges = delta.new_risks.length > 0 || delta.resolved_risks.length > 0 ||
                     delta.worsened.length > 0 || delta.improved.length > 0;

  if (!hasChanges) {
    return (
      <div className="text-xs text-slate-500 italic px-3 py-2">No changes since last scan</div>
    );
  }

  return (
    <div className="space-y-2 px-3 py-2">
      {delta.new_risks.length > 0 && (
        <div>
          <span className="text-[10px] uppercase tracking-wider text-emerald-400 font-semibold">+ New</span>
          <div className="mt-1 space-y-0.5">
            {delta.new_risks.map((r, i) => (
              <div key={i} className="text-[11px] text-emerald-300/80 flex items-center gap-1">
                <span className="material-symbols-outlined text-xs">add</span>
                {r}
              </div>
            ))}
          </div>
        </div>
      )}
      {delta.resolved_risks.length > 0 && (
        <div>
          <span className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">Resolved</span>
          <div className="mt-1 space-y-0.5">
            {delta.resolved_risks.map((r, i) => (
              <div key={i} className="text-[11px] text-slate-500 line-through">{r}</div>
            ))}
          </div>
        </div>
      )}
      {delta.worsened.length > 0 && (
        <div>
          <span className="text-[10px] uppercase tracking-wider text-red-400 font-semibold">Worsened</span>
          <div className="mt-1 space-y-0.5">
            {delta.worsened.map((r, i) => (
              <div key={i} className="text-[11px] text-red-400 flex items-center gap-1">
                <span className="material-symbols-outlined text-xs">arrow_upward</span>
                {r}
              </div>
            ))}
          </div>
        </div>
      )}
      {delta.improved.length > 0 && (
        <div>
          <span className="text-[10px] uppercase tracking-wider text-emerald-400 font-semibold">Improved</span>
          <div className="mt-1 space-y-0.5">
            {delta.improved.map((r, i) => (
              <div key={i} className="text-[11px] text-emerald-300/80 flex items-center gap-1">
                <span className="material-symbols-outlined text-xs">arrow_downward</span>
                {r}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
