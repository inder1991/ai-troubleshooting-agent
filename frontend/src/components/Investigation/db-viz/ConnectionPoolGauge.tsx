import React from 'react';

interface ConnectionPoolGaugeProps {
  active: number;
  idle: number;
  waiting: number;
  max: number;
}

const ConnectionPoolGauge: React.FC<ConnectionPoolGaugeProps> = ({
  active,
  idle,
  waiting,
  max,
}) => {
  const utilization = max > 0 ? (active / max) * 100 : 0;
  const radius = 40;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (circumference * Math.min(utilization, 100)) / 100;

  const color =
    utilization > 80 ? '#ef4444' : utilization > 60 ? '#f59e0b' : '#10b981';

  return (
    <div className="flex items-center gap-4">
      {/* SVG Arc Gauge */}
      <div className="relative w-24 h-24">
        <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
          {/* Background circle */}
          <circle
            cx="50"
            cy="50"
            r={radius}
            fill="none"
            stroke="#1e2f33"
            strokeWidth="8"
          />
          {/* Progress arc */}
          <circle
            cx="50"
            cy="50"
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            className="transition-all duration-700 ease-out"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-lg font-bold" style={{ color }}>
            {Math.round(utilization)}%
          </span>
          <span className="text-[8px] text-slate-500 uppercase tracking-wider">used</span>
        </div>
      </div>

      {/* Stats */}
      <div className="space-y-1.5">
        {[
          { label: 'Active', value: active, dotColor: color },
          { label: 'Idle', value: idle, dotColor: '#64748b' },
          { label: 'Waiting', value: waiting, dotColor: '#f59e0b' },
          { label: 'Max', value: max, dotColor: '#475569' },
        ].map(({ label, value, dotColor }) => (
          <div key={label} className="flex items-center gap-2">
            <span
              className="w-2 h-2 rounded-full"
              style={{ backgroundColor: dotColor }}
            />
            <span className="text-[10px] text-slate-400 w-12">{label}</span>
            <span className="text-[11px] text-white font-mono">{value}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default ConnectionPoolGauge;
