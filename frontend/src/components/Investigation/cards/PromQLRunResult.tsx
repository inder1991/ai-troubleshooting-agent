import React from 'react';
import type { TimeSeriesDataPoint } from '../../../types';
import AnomalySparkline from './AnomalySparkline';

interface PromQLRunResultProps {
  dataPoints: TimeSeriesDataPoint[];
  currentValue: number;
  loading: boolean;
  error?: string;
}

const PromQLRunResult: React.FC<PromQLRunResultProps> = ({
  dataPoints,
  currentValue,
  loading,
  error,
}) => {
  if (loading) {
    return (
      <div className="mt-2 space-y-1.5">
        <div className="h-2 w-3/4 bg-cyan-500/20 rounded animate-pulse" />
        <div className="h-2 w-1/2 bg-cyan-500/10 rounded animate-pulse" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="mt-2 text-[10px] text-red-400 font-mono">
        {error}
      </div>
    );
  }

  if (dataPoints.length === 0) return null;

  // Determine severity color from current value (heuristic)
  const valueColor = 'text-cyan-400';

  return (
    <div className="mt-2 space-y-1.5">
      <AnomalySparkline
        dataPoints={dataPoints}
        baselineValue={dataPoints.length > 0 ? dataPoints[0].value : 0}
        peakValue={Math.max(...dataPoints.map((dp) => dp.value))}
        spikeStart=""
        spikeEnd=""
        severity="info"
      />
      <div className="flex items-baseline gap-2">
        <span className="text-[10px] text-slate-500">Current:</span>
        <span className={`text-sm font-mono font-bold ${valueColor}`}>
          {formatNumber(currentValue)}
        </span>
      </div>
    </div>
  );
};

function formatNumber(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(2)}k`;
  if (v < 0.01 && v > 0) return v.toExponential(2);
  return v.toFixed(2);
}

export default PromQLRunResult;
