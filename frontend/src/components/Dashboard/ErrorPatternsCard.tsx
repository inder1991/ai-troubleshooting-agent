import React from 'react';
import type { ErrorPattern, Severity } from '../../types';

interface ErrorPatternsCardProps {
  patterns: ErrorPattern[];
}

const severityBadge = (severity: Severity): string => {
  const colors: Record<Severity, string> = {
    critical: 'bg-red-600 text-red-100',
    high: 'bg-orange-600 text-orange-100',
    medium: 'bg-yellow-600 text-yellow-100',
    low: 'bg-blue-600 text-blue-100',
    info: 'bg-gray-600 text-gray-100',
  };
  return colors[severity];
};

const ErrorPatternsCard: React.FC<ErrorPatternsCardProps> = ({ patterns }) => {
  if (patterns.length === 0) return null;

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
      <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-red-500" />
        Error Patterns
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-400 text-xs border-b border-gray-700">
              <th className="text-left py-2 pr-3">Pattern</th>
              <th className="text-left py-2 pr-3">Severity</th>
              <th className="text-right py-2 pr-3">Count</th>
              <th className="text-right py-2">Confidence</th>
            </tr>
          </thead>
          <tbody>
            {patterns.map((p, i) => (
              <tr key={i} className="border-b border-gray-700/50 hover:bg-gray-700/30">
                <td className="py-2 pr-3 text-gray-200 max-w-[200px] truncate" title={p.sample_message}>
                  {p.pattern}
                </td>
                <td className="py-2 pr-3">
                  <span className={`text-xs px-2 py-0.5 rounded-full ${severityBadge(p.severity)}`}>
                    {p.severity}
                  </span>
                </td>
                <td className="py-2 pr-3 text-right text-gray-300 font-mono">{p.count}</td>
                <td className="py-2 text-right text-gray-300 font-mono">
                  {Math.round(p.confidence * 100)}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default ErrorPatternsCard;
