import React, { useMemo } from 'react';
import type { FleetNode } from '../../types';

interface FleetHeatmapProps {
  nodes: FleetNode[];
  selectedNode?: string;
  onSelectNode?: (nodeName: string) => void;
}

const statusColor = (status: FleetNode['status']) => {
  switch (status) {
    case 'critical': return 'bg-red-500';
    case 'warning': return 'bg-amber-500';
    case 'healthy': return 'bg-[#1f3b42]';
    default: return 'bg-slate-700';
  }
};

const FleetHeatmap: React.FC<FleetHeatmapProps> = ({ nodes, selectedNode, onSelectNode }) => {
  const nodeCount = nodes.length || 0;

  const displayNodes = useMemo(() => {
    return nodes;
  }, [nodes]);

  return (
    <div className="bg-[#152a2f]/40 rounded border border-[#1f3b42] p-3">
      <h3 className="text-[10px] uppercase font-bold tracking-widest text-slate-500 mb-3 flex justify-between">
        Fleet Heatmap <span>{nodeCount} Nodes</span>
      </h3>
      {displayNodes.length === 0 && (
        <div className="text-[10px] text-slate-600 text-center py-4">Waiting for node data...</div>
      )}
      <div className="grid grid-cols-6 sm:grid-cols-8 md:grid-cols-12 gap-1 min-h-[80px]">
        {displayNodes.map((node, i) => {
          const isCritical = node.status === 'critical';
          const isSelected = node.name === selectedNode;
          return (
            <button
              key={node.name || i}
              type="button"
              className={`
                aspect-square rounded-[1px] transition-all duration-500 cursor-pointer
                ${statusColor(node.status)}
                ${isCritical ? 'animate-pulse opacity-100 z-10 shadow-[0_0_12px_#ef4444]' : 'opacity-20 hover:opacity-60'}
                ${isSelected ? 'ring-2 ring-[#e09f3e] ring-offset-1 ring-offset-[#1a1814] z-20' : ''}
                focus:outline-none focus:ring-1 focus:ring-[#e09f3e]
              `}
              onClick={() => onSelectNode?.(node.name)}
              aria-label={`Node ${node.name}: ${node.status}, CPU ${Math.round(node.cpu_pct)}%${node.disk_pressure ? ', disk pressure' : ''}`}
              title={`${node.name} | ${node.cpu_pct ?? '—'}% CPU${node.disk_pressure ? ' | DISK PRESSURE' : ''}`}
            />
          );
        })}
      </div>
    </div>
  );
};

export default FleetHeatmap;
