import React from 'react';
import type { Severity } from '../../types';

interface InlineCardProps {
  title: string;
  keyStat: string;
  confidence: number;
  severity: Severity;
}

const severityColors: Record<Severity, string> = {
  critical: 'bg-red-600',
  high: 'bg-orange-600',
  medium: 'bg-yellow-600',
  low: 'bg-blue-600',
  info: 'bg-gray-600',
};

const InlineCard: React.FC<InlineCardProps> = ({
  title,
  keyStat,
  confidence,
  severity,
}) => {
  const confidencePercent = Math.round(confidence * 100);

  return (
    <div className="inline-flex items-center gap-3 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 my-1">
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-white truncate">{title}</div>
        <div className="text-xs text-gray-400">{keyStat}</div>
      </div>
      <span
        className={`text-xs px-2 py-0.5 rounded-full text-white ${severityColors[severity]}`}
      >
        {severity}
      </span>
      <span
        className={`text-xs px-2 py-0.5 rounded-full ${
          confidencePercent >= 80
            ? 'bg-green-700 text-green-100'
            : confidencePercent >= 50
            ? 'bg-yellow-700 text-yellow-100'
            : 'bg-red-700 text-red-100'
        }`}
      >
        {confidencePercent}%
      </span>
    </div>
  );
};

export default InlineCard;
