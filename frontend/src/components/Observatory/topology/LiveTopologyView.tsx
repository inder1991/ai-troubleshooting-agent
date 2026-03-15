import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import ReactFlow, {
  Background, Controls, MiniMap,
  useNodesState, useEdgesState,
  Node, Edge,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { useQuery } from '@tanstack/react-query';
import { fetchTopologyCurrent, fetchBatchDeviceHealth } from '../../../services/api';
import LiveDeviceNode from './LiveDeviceNode';
import TopologyLegend from './TopologyLegend';

const nodeTypes = { device: LiveDeviceNode };

// Edge type filter defaults
const DEFAULT_FILTERS: Record<string, boolean> = {
  layer2_link: true,
  layer3_link: true,
  ha_peer: true,
  tunnel_link: true,
  routes_via: false,  // Off by default - too noisy
  attached_to: true,
  load_balances: true,
  mpls_path: true,
};

const FILTER_LABELS: Record<string, string> = {
  layer2_link: 'Physical',
  layer3_link: 'L3 Links',
  ha_peer: 'HA Pairs',
  tunnel_link: 'Tunnels',
  routes_via: 'Routes',
  attached_to: 'Attachments',
  load_balances: 'Load Balancers',
  mpls_path: 'MPLS',
};

const LiveTopologyView: React.FC = () => {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [lastVersion, setLastVersion] = useState('');
  const [edgeFilters, setEdgeFilters] = useState<Record<string, boolean>>(DEFAULT_FILTERS);
  const [groupFilter, setGroupFilter] = useState('all');
  const reactFlowInstance = useRef<any>(null);
  const hasInitialFit = useRef(false);

  // Fetch topology
  const { data: topoData, isLoading, error, refetch } = useQuery({
    queryKey: ['live-topology'],
    queryFn: fetchTopologyCurrent,
    refetchInterval: 60000,
    staleTime: 30000,
  });

  // Fetch health status more frequently
  const { data: healthData } = useQuery({
    queryKey: ['device-health-batch'],
    queryFn: fetchBatchDeviceHealth,
    refetchInterval: 30000,
  });

  // Apply topology data
  useEffect(() => {
    if (!topoData?.nodes) return;

    const version = topoData.topology_version || '';
    const isNewVersion = version !== lastVersion;

    // Load saved positions (prevents dagre yo-yo on re-render)
    let savedPositions: Record<string, { x: number; y: number }> = {};
    try {
      savedPositions = JSON.parse(localStorage.getItem('topo-positions') || '{}');
    } catch { /* ignore */ }

    // Apply nodes with saved positions or backend positions
    const newNodes: Node[] = topoData.nodes.map((n: any) => ({
      ...n,
      position: (!isNewVersion && savedPositions[n.id]) ? savedPositions[n.id] : (n.position || { x: 0, y: 0 }),
    }));

    // Apply edge filters
    const filteredEdges: Edge[] = (topoData.edges || []).filter((e: any) => {
      const edgeType = e.data?.edgeType || 'layer3_link';
      return edgeFilters[edgeType] !== false;
    });

    // Apply group filter
    const visibleNodes = groupFilter === 'all'
      ? newNodes
      : newNodes.filter((n: any) => n.data?.group === groupFilter || n.type === 'group');

    const visibleNodeIds = new Set(visibleNodes.map(n => n.id));
    const visibleEdges = filteredEdges.filter((e: Edge) =>
      visibleNodeIds.has(e.source) && visibleNodeIds.has(e.target)
    );

    setNodes(visibleNodes);
    setEdges(visibleEdges);

    if (isNewVersion) {
      setLastVersion(version);
    }
  }, [topoData, edgeFilters, groupFilter]);

  // Update node status from health data — only update changed nodes
  useEffect(() => {
    if (!healthData) return;
    setNodes(prev => prev.map(node => {
      const health = healthData[node.id];
      if (health && node.data && health.status !== node.data.status) {
        return { ...node, data: { ...node.data, status: health.status } };
      }
      return node; // Same reference — no re-render for this node
    }));
  }, [healthData]);

  // Save positions on node drag
  const onNodeDragStop = useCallback((_: any, node: Node) => {
    try {
      const saved = JSON.parse(localStorage.getItem('topo-positions') || '{}');
      saved[node.id] = node.position;
      localStorage.setItem('topo-positions', JSON.stringify(saved));
    } catch { /* ignore */ }
  }, []);

  const groups = useMemo(() => topoData?.groups || [], [topoData]);

  // Memoize MiniMap nodeColor
  const miniMapNodeColor = useCallback((node: any) => {
    const status = node.data?.status || 'unknown';
    if (status === 'healthy') return '#10b981';
    if (status === 'degraded') return '#f59e0b';
    if (status === 'critical') return '#ef4444';
    return '#64748b';
  }, []);

  if (isLoading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#64748b' }}>
        <span className="material-symbols-outlined animate-spin" style={{ fontSize: 20, marginRight: 8 }}>progress_activity</span>
        Loading topology...
      </div>
    );
  }

  if (error || !topoData) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#64748b', gap: 8 }}>
        <span className="material-symbols-outlined" style={{ fontSize: 32, color: '#ef4444' }}>error</span>
        <p style={{ fontSize: 13 }}>Failed to load topology</p>
        <button
          onClick={() => refetch()}
          style={{ background: '#1e1b15', border: '1px solid #3d3528', borderRadius: 6, color: '#8a7e6b', fontSize: 12, padding: '6px 16px', cursor: 'pointer', marginTop: 8 }}
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      {/* Toolbar */}
      <div style={{
        position: 'absolute', top: 12, left: 12, zIndex: 20,
        display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap',
      }}>
        {/* Group filter */}
        <select
          value={groupFilter}
          onChange={e => setGroupFilter(e.target.value)}
          style={{
            background: '#1e1b15', border: '1px solid #3d3528', borderRadius: 6,
            color: '#8a7e6b', fontSize: 10, padding: '4px 8px', outline: 'none',
          }}
        >
          <option value="all">All Groups</option>
          {groups.map((g: string) => (
            <option key={g} value={g}>{g.charAt(0).toUpperCase() + g.slice(1)}</option>
          ))}
        </select>

        {/* Edge type toggles */}
        <div style={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
          {Object.entries(edgeFilters).map(([type, enabled]) => (
            <button
              key={type}
              onClick={() => setEdgeFilters(prev => ({ ...prev, [type]: !prev[type] }))}
              style={{
                background: enabled ? 'rgba(224,159,62,0.15)' : 'transparent',
                border: `1px solid ${enabled ? 'rgba(224,159,62,0.3)' : '#3d3528'}`,
                color: enabled ? '#e09f3e' : '#64748b',
                borderRadius: 4, padding: '4px 10px', fontSize: 11, cursor: 'pointer',
                minHeight: 28,
              }}
            >
              {FILTER_LABELS[type] || type}
            </button>
          ))}
        </div>

        {/* Fit View button */}
        <button
          onClick={() => reactFlowInstance.current?.fitView({ padding: 0.15 })}
          style={{ background: '#1e1b15', border: '1px solid #3d3528', borderRadius: 6, color: '#8a7e6b', fontSize: 10, padding: '4px 8px', cursor: 'pointer' }}
          title="Fit view to canvas"
        >
          <span className="material-symbols-outlined" style={{ fontSize: 14 }}>fit_screen</span>
        </button>

        {/* Stats */}
        <span style={{ color: '#64748b', fontSize: 10, marginLeft: 8 }}>
          {topoData.device_count} devices | {topoData.edge_count} links
        </span>
      </div>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeDragStop={onNodeDragStop}
        nodeTypes={nodeTypes}
        onInit={(instance) => {
          reactFlowInstance.current = instance;
          // Fit view once on initial load, then never again
          setTimeout(() => instance.fitView({ padding: 0.15 }), 100);
          hasInitialFit.current = true;
        }}
        minZoom={0.1}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
        style={{ background: '#1a1814' }}
      >
        <Background color="#3d3528" gap={40} size={1} style={{ opacity: 0.15 }} />
        <Controls
          style={{ background: '#1e1b15', border: '1px solid #3d3528', borderRadius: 8 }}
          showInteractive={false}
        />
        <MiniMap
          nodeColor={miniMapNodeColor}
          style={{ background: '#1e1b15', border: '1px solid #3d3528', borderRadius: 8 }}
          maskColor="rgba(26, 24, 20, 0.8)"
        />
      </ReactFlow>

      <TopologyLegend />
    </div>
  );
};

export default LiveTopologyView;
