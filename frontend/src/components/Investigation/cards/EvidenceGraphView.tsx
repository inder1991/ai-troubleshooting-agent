import React, { useMemo } from 'react';
import ReactFlow, { Background, Controls, MiniMap } from 'reactflow';
import 'reactflow/dist/style.css';
import type { EvidenceGraphData } from '../../../types';

interface EvidenceGraphViewProps {
  graph: EvidenceGraphData;
  onNodeClick?: (nodeId: string) => void;
}

const NODE_COLORS: Record<string, string> = {
  error_event: '#ef4444',
  metric_anomaly: '#d4922e',
  k8s_event: '#f97316',
  trace_span: '#8b5cf6',
  code_change: '#10b981',
  code_location: '#3b82f6',
  config_change: '#eab308',
};

const EvidenceGraphView: React.FC<EvidenceGraphViewProps> = ({ graph, onNodeClick }) => {
  const { nodes, edges } = useMemo(() => {
    const rfNodes = graph.nodes.map((n, i) => ({
      id: n.id,
      position: { x: (i % 4) * 220, y: Math.floor(i / 4) * 120 },
      data: {
        label: `${n.node_type}\n${n.data?.service || n.data?.metric_name || n.id.slice(0, 8)}`,
      },
      style: {
        background: NODE_COLORS[n.node_type] || '#666',
        color: '#fff',
        border: graph.root_causes.some(r => r.node_id === n.id) ? '2px solid #fbbf24' : 'none',
        borderRadius: 8,
        padding: '8px 12px',
        fontSize: 11,
        fontWeight: 600,
      },
    }));
    const rfEdges = graph.edges.map((e, i) => ({
      id: `e-${i}`,
      source: e.source,
      target: e.target,
      label: e.edge_type,
      style: { stroke: `rgba(255,255,255,${e.confidence})` },
      labelStyle: { fill: '#8a7e6b', fontSize: 9 },
      animated: e.edge_type === 'causes',
    }));
    return { nodes: rfNodes, edges: rfEdges };
  }, [graph]);

  return (
    <div className="w-full h-[400px] bg-black/30 rounded-lg overflow-hidden">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodeClick={(_, node) => onNodeClick?.(node.id)}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#1a1a1a" />
        <Controls />
        <MiniMap style={{ background: '#0a0a0a' }} />
      </ReactFlow>
    </div>
  );
};

export default EvidenceGraphView;
