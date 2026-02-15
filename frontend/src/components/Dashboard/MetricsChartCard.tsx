import React from 'react';
import type { MetricAnomaly, Severity } from '../../types';

interface MetricsChartCardProps {
  anomalies: MetricAnomaly[];
}

const severityColor = (severity: Severity): string => {
  const colors: Record<Severity, string> = {
    critical: '#ef4444',
    high: '#f97316',
    medium: '#eab308',
    low: '#3b82f6',
    info: '#6b7280',
  };
  return colors[severity];
};

const MetricsChartCard: React.FC<MetricsChartCardProps> = ({ anomalies }) => {
  if (anomalies.length === 0) return null;

  const maxDeviation = Math.max(...anomalies.map((a) => Math.abs(a.deviation_percent)));

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
      <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-yellow-500" />
        Metric Anomalies
      </h3>

      {/* Simple SVG bar chart */}
      <div className="mb-4">
        <svg
          viewBox={`0 0 400 ${anomalies.length * 40 + 10}`}
          className="w-full"
          style={{ maxHeight: '300px' }}
        >
          {anomalies.map((a, i) => {
            const barWidth = (Math.abs(a.deviation_percent) / maxDeviation) * 280;
            const y = i * 40 + 5;
            return (
              <g key={i}>
                <text x="0" y={y + 18} fill="#9ca3af" fontSize="11" fontFamily="monospace">
                  {a.metric_name.length > 16
                    ? a.metric_name.substring(0, 16) + '...'
                    : a.metric_name}
                </text>
                <rect
                  x="120"
                  y={y + 4}
                  width={barWidth}
                  height="20"
                  rx="3"
                  fill={severityColor(a.severity)}
                  opacity="0.8"
                />
                <text x={120 + barWidth + 5} y={y + 18} fill="#d1d5db" fontSize="11" fontFamily="monospace">
                  {a.direction === 'above' ? '+' : '-'}{Math.round(a.deviation_percent)}%
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* Data table */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-400 border-b border-gray-700">
              <th className="text-left py-1.5 pr-2">Metric</th>
              <th className="text-right py-1.5 pr-2">Current</th>
              <th className="text-right py-1.5 pr-2">Baseline</th>
              <th className="text-right py-1.5">Deviation</th>
            </tr>
          </thead>
          <tbody>
            {anomalies.map((a, i) => (
              <tr key={i} className="border-b border-gray-700/50">
                <td className="py-1.5 pr-2 text-gray-300 truncate max-w-[140px]">{a.metric_name}</td>
                <td className="py-1.5 pr-2 text-right text-gray-300 font-mono">
                  {a.current_value.toFixed(2)}
                </td>
                <td className="py-1.5 pr-2 text-right text-gray-300 font-mono">
                  {a.baseline_value.toFixed(2)}
                </td>
                <td
                  className="py-1.5 text-right font-mono"
                  style={{ color: severityColor(a.severity) }}
                >
                  {a.direction === 'above' ? '+' : '-'}{Math.round(a.deviation_percent)}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default MetricsChartCard;
