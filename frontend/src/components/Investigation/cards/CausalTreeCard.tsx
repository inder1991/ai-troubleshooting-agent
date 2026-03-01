import React, { useState, useCallback } from 'react';
import type { CausalTree, TriageStatus } from '../../../types';
import { updateTriageStatus } from '../../../services/api';
import { parseResourceEntities } from '../../../utils/parseResourceEntities';
import { useTelescopeContext } from '../../../contexts/TelescopeContext';
import CausalRoleBadge from './CausalRoleBadge';
import RecommendationCard from './RecommendationCard';
import NeuralChart from '../charts/NeuralChart';

interface CausalTreeCardProps {
  tree: CausalTree;
  sessionId: string;
  onTriageUpdate?: (treeId: string, status: TriageStatus) => void;
}

const SEVERITY_BORDER: Record<string, string> = {
  critical: 'border-l-red-500',
  warning: 'border-l-amber-500',
  info: 'border-l-slate-500',
};

const TRIAGE_SEQUENCE: TriageStatus[] = ['untriaged', 'acknowledged', 'mitigated', 'resolved'];
const TRIAGE_COLORS: Record<TriageStatus, string> = {
  untriaged: 'text-red-400 bg-red-950/30',
  acknowledged: 'text-amber-400 bg-amber-950/30',
  mitigated: 'text-cyan-400 bg-cyan-950/30',
  resolved: 'text-emerald-400 bg-emerald-950/30',
};

const CausalTreeCard: React.FC<CausalTreeCardProps> = ({ tree, sessionId, onTriageUpdate }) => {
  const [expanded, setExpanded] = useState(true);
  const [triage, setTriage] = useState<TriageStatus>(tree.triage_status);
  const { openTelescope } = useTelescopeContext();

  const handleEntityClick = useCallback((kind: string, name: string, namespace: string | null) => {
    openTelescope({ kind, name, namespace: namespace || 'default' });
  }, [openTelescope]);

  const cycleTriage = useCallback(async () => {
    const currentIdx = TRIAGE_SEQUENCE.indexOf(triage);
    const nextStatus = TRIAGE_SEQUENCE[(currentIdx + 1) % TRIAGE_SEQUENCE.length];
    setTriage(nextStatus);
    onTriageUpdate?.(tree.id, nextStatus);
    try {
      await updateTriageStatus(sessionId, tree.id, nextStatus);
    } catch {
      /* optimistic update */
    }
  }, [triage, tree.id, sessionId, onTriageUpdate]);

  const blastCount = tree.blast_radius
    ? (tree.blast_radius.upstream_affected?.length || 0) + (tree.blast_radius.downstream_affected?.length || 0)
    : 0;

  return (
    <div className={`rounded-lg border border-slate-800/50 border-l-[3px] ${SEVERITY_BORDER[tree.severity]} bg-slate-900/30`}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 cursor-pointer" onClick={() => setExpanded(!expanded)}>
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <span className="material-symbols-outlined text-[16px] text-slate-500">{expanded ? 'expand_more' : 'chevron_right'}</span>
          <div className="flex-1 min-w-0">
            <div className="text-[11px] font-medium text-slate-200 truncate">
              {parseResourceEntities(tree.root_cause.summary, handleEntityClick)}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {blastCount > 0 && (
            <span className="text-[9px] text-amber-400 bg-amber-950/30 px-1.5 py-0.5 rounded font-mono">
              {blastCount} affected
            </span>
          )}
          <button onClick={(e) => { e.stopPropagation(); cycleTriage(); }} className={`text-[9px] font-bold px-2 py-0.5 rounded uppercase tracking-wider ${TRIAGE_COLORS[triage]}`}>
            {triage}
          </button>
        </div>
      </div>

      {/* Expandable body */}
      {expanded && (
        <div className="px-4 pb-4 space-y-3">
          {/* Root cause details */}
          <div className="text-[10px] text-slate-400">
            {parseResourceEntities(tree.root_cause.description || tree.root_cause.summary, handleEntityClick)}
          </div>

          {/* Cascading symptoms */}
          {tree.cascading_symptoms.length > 0 && (
            <div className="space-y-1">
              <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">Cascading Symptoms</span>
              {tree.cascading_symptoms.map((s, i) => (
                <div key={i} className="flex items-start gap-2 pl-3 border-l border-slate-700/40">
                  <CausalRoleBadge role="cascading_failure" />
                  <span className="text-[10px] text-slate-400">
                    {parseResourceEntities(s.summary, handleEntityClick)}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Correlated signals */}
          {tree.correlated_signals.length > 0 && (
            <div className="space-y-1">
              <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">Correlated Signals</span>
              {tree.correlated_signals.map((sig, i) => (
                <div key={i} className="text-[10px] text-slate-400">
                  <span className="text-cyan-400">{sig.group_name}</span>: {sig.narrative}
                </div>
              ))}
            </div>
          )}

          {/* Operational recommendations */}
          {tree.operational_recommendations.length > 0 && (
            <div className="space-y-2">
              <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">Recommendations</span>
              {tree.operational_recommendations.map(rec => (
                <RecommendationCard key={rec.id} recommendation={rec} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default CausalTreeCard;
