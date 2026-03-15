import React, { useState } from 'react';
import type { ScoredRecommendationDTO } from '../../types';

interface RecommendationCardProps {
  rec: ScoredRecommendationDTO;
}

const severityDot: Record<string, string> = {
  critical: 'bg-red-500',
  high: 'bg-red-400',
  medium: 'bg-amber-500',
  low: 'bg-blue-400',
  info: 'bg-slate-400',
};

const riskBg: Record<string, string> = {
  safe: 'bg-green-500/15 text-green-400 border-green-500/30',
  caution: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  destructive: 'bg-red-500/15 text-red-400 border-red-500/30',
};

const RecommendationCard: React.FC<RecommendationCardProps> = ({ rec }) => {
  const [showCommands, setShowCommands] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);

  const copyText = (text: string, label: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(label);
      setTimeout(() => setCopied(null), 1500);
    });
  };

  return (
    <div className="bg-[#1e1b15] border border-[#3d3528]/50 rounded-lg p-4 hover:border-[#3d3528] transition-colors">
      {/* Title row */}
      <div className="flex items-start gap-2 mb-2">
        <span className={`w-2 h-2 rounded-full flex-shrink-0 mt-1.5 ${severityDot[rec.severity] || severityDot.info}`} />
        <div className="flex-1 min-w-0">
          <h4 className="text-sm font-medium text-slate-100">{rec.title}</h4>
          <p className="text-xs text-slate-400 mt-1 leading-relaxed">{rec.description}</p>
        </div>

        {/* Badges */}
        <div className="flex items-center gap-2 flex-shrink-0">
          {rec.estimated_savings_usd > 0 && (
            <span className="text-[10px] font-medium bg-green-500/15 text-green-400 border border-green-500/30 px-2 py-0.5 rounded">
              -${rec.estimated_savings_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}/mo
            </span>
          )}
          {rec.days_until_impact > 0 && rec.days_until_impact < 30 && (
            <span className="text-[10px] font-medium bg-red-500/15 text-red-400 border border-red-500/30 px-2 py-0.5 rounded">
              {rec.days_until_impact}d
            </span>
          )}
        </div>
      </div>

      {/* Meta row */}
      <div className="flex items-center gap-3 mt-3 flex-wrap">
        {/* Risk level */}
        <span className={`text-[10px] font-medium px-2 py-0.5 rounded border ${riskBg[rec.risk_level] || riskBg.caution}`}>
          {rec.risk_level}
        </span>

        {/* Confidence */}
        <span className="text-[10px] text-slate-500">
          {(rec.confidence * 100).toFixed(0)}% confidence
        </span>

        {/* Score */}
        <span className="text-[10px] text-slate-500">
          Score: {rec.score.toFixed(1)}
        </span>

        {/* Source */}
        <span className="text-[10px] text-slate-600">{rec.source}</span>
      </div>

      {/* Affected resources */}
      {rec.affected_resources.length > 0 && (
        <div className="mt-3">
          <div className="text-[10px] text-slate-500 mb-1">Affected Resources</div>
          <div className="flex flex-wrap gap-1">
            {rec.affected_resources.slice(0, 5).map((r, i) => (
              <span key={i} className="text-[10px] bg-[#252118] text-slate-400 px-2 py-0.5 rounded font-mono">
                {r}
              </span>
            ))}
            {rec.affected_resources.length > 5 && (
              <span className="text-[10px] text-slate-500">+{rec.affected_resources.length - 5} more</span>
            )}
          </div>
        </div>
      )}

      {/* Commands toggle */}
      {rec.commands.length > 0 && (
        <div className="mt-3">
          <button
            onClick={() => setShowCommands(!showCommands)}
            className="text-[10px] text-[#e09f3e] hover:text-[#e09f3e]/80 transition-colors flex items-center gap-1"
          >
            <span className="material-symbols-outlined text-[14px]">{showCommands ? 'expand_less' : 'expand_more'}</span>
            {showCommands ? 'Hide' : 'Show'} commands ({rec.commands.length})
          </button>

          {showCommands && (
            <div className="mt-2 space-y-2">
              {rec.commands.map((cmd, i) => (
                <div key={i} className="flex items-start gap-2 bg-[#13110d] rounded px-3 py-2">
                  <code className="text-[11px] text-slate-300 font-mono flex-1 break-all">{cmd}</code>
                  <button
                    onClick={() => copyText(cmd, `cmd-${i}`)}
                    className="text-slate-500 hover:text-slate-300 transition-colors flex-shrink-0"
                    title="Copy"
                  >
                    <span className="material-symbols-outlined text-[14px]">
                      {copied === `cmd-${i}` ? 'check' : 'content_copy'}
                    </span>
                  </button>
                </div>
              ))}

              {/* Dry Run / Rollback */}
              <div className="flex items-center gap-2 pt-1">
                {rec.dry_run_command && (
                  <button
                    onClick={() => copyText(rec.dry_run_command, 'dry-run')}
                    className="px-2.5 py-1 text-[10px] font-medium bg-blue-500/15 text-blue-400 border border-blue-500/30 rounded hover:bg-blue-500/25 transition-colors"
                  >
                    {copied === 'dry-run' ? 'Copied!' : 'Dry Run'}
                  </button>
                )}
                {rec.rollback_command && (
                  <button
                    onClick={() => copyText(rec.rollback_command, 'rollback')}
                    className="px-2.5 py-1 text-[10px] font-medium bg-red-500/15 text-red-400 border border-red-500/30 rounded hover:bg-red-500/25 transition-colors"
                  >
                    {copied === 'rollback' ? 'Copied!' : 'Rollback'}
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default RecommendationCard;
