import React from 'react';
import type { CodeImpact } from '../../types';

interface CodeImpactCardProps {
  impacts: CodeImpact[];
}

const impactTypeBadge = (type: CodeImpact['impact_type']): string => {
  const colors: Record<CodeImpact['impact_type'], string> = {
    root_cause: 'bg-red-900 text-red-300',
    affected: 'bg-orange-900 text-orange-300',
    dependency: 'bg-blue-900 text-blue-300',
    test: 'bg-green-900 text-green-300',
  };
  return colors[type];
};

const impactTypeLabel = (type: CodeImpact['impact_type']): string => {
  const labels: Record<CodeImpact['impact_type'], string> = {
    root_cause: 'Root Cause',
    affected: 'Affected',
    dependency: 'Dependency',
    test: 'Test',
  };
  return labels[type];
};

const CodeImpactCard: React.FC<CodeImpactCardProps> = ({ impacts }) => {
  if (impacts.length === 0) return null;

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
      <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-orange-500" />
        Code Impact
      </h3>
      <div className="space-y-2">
        {impacts.map((impact, i) => (
          <div key={i} className="bg-gray-900/50 rounded px-3 py-2">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-sm text-gray-200 font-mono truncate flex-1">
                {impact.file_path}
              </span>
              <span className={`text-xs px-2 py-0.5 rounded-full ${impactTypeBadge(impact.impact_type)}`}>
                {impactTypeLabel(impact.impact_type)}
              </span>
            </div>
            <div className="text-xs text-gray-400">{impact.description}</div>
            {impact.fix_area && (
              <div className="text-xs text-green-400 mt-1">
                Fix area: {impact.fix_area}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default CodeImpactCard;
