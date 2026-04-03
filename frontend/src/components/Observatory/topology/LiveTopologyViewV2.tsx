import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import ReactFlow, {
  Background, Controls, MiniMap,
  useNodesState, useEdgesState,
  Node, Edge,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { useQuery } from '@tanstack/react-query';
import { fetchBatchDeviceHealth, fetchBlastRadius, fetchTopologyPath } from '../../../services/api';
import LiveDeviceNode from './LiveDeviceNode';
import EnvironmentLabel from './EnvironmentLabel';
import TopologyLegend from './TopologyLegend';
import { TopologyStreamManager, TopologyDelta } from './realtime/TopologyStreamManager';

/* ── Constants ─────────────────────────────────────────────────────── */

const ClusterNode: React.FC<{ data: any }> = ({ data }) => (
  <div
    onClick={data.onExpand}
    style={{
      background: '#0f2023', border: `1px solid ${data.accent || '#07b6d5'}40`,
      borderRadius: 8, padding: '10px 16px', cursor: 'pointer', minWidth: 140,
      display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4,
    }}
    title="Click to expand"
  >
    <span className="material-symbols-outlined" style={{ fontSize: 20, color: data.accent || '#07b6d5' }}>
      device_hub
    </span>
    <div style={{ fontSize: 11, fontFamily: 'monospace', color: '#e8e0d4', fontWeight: 600 }}>
      {data.label}
    </div>
    <div style={{ fontSize: 10, fontFamily: 'monospace', color: '#64748b' }}>
      {data.deviceCount} devices · click to expand
    </div>
  </div>
);

const nodeTypes = { device: LiveDeviceNode, envLabel: EnvironmentLabel, cluster: ClusterNode };

const STATUS_COLORS: Record<string, string> = {
  healthy: '#22c55e', degraded: '#f59e0b', critical: '#ef4444',
  unreachable: '#ef4444', stale: '#6b7280', unknown: '#6b7280', initializing: '#e09f3e',
};

const DEFAULT_FILTERS: Record<string, boolean> = {
  physical: true,
  ha_peer: true,
  tunnel: true,
  route: false,
  cloud_attach: true,
  load_balancer: true,
  mpls: true,
};

const FILTER_LABELS: Record<string, string> = {
  physical: 'Physical',
  ha_peer: 'HA Pairs',
  tunnel: 'Tunnels',
  route: 'Routes',
  cloud_attach: 'Cloud',
  load_balancer: 'LB',
  mpls: 'MPLS',
};

const POSITIONS_KEY = 'topo-positions-v6'; // v6 = two-phase layout (group force + tier grid)

/* ── API ───────────────────────────────────────────────────────────── */

async function fetchTopologyV5(): Promise<any> {
  const resp = await fetch('/api/v5/topology');
  if (!resp.ok) throw new Error(`Topology fetch failed (HTTP ${resp.status})`);
  return resp.json();
}

/* ── Component ─────────────────────────────────────────────────────── */

const LiveTopologyViewV2: React.FC = () => {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [edgeFilters, setEdgeFilters] = useState<Record<string, boolean>>(DEFAULT_FILTERS);
  const [groupFilter, setGroupFilter] = useState('all');
  const reactFlowInstance = useRef<any>(null);
  const streamRef = useRef<TopologyStreamManager | null>(null);

  // Hover — only track position when a node is hovered (perf fix)
  const [hoveredNode, setHoveredNode] = useState<{ id: string; data: any } | null>(null);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
  const hoveredRef = useRef(false);

  // Blast radius
  const [blastTargets, setBlastTargets] = useState<Set<string>>(new Set());

  // Path trace
  const [pathMode, setPathMode] = useState(false);
  const [pathSource, setPathSource] = useState<string | null>(null);
  const [pathNodes, setPathNodes] = useState<Set<string>>(new Set());

  // Context menu
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; nodeId: string; data: any } | null>(null);

  // Filters popover
  const [showFilters, setShowFilters] = useState(false);

  // Topology change detection
  const [lastTopoVersion, setLastTopoVersion] = useState<string>('');
  const [topoChangeToast, setTopoChangeToast] = useState<string | null>(null);

  // Group clustering
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());

  const toggleGroup = useCallback((groupId: string) => {
    setCollapsedGroups(prev => {
      const next = new Set(prev);
      if (next.has(groupId)) next.delete(groupId); else next.add(groupId);
      return next;
    });
  }, []);

  /* ── Data fetching ─────────────────────────────────────────────── */

  const { data: topoData, isLoading, error, refetch } = useQuery({
    queryKey: ['topology-v5'],
    queryFn: fetchTopologyV5,
    refetchInterval: 60000,
    staleTime: 30000,
  });

  const { data: healthData } = useQuery({
    queryKey: ['device-health-batch'],
    queryFn: fetchBatchDeviceHealth,
    refetchInterval: 30000,
  });

  /* ── Apply topology data ───────────────────────────────────────── */

  useEffect(() => {
    if (!topoData?.nodes) return;

    const newNodes: Node[] = topoData.nodes.map((n: any) => ({
      ...n,
      position: n.position || { x: 0, y: 0 },
    }));

    // Restore drag-saved positions
    let savedPositions: Record<string, { x: number; y: number }> = {};
    try {
      savedPositions = JSON.parse(localStorage.getItem(POSITIONS_KEY) || '{}');
    } catch { /* noop */ }

    const positioned = newNodes.map(n => {
      if (savedPositions[n.id] && n.type !== 'group' && n.type !== 'envLabel') {
        return { ...n, position: savedPositions[n.id] };
      }
      return n;
    });

    // Edge filters
    const filteredEdges = (topoData.edges || []).filter((e: any) => {
      const edgeType = e.data?.edgeType || 'physical';
      return edgeFilters[edgeType] !== false;
    });

    // Group filter — use group ID, not label
    const visibleNodes = groupFilter === 'all'
      ? positioned
      : positioned.filter((n: Node) => {
          if (n.type === 'group') return n.id === `group-${groupFilter}`;
          if (n.type === 'envLabel') return n.id === `env-label-${groupFilter}`;
          return n.data?.group === groupFilter;
        });

    const visibleNodeIds = new Set(visibleNodes.map(n => n.id));
    const visibleEdges = filteredEdges.filter((e: any) =>
      visibleNodeIds.has(e.source) && visibleNodeIds.has(e.target)
    );

    // Apply group collapsing
    const GROUP_ACCENTS: Record<string, string> = {
      onprem: '#22c55e', aws: '#f59e0b', azure: '#3b82f6',
      oci: '#ef4444', gcp: '#a855f7', branch: '#06b6d4',
    };

    let finalNodes = visibleNodes;
    let finalEdges = visibleEdges;

    if (collapsedGroups.size > 0) {
      const collapsedNodeIds = new Set<string>();
      const clusterNodes: Node[] = [];

      for (const groupId of collapsedGroups) {
        const groupDevices = visibleNodes.filter(
          n => n.type === 'device' && n.data?.group === groupId
        );
        if (groupDevices.length === 0) continue;

        groupDevices.forEach(n => collapsedNodeIds.add(n.id));

        // Find center position of collapsed group
        const avgX = groupDevices.reduce((s, n) => s + n.position.x, 0) / groupDevices.length;
        const avgY = groupDevices.reduce((s, n) => s + n.position.y, 0) / groupDevices.length;

        clusterNodes.push({
          id: `cluster-${groupId}`,
          type: 'cluster',
          position: { x: avgX, y: avgY },
          data: {
            label: groupId.toUpperCase(),
            deviceCount: groupDevices.length,
            accent: GROUP_ACCENTS[groupId] || '#07b6d5',
            onExpand: () => toggleGroup(groupId),
          },
        });
      }

      // Remove collapsed device nodes + their group/envLabel nodes
      finalNodes = visibleNodes.filter(n => {
        if (collapsedNodeIds.has(n.id)) return false;
        if (n.type === 'group' && collapsedGroups.has(n.id.replace('group-', ''))) return false;
        if (n.type === 'envLabel' && collapsedGroups.has(n.id.replace('env-label-', ''))) return false;
        return true;
      });
      finalNodes = [...finalNodes, ...clusterNodes];

      // Remap edges: if source/target is collapsed, point to cluster node
      const seenEdges = new Set<string>();
      finalEdges = visibleEdges
        .filter(e => !(collapsedNodeIds.has(e.source) && collapsedNodeIds.has(e.target)))
        .map(e => {
          const src = collapsedNodeIds.has(e.source)
            ? `cluster-${visibleNodes.find(n => n.id === e.source)?.data?.group || ''}`
            : e.source;
          const tgt = collapsedNodeIds.has(e.target)
            ? `cluster-${visibleNodes.find(n => n.id === e.target)?.data?.group || ''}`
            : e.target;
          return { ...e, id: `${src}-${tgt}`, source: src, target: tgt };
        })
        .filter(e => {
          const key = `${e.source}||${e.target}`;
          if (seenEdges.has(key)) return false;
          seenEdges.add(key);
          return true;
        });
    }

    setNodes(finalNodes);
    setEdges(finalEdges);
  }, [topoData, edgeFilters, groupFilter, collapsedGroups]);

  /* ── Topology change detection ────────────────────────────────── */

  useEffect(() => {
    const version = topoData?.topology_version;
    if (!version) return;
    if (!lastTopoVersion) {
      setLastTopoVersion(version);
      return;
    }
    if (version !== lastTopoVersion) {
      setLastTopoVersion(version);
      setTopoChangeToast('Topology updated — new devices or links detected');
      setTimeout(() => setTopoChangeToast(null), 4000);
    }
  }, [topoData?.topology_version]);

  /* ── WebSocket ─────────────────────────────────────────────────── */

  useEffect(() => {
    const wsUrl = `ws://${window.location.host}/api/v5/topology/stream`;
    const stream = new TopologyStreamManager((delta: TopologyDelta) => {
      if (delta.entity_type === 'node') {
        if (delta.event_type === 'node_added') { refetch(); }
        else if (delta.event_type === 'node_removed') {
          setNodes(prev => prev.filter(n => n.id !== delta.entity_id));
        } else {
          setNodes(prev => prev.map(n =>
            n.id === delta.entity_id ? { ...n, data: { ...n.data, ...delta.data } } : n
          ));
        }
      }
      if (delta.entity_type === 'edge') {
        if (delta.event_type === 'edge_removed') {
          setEdges(prev => prev.filter(e => e.id !== delta.entity_id));
        } else {
          setEdges(prev => prev.map(e =>
            e.id === delta.entity_id ? { ...e, data: { ...e.data, ...delta.data } } : e
          ));
        }
      }
    });
    stream.connect(wsUrl);
    streamRef.current = stream;
    return () => { stream.disconnect(); streamRef.current = null; };
  }, [refetch]);

  /* ── Health updates ────────────────────────────────────────────── */

  useEffect(() => {
    if (!healthData) return;
    setNodes(prev => prev.map(node => {
      const health = healthData[node.id];
      if (health && node.data && health.status !== node.data.status) {
        return { ...node, data: { ...node.data, status: health.status } };
      }
      return node;
    }));
  }, [healthData]);

  /* ── Highlight effects ─────────────────────────────────────────── */

  useEffect(() => {
    if (blastTargets.size === 0) return;
    setNodes(prev => prev.map(n => ({
      ...n, data: { ...n.data, isBlastTarget: blastTargets.has(n.id) },
    })));
  }, [blastTargets]);

  useEffect(() => {
    if (pathNodes.size === 0) return;
    setNodes(prev => prev.map(n => ({
      ...n, data: { ...n.data, isOnPath: pathNodes.has(n.id) },
    })));
  }, [pathNodes]);

  /* ── Drag persistence ──────────────────────────────────────────── */

  const onNodeDragStop = useCallback((_: any, node: Node) => {
    try {
      const saved = JSON.parse(localStorage.getItem(POSITIONS_KEY) || '{}');
      saved[node.id] = node.position;
      localStorage.setItem(POSITIONS_KEY, JSON.stringify(saved));
    } catch { /* noop */ }
  }, []);

  /* ── Keyboard shortcuts ────────────────────────────────────────── */

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return;
      if (e.key === 'p' || e.key === 'P') {
        setPathMode(prev => !prev);
        if (pathMode) { setPathSource(null); setPathNodes(new Set()); }
      }
      if (e.key === 'f' || e.key === 'F') {
        reactFlowInstance.current?.fitView({ padding: 0.12 });
      }
      if (e.key === 'Escape') {
        setPathMode(false); setPathSource(null); setPathNodes(new Set());
        setBlastTargets(new Set()); setContextMenu(null); setShowFilters(false);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [pathMode]);

  /* ── Derived data ──────────────────────────────────────────────── */

  const groups = useMemo(() => {
    if (!topoData?.groups) return [];
    return topoData.groups.map((g: any) => ({ id: g.id, label: g.label || g.id }));
  }, [topoData]);

  const miniMapNodeColor = useCallback((node: any) => {
    const s = node.data?.status || 'unknown';
    return STATUS_COLORS[s] || '#6b7280';
  }, []);

  /* ── Mouse tracking (only when hovering a node) ────────────────── */

  const onMouseMoveThrottled = useCallback((e: React.MouseEvent) => {
    if (hoveredRef.current) {
      setMousePos({ x: e.clientX, y: e.clientY });
    }
  }, []);

  /* ── Loading / Error states ────────────────────────────────────── */

  if (isLoading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#7a7060' }}>
        <span className="material-symbols-outlined animate-spin" style={{ fontSize: 18, marginRight: 8 }}>progress_activity</span>
        Loading topology...
      </div>
    );
  }

  if (error || !topoData) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#7a7060', gap: 8 }}>
        <span className="material-symbols-outlined" style={{ fontSize: 28, color: '#ef4444' }}>warning</span>
        <p style={{ fontSize: 13 }}>Failed to load topology</p>
        <p style={{ fontSize: 11, color: '#5a5348' }}>{error instanceof Error ? error.message : 'Network error'}</p>
        <button
          onClick={() => refetch()}
          style={{
            background: 'transparent', border: '1px solid #3d3528', borderRadius: 4,
            color: '#7a7060', fontSize: 11, padding: '5px 14px', cursor: 'pointer', marginTop: 4,
          }}
        >
          Retry
        </button>
      </div>
    );
  }

  /* ── Render ────────────────────────────────────────────────────── */

  return (
    <div
      style={{ width: '100%', height: '100%', position: 'relative' }}
      onMouseMove={onMouseMoveThrottled}
      onClick={() => { setContextMenu(null); setShowFilters(false); }}
    >
      {/* ── Topology change toast ───────────────────────────────── */}
      {topoChangeToast && (
        <div style={{
          position: 'absolute', top: 50, left: '50%', transform: 'translateX(-50%)',
          zIndex: 50, background: '#0f2023', border: '1px solid #07b6d5',
          borderRadius: 6, padding: '6px 14px',
          fontSize: 11, fontFamily: 'monospace', color: '#07b6d5',
          display: 'flex', alignItems: 'center', gap: 6,
          boxShadow: '0 2px 16px rgba(7,182,213,0.15)',
        }}>
          <span className="material-symbols-outlined" style={{ fontSize: 14 }}>refresh</span>
          {topoChangeToast}
        </div>
      )}

      {/* ── Toolbar ──────────────────────────────────────────────── */}
      <div style={{
        position: 'absolute', top: 10, left: 10, zIndex: 20,
        display: 'flex', gap: 5, alignItems: 'center',
        background: 'rgba(18,16,12,0.85)', backdropFilter: 'blur(8px)',
        borderRadius: 6, padding: '4px 8px',
        border: '1px solid #2a2520',
      }}>
        {/* Group filter */}
        <select
          value={groupFilter}
          onChange={e => setGroupFilter(e.target.value)}
          style={{
            background: 'transparent', border: '1px solid #2a2520', borderRadius: 4,
            color: '#9a9080', fontSize: 10, padding: '3px 6px', outline: 'none', minHeight: 26,
          }}
        >
          <option value="all">All Environments</option>
          {groups.map((g: { id: string; label: string }) => (
            <option key={g.id} value={g.id}>{g.label}</option>
          ))}
        </select>

        {/* Group collapse toggles */}
        {groups.length > 0 && groupFilter === 'all' && (groups as { id: string; label: string }[]).map((g) => (
          <button
            key={g.id}
            onClick={() => toggleGroup(g.id)}
            style={{
              fontSize: 9, padding: '2px 6px', borderRadius: 3, cursor: 'pointer',
              background: collapsedGroups.has(g.id) ? 'rgba(7,182,213,0.15)' : 'transparent',
              border: `1px solid ${collapsedGroups.has(g.id) ? '#07b6d5' : '#2a2520'}`,
              color: collapsedGroups.has(g.id) ? '#07b6d5' : '#7a7060',
              fontFamily: 'monospace', minHeight: 26,
            }}
          >
            {collapsedGroups.has(g.id) ? '▶' : '▼'} {g.label}
          </button>
        ))}

        {/* Edge filters */}
        <div style={{ position: 'relative' }}>
          <button
            onClick={(e) => { e.stopPropagation(); setShowFilters(!showFilters); }}
            style={{
              background: showFilters ? 'rgba(224,159,62,0.1)' : 'transparent',
              border: `1px solid ${showFilters ? '#e09f3e40' : '#2a2520'}`,
              borderRadius: 4, color: showFilters ? '#e09f3e' : '#7a7060',
              fontSize: 10, padding: '3px 8px', cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: 3, minHeight: 26,
            }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 13 }}>tune</span>
            Edges
          </button>
          {showFilters && (
            <div
              style={{
                position: 'absolute', top: 30, left: 0, zIndex: 30,
                background: '#15130f', border: '1px solid #2a2520', borderRadius: 6,
                padding: 6, minWidth: 140, boxShadow: '0 4px 16px rgba(0,0,0,0.6)',
              }}
              onClick={e => e.stopPropagation()}
            >
              {Object.entries(edgeFilters).map(([type, enabled]) => (
                <label
                  key={type}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 6,
                    padding: '3px 5px', fontSize: 10, color: enabled ? '#c0b090' : '#5a5348',
                    cursor: 'pointer', borderRadius: 3,
                  }}
                >
                  <input
                    type="checkbox"
                    checked={enabled}
                    onChange={() => setEdgeFilters(prev => ({ ...prev, [type]: !prev[type] }))}
                    style={{ accentColor: '#e09f3e', width: 12, height: 12 }}
                  />
                  {FILTER_LABELS[type] || type}
                </label>
              ))}
            </div>
          )}
        </div>

        <button
          onClick={() => reactFlowInstance.current?.fitView({ padding: 0.12 })}
          style={{ background: 'transparent', border: '1px solid #2a2520', borderRadius: 4, color: '#7a7060', padding: '3px 6px', cursor: 'pointer', minHeight: 26 }}
          title="Fit view (F)"
        >
          <span className="material-symbols-outlined" style={{ fontSize: 13 }}>fit_screen</span>
        </button>

        <button
          onClick={() => {
            if (pathMode) { setPathMode(false); setPathSource(null); setPathNodes(new Set()); }
            else { setPathMode(true); setBlastTargets(new Set()); }
          }}
          style={{
            background: pathMode ? 'rgba(224,159,62,0.12)' : 'transparent',
            border: `1px solid ${pathMode ? '#e09f3e40' : '#2a2520'}`,
            borderRadius: 4, color: pathMode ? '#e09f3e' : '#7a7060',
            fontSize: 10, padding: '3px 8px', cursor: 'pointer',
            display: 'flex', alignItems: 'center', gap: 3, minHeight: 26,
          }}
          title="Trace path (P)"
        >
          <span className="material-symbols-outlined" style={{ fontSize: 13 }}>route</span>
          {pathMode ? (pathSource ? 'Click dest' : 'Click src') : 'Path'}
        </button>

        <span style={{ color: '#5a5348', fontSize: 10, marginLeft: 2 }}>
          {topoData.device_count} devices · {topoData.edge_count} links
        </span>
      </div>

      {/* ── Status badges ────────────────────────────────────────── */}
      {(blastTargets.size > 0 || pathNodes.size > 0) && (
        <div style={{ position: 'absolute', top: 44, left: 10, zIndex: 20, display: 'flex', gap: 5 }}>
          {blastTargets.size > 0 && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 5,
              background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)',
              borderRadius: 4, padding: '3px 8px', fontSize: 10, color: '#ef4444',
            }}>
              <span className="material-symbols-outlined" style={{ fontSize: 13 }}>crisis_alert</span>
              {blastTargets.size} affected
              <button
                onClick={() => setBlastTargets(new Set())}
                style={{ color: '#ef4444', background: 'none', border: 'none', cursor: 'pointer', fontSize: 12, padding: 0 }}
              >
                x
              </button>
            </div>
          )}
          {pathNodes.size > 0 && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 5,
              background: 'rgba(224,159,62,0.1)', border: '1px solid rgba(224,159,62,0.2)',
              borderRadius: 4, padding: '3px 8px', fontSize: 10, color: '#e09f3e',
            }}>
              <span className="material-symbols-outlined" style={{ fontSize: 13 }}>route</span>
              {pathNodes.size} hops
              <button
                onClick={() => setPathNodes(new Set())}
                style={{ color: '#e09f3e', background: 'none', border: 'none', cursor: 'pointer', fontSize: 12, padding: 0 }}
              >
                x
              </button>
            </div>
          )}
        </div>
      )}

      {/* ── ReactFlow Canvas ─────────────────────────────────────── */}
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeDragStop={onNodeDragStop}
        nodeTypes={nodeTypes}
        onInit={(instance) => {
          reactFlowInstance.current = instance;
          setTimeout(() => instance.fitView({ padding: 0.12 }), 100);
        }}
        onNodeMouseEnter={(_, node) => {
          hoveredRef.current = true;
          const health = healthData?.[node.id];
          setHoveredNode({
            id: node.id,
            data: { ...node.data, cpu: health?.cpu_pct, memory: health?.memory_pct },
          });
        }}
        onNodeMouseLeave={() => {
          hoveredRef.current = false;
          setHoveredNode(null);
        }}
        onNodeClick={async (_, node) => {
          if (node.type === 'group') return;
          if (pathMode) {
            if (!pathSource) {
              setPathSource(node.id);
            } else {
              try {
                const srcIp = nodes.find(n => n.id === pathSource)?.data?.ip || pathSource;
                const dstIp = node.data?.ip || node.id;
                const result = await fetchTopologyPath(srcIp, dstIp);
                if (result.paths?.length > 0) setPathNodes(new Set(result.paths[0]));
              } catch (err) {
                console.warn('Path trace failed:', err);
              }
              setPathMode(false); setPathSource(null);
            }
            return;
          }
          if (blastTargets.size > 0) setBlastTargets(new Set());
          if (pathNodes.size > 0) setPathNodes(new Set());
        }}
        onNodeContextMenu={(e, node) => {
          e.preventDefault();
          setContextMenu({ x: e.clientX, y: e.clientY, nodeId: node.id, data: node.data });
        }}
        minZoom={0.1}
        maxZoom={2.5}
        proOptions={{ hideAttribution: true }}
        style={{ background: '#0d0c0a' }}
      >
        <Background color="#ffffff" gap={40} size={0.3} style={{ opacity: 0.03 }} />
        <Controls
          style={{ background: '#15130f', border: '1px solid #2a2520', borderRadius: 6 }}
          showInteractive={false}
        />
        <MiniMap
          nodeColor={miniMapNodeColor}
          style={{ background: '#15130f', border: '1px solid #2a2520', borderRadius: 6 }}
          maskColor="rgba(13, 12, 10, 0.85)"
        />
      </ReactFlow>

      <TopologyLegend />

      {/* ── Hover tooltip ────────────────────────────────────────── */}
      {hoveredNode && (
        <div style={{
          position: 'fixed',
          left: mousePos.x + 14,
          top: mousePos.y - 8,
          zIndex: 50,
          background: '#15130f',
          border: '1px solid #2a2520',
          borderRadius: 6,
          padding: '6px 10px',
          minWidth: 170,
          maxWidth: 240,
          pointerEvents: 'none',
          boxShadow: '0 4px 20px rgba(0,0,0,0.7)',
          fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
        }}>
          <div style={{ color: '#e8e0d4', fontSize: 11, fontWeight: 600, marginBottom: 3 }}>{hoveredNode.data.label}</div>
          <div style={{ color: '#7a7060', fontSize: 10, marginBottom: 5 }}>{hoveredNode.data.vendor}</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {[
              ['Status', hoveredNode.data.status, STATUS_COLORS[hoveredNode.data.status] || '#6b7280'],
              hoveredNode.data.cpu != null && ['CPU', `${hoveredNode.data.cpu.toFixed(1)}%`, hoveredNode.data.cpu > 80 ? '#f59e0b' : '#22c55e'],
              hoveredNode.data.memory != null && ['Memory', `${hoveredNode.data.memory.toFixed(1)}%`, hoveredNode.data.memory > 85 ? '#f59e0b' : '#22c55e'],
              hoveredNode.data.ip && ['IP', hoveredNode.data.ip, '#7a7060'],
              hoveredNode.data.haRole && ['HA', hoveredNode.data.haRole, hoveredNode.data.haRole === 'active' ? '#22c55e' : '#6b7280'],
              hoveredNode.data.sessionCount != null && ['Sessions', hoveredNode.data.sessionCount.toLocaleString(), '#7a7060'],
              hoveredNode.data.bgpPeers && ['BGP', hoveredNode.data.bgpPeers, '#7a7060'],
              hoveredNode.data.poolHealth && ['Pool', hoveredNode.data.poolHealth, '#22c55e'],
            ]
              .filter(Boolean)
              .map((row: any, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, gap: 12 }}>
                  <span style={{ color: '#5a5348' }}>{row[0]}</span>
                  <span style={{ color: row[2], fontWeight: 500, fontFamily: row[0] === 'IP' ? 'ui-monospace, monospace' : 'inherit' }}>{row[1]}</span>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* ── Context menu ─────────────────────────────────────────── */}
      {contextMenu && (
        <div
          role="menu"
          aria-label="Device actions"
          style={{
            position: 'fixed',
            left: contextMenu.x,
            top: contextMenu.y,
            zIndex: 60,
            background: '#15130f',
            border: '1px solid #2a2520',
            borderRadius: 6,
            padding: 3,
            minWidth: 150,
            boxShadow: '0 8px 28px rgba(0,0,0,0.7)',
          }}
          onClick={e => e.stopPropagation()}
        >
          <div style={{ padding: '5px 8px', color: '#c0b090', fontSize: 10, fontWeight: 600, borderBottom: '1px solid #2a2520', marginBottom: 2 }}>
            {contextMenu.data?.label}
          </div>
          {[
            { icon: 'crisis_alert', label: 'Blast Radius', action: async () => {
              try {
                const result = await fetchBlastRadius(contextMenu.nodeId);
                setBlastTargets(new Set(result.affected.map((a: any) => a.id)));
              } catch (err) { console.warn('Blast radius failed:', err); }
              setContextMenu(null);
            }},
            { icon: 'route', label: 'Trace Path', action: () => {
              setPathMode(true); setPathSource(contextMenu.nodeId); setContextMenu(null);
            }},
          ].map(item => (
            <button
              key={item.label}
              role="menuitem"
              onClick={item.action}
              style={{
                width: '100%', textAlign: 'left',
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '5px 8px', fontSize: 10, color: '#7a7060',
                background: 'transparent', border: 'none', cursor: 'pointer',
                borderRadius: 3,
              }}
              onMouseEnter={e => { e.currentTarget.style.background = '#1e1b15'; e.currentTarget.style.color = '#e09f3e'; }}
              onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = '#7a7060'; }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 13 }}>{item.icon}</span>
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

export default LiveTopologyViewV2;
