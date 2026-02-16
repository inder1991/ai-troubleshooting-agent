import React from 'react';
import type { Finding, CriticVerdict, Breadcrumb, Severity } from '../../types';

interface DiagnosisSummaryCardProps {
  confidence: number;
  findings: Finding[];
  criticVerdicts: CriticVerdict[];
  breadcrumbs: Breadcrumb[];
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

const verdictBadge = (verdict: CriticVerdict['verdict']): string => {
  const colors: Record<CriticVerdict['verdict'], string> = {
    confirmed: 'bg-green-700 text-green-200',
    plausible: 'bg-blue-700 text-blue-200',
    weak: 'bg-yellow-700 text-yellow-200',
    rejected: 'bg-red-700 text-red-200',
  };
  return colors[verdict];
};

const DiagnosisSummaryCard: React.FC<DiagnosisSummaryCardProps> = ({
  confidence,
  findings,
  criticVerdicts,
  breadcrumbs,
}) => {
  const confidencePercent = Math.round(confidence * 100);
  const confidenceColor =
    confidencePercent >= 80
      ? 'text-green-400'
      : confidencePercent >= 50
      ? 'text-yellow-400'
      : 'text-red-400';

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
      <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-green-500" />
        Diagnosis Summary
      </h3>

      {/* Overall Confidence */}
      <div className="bg-gray-900/50 rounded px-4 py-3 mb-4 text-center">
        <div className="text-xs text-gray-400 mb-1">Overall Confidence</div>
        <div className={`text-3xl font-bold ${confidenceColor}`}>
          {confidencePercent}%
        </div>
      </div>

      {/* Findings with Critic Verdicts */}
      {findings.length > 0 && (
        <div className="mb-4">
          <h4 className="text-xs text-gray-400 mb-2 uppercase tracking-wide">
            Findings ({findings.length})
          </h4>
          <div className="space-y-2">
            {findings.map((finding, i) => {
              const verdict = criticVerdicts.find((v) => v.finding_index === i);
              return (
                <div key={i} className="bg-gray-900/50 rounded px-3 py-2">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm text-gray-200 flex-1">{finding.title}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full ${severityBadge(finding.severity)}`}>
                      {finding.severity}
                    </span>
                    {verdict && (
                      <span className={`text-xs px-2 py-0.5 rounded-full ${verdictBadge(verdict.verdict)}`}>
                        {verdict.verdict}
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-gray-400">{finding.description}</div>
                  <div className="text-xs text-gray-500 mt-1">
                    Agent: {finding.agent_name} | Confidence: {Math.round(finding.confidence * 100)}%
                  </div>
                  {verdict && (
                    <div className="text-xs text-gray-500 mt-1 italic">
                      Critic: {verdict.reasoning}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Breadcrumbs */}
      {breadcrumbs.length > 0 && (
        <div>
          <h4 className="text-xs text-gray-400 mb-2 uppercase tracking-wide">
            Investigation Trail ({breadcrumbs.length})
          </h4>
          <div className="space-y-1 max-h-40 overflow-y-auto">
            {breadcrumbs.map((bc, i) => (
              <div key={i} className="flex items-start gap-2 text-xs">
                <span className="text-gray-600 whitespace-nowrap font-mono">
                  {new Date(bc.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                </span>
                <span className="text-blue-400 font-medium whitespace-nowrap">{bc.agent_name}</span>
                <span className="text-gray-400">{bc.action}</span>
                <span className="text-gray-500 truncate">{bc.detail}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default DiagnosisSummaryCard;
