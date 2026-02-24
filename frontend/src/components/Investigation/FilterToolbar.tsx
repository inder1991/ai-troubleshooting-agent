import React from 'react';
import type { FilterMode } from './Investigator';

interface FilterToolbarProps {
  mode: FilterMode;
  onModeChange: (mode: FilterMode) => void;
  counts: { all: number; reasoning: number; findings: number; raw: number };
}

const filters: { key: FilterMode; label: string }[] = [
  { key: 'all', label: 'ALL' },
  { key: 'reasoning', label: 'INTEL' },
  { key: 'findings', label: 'FINDS' },
  { key: 'raw', label: 'RAW' },
];

export const FilterToolbar: React.FC<FilterToolbarProps> = ({ mode, onModeChange, counts }) => {
  return (
    <div className="flex gap-0.5">
      {filters.map((f) => {
        const isActive = mode === f.key;
        return (
          <button
            key={f.key}
            onClick={() => onModeChange(f.key)}
            className={`text-[9px] px-2 py-0.5 rounded border font-bold uppercase tracking-wider transition-colors ${
              isActive
                ? 'bg-[#07b6d5]/20 text-[#07b6d5] border-[#07b6d5]/30'
                : 'bg-slate-800/50 text-slate-500 border-slate-700 hover:text-slate-400'
            }`}
            aria-pressed={isActive}
          >
            {f.label}
            <span className="ml-1 font-mono text-[8px] opacity-60">({counts[f.key]})</span>
          </button>
        );
      })}
    </div>
  );
};
