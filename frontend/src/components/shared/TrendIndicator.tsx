import React from 'react';

interface TrendIndicatorProps {
  value: string;
  direction: 'up' | 'down' | 'neutral';
  type: 'good' | 'bad' | 'neutral';
}

export const TrendIndicator: React.FC<TrendIndicatorProps> = ({ value, direction, type }) => {
  const styles = type === 'good'
    ? 'text-green-500 bg-green-500/10'
    : type === 'bad'
      ? 'text-[#ef4444] bg-[#ef4444]/10'
      : 'text-slate-400 bg-slate-400/10';

  const icon = direction === 'up' ? 'arrow_upward' : direction === 'down' ? 'arrow_downward' : 'remove';

  return (
    <div className={`flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono font-bold ${styles}`}>
      <span className="material-symbols-outlined text-[12px]" style={{ fontFamily: 'Material Symbols Outlined' }}>{icon}</span>
      {value}
    </div>
  );
};
