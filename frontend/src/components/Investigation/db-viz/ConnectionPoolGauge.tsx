import React from 'react';
import { VIZ_COLORS } from '../db-board/constants';

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
    utilization > 80 ? VIZ_COLORS.critical : utilization > 60 ? VIZ_COLORS.warning : VIZ_COLORS.excellent;

  return (
    <div className="flex items-center gap-4">
      {/* SVG Arc Gauge */}
      <div className="relative w-24 h-24">
        <svg viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet" className="w-full h-auto -rotate-90">
          {/* Background circle */}
          <circle
            cx="50"
            cy="50"
            r={radius}
            fill="none"
            stroke="#252118"
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
          <span className="text-chrome text-slate-400 uppercase tracking-wider">used</span>
        </div>
      </div>

      {/* Stats */}
      <div className="space-y-1.5">
        {[
          { label: 'Active', value: active, dotColor: color },
          { label: 'Idle', value: idle, dotColor: VIZ_COLORS.neutral },
          { label: 'Waiting', value: waiting, dotColor: VIZ_COLORS.warning },
          { label: 'Max', value: max, dotColor: '#475569' },
        ].map(({ label, value, dotColor }) => (
          <div key={label} className="flex items-center gap-2">
            <span
              className="w-2 h-2 rounded-full"
              style={{ backgroundColor: dotColor }}
            />
            <span className="text-body-xs text-slate-400 w-12">{label}</span>
            <span className="text-body-xs text-white font-mono">{value}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default ConnectionPoolGauge;
