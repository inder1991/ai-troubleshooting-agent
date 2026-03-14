import React from 'react';
import { SparklineWidget } from './SparklineWidget';
import { TrendIndicator } from './TrendIndicator';

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
  const sparkColor = trendType === 'good' ? 'green' : trendType === 'bad' ? 'red' : 'gold';

  return (
    <div className="bg-[#1a1814] border border-[#3d3528] rounded-lg p-4 flex flex-col justify-between h-32 hover:border-[#e09f3e]/50 transition-colors relative overflow-hidden group">
      <div className="absolute inset-0 bg-gradient-to-b from-transparent to-[#e09f3e]/5 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />

      <div className="flex justify-between items-start z-10">
        <h3 className="text-[#8a7e6b] text-xs font-semibold font-display">{title}</h3>
        <TrendIndicator value={trendValue} direction={trendDirection} type={trendType} />
      </div>

      <div className="flex items-end justify-between mt-2 z-10">
        <div className="text-3xl font-display font-bold text-[#e8e0d4] tracking-tight">{value}</div>
        <div className="w-24 opacity-80 group-hover:opacity-100 transition-opacity">
          <SparklineWidget data={sparklineData} color={sparkColor} height={28} />
        </div>
      </div>
    </div>
  );
};
