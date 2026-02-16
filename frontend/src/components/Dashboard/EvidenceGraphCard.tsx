import React from 'react';
import type { EvidenceNodeData, CausalEdgeData } from '../../types';

interface EvidenceGraphCardProps {
  nodes: EvidenceNodeData[];
  edges: CausalEdgeData[];
  rootCauses: string[];
}

const nodeTypeColor: Record<string, string> = {
  cause: '#f97316',
  symptom: '#ef4444',
  contributing_factor: '#eab308',
  context: '#94a3b8',
};

const nodeTypeBg: Record<string, string> = {
  cause: 'bg-orange-500/10 border-orange-500/40',
  symptom: 'bg-red-500/10 border-red-500/40',
  contributing_factor: 'bg-yellow-500/10 border-yellow-500/40',
  context: 'bg-gray-500/10 border-gray-500/40',
};

const nodeTypeLabel: Record<string, string> = {
  cause: 'Root Cause',
  symptom: 'Symptom',
  contributing_factor: 'Contributing',
  context: 'Context',
};

const EvidenceGraphCard: React.FC<EvidenceGraphCardProps> = ({ nodes, edges, rootCauses }) => {
  if (nodes.length === 0) return null;

  const nodeMap = new Map(nodes.map((n) => [n.id, n]));

  // Build adjacency for layout: root causes -> intermediates -> leaf symptoms
  const roots = nodes.filter((n) => rootCauses.includes(n.id));
  const targetIds = new Set(edges.map((e) => e.target_id));
  const sourceIds = new Set(edges.map((e) => e.source_id));
  const leaves = nodes.filter((n) => !sourceIds.has(n.id) && targetIds.has(n.id));
  const intermediates = nodes.filter(
    (n) => !rootCauses.includes(n.id) && sourceIds.has(n.id) && targetIds.has(n.id)
  );
  // Isolated nodes (no edges)
  const connected = new Set([...rootCauses, ...leaves.map((l) => l.id), ...intermediates.map((m) => m.id)]);
  const isolated = nodes.filter((n) => !connected.has(n.id));

  const renderNode = (node: EvidenceNodeData) => {
    const color = nodeTypeColor[node.node_type] || '#94a3b8';
    const bgClass = nodeTypeBg[node.node_type] || 'bg-gray-500/10 border-gray-500/40';
    const label = nodeTypeLabel[node.node_type] || node.node_type;

    return (
      <div
        key={node.id}
        className={`border rounded-lg px-3 py-2 ${bgClass} min-w-[140px] max-w-[200px]`}
      >
        <div className="flex items-center gap-1.5 mb-1">
          <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
          <span className="text-[10px] font-medium uppercase tracking-wide" style={{ color }}>
            {label}
          </span>
        </div>
        <p className="text-xs text-gray-300 line-clamp-2">{node.claim}</p>
        <div className="mt-1 flex items-center justify-between">
          <span className="text-[10px] text-gray-500">{node.source_agent}</span>
          <span className="text-[10px] text-gray-500 font-mono">{Math.round(node.confidence * 100)}%</span>
        </div>
      </div>
    );
  };

  const renderEdgeLabel = (edge: CausalEdgeData) => {
    const sourceNode = nodeMap.get(edge.source_id);
    const targetNode = nodeMap.get(edge.target_id);
    if (!sourceNode || !targetNode) return null;

    return (
      <div key={`${edge.source_id}-${edge.target_id}`} className="flex items-center gap-1 text-[10px] text-gray-500">
        <span className="truncate max-w-[80px]">{sourceNode.claim.slice(0, 20)}</span>
        <span className="text-gray-600">--{edge.relationship}--&gt;</span>
        <span className="truncate max-w-[80px]">{targetNode.claim.slice(0, 20)}</span>
        <span className="text-gray-400 font-mono ml-1">{Math.round(edge.confidence * 100)}%</span>
      </div>
    );
  };

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
      <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-orange-500" />
        Evidence Graph
      </h3>

      {/* Causal chain visualization: roots -> intermediates -> leaves */}
      <div className="flex items-start gap-3 overflow-x-auto pb-2">
        {/* Root causes column */}
        {roots.length > 0 && (
          <div className="flex flex-col gap-2 flex-shrink-0">
            <div className="text-[10px] text-gray-500 uppercase tracking-wide text-center mb-1">Root Causes</div>
            {roots.map(renderNode)}
          </div>
        )}

        {/* Arrow */}
        {roots.length > 0 && (intermediates.length > 0 || leaves.length > 0) && (
          <div className="flex items-center self-center text-gray-600 flex-shrink-0 pt-4">
            <div className="w-8 h-px bg-gray-600" />
            <div className="text-xs">&#9654;</div>
          </div>
        )}

        {/* Intermediates column */}
        {intermediates.length > 0 && (
          <div className="flex flex-col gap-2 flex-shrink-0">
            <div className="text-[10px] text-gray-500 uppercase tracking-wide text-center mb-1">Contributing</div>
            {intermediates.map(renderNode)}
          </div>
        )}

        {/* Arrow */}
        {intermediates.length > 0 && leaves.length > 0 && (
          <div className="flex items-center self-center text-gray-600 flex-shrink-0 pt-4">
            <div className="w-8 h-px bg-gray-600" />
            <div className="text-xs">&#9654;</div>
          </div>
        )}

        {/* Leaves / symptoms column */}
        {leaves.length > 0 && (
          <div className="flex flex-col gap-2 flex-shrink-0">
            <div className="text-[10px] text-gray-500 uppercase tracking-wide text-center mb-1">Symptoms</div>
            {leaves.map(renderNode)}
          </div>
        )}

        {/* Isolated nodes */}
        {isolated.length > 0 && (
          <div className="flex flex-col gap-2 flex-shrink-0">
            <div className="text-[10px] text-gray-500 uppercase tracking-wide text-center mb-1">Evidence</div>
            {isolated.map(renderNode)}
          </div>
        )}
      </div>

      {/* Edge details */}
      {edges.length > 0 && (
        <div className="mt-3 border-t border-gray-700 pt-2 space-y-1">
          <div className="text-[10px] text-gray-500 uppercase tracking-wide mb-1">Causal Links</div>
          {edges.map(renderEdgeLabel)}
        </div>
      )}

      {/* Legend */}
      <div className="flex gap-4 mt-3 border-t border-gray-700 pt-2">
        {Object.entries(nodeTypeColor).map(([type, color]) => (
          <div key={type} className="flex items-center gap-1">
            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
            <span className="text-[10px] text-gray-500 capitalize">{type.replace('_', ' ')}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default EvidenceGraphCard;
