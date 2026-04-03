import React, { useMemo } from 'react';
import ReactFlow, { Background, Controls } from 'reactflow';
import type { Node, Edge } from 'reactflow';
import 'reactflow/dist/style.css';
import type { ParsedWorkflow } from './workflowParser';

const NODE_W = 160;
const NODE_H = 48;

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
      const x = layer * (NODE_W + 60);
      const y = siblingIdx * (NODE_H + 20) - ((siblings.length - 1) * (NODE_H + 20)) / 2 + 200;

      return {
        id: step.id,
        position: { x, y },
        data: { label: step.id },
        style: {
          background: step.gate ? 'rgba(245,158,11,0.12)' : 'rgba(7,182,213,0.08)',
          border: `1px solid ${step.gate ? '#f59e0b' : '#07b6d5'}40`,
          borderRadius: 6,
          fontSize: 10,
          fontFamily: 'monospace',
          color: '#e8e0d4',
          width: NODE_W,
          padding: '6px 10px',
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
          style: { stroke: '#1e2a2e', strokeWidth: 1.5 },
        });
      });
    });

    return { nodes, edges };
  }, [workflow]);

  if (workflow.steps.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-xs font-mono" style={{ color: '#3d4a50', background: '#080f12' }}>
        No steps defined yet
      </div>
    );
  }

  return (
    <div style={{ width: '100%', height: '100%', background: '#080f12' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
      >
        <Background color="#1e2a2e" gap={20} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
};

export default WorkflowDagPreview;
