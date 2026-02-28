import React, { useState, useRef, useCallback } from 'react';
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

  if (steps.length === 0) return null;

  const primaryStep = steps[0];

  return (
    <div className="bg-[#152a2f] border border-[#1f3b42] rounded-lg p-4 shadow-lg">
      <h3 className="text-[10px] uppercase font-bold tracking-widest text-slate-500 mb-3">Proposed Remediation</h3>

      {primaryStep.command && (
        <div className="bg-black/40 rounded p-3 font-mono text-xs text-emerald-400 mb-3 border border-[#1f3b42]/30 flex items-center gap-2">
          <span className="text-slate-500">$</span>
          {primaryStep.command}
        </div>
      )}

      {blastRadius && (
        <div className="text-[10px] text-slate-500 mb-4 leading-relaxed">
          <span className="text-amber-500 font-bold">Risk Assessment:</span>{' '}
          {blastRadius.affected_pods} pods affected across {blastRadius.affected_namespaces} namespace(s) on {blastRadius.affected_nodes} node(s).
          {blastRadius.summary && <span className="text-white ml-1">{blastRadius.summary}</span>}
        </div>
      )}

      {primaryStep.command && (
        <button
          className="w-full bg-[#13b6ec]/10 border border-[#13b6ec] rounded h-12 flex items-center justify-between px-4 relative overflow-hidden cursor-pointer select-none transition-colors"
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
            holdingIndex === 0 ? 'text-white' : 'text-[#13b6ec]'
          }`}>
            Confirm {primaryStep.description || 'Action'}
          </span>
          <div className="relative w-8 h-8 z-10">
            <svg className="w-full h-full rotate-[-90deg]" viewBox="0 0 36 36">
              <path
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                fill="none"
                stroke={holdingIndex === 0 ? '#ffffff30' : '#13b6ec30'}
                strokeWidth="3"
              />
              <path
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                fill="none"
                stroke={holdingIndex === 0 ? '#fff' : '#13b6ec'}
                strokeWidth="3"
                strokeDasharray={`${(holdingIndex === 0 ? holdProgress : 0) * 100}, 100`}
                style={{ filter: 'drop-shadow(0 0 2px rgba(19,182,236,0.8))' }}
              />
            </svg>
            <div className={`absolute inset-0 flex items-center justify-center text-[8px] font-mono font-bold transition-colors ${
              holdingIndex === 0 ? 'text-white' : 'text-[#13b6ec]'
            }`}>
              HOLD
            </div>
          </div>
        </button>
      )}

      {steps.length > 1 && (
        <div className="mt-3 space-y-2">
          {steps.slice(1).map((step, i) => (
            <div key={i} className="text-xs text-slate-400">
              <p>{step.description}</p>
              {step.command && (
                <code className="text-[10px] text-[#13b6ec] block mt-1 font-mono">$ {step.command}</code>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default RemediationCard;
