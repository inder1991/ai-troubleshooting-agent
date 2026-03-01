import React, { useState, useCallback } from 'react';
import type { OperationalRecommendation, CommandStep } from '../../../types';

const URGENCY_STYLES: Record<string, { label: string; className: string }> = {
  immediate: { label: 'IMMEDIATE', className: 'text-red-400 bg-red-950/30 border-red-500/40' },
  short_term: { label: 'SHORT TERM', className: 'text-amber-400 bg-amber-950/30 border-amber-500/40' },
  preventive: { label: 'PREVENTIVE', className: 'text-slate-400 bg-slate-800/30 border-slate-500/40' },
};

const RISK_STYLES: Record<string, { label: string; className: string }> = {
  safe: { label: 'SAFE', className: 'text-emerald-400' },
  caution: { label: 'CAUTION', className: 'text-amber-400' },
  destructive: { label: 'DESTRUCTIVE', className: 'text-red-400' },
};

// Detect <PLACEHOLDER> syntax in commands
const PLACEHOLDER_REGEX = /<[A-Z_]+>/g;

const hasPlaceholder = (command: string): boolean => {
  PLACEHOLDER_REGEX.lastIndex = 0;
  return PLACEHOLDER_REGEX.test(command);
};

const renderCommand = (command: string): React.ReactNode => {
  // Reset regex
  PLACEHOLDER_REGEX.lastIndex = 0;
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = PLACEHOLDER_REGEX.exec(command)) !== null) {
    if (match.index > lastIndex) {
      parts.push(command.slice(lastIndex, match.index));
    }
    parts.push(
      <span key={match.index} className="text-amber-400 bg-amber-950/40 px-1 rounded animate-pulse font-bold">
        {match[0]}
      </span>
    );
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < command.length) {
    parts.push(command.slice(lastIndex));
  }
  return parts.length > 0 ? parts : command;
};

interface CommandBlockProps {
  step: CommandStep;
  showDryRun: boolean;
}

const CommandBlock: React.FC<CommandBlockProps> = ({ step, showDryRun }) => {
  const [copied, setCopied] = useState(false);
  const command = showDryRun && step.dry_run_command ? step.dry_run_command : step.command;

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(command);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [command]);

  return (
    <div className="space-y-1">
      <div className="text-[9px] text-slate-500">{step.order}. {step.description}</div>
      <div className="relative group">
        <pre className="text-[10px] font-mono bg-slate-950/60 border border-slate-800/50 rounded px-3 py-2 text-slate-300 overflow-x-auto whitespace-pre-wrap">
          <span className="text-slate-600 mr-2">$</span>
          {renderCommand(command)}
        </pre>
        <button
          onClick={handleCopy}
          className="absolute top-1.5 right-1.5 opacity-0 group-hover:opacity-100 transition-opacity px-1.5 py-0.5 rounded text-[9px] bg-slate-800 text-slate-400 hover:text-cyan-400"
        >
          {copied ? 'Copied!' : 'Copy'}
        </button>
      </div>
      {step.validation_command && (
        <div className="text-[9px] text-slate-600 pl-2">
          Verify: <code className="text-slate-500">{step.validation_command}</code>
        </div>
      )}
    </div>
  );
};

interface RecommendationCardProps {
  recommendation: OperationalRecommendation;
}

const RecommendationCard: React.FC<RecommendationCardProps> = ({ recommendation: rec }) => {
  const [showDryRun, setShowDryRun] = useState(true);
  const [showRollback, setShowRollback] = useState(false);

  const urgency = URGENCY_STYLES[rec.urgency] || URGENCY_STYLES.preventive;
  const risk = RISK_STYLES[rec.risk_level] || RISK_STYLES.safe;

  const hasDryRun = rec.commands.some(c => c.dry_run_command);
  const commandsHavePlaceholders = rec.commands.some(c => hasPlaceholder(c.command));

  return (
    <div className="rounded border border-slate-800/40 bg-slate-900/20 p-3 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`text-[8px] font-bold px-1.5 py-0.5 rounded border ${urgency.className}`}>
            {urgency.label}
          </span>
          <span className="text-[10px] text-slate-300 font-medium">{rec.title}</span>
        </div>
        <span className={`text-[8px] font-bold ${risk.className}`}>{risk.label}</span>
      </div>

      {/* Placeholder warning */}
      {commandsHavePlaceholders && (
        <div className="flex items-center gap-1.5 text-[9px] text-amber-400 bg-amber-950/20 border border-amber-500/20 rounded px-2 py-1">
          <span className="material-symbols-outlined text-[14px]">warning</span>
          Commands contain placeholders — review before executing
        </div>
      )}

      {/* Prerequisites */}
      {rec.prerequisites.length > 0 && (
        <div className="space-y-0.5">
          <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">Prerequisites</span>
          {rec.prerequisites.map((p, i) => (
            <div key={i} className="text-[10px] text-slate-400 pl-2">{'\u2022'} {p}</div>
          ))}
        </div>
      )}

      {/* Dry-run toggle */}
      {hasDryRun && (
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowDryRun(true)}
            className={`text-[9px] font-bold px-2 py-0.5 rounded transition-colors ${showDryRun ? 'bg-cyan-950/40 text-cyan-400 border border-cyan-700/40' : 'text-slate-500 hover:text-slate-300'}`}
          >
            Dry Run
          </button>
          <button
            onClick={() => setShowDryRun(false)}
            className={`text-[9px] font-bold px-2 py-0.5 rounded transition-colors ${!showDryRun ? 'bg-cyan-950/40 text-cyan-400 border border-cyan-700/40' : 'text-slate-500 hover:text-slate-300'}`}
          >
            Live
          </button>
        </div>
      )}

      {/* Command steps */}
      <div className="space-y-2">
        {rec.commands.map(step => (
          <CommandBlock key={step.order} step={step} showDryRun={showDryRun} />
        ))}
      </div>

      {/* Expected outcome */}
      <div className="text-[9px] text-slate-500">
        <span className="font-bold uppercase tracking-wider">Expected outcome:</span> {rec.expected_outcome}
      </div>

      {/* Rollback section */}
      {rec.rollback_commands.length > 0 && (
        <div>
          <button
            onClick={() => setShowRollback(!showRollback)}
            className="flex items-center gap-1 text-[9px] text-slate-500 hover:text-slate-300 transition-colors"
          >
            <span className="material-symbols-outlined text-[14px]">{showRollback ? 'expand_more' : 'chevron_right'}</span>
            Rollback Commands ({rec.rollback_commands.length})
          </button>
          {showRollback && (
            <div className="mt-2 space-y-2 border-l-2 border-red-500/30 pl-3">
              {rec.rollback_commands.map(step => (
                <CommandBlock key={step.order} step={step} showDryRun={false} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default RecommendationCard;
