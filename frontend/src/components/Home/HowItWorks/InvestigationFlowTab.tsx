import React, { useState, useRef, useCallback } from 'react';
import { motion } from 'framer-motion';
import { flowNodeVariants } from './howItWorksAnimations';
import {
  flowNodes,
  phaseLabels,
  animationSequence,
} from './investigationFlowData';
import type { FlowNode } from './investigationFlowData';

type NodeStatus = 'hidden' | 'visible' | 'active' | 'done';

const InvestigationFlowTab: React.FC = () => {
  const [nodeStatuses, setNodeStatuses] = useState<Record<string, NodeStatus>>(
    {}
  );
  const [activePhaseIndex, setActivePhaseIndex] = useState(-1);
  const [progressPercent, setProgressPercent] = useState(0);
  const [isRunning, setIsRunning] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [showBracket, setShowBracket] = useState(false);
  const timeoutIds = useRef<number[]>([]);

  const resetAnimation = useCallback(() => {
    timeoutIds.current.forEach((tid) => window.clearTimeout(tid));
    timeoutIds.current = [];
    setNodeStatuses({});
    setActivePhaseIndex(-1);
    setProgressPercent(0);
    setIsRunning(false);
    setShowBracket(false);
  }, []);

  const startAnimation = useCallback(() => {
    resetAnimation();
    setIsRunning(true);

    let cumDelay = 0;
    animationSequence.forEach((step) => {
      cumDelay += step.delayMs / speed;
      const tid = window.setTimeout(() => {
        setNodeStatuses((prev) => ({ ...prev, [step.nodeId]: step.toStatus }));
        if (step.phaseIndex !== undefined) setActivePhaseIndex(step.phaseIndex);
        if (step.progress !== undefined) setProgressPercent(step.progress);
        if (step.showBracket === true) setShowBracket(true);
        if (step.showBracket === false) setShowBracket(false);
      }, cumDelay);
      timeoutIds.current.push(tid);
    });

    const finishTid = window.setTimeout(
      () => setIsRunning(false),
      cumDelay + 500
    );
    timeoutIds.current.push(finishTid);
  }, [speed, resetAnimation]);

  const getStatusClasses = (status: NodeStatus): string => {
    switch (status) {
      case 'active':
        return 'border-[#e09f3e] shadow-[0_0_30px_rgba(224,159,62,0.15)]';
      case 'done':
        return 'border-[#3d3528]/60 opacity-60';
      case 'visible':
      default:
        return 'border-[#3d3528]';
    }
  };

  const getStatusLabel = (
    status: NodeStatus
  ): { text: string; className: string } => {
    switch (status) {
      case 'active':
        return {
          text: 'processing...',
          className: 'text-[#e09f3e] animate-pulse',
        };
      case 'done':
        return { text: 'complete \u2713', className: 'text-emerald-500' };
      case 'visible':
      default:
        return { text: 'waiting', className: 'text-slate-500' };
    }
  };

  const speeds = [0.5, 1, 2, 4];

  return (
    <div>
      {/* 1. Header */}
      <div className="flex items-center justify-between">
        <span className="text-sm font-bold text-white">
          Live Investigation: Checkout Failure
        </span>
        <span className="bg-red-500/20 text-red-400 text-body-xs font-bold uppercase px-2 py-0.5 rounded">
          SEV-1
        </span>
      </div>

      {/* 2. Progress Bar */}
      <div className="h-1.5 bg-[#3d3528] rounded-full mt-3 mb-4 overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-700 ease-out bg-[#e09f3e]"
          style={{ width: `${progressPercent}%` }}
        />
      </div>

      {/* 3. Phase Labels */}
      <div className="flex justify-between mb-6 gap-1">
        {phaseLabels.map((label, index) => {
          let dotColor: string;
          let textColor: string;

          if (index < activePhaseIndex) {
            dotColor = 'bg-slate-400';
            textColor = 'text-slate-400';
          } else if (index === activePhaseIndex) {
            dotColor = 'bg-[#e09f3e]';
            textColor = 'text-[#e09f3e] font-bold';
          } else {
            dotColor = 'bg-slate-600';
            textColor = 'text-slate-600';
          }

          return (
            <div
              key={label}
              className={`flex items-center gap-1 text-body-xs font-mono uppercase tracking-wider ${textColor}`}
            >
              <span
                className={`inline-block w-1.5 h-1.5 rounded-full ${dotColor}`}
              />
              {label}
            </div>
          );
        })}
      </div>

      {/* 4. Node Canvas — horizontal scroll wrapper */}
      <div className="overflow-x-auto">
        <div
          className="relative"
          style={{ minWidth: 1240, minHeight: 520 }}
        >
          {/* Parallel bracket */}
          {showBracket && (
            <div
              className="absolute border-2 border-dashed rounded-2xl pointer-events-none transition-opacity duration-500"
              style={{
                left: 275,
                top: 90,
                width: 565,
                height: 210,
                borderColor: 'rgba(224,159,62,0.15)',
                zIndex: 0,
              }}
            >
              <div
                className="absolute -top-2.5 left-5 px-2 text-body-xs font-bold tracking-wider uppercase"
                style={{
                  backgroundColor: '#1a1814',
                  color: 'rgba(224,159,62,0.3)',
                }}
              >
                asyncio.gather — parallel
              </div>
            </div>
          )}

          {/* Flow nodes */}
          {flowNodes.map((node: FlowNode) => {
            const status = nodeStatuses[node.id];
            if (!status || status === 'hidden') return null;

            const statusClasses = getStatusClasses(status);
            const statusLabel = getStatusLabel(status);

            return (
              <motion.div
                key={node.id}
                className={`absolute rounded-xl border p-4 ${statusClasses}`}
                style={{
                  left: node.position.left,
                  top: node.position.top,
                  minWidth: node.minWidth || 150,
                  backgroundColor: 'rgba(15,32,35,0.8)',
                }}
                variants={flowNodeVariants}
                initial="hidden"
                animate={status}
              >
                {/* Icon circle */}
                <div
                  className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold text-[#1a1814] mb-2 relative"
                  style={{ backgroundColor: node.color }}
                >
                  {node.iconLabel}
                  {status === 'active' && (
                    <div
                      className="absolute inset-0 rounded-full border-2 animate-ping opacity-40"
                      style={{ borderColor: node.color }}
                    />
                  )}
                </div>

                {/* Name */}
                <div
                  className="text-xs font-bold tracking-wide mb-1"
                  style={{ color: node.color }}
                >
                  {node.name}
                </div>

                {/* Detail */}
                <div className="text-body-xs font-mono text-slate-400 whitespace-pre-line">
                  {node.detail}
                </div>

                {/* Status */}
                <div
                  className={`text-body-xs uppercase font-bold tracking-wider mt-2 ${statusLabel.className}`}
                >
                  {statusLabel.text}
                </div>

                {/* Output (shown when done) */}
                <div
                  className={`transition-all duration-400 ${
                    status === 'done'
                      ? 'max-h-48 opacity-100'
                      : 'max-h-0 opacity-0 overflow-hidden'
                  }`}
                >
                  <div className="text-body-xs font-mono text-slate-300 mt-2 pt-2 border-t border-[#3d3528]">
                    {node.outputText}
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>

      {/* 5. Controls Bar */}
      <div className="flex items-center justify-between mt-4 pt-4 border-t border-[#3d3528]">
        {/* Speed buttons */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500">Speed:</span>
          {speeds.map((s) => (
            <button
              key={s}
              onClick={() => setSpeed(s)}
              className={`px-2.5 py-1 rounded text-xs font-mono transition-colors ${
                speed === s
                  ? 'bg-[#e09f3e]/20 text-[#e09f3e] border border-[#e09f3e]/30'
                  : 'bg-slate-900/50 text-slate-500 border border-[#3d3528] hover:text-slate-300'
              }`}
            >
              {s}x
            </button>
          ))}
        </div>

        {/* Start / Reset */}
        <div className="flex items-center gap-2">
          {(isRunning || progressPercent > 0) && (
            <button
              onClick={resetAnimation}
              className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm font-bold transition-colors border border-[#3d3528]"
            >
              Reset
            </button>
          )}
          <button
            onClick={startAnimation}
            disabled={isRunning}
            className={`px-4 py-2 rounded-lg text-sm font-bold transition-colors ${
              isRunning
                ? 'bg-[#e09f3e]/40 text-white/50 cursor-not-allowed'
                : 'bg-[#e09f3e] hover:bg-[#e09f3e]/80 text-white'
            }`}
          >
            Start Investigation
          </button>
        </div>
      </div>
    </div>
  );
};

export default InvestigationFlowTab;
