import React from 'react';
import { SparklineWidget } from './SparklineWidget';

interface MetricCardProps {
  title: string;
  value: string | number;
  trendValue: string;
  trendDirection: 'up' | 'down' | 'neutral';
  trendType: 'good' | 'bad' | 'neutral';
  sparklineData: number[];
}

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  trendValue,
  trendDirection,
  trendType,
  sparklineData,
}) => {
  const trendStyles = trendType === 'good'
    ? 'text-green-500 bg-green-500/10'
    : trendType === 'bad'
      ? 'text-[#ef4444] bg-[#ef4444]/10'
      : 'text-slate-400 bg-slate-400/10';

  const sparkColor = trendType === 'good' ? 'green' : trendType === 'bad' ? 'red' : 'cyan';
  const arrowIcon = trendDirection === 'up' ? 'arrow_upward' : trendDirection === 'down' ? 'arrow_downward' : 'remove';

  return (
    <div className="bg-[#0f2023] border border-[#224349] rounded-lg p-4 flex flex-col justify-between h-32 hover:border-[#07b6d5]/50 transition-colors relative overflow-hidden group">
      <div className="absolute inset-0 bg-gradient-to-b from-transparent to-[#07b6d5]/5 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />

      <div className="flex justify-between items-start z-10">
        <h3 className="text-[#94a3b8] text-xs font-semibold uppercase tracking-wider">{title}</h3>
        <div className={`flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono font-bold ${trendStyles}`}>
          <span className="material-symbols-outlined text-[12px]" style={{ fontFamily: 'Material Symbols Outlined' }}>{arrowIcon}</span>
          {trendValue}
        </div>
      </div>

      <div className="flex items-end justify-between mt-2 z-10">
        <div className="text-3xl font-mono font-bold text-[#e2e8f0] tracking-tight">{value}</div>
        <div className="w-24 opacity-80 group-hover:opacity-100 transition-opacity">
          <SparklineWidget data={sparklineData} color={sparkColor} height={28} />
        </div>
      </div>
    </div>
  );
};
