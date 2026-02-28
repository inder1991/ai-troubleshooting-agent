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
    if (nodes.length > 0) return nodes;
    return Array.from({ length: 60 }, (_, i) => ({
      name: `node-${i}`,
      status: 'unknown' as const,
    }));
  }, [nodes]);

  return (
    <div className="bg-[#152a2f]/40 rounded border border-[#1f3b42] p-3">
      <h3 className="text-[10px] uppercase font-bold tracking-widest text-slate-500 mb-3 flex justify-between">
        Fleet Heatmap <span>{nodeCount} Nodes</span>
      </h3>
      <div className="grid grid-cols-12 gap-1 min-h-[80px]">
        {displayNodes.map((node, i) => {
          const isCritical = node.status === 'critical';
          const isSelected = node.name === selectedNode;
          return (
            <div
              key={node.name || i}
              className={`
                aspect-square rounded-[1px] transition-all duration-500 cursor-pointer
                ${statusColor(node.status)}
                ${isCritical ? 'animate-pulse opacity-100 z-10 shadow-[0_0_12px_#ef4444]' : 'opacity-20 hover:opacity-60'}
                ${isSelected ? 'ring-2 ring-[#13b6ec] ring-offset-1 ring-offset-[#0f2023] z-20' : ''}
              `}
              onClick={() => onSelectNode?.(node.name)}
              title={`${node.name} | ${node.cpu_pct ?? '—'}% CPU${node.disk_pressure ? ' | DISK PRESSURE' : ''}`}
            />
          );
        })}
      </div>
    </div>
  );
};

export default FleetHeatmap;
