import React, { useMemo } from 'react';
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis,
  Tooltip, CartesianGrid, ReferenceLine,
} from 'recharts';

export interface NeuralChartLine {
  dataKey: string;
  color: 'cyan' | 'amber' | 'red' | 'slate';
  label?: string;
}

export interface NeuralChartProps {
  data: Array<Record<string, number | string>>;
  lines: NeuralChartLine[];
  height?: number;
  showGrid?: boolean;
  thresholdValue?: number;
  xAxisKey?: string;
}

const COLOR_MAP: Record<string, string> = {
  cyan: '#07b6d5',
  amber: '#f59e0b',
  red: '#ef4444',
  slate: '#64748b',
};

const GLOW_FILTER_ID = 'neural-glow';

const WarRoomTooltip: React.FC<{ active?: boolean; payload?: Array<{ name: string; value: number; color: string }>; label?: string }> = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-[#0f2023]/95 backdrop-blur-sm border border-slate-700/50 rounded px-3 py-2 shadow-xl">
      <div className="text-[9px] text-slate-500 font-mono mb-1">{label}</div>
      {payload.map((p, i) => (
        <div key={i} className="flex items-center gap-2 text-[10px] font-mono">
          <span className="w-2 h-2 rounded-full" style={{ backgroundColor: p.color }} />
          <span className="text-slate-400">{p.name}:</span>
          <span className="text-slate-200 font-medium">{typeof p.value === 'number' ? p.value.toFixed(2) : p.value}</span>
        </div>
      ))}
    </div>
  );
};

const NeuralChart: React.FC<NeuralChartProps> = React.memo(({
  data,
  lines,
  height = 120,
  showGrid = true,
  thresholdValue,
  xAxisKey = 'timestamp',
}) => {
  // Deep memoize data to prevent SVG filter repainting
  const stableData = useMemo(() => data, [JSON.stringify(data)]);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={stableData} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
        {/* SVG glow filter */}
        <defs>
          <filter id={GLOW_FILTER_ID} x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="2" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {showGrid && (
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(100,116,139,0.15)" />
        )}

        <XAxis
          dataKey={xAxisKey}
          tick={{ fontSize: 9, fill: '#64748b' }}
          axisLine={{ stroke: '#334155' }}
          tickLine={false}
        />
        <YAxis
          tick={{ fontSize: 9, fill: '#64748b' }}
          axisLine={{ stroke: '#334155' }}
          tickLine={false}
          width={40}
        />

        <Tooltip content={<WarRoomTooltip />} />

        {thresholdValue !== undefined && (
          <ReferenceLine
            y={thresholdValue}
            stroke="#f59e0b"
            strokeDasharray="4 4"
            strokeWidth={1}
          />
        )}

        {lines.map(line => (
          <Line
            key={line.dataKey}
            type="monotone"
            dataKey={line.dataKey}
            stroke={COLOR_MAP[line.color]}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 3, fill: COLOR_MAP[line.color] }}
            name={line.label || line.dataKey}
            filter={`url(#${GLOW_FILTER_ID})`}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
});

NeuralChart.displayName = 'NeuralChart';

export default NeuralChart;
