import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import ReactFlow, {
  Background, Controls, MiniMap,
  useNodesState, useEdgesState,
  Node, Edge,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { useQuery } from '@tanstack/react-query';
import { fetchTopologyCurrent, fetchBatchDeviceHealth, fetchBlastRadius, fetchTopologyPath } from '../../../services/api';
import LiveDeviceNode from './LiveDeviceNode';
import TopologyLegend from './TopologyLegend';

const nodeTypes = { device: LiveDeviceNode };

const STATUS_COLORS: Record<string, string> = {
  healthy: '#22c55e', degraded: '#f59e0b', critical: '#ef4444',
  unreachable: '#ef4444', stale: '#94a3b8', unknown: '#94a3b8', initializing: '#e09f3e',
};

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

  // Task 6: Hover tooltip
  const [hoveredNode, setHoveredNode] = useState<{ id: string; x: number; y: number; data: any } | null>(null);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });

  // Task 7: Blast radius
  const [blastTargets, setBlastTargets] = useState<Set<string>>(new Set());

  // Task 8: Path trace
  const [pathMode, setPathMode] = useState(false);
  const [pathSource, setPathSource] = useState<string | null>(null);
  const [pathNodes, setPathNodes] = useState<Set<string>>(new Set());

  // Task 9: Context menu
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; nodeId: string; data: any } | null>(null);

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

  // Task 7: Pass blast targets to node data
  useEffect(() => {
    if (blastTargets.size === 0) return;
    setNodes(prev => prev.map(n => ({
      ...n,
      data: { ...n.data, isBlastTarget: blastTargets.has(n.id) },
    })));
  }, [blastTargets]);

  // Task 8: Pass path highlight to node data
  useEffect(() => {
    if (pathNodes.size === 0) return;
    setNodes(prev => prev.map(n => ({
      ...n,
      data: { ...n.data, isOnPath: pathNodes.has(n.id) },
    })));
  }, [pathNodes]);

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
    if (status === 'healthy') return '#22c55e';
    if (status === 'degraded') return '#f59e0b';
    if (status === 'critical') return '#ef4444';
    return '#94a3b8';
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
    <div
      style={{ width: '100%', height: '100%', position: 'relative' }}
      onMouseMove={(e) => setMousePos({ x: e.clientX, y: e.clientY })}
      onClick={() => setContextMenu(null)}
    >
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

        {/* Task 8: Trace Path button */}
        <button
          onClick={() => {
            if (pathMode) {
              setPathMode(false);
              setPathSource(null);
              setPathNodes(new Set());
            } else {
              setPathMode(true);
              setBlastTargets(new Set());
            }
          }}
          style={{
            background: pathMode ? 'rgba(224,159,62,0.2)' : '#1e1b15',
            border: `1px solid ${pathMode ? '#e09f3e' : '#3d3528'}`,
            borderRadius: 6,
            color: pathMode ? '#e09f3e' : '#8a7e6b',
            fontSize: 11, padding: '4px 10px', cursor: 'pointer',
            display: 'flex', alignItems: 'center', gap: 4,
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: 14 }}>route</span>
          {pathMode ? (pathSource ? 'Click destination...' : 'Click source...') : 'Trace Path'}
        </button>

        {/* Task 7: Blast radius badge */}
        {blastTargets.size > 0 && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6,
            background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.3)',
            borderRadius: 6, padding: '4px 10px', fontSize: 11, color: '#ef4444',
          }}>
            <span className="material-symbols-outlined" style={{ fontSize: 14 }}>crisis_alert</span>
            Blast Radius: {blastTargets.size} affected
            <button onClick={() => setBlastTargets(new Set())} style={{ color: '#ef4444', background: 'none', border: 'none', cursor: 'pointer', fontSize: 11 }}>&#x2715;</button>
          </div>
        )}

        {/* Task 8: Path info badge */}
        {pathNodes.size > 0 && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6,
            background: 'rgba(224,159,62,0.15)', border: '1px solid rgba(224,159,62,0.3)',
            borderRadius: 6, padding: '4px 10px', fontSize: 11, color: '#e09f3e',
          }}>
            <span className="material-symbols-outlined" style={{ fontSize: 14 }}>route</span>
            Path: {pathNodes.size} hops
            <button onClick={() => setPathNodes(new Set())} style={{ color: '#e09f3e', background: 'none', border: 'none', cursor: 'pointer', fontSize: 11 }}>&#x2715;</button>
          </div>
        )}

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
          setTimeout(() => instance.fitView({ padding: 0.15 }), 100);
          hasInitialFit.current = true;
        }}
        onNodeMouseEnter={(_, node) => {
          const health = healthData?.[node.id];
          setHoveredNode({
            id: node.id,
            x: node.position.x + 80,
            y: node.position.y - 20,
            data: { ...node.data, cpu: health?.cpu_pct, memory: health?.memory_pct },
          });
        }}
        onNodeMouseLeave={() => setHoveredNode(null)}
        onNodeClick={async (_, node) => {
          if (node.type === 'group') return;

          if (pathMode) {
            if (!pathSource) {
              setPathSource(node.id);
            } else {
              try {
                const srcIp = node.data?.ip || node.id;
                const dstIp = nodes.find(n => n.id === pathSource)?.data?.ip || pathSource;
                const result = await fetchTopologyPath(dstIp, srcIp);
                if (result.paths && result.paths.length > 0) {
                  setPathNodes(new Set(result.paths[0]));
                }
              } catch { /* ignore */ }
              setPathMode(false);
              setPathSource(null);
              setTimeout(() => setPathNodes(new Set()), 8000);
            }
            return;
          }

          try {
            const result = await fetchBlastRadius(node.id);
            const affectedIds = new Set(result.affected.map((a: any) => a.id));
            setBlastTargets(affectedIds);
            setTimeout(() => setBlastTargets(new Set()), 5000);
          } catch { /* ignore */ }
        }}
        onNodeContextMenu={(e, node) => {
          e.preventDefault();
          setContextMenu({
            x: e.clientX,
            y: e.clientY,
            nodeId: node.id,
            data: node.data,
          });
        }}
        minZoom={0.1}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
        style={{ background: '#201d17' }}
      >
        <Background color="#ffffff" gap={30} size={0.5} style={{ opacity: 0.04 }} />
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

      {/* Task 6: Hover tooltip */}
      {hoveredNode && (
        <div style={{
          position: 'fixed',
          left: mousePos.x + 16,
          top: mousePos.y - 10,
          zIndex: 50,
          background: '#1e1b15',
          border: '1px solid #3d3528',
          borderRadius: 8,
          padding: '8px 12px',
          minWidth: 180,
          pointerEvents: 'none',
          boxShadow: '0 4px 16px rgba(0,0,0,0.5)',
        }}>
          <div style={{ color: 'white', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>{hoveredNode.data.label}</div>
          <div style={{ color: '#8a7e6b', fontSize: 10, marginBottom: 6 }}>{hoveredNode.data.vendor}</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10 }}>
              <span style={{ color: '#64748b' }}>Status</span>
              <span style={{ color: STATUS_COLORS[hoveredNode.data.status] || '#64748b', fontWeight: 600 }}>{hoveredNode.data.status}</span>
            </div>
            {hoveredNode.data.cpu != null && (
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10 }}>
                <span style={{ color: '#64748b' }}>CPU</span>
                <span style={{ color: hoveredNode.data.cpu > 80 ? '#f59e0b' : '#22c55e', fontFamily: 'monospace' }}>{hoveredNode.data.cpu.toFixed(1)}%</span>
              </div>
            )}
            {hoveredNode.data.memory != null && (
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10 }}>
                <span style={{ color: '#64748b' }}>Memory</span>
                <span style={{ color: hoveredNode.data.memory > 85 ? '#f59e0b' : '#22c55e', fontFamily: 'monospace' }}>{hoveredNode.data.memory.toFixed(1)}%</span>
              </div>
            )}
            {hoveredNode.data.ip && (
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10 }}>
                <span style={{ color: '#64748b' }}>IP</span>
                <span style={{ color: '#94a3b8', fontFamily: 'monospace' }}>{hoveredNode.data.ip}</span>
              </div>
            )}
            {hoveredNode.data.haRole && (
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10 }}>
                <span style={{ color: '#64748b' }}>HA Role</span>
                <span style={{ color: hoveredNode.data.haRole === 'active' ? '#22c55e' : '#64748b' }}>{hoveredNode.data.haRole}</span>
              </div>
            )}
            {hoveredNode.data.interfaces?.length > 0 && (
              <div style={{ marginTop: 4, paddingTop: 4, borderTop: '1px solid #3d3528' }}>
                <div style={{ color: '#64748b', fontSize: 9, marginBottom: 2 }}>Interfaces: {hoveredNode.data.interfaces.length}</div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Task 9: Context menu */}
      {contextMenu && (
        <div
          style={{
            position: 'fixed',
            left: contextMenu.x,
            top: contextMenu.y,
            zIndex: 60,
            background: '#1e1b15',
            border: '1px solid #3d3528',
            borderRadius: 8,
            padding: 4,
            minWidth: 160,
            boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
          }}
          onClick={e => e.stopPropagation()}
        >
          <div style={{ padding: '6px 10px', color: 'white', fontSize: 11, fontWeight: 600, borderBottom: '1px solid #3d3528', marginBottom: 2 }}>
            {contextMenu.data?.label}
          </div>
          {[
            { icon: 'crisis_alert', label: 'Show Blast Radius', action: async () => {
              try {
                const result = await fetchBlastRadius(contextMenu.nodeId);
                setBlastTargets(new Set(result.affected.map((a: any) => a.id)));
                setTimeout(() => setBlastTargets(new Set()), 5000);
              } catch { /* ignore */ }
              setContextMenu(null);
            }},
            { icon: 'route', label: 'Trace Path From Here', action: () => { setPathMode(true); setPathSource(contextMenu.nodeId); setContextMenu(null); } },
            { icon: 'info', label: 'Show Details', action: () => { setContextMenu(null); } },
            { icon: 'terminal', label: 'Show Interfaces', action: () => { setContextMenu(null); } },
          ].map(item => (
            <button
              key={item.label}
              onClick={item.action}
              style={{
                width: '100%', textAlign: 'left',
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '6px 10px', fontSize: 11, color: '#8a7e6b',
                background: 'transparent', border: 'none', cursor: 'pointer',
                borderRadius: 4,
              }}
              onMouseEnter={e => { e.currentTarget.style.background = '#252118'; e.currentTarget.style.color = '#e09f3e'; }}
              onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = '#8a7e6b'; }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 14 }}>{item.icon}</span>
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

export default LiveTopologyView;
