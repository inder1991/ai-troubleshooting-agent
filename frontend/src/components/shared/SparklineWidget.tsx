import React, { useMemo } from 'react';

interface SparklineWidgetProps {
  data: number[];
  color?: 'cyan' | 'green' | 'amber' | 'red' | 'slate';
  width?: number | string;
  height?: number;
  strokeWidth?: number;
}

const colorMap: Record<string, string> = {
  cyan: '#13b6ec',
  green: '#22c55e',
  amber: '#f59e0b',
  red: '#ef4444',
  slate: '#64748b',
};

export const SparklineWidget: React.FC<SparklineWidgetProps> = ({
  data,
  color = 'cyan',
  width = '100%',
  height = 32,
  strokeWidth = 2,
}) => {
  const points = useMemo(() => {
    if (!data || data.length < 2) return '';
    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;
    return data
      .map((val, i) => {
        const x = (i / (data.length - 1)) * 100;
        const y = 100 - ((val - min) / range) * 100;
        return `${x},${y}`;
      })
      .join(' ');
  }, [data]);

  if (!data || data.length < 2) {
    return <div className="h-8 text-[10px] text-slate-500">No data</div>;
  }

  return (
    <svg
      width={width}
      height={height}
      viewBox="0 -5 100 110"
      preserveAspectRatio="none"
      className="overflow-visible"
    >
      <polyline
        fill="none"
        stroke={colorMap[color] || colorMap.cyan}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
        className="transition-all duration-300 ease-in-out"
      />
    </svg>
  );
};
