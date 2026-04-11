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
            className={`text-body-xs px-2 py-0.5 rounded border font-bold uppercase tracking-wider transition-colors ${
              isActive
                ? 'bg-[#e09f3e]/20 text-[#e09f3e] border-[#e09f3e]/30'
                : 'bg-slate-800/50 text-slate-400 border-slate-700 hover:text-slate-400'
            }`}
            aria-pressed={isActive}
          >
            {f.label}
            <span className="ml-1 font-mono text-chrome opacity-80 bg-slate-800 text-slate-300 px-1 rounded">({counts[f.key]})</span>
          </button>
        );
      })}
    </div>
  );
};
