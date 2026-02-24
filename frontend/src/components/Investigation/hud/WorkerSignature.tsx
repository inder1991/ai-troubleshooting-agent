import React from 'react';
import { motion } from 'framer-motion';

type AgentCode = 'L' | 'M' | 'K' | 'D' | 'C';

const agentMap: Record<AgentCode, { name: string; color: string; bgColor: string }> = {
  L: { name: 'Log Analyzer', color: '#ef4444', bgColor: 'bg-red-500' },
  M: { name: 'Metrics Agent', color: '#06b6d4', bgColor: 'bg-cyan-500' },
  K: { name: 'K8s Inspector', color: '#f97316', bgColor: 'bg-orange-500' },
  D: { name: 'Code Navigator', color: '#3b82f6', bgColor: 'bg-blue-500' },
  C: { name: 'Change Agent', color: '#10b981', bgColor: 'bg-emerald-500' },
};

interface WorkerSignatureProps {
  confidence: number;
  agentCode: AgentCode;
}

const WorkerSignature: React.FC<WorkerSignatureProps> = ({ confidence, agentCode }) => {
  const agent = agentMap[agentCode] || agentMap.C;

  return (
    <div className="mt-4 pt-3 border-t border-slate-800/50">
      <div className="flex items-center justify-between">
        {/* Left: Agent dot + verified by */}
        <div className="flex items-center gap-2">
          <div
            className="w-1.5 h-1.5 rounded-full"
            style={{
              backgroundColor: agent.color,
              boxShadow: `0 0 6px ${agent.color}`,
            }}
          />
          <span className="text-[9px] text-slate-500">
            Verified by <span className="font-bold text-slate-400">{agent.name}</span>
          </span>
        </div>

        {/* Right: Confidence text */}
        <span className="text-[9px] font-mono text-slate-500">
          {confidence}% Confidence
        </span>
      </div>

      {/* Animated confidence bar */}
      <div className="mt-1.5 h-0.5 bg-slate-800/50 rounded-full overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${confidence}%` }}
          transition={{ duration: 1, ease: 'easeOut' }}
          className="h-full rounded-full"
          style={{ backgroundColor: agent.color }}
        />
      </div>
    </div>
  );
};

export default WorkerSignature;
