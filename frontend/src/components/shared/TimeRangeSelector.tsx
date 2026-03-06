import React from 'react';

interface TimeRangeSelectorProps {
  options?: string[];
  selected: string;
  onChange: (range: string) => void;
}

export const TimeRangeSelector: React.FC<TimeRangeSelectorProps> = ({
  options = ['5m', '15m', '1h', '6h', '24h', '7d'],
  selected,
  onChange,
}) => (
  <div className="flex items-center gap-0.5 bg-[#0a1517] rounded-lg p-0.5 border border-[#224349]">
    {options.map((opt) => (
      <button
        key={opt}
        onClick={() => onChange(opt)}
        className={`px-2.5 py-1 text-[10px] font-mono font-bold uppercase rounded-md transition-colors ${
          selected === opt
            ? 'bg-[#07b6d5]/20 text-[#07b6d5] border border-[#07b6d5]/30'
            : 'text-slate-500 hover:text-slate-300 border border-transparent'
        }`}
      >
        {opt}
      </button>
    ))}
  </div>
);
