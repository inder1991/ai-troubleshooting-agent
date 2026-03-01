import React from 'react';
import type { CausalTree, TriageStatus } from '../../types';
import CausalTreeCard from './cards/CausalTreeCard';

interface CausalForestViewProps {
  forest: CausalTree[];
  sessionId: string;
  onTriageUpdate?: (treeId: string, status: TriageStatus) => void;
}

const CausalForestView: React.FC<CausalForestViewProps> = ({ forest, sessionId, onTriageUpdate }) => {
  if (!forest.length) return null;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 px-4">
        <span className="material-symbols-outlined text-[16px] text-cyan-500">account_tree</span>
        <span className="text-[10px] font-black text-slate-300 tracking-[0.1em] uppercase">Causal Forest</span>
        <span className="text-[9px] text-slate-500 font-mono">{forest.length} root cause{forest.length !== 1 ? 's' : ''}</span>
      </div>
      {forest.map(tree => (
        <CausalTreeCard key={tree.id} tree={tree} sessionId={sessionId} onTriageUpdate={onTriageUpdate} />
      ))}
    </div>
  );
};

export default CausalForestView;
