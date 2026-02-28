import React from 'react';
import type { ClusterDomainReport } from '../../types';

interface ExecutionDAGProps {
  domainReports: ClusterDomainReport[];
  phase: string;
}

interface DAGNode {
  label: string;
  status: 'pending' | 'running' | 'complete' | 'failed';
}

const nodeStyle = (status: DAGNode['status']) => {
  switch (status) {
    case 'running': return 'border-amber-500 text-amber-500 animate-pulse-amber shadow-[0_0_10px_rgba(245,158,11,0.2)]';
    case 'complete': return 'border-[#13b6ec] text-[#13b6ec]';
    case 'failed': return 'border-red-500 text-red-500';
    default: return 'border-[#1f3b42] text-slate-600 italic';
  }
};

const ExecutionDAG: React.FC<ExecutionDAGProps> = ({ domainReports, phase }) => {
  const agentsDone = domainReports.filter(r => r.status === 'SUCCESS' || r.status === 'PARTIAL' || r.status === 'FAILED').length;
  const anyRunning = domainReports.some(r => r.status === 'RUNNING');

  const dagNodes: DAGNode[] = [
    { label: 'InputParser', status: phase !== 'pre_flight' ? 'complete' : 'running' },
    {
      label: `Agents (${agentsDone}/4)`,
      status: agentsDone === 4 ? 'complete' : anyRunning ? 'running' : agentsDone > 0 ? 'running' : 'pending',
    },
    {
      label: 'Synthesizer',
      status: phase === 'complete' ? 'complete' : agentsDone === 4 ? 'running' : 'pending',
    },
  ];

  return (
    <div className="flex-1 min-h-[200px] bg-[#152a2f]/40 rounded border border-[#1f3b42] p-3 flex flex-col">
      <h3 className="text-[10px] uppercase font-bold tracking-widest text-slate-500 mb-4">Execution DAG</h3>
      <div className="relative flex flex-col items-center gap-6 h-full py-2">
        {dagNodes.map((node, i) => (
          <React.Fragment key={node.label}>
            {i > 0 && <div className="w-px h-6 bg-[#13b6ec]/30" />}
            <div className={`px-4 py-2 border rounded bg-[#0f2023] flex items-center justify-center text-[10px] font-mono ${nodeStyle(node.status)}`}>
              {node.label}
            </div>
          </React.Fragment>
        ))}
      </div>
    </div>
  );
};

export default ExecutionDAG;
