import React from 'react';

interface SaturationGaugeProps {
  metricName: string;
  currentValue: number;
  label?: string;
  threshold?: number;
}

const SaturationGauge: React.FC<SaturationGaugeProps> = ({
  metricName,
  currentValue,
  label,
  threshold = 0.9,
}) => {
  // Normalize: if value > 1.5, treat as percentage (divide by 100)
  const normalized = currentValue > 1.5 ? currentValue / 100 : currentValue;
  const pct = Math.min(Math.max(normalized, 0), 1);
  const displayPct = Math.round(pct * 100);

  // Color thresholds
  const color = pct > 0.9 ? '#ef4444' : pct > 0.7 ? '#f59e0b' : '#07b6d5';
  const isCritical = pct > threshold;

  // Arc geometry: semi-circle from left to right
  const cx = 60, cy = 55, r = 40;
  const startAngle = Math.PI; // left
  const endAngle = 0; // right
  const totalArc = Math.PI;

  // Full arc path (background)
  const arcPath = (startA: number, endA: number) => {
    const x1 = cx + r * Math.cos(startA);
    const y1 = cy - r * Math.sin(startA);
    const x2 = cx + r * Math.cos(endA);
    const y2 = cy - r * Math.sin(endA);
    const largeArc = Math.abs(startA - endA) > Math.PI ? 1 : 0;
    return `M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}`;
  };

  const bgPath = arcPath(startAngle, endAngle);

  // Value arc: from startAngle, sweep pct of totalArc
  const valueEndAngle = startAngle - pct * totalArc;
  const valuePath = arcPath(startAngle, valueEndAngle);

  // Circumference of full semi-circle for dasharray
  const fullLen = Math.PI * r;

  return (
    <div className={`flex flex-col items-center ${isCritical ? 'gauge-critical' : ''}`}>
      <svg viewBox="0 0 120 70" width="120" height="70" className="overflow-visible">
        {/* Background arc */}
        <path
          d={bgPath}
          fill="none"
          stroke="#334155"
          strokeWidth="8"
          strokeLinecap="round"
        />
        {/* Value arc */}
        <path
          d={bgPath}
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={fullLen}
          strokeDashoffset={fullLen * (1 - pct)}
        />
        {/* Center value text */}
        <text
          x={cx}
          y={cy - 5}
          textAnchor="middle"
          className="font-mono font-bold"
          fill="white"
          fontSize="16"
        >
          {displayPct}%
        </text>
      </svg>
      <span className="text-[9px] text-slate-500 truncate max-w-[120px] text-center mt-0.5">
        {label || metricName.split('/').pop()?.replace(/_/g, ' ')}
      </span>
    </div>
  );
};

export default SaturationGauge;
