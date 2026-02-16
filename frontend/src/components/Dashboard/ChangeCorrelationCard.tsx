import React from 'react';
import { GitCommit, RotateCcw, FileCode, User, Clock } from 'lucide-react';
import type { ChangeCorrelation } from '../../types';

interface ChangeCorrelationCardProps {
  changes: ChangeCorrelation[];
}

const changeTypeBadge: Record<string, { label: string; className: string }> = {
  code_deploy: { label: 'Deploy', className: 'bg-blue-500/20 text-blue-400' },
  config_change: { label: 'Config', className: 'bg-purple-500/20 text-purple-400' },
  infra_change: { label: 'Infra', className: 'bg-orange-500/20 text-orange-400' },
  dependency_update: { label: 'Dependency', className: 'bg-teal-500/20 text-teal-400' },
};

function riskColor(score: number): string {
  if (score > 0.7) return '#ef4444';
  if (score >= 0.4) return '#eab308';
  return '#22c55e';
}

function riskLabel(score: number): string {
  if (score > 0.7) return 'High';
  if (score >= 0.4) return 'Medium';
  return 'Low';
}

function riskBgClass(score: number): string {
  if (score > 0.7) return 'bg-red-500/20 text-red-400';
  if (score >= 0.4) return 'bg-yellow-500/20 text-yellow-400';
  return 'bg-green-500/20 text-green-400';
}

const ChangeCorrelationCard: React.FC<ChangeCorrelationCardProps> = ({ changes }) => {
  if (changes.length === 0) return null;

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
      <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
        <GitCommit className="w-4 h-4 text-[#07b6d5]" />
        Change Correlations
        <span className="text-xs text-gray-500 font-normal ml-auto">
          {changes.length} recent {changes.length === 1 ? 'change' : 'changes'}
        </span>
      </h3>

      <div className="space-y-2">
        {changes.map((change) => {
          const badge = changeTypeBadge[change.change_type] || {
            label: change.change_type,
            className: 'bg-gray-500/20 text-gray-400',
          };
          const color = riskColor(change.risk_score);

          return (
            <div
              key={change.change_id}
              className="bg-[#1a2a2e] border border-gray-700 rounded-lg p-3"
            >
              {/* Header: type badge + risk label */}
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${badge.className}`}>
                    {badge.label}
                  </span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${riskBgClass(change.risk_score)}`}>
                    {riskLabel(change.risk_score)} Risk
                  </span>
                </div>
                {change.risk_score > 0.7 && (
                  <button
                    className="flex items-center gap-1 text-[10px] px-2 py-1 rounded border border-red-500/40 bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors cursor-pointer"
                    onClick={() => {}}
                    title="Rollback this change (not yet functional)"
                  >
                    <RotateCcw className="w-3 h-3" />
                    Rollback
                  </button>
                )}
              </div>

              {/* Description */}
              <p className="text-xs text-gray-300 mb-2 line-clamp-2">{change.description}</p>

              {/* Risk score bar */}
              <div className="flex items-center gap-2 mb-2">
                <span className="text-[10px] text-gray-500 w-14 flex-shrink-0">Risk</span>
                <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all"
                    style={{ width: `${Math.round(change.risk_score * 100)}%`, backgroundColor: color }}
                  />
                </div>
                <span className="text-[10px] font-mono text-gray-400 w-8 text-right">
                  {Math.round(change.risk_score * 100)}%
                </span>
              </div>

              {/* Temporal correlation bar */}
              <div className="flex items-center gap-2 mb-2">
                <span className="text-[10px] text-gray-500 w-14 flex-shrink-0">Temporal</span>
                <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full bg-[#07b6d5] transition-all"
                    style={{ width: `${Math.round(change.temporal_correlation * 100)}%` }}
                  />
                </div>
                <span className="text-[10px] font-mono text-gray-400 w-8 text-right">
                  {Math.round(change.temporal_correlation * 100)}%
                </span>
              </div>

              {/* Meta: author, files, timestamp */}
              <div className="flex items-center gap-3 text-[10px] text-gray-500">
                <span className="flex items-center gap-1">
                  <User className="w-3 h-3" />
                  {change.author}
                </span>
                {change.files_changed.length > 0 && (
                  <span className="flex items-center gap-1">
                    <FileCode className="w-3 h-3" />
                    {change.files_changed.length} {change.files_changed.length === 1 ? 'file' : 'files'}
                  </span>
                )}
                {change.timestamp && (
                  <span className="flex items-center gap-1 ml-auto">
                    <Clock className="w-3 h-3" />
                    {new Date(change.timestamp).toLocaleTimeString()}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default ChangeCorrelationCard;
