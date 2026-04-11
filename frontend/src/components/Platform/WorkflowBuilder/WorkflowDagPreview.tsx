import React, { useMemo } from 'react';
import ReactFlow, { Background, Controls, MarkerType } from 'reactflow';
import type { Node, Edge } from 'reactflow';
import 'reactflow/dist/style.css';
import type { ParsedWorkflow } from './workflowParser';

const NODE_W = 170;
const NODE_H = 56;

function nodeColor(gate?: string): { bg: string; border: string } {
  if (gate) return { bg: 'rgba(245,158,11,0.12)', border: '#f59e0b' };
  return { bg: 'rgba(7,182,213,0.08)', border: '#07b6d5' };
}

interface Props { workflow: ParsedWorkflow; }

const WorkflowDagPreview: React.FC<Props> = ({ workflow }) => {
  const { nodes, edges } = useMemo(() => {
    const steps = workflow.steps;
    if (steps.length === 0) return { nodes: [] as Node[], edges: [] as Edge[] };

    const depth: Record<string, number> = {};
    const getDepth = (id: string): number => {
      if (depth[id] !== undefined) return depth[id];
      const step = steps.find(s => s.id === id);
      if (!step || step.depends_on.length === 0) return (depth[id] = 0);
      return (depth[id] = Math.max(...step.depends_on.map(d => getDepth(d) + 1)));
    };
    steps.forEach(s => getDepth(s.id));

    const layers: Record<number, string[]> = {};
    steps.forEach(s => {
      const d = depth[s.id] || 0;
      layers[d] = layers[d] || [];
      layers[d].push(s.id);
    });

    const nodes: Node[] = steps.map(step => {
      const layer = depth[step.id] || 0;
      const siblings = layers[layer];
      const siblingIdx = siblings.indexOf(step.id);
      const x = layer * (NODE_W + 70);
      const y = siblingIdx * (NODE_H + 24) - ((siblings.length - 1) * (NODE_H + 24)) / 2 + 220;
      const { bg, border } = nodeColor(step.gate);
      const showAgent = step.agent && step.agent !== step.id;

      return {
        id: step.id,
        position: { x, y },
        data: {
          label: (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <div style={{ fontSize: 11, fontFamily: '"JetBrains Mono", monospace', color: '#e8e0d4', fontWeight: 500 }}>
                {step.id}
              </div>
              {showAgent && (
                <div style={{ fontSize: 9, fontFamily: 'Inter, sans-serif', color: '#64748b', letterSpacing: '0.02em' }}>
                  {step.agent}
                </div>
              )}
              {step.gate && (
                <div style={{ fontSize: 8, fontFamily: 'Inter, sans-serif', color: '#f59e0b', textTransform: 'uppercase', letterSpacing: '0.06em', marginTop: 2 }}>
                  ⏸ {step.gate.replace(/_/g, ' ')}
                </div>
              )}
            </div>
          ),
        },
        style: {
          background: bg,
          border: `1px solid ${border}40`,
          borderRadius: 6,
          width: NODE_W,
          padding: '8px 12px',
        },
      };
    });

    const edges: Edge[] = [];
    steps.forEach(step => {
      step.depends_on.forEach(dep => {
        edges.push({
          id: `${dep}-${step.id}`,
          source: dep,
          target: step.id,
          type: 'smoothstep',
          style: { stroke: '#07b6d540', strokeWidth: 1.5 },
          markerEnd: { type: MarkerType.ArrowClosed, color: '#07b6d540', width: 14, height: 14 },
        });
      });
    });

    return { nodes, edges };
  }, [workflow]);

  if (workflow.steps.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3" style={{ background: '#080f12' }}>
        <span className="material-symbols-outlined" style={{ fontSize: 32, color: '#1e2a2e' }}>account_tree</span>
        <div className="text-xs font-sans" style={{ color: '#3d4a50' }}>Define steps in the YAML editor</div>
      </div>
    );
  }

  return (
    <div style={{ width: '100%', height: '100%', background: '#080f12', position: 'relative' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
      >
        <Background color="#1e2a2e" gap={24} size={1} />
        <Controls showInteractive={false} style={{ background: '#0c1a1f', border: '1px solid #1e2a2e' }} />
      </ReactFlow>
      {/* Legend */}
      <div className="absolute bottom-3 right-3 flex items-center gap-3 px-3 py-1.5 rounded"
        style={{ background: '#0c1a1f', border: '1px solid #1e2a2e' }}>
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 rounded-sm" style={{ background: 'rgba(7,182,213,0.08)', border: '1px solid #07b6d540' }} />
          <span className="text-body-xs font-sans" style={{ color: '#3d4a50' }}>Step</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 rounded-sm" style={{ background: 'rgba(245,158,11,0.12)', border: '1px solid #f59e0b40' }} />
          <span className="text-body-xs font-sans" style={{ color: '#3d4a50' }}>Gate</span>
        </div>
      </div>
    </div>
  );
};

export default WorkflowDagPreview;
