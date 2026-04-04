import React, { useState, useRef, useCallback, useEffect } from 'react';
import type { ClusterRemediationStep, ClusterBlastRadius } from '../../types';
import { useChatUI } from '../../contexts/ChatContext';

interface RemediationCardProps {
  steps: ClusterRemediationStep[];
  blastRadius?: ClusterBlastRadius;
}

const HOLD_DURATION_MS = 1500;

const RemediationCard: React.FC<RemediationCardProps> = ({ steps, blastRadius }) => {
  const [holdingIndex, setHoldingIndex] = useState<number | null>(null);
  const [holdProgress, setHoldProgress] = useState(0);
  const [executedSteps, setExecutedSteps] = useState<Set<number>>(new Set());
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startRef = useRef(0);
  const { sendMessage, openDrawer } = useChatUI();

  const startHold = useCallback((index: number, command: string) => {
    setHoldingIndex(index);
    startRef.current = Date.now();
    timerRef.current = setInterval(() => {
      const elapsed = Date.now() - startRef.current;
      const pct = Math.min(elapsed / HOLD_DURATION_MS, 1);
      setHoldProgress(pct);
      if (pct >= 1) {
        if (timerRef.current) clearInterval(timerRef.current);
        setHoldingIndex(null);
        setHoldProgress(0);
        setExecutedSteps(prev => new Set(prev).add(index));
        sendMessage(`Execute: ${command}`);
        openDrawer();
      }
    }, 30);
  }, [sendMessage, openDrawer]);

  const cancelHold = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    setHoldingIndex(null);
    setHoldProgress(0);
  }, []);

  const runQuickAction = useCallback((command: string) => {
    sendMessage(`Execute: ${command}`);
    openDrawer();
  }, [sendMessage, openDrawer]);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  if (steps.length === 0) return null;

  const primaryStep = steps[0];

  return (
    <div className="bg-wr-surface border border-wr-border rounded-lg p-4 shadow-lg">
      <h3 className="text-[10px] uppercase font-bold tracking-widest text-slate-500 mb-3">Proposed Remediation</h3>

      {/* Pre-check command */}
      {primaryStep.pre_check && (
        <div className="mb-3">
          <span className="text-[9px] uppercase font-semibold text-slate-500 tracking-wider">Pre-check</span>
          <div className="bg-black/40 rounded p-2 font-mono text-[10px] text-blue-400 mt-1 border border-wr-border/30 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-slate-500 shrink-0">$</span>
              <span className="truncate">{primaryStep.pre_check}</span>
            </div>
            <button
              onClick={() => runQuickAction(primaryStep.pre_check!)}
              className="shrink-0 text-[9px] px-2 py-0.5 rounded border border-blue-500/30 text-blue-400 hover:bg-blue-500/10 transition-colors"
            >
              Run
            </button>
          </div>
        </div>
      )}

      {/* Dry-run command */}
      {primaryStep.dry_run && (
        <div className="mb-3">
          <span className="text-[9px] uppercase font-semibold text-slate-500 tracking-wider">Dry Run</span>
          <div className="bg-black/40 rounded p-2 font-mono text-[10px] text-amber-400 mt-1 border border-wr-border/30 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-slate-500 shrink-0">$</span>
              <span className="truncate">{primaryStep.dry_run}</span>
            </div>
            <button
              onClick={() => runQuickAction(primaryStep.dry_run!)}
              className="shrink-0 text-[9px] px-2 py-0.5 rounded border border-amber-500/30 text-amber-400 hover:bg-amber-500/10 transition-colors"
            >
              Preview
            </button>
          </div>
          {primaryStep.expected_output && (
            <div className="text-[9px] text-slate-600 mt-1 pl-2 border-l border-slate-700">
              Expected: {primaryStep.expected_output}
            </div>
          )}
        </div>
      )}

      {/* Main command */}
      {primaryStep.command && (
        <div className="bg-black/40 rounded p-3 font-mono text-xs text-emerald-400 mb-3 border border-wr-border/30 flex items-center gap-2">
          <span className="text-slate-500">$</span>
          {primaryStep.command}
        </div>
      )}

      {/* Validation errors */}
      {primaryStep.validation_errors && primaryStep.validation_errors.length > 0 && (
        <div className="mb-3 px-2 py-1.5 rounded border border-red-500/20 bg-red-500/5">
          <span className="text-[9px] uppercase font-semibold text-red-400 tracking-wider">Validation Errors</span>
          {primaryStep.validation_errors.map((err, i) => (
            <div key={i} className="text-[10px] text-red-300 mt-0.5">• {err}</div>
          ))}
        </div>
      )}

      {blastRadius && (
        <div className="text-[11px] text-slate-500 mb-4 leading-relaxed">
          <span className="text-amber-500 font-bold">Risk Assessment:</span>{' '}
          {blastRadius.affected_pods.length} pod{blastRadius.affected_pods.length !== 1 ? 's' : ''} affected
          across {blastRadius.affected_namespaces.length} namespace{blastRadius.affected_namespaces.length !== 1 ? 's' : ''}
          on {blastRadius.affected_nodes.length} node{blastRadius.affected_nodes.length !== 1 ? 's' : ''}.
          {blastRadius.summary && <span className="text-white ml-1">{blastRadius.summary}</span>}
          {blastRadius.affected_pods.length > 0 && (
            <div className="mt-1 font-mono text-[10px] text-slate-600">
              {blastRadius.affected_pods.slice(0, 5).join(', ')}
              {blastRadius.affected_pods.length > 5 && ` +${blastRadius.affected_pods.length - 5} more`}
            </div>
          )}
        </div>
      )}

      {/* Simulation preview */}
      {primaryStep.validation?.simulation && (
        <div className="mb-3 px-3 py-2 rounded border border-wr-border bg-wr-bg/40">
          <span className="text-[9px] uppercase font-bold tracking-wider text-slate-500">Impact Simulation</span>
          <div className="mt-1.5 space-y-1 text-[10px]">
            <div className="text-slate-400">
              <span className="text-slate-500">Action:</span>{' '}
              <span className="text-wr-accent font-mono">{primaryStep.validation.simulation.action}</span>{' '}
              <span className="text-slate-300 font-mono">{primaryStep.validation.simulation.target}</span>
            </div>
            <div className="text-slate-400">
              <span className="text-slate-500">Impact:</span>{' '}
              {primaryStep.validation.simulation.impact}
            </div>
            {primaryStep.validation.simulation.side_effects && primaryStep.validation.simulation.side_effects.length > 0 && (
              <div>
                <span className="text-slate-500">Side effects:</span>
                {primaryStep.validation.simulation.side_effects.map((se, i) => (
                  <div key={i} className="text-amber-400/70 ml-2">- {se}</div>
                ))}
              </div>
            )}
            <div className="text-slate-400">
              <span className="text-slate-500">Recovery:</span>{' '}
              {primaryStep.validation.simulation.recovery}
            </div>
          </div>
        </div>
      )}

      {/* Remediation confidence badge */}
      {primaryStep.validation?.remediation_confidence != null && (
        <div className="mb-3 flex items-center gap-2">
          <span className="text-[9px] uppercase font-semibold text-slate-500 tracking-wider">Confidence:</span>
          <span className="text-[10px] text-slate-400">{primaryStep.validation.confidence_label}</span>
          <span
            className="w-2 h-2 rounded-full"
            style={{
              backgroundColor:
                primaryStep.validation.remediation_confidence >= 0.8 ? 'var(--wr-status-success)' :
                primaryStep.validation.remediation_confidence >= 0.5 ? 'var(--wr-accent)' :
                primaryStep.validation.remediation_confidence >= 0.3 ? 'var(--wr-text-muted)' :
                'var(--wr-severity-high)',
            }}
          />
        </div>
      )}

      {/* Blocked reason */}
      {primaryStep.validation?.blocked && (
        <div className="mb-3 px-2 py-1.5 rounded border border-red-500/20 bg-red-500/5">
          <div className="flex items-center gap-1.5">
            <span className="material-symbols-outlined text-red-400 text-[14px]">block</span>
            <span className="text-[10px] text-red-400 font-semibold">Blocked</span>
          </div>
          {primaryStep.validation.block_reason && (
            <p className="text-[10px] text-red-300/70 mt-1">{primaryStep.validation.block_reason}</p>
          )}
        </div>
      )}

      {/* Requires confirmation warning */}
      {primaryStep.validation?.requires_confirmation && !primaryStep.validation?.blocked && primaryStep.command && (
        <div className="mb-2 flex items-center gap-1.5 px-2 py-1 rounded bg-amber-500/5 border border-amber-500/20">
          <span className="material-symbols-outlined text-amber-500 text-[14px]">warning</span>
          <span className="text-[9px] text-amber-400">This action requires manual confirmation before execution</span>
        </div>
      )}

      {primaryStep.command && !primaryStep.validation?.blocked && (
        <button
          className="w-full bg-wr-accent/10 border border-wr-accent rounded h-12 flex items-center justify-between px-4 relative overflow-hidden cursor-pointer select-none transition-colors"
          onMouseDown={() => startHold(0, primaryStep.command!)}
          onMouseUp={cancelHold}
          onMouseLeave={cancelHold}
          onTouchStart={() => startHold(0, primaryStep.command!)}
          onTouchEnd={cancelHold}
        >
          <div
            className="absolute inset-0 bg-red-900/80 z-0 transition-none"
            style={{ width: holdingIndex === 0 ? `${holdProgress * 100}%` : '0%' }}
          />
          <span className={`font-bold tracking-widest text-xs uppercase z-10 transition-colors ${
            holdingIndex === 0 ? 'text-white' : 'text-wr-accent'
          }`}>
            Confirm {primaryStep.description || 'Action'}
          </span>
          <div className="relative w-8 h-8 z-10">
            <svg className="w-full h-full rotate-[-90deg]" viewBox="0 0 36 36">
              <path
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                fill="none"
                stroke={holdingIndex === 0 ? '#ffffff30' : 'var(--wr-accent-glow)'}
                strokeWidth="3"
              />
              <path
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                fill="none"
                stroke={holdingIndex === 0 ? '#fff' : 'var(--wr-accent)'}
                strokeWidth="3"
                strokeDasharray={`${(holdingIndex === 0 ? holdProgress : 0) * 100}, 100`}
                style={{ filter: 'drop-shadow(0 0 2px rgba(224,159,62,0.8))' }}
              />
            </svg>
            <div className={`absolute inset-0 flex items-center justify-center text-[8px] font-mono font-bold transition-colors ${
              holdingIndex === 0 ? 'text-white' : 'text-wr-accent'
            }`}>
              HOLD
            </div>
          </div>
        </button>
      )}

      {/* Post-execution actions: Verify + Rollback */}
      {executedSteps.has(0) && (primaryStep.verify || primaryStep.rollback) && (
        <div className="flex gap-2 mt-2">
          {primaryStep.verify && (
            <button
              onClick={() => runQuickAction(primaryStep.verify!)}
              className="flex-1 text-[10px] px-3 py-1.5 rounded border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10 transition-colors font-semibold uppercase tracking-wider"
            >
              Verify
            </button>
          )}
          {primaryStep.rollback && (
            <button
              onClick={() => runQuickAction(primaryStep.rollback!)}
              className="flex-1 text-[10px] px-3 py-1.5 rounded border border-red-500/30 text-red-400 hover:bg-red-500/10 transition-colors font-semibold uppercase tracking-wider"
            >
              Rollback
            </button>
          )}
        </div>
      )}

      {/* Rollback/verify info shown even before execution */}
      {!executedSteps.has(0) && (primaryStep.verify || primaryStep.rollback) && (
        <div className="mt-2 text-[9px] text-slate-600 space-y-0.5">
          {primaryStep.rollback && (
            <div className="flex items-center gap-1">
              <span className="text-slate-500">Rollback:</span>
              <code className="text-red-400/60 font-mono">{primaryStep.rollback}</code>
            </div>
          )}
          {primaryStep.verify && (
            <div className="flex items-center gap-1">
              <span className="text-slate-500">Verify:</span>
              <code className="text-emerald-400/60 font-mono">{primaryStep.verify}</code>
            </div>
          )}
        </div>
      )}

      {steps.length > 1 && (
        <div className="mt-3 space-y-2">
          {steps.slice(1).map((step, i) => (
            <div key={i} className="text-xs text-slate-400">
              <p>{step.description}</p>
              {step.pre_check && (
                <div className="flex items-center gap-1 mt-1">
                  <code className="text-[10px] text-blue-400/70 font-mono">pre: {step.pre_check}</code>
                </div>
              )}
              {step.command && (
                <code className="text-[10px] text-wr-accent block mt-1 font-mono">$ {step.command}</code>
              )}
              {step.rollback && (
                <code className="text-[10px] text-red-400/50 block mt-0.5 font-mono">rollback: {step.rollback}</code>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default RemediationCard;
