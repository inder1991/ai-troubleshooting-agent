import React, { useCallback, useRef, useState, useEffect, useMemo, DragEvent } from 'react';
import ReactFlow, {
  ReactFlowProvider,
  ConnectionMode,
  addEdge,
  useNodesState,
  useEdgesState,
  Controls,
  Background,
  Connection,
  Edge,
  Node,
  BackgroundVariant,
  ReactFlowInstance,
} from 'reactflow';
import 'reactflow/dist/style.css';
import '@reactflow/node-resizer/dist/style.css';
import NodePalette from './NodePalette';
import DeviceNode from './DeviceNode';
import SubnetGroupNode from './SubnetGroupNode';
import VPCNode from './VPCNode';
import ComplianceZoneNode from './ComplianceZoneNode';
import HAGroupNode from './HAGroupNode';
import AZNode from './AZNode';
import ASGNode from './ASGNode';
import InterfaceNode from './InterfaceNode';
import TextAnnotationNode from './TextAnnotationNode';
import LabeledEdge from './LabeledEdge';
import DevicePropertyPanel from './DevicePropertyPanel';
import TopologyToolbar from './TopologyToolbar';
import IPAMUploadDialog from './IPAMUploadDialog';
import AdapterConfigDialog from './AdapterConfigDialog';
import ValidationPanel from './ValidationPanel';
import { validateTopology, type ValidationError } from '../../utils/networkValidation';
import { loadTopology, saveTopology, promoteTopology, API_BASE_URL } from '../../services/api';
import { useToast } from '../Toast/ToastContext';

const nodeTypes = {
  device: DeviceNode,
  interface: InterfaceNode,
  text_annotation: TextAnnotationNode,
  subnet: SubnetGroupNode,
  vpc: VPCNode,
  compliance_zone: ComplianceZoneNode,
  ha_group: HAGroupNode,
  availability_zone: AZNode,
  auto_scaling_group: ASGNode,
};

const edgeTypes = {
  labeled: LabeledEdge,
};

let idCounter = 0;
const getNextId = () => `node_${Date.now()}_${idCounter++}`;

const CONTAINER_TYPES = new Set(['vpc', 'subnet', 'compliance_zone', 'ha_group', 'availability_zone', 'auto_scaling_group']);

/** Tiered z-index so nested containers stack correctly. */
const Z_INDEX_MAP: Record<string, number> = {
  vpc: 0,
  availability_zone: 1,
  compliance_zone: 1,
  subnet: 2,
  auto_scaling_group: 2,
  ha_group: 2,
};
function applyZIndex(nodeList: Node[]): Node[] {
  return nodeList.map((n) => ({
    ...n,
    zIndex: Z_INDEX_MAP[n.type || ''] ?? 10,
  }));
}

/** Nesting rules: which node types can be children of which container types. */
const NESTABLE_IN_CONTAINER: Record<string, Set<string>> = {
  vpc: new Set(['subnet', 'availability_zone', 'device', 'auto_scaling_group', 'interface']),
  availability_zone: new Set(['subnet', 'device', 'auto_scaling_group', 'interface']),
  subnet: new Set(['device', 'interface']),
  auto_scaling_group: new Set(['device', 'interface']),
  compliance_zone: new Set(['device', 'subnet', 'interface']),
  ha_group: new Set(['device', 'interface']),
};

function TopologyEditorInner() {
  const { addToast } = useToast();
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const [reactFlowInstance, setReactFlowInstance] = useState<ReactFlowInstance | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const selectedNode = useMemo(() =>
    selectedNodeId ? nodes.find(n => n.id === selectedNodeId) || null : null,
    [selectedNodeId, nodes]
  );
  const selectedEdge = useMemo(() =>
    selectedEdgeId ? edges.find(e => e.id === selectedEdgeId) || null : null,
    [selectedEdgeId, edges]
  );
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);
  const [ipamOpen, setIpamOpen] = useState(false);
  const [adapterOpen, setAdapterOpen] = useState(false);
  const [adapterNodeId, setAdapterNodeId] = useState<string | null>(null);
  const [adapterNodeName, setAdapterNodeName] = useState<string | undefined>(undefined);
  const [promoting, setPromoting] = useState(false);
  const [validationErrors, setValidationErrors] = useState<ValidationError[]>([]);

  // Undo/Redo history
  const historyRef = useRef<{ nodes: Node[]; edges: Edge[] }[]>([]);
  const historyIndexRef = useRef(-1);
  const isUndoRedoRef = useRef(false);

  const pushHistory = useCallback(() => {
    if (isUndoRedoRef.current) { isUndoRedoRef.current = false; return; }
    const snap = { nodes: JSON.parse(JSON.stringify(nodes)), edges: JSON.parse(JSON.stringify(edges)) };
    const idx = historyIndexRef.current;
    historyRef.current = historyRef.current.slice(0, idx + 1);
    historyRef.current.push(snap);
    if (historyRef.current.length > 50) historyRef.current.shift();
    historyIndexRef.current = historyRef.current.length - 1;
  }, [nodes, edges]);

  // Snapshot after meaningful changes (debounced)
  const pushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (pushTimerRef.current) clearTimeout(pushTimerRef.current);
    pushTimerRef.current = setTimeout(pushHistory, 500);
    return () => { if (pushTimerRef.current) clearTimeout(pushTimerRef.current); };
  }, [nodes, edges, pushHistory]);

  const handleUndo = useCallback(() => {
    const idx = historyIndexRef.current;
    if (idx <= 0) return;
    historyIndexRef.current = idx - 1;
    const snap = historyRef.current[idx - 1];
    isUndoRedoRef.current = true;
    setNodes(snap.nodes);
    setEdges(snap.edges);
  }, [setNodes, setEdges]);

  const handleRedo = useCallback(() => {
    const idx = historyIndexRef.current;
    if (idx >= historyRef.current.length - 1) return;
    historyIndexRef.current = idx + 1;
    const snap = historyRef.current[idx + 1];
    isUndoRedoRef.current = true;
    setNodes(snap.nodes);
    setEdges(snap.edges);
  }, [setNodes, setEdges]);

  // Keyboard shortcuts for undo/redo
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'z' && !e.shiftKey) { e.preventDefault(); handleUndo(); }
      if ((e.metaKey || e.ctrlKey) && e.key === 'z' && e.shiftKey) { e.preventDefault(); handleRedo(); }
      if ((e.metaKey || e.ctrlKey) && e.key === 'y') { e.preventDefault(); handleRedo(); }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [handleUndo, handleRedo]);

  // Delete selected nodes/edges via toolbar button
  const handleDeleteSelected = useCallback(() => {
    setNodes((nds) => nds.filter((n) => !n.selected));
    setEdges((eds) => eds.filter((e) => !e.selected));
    setSelectedNodeId(null);
  }, [setNodes, setEdges]);

  // Load topology on mount
  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const data = await loadTopology();
        const snapshotJson = data?.snapshot?.snapshot_json;
        if (snapshotJson) {
          const parsed = typeof snapshotJson === 'string'
            ? JSON.parse(snapshotJson)
            : snapshotJson;
          if (parsed.nodes) setNodes(applyZIndex(parsed.nodes));
          if (parsed.edges) setEdges(parsed.edges);
        }
      } catch {
        // No saved topology -- start fresh
      } finally {
        setLoading(false);
      }
    })();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Connection handler
  const onConnect = useCallback(
    (params: Connection) => {
      setEdges((eds) =>
        addEdge(
          {
            ...params,
            type: 'labeled',
            data: {
              label: 'connected_to',
              sourceHandle: params.sourceHandle || '',
              targetHandle: params.targetHandle || '',
            },
            animated: true,
          },
          eds,
        ),
      );
    },
    [setEdges],
  );

  // Selection handlers
  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      setSelectedNodeId(node.id);
      setSelectedEdgeId(null);
    },
    [],
  );

  const onEdgeClick = useCallback(
    (_: React.MouseEvent, edge: Edge) => {
      setSelectedEdgeId(edge.id);
      setSelectedNodeId(null);
    },
    [],
  );

  const onPaneClick = useCallback(() => {
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
  }, []);

  // Containment tracking: when any node is dragged, check if it lands inside a valid container
  const onNodeDragStop = useCallback(
    (_: React.MouseEvent, draggedNode: Node) => {
      const draggedType = draggedNode.type || 'device';

      setNodes((currentNodes) => {
        const containers = currentNodes.filter(
          (n) => CONTAINER_TYPES.has(n.type || '') && n.id !== draggedNode.id
        );

        let newParentId: string | undefined = undefined;
        let smallestArea = Infinity;

        for (const container of containers) {
          const containerType = container.type || '';
          const allowed = NESTABLE_IN_CONTAINER[containerType];
          if (!allowed || !allowed.has(draggedType)) continue;

          const cw = (container.style?.width as number) || 300;
          const ch = (container.style?.height as number) || 200;
          const cx = container.position.x;
          const cy = container.position.y;
          const dx = draggedNode.position.x;
          const dy = draggedNode.position.y;

          if (dx >= cx && dx <= cx + cw && dy >= cy && dy <= cy + ch) {
            const area = cw * ch;
            if (area < smallestArea) {
              smallestArea = area;
              newParentId = container.id;
            }
          }
        }

        return currentNodes.map((n) =>
          n.id === draggedNode.id
            ? { ...n, data: { ...n.data, parentContainerId: newParentId || '' } }
            : n
        );
      });
    },
    [setNodes]
  );

  // Drag-and-drop from palette
  const onDragOver = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      const type = event.dataTransfer.getData('application/reactflow');
      if (!type || !reactFlowInstance || !reactFlowWrapper.current) return;

      const bounds = reactFlowWrapper.current.getBoundingClientRect();
      const position = reactFlowInstance.project({
        x: event.clientX - bounds.left,
        y: event.clientY - bounds.top,
      });

      // Text annotation — not a container or device
      if (type === 'text_annotation') {
        const annotationNode: Node = {
          id: getNextId(),
          type: 'text_annotation',
          position,
          zIndex: 12,
          style: { width: 160, height: 60 },
          data: {
            label: 'Text Note',
            text: '',
            fontSize: 12,
            color: '#e2e8f0',
            backgroundColor: 'transparent',
            borderStyle: 'none',
          },
        };
        setNodes((nds) => nds.concat(annotationNode));
        return;
      }

      const isContainer = type === 'subnet' || type === 'zone' || type === 'vpc' || type === 'compliance_zone' || type === 'ha_group' || type === 'availability_zone' || type === 'auto_scaling_group';

      const containerTypeMap: Record<string, string> = {
        vpc: 'vpc', compliance_zone: 'compliance_zone', ha_group: 'ha_group',
        availability_zone: 'availability_zone', auto_scaling_group: 'auto_scaling_group',
        subnet: 'subnet', zone: 'subnet',
      };
      const nodeType = isContainer ? (containerTypeMap[type] || 'subnet') : 'device';

      const CIDR_TYPES = new Set(['subnet', 'zone', 'vpc', 'compliance_zone']);

      const newNode: Node = {
        id: getNextId(),
        type: nodeType,
        position,
        zIndex: Z_INDEX_MAP[nodeType] ?? 10,
        data: {
          label: type.charAt(0).toUpperCase() + type.slice(1).replace(/_/g, ' '),
          deviceType: type,
          ip: '',
          vendor: '',
          zone: '',
          status: 'healthy',
          ...(CIDR_TYPES.has(type) ? { cidr: '10.0.0.0/24' } : {}),
        },
        ...(isContainer
          ? {
              style: {
                width: ({ vpc: 800, availability_zone: 500, auto_scaling_group: 400, ha_group: 350, compliance_zone: 400 } as Record<string, number>)[type] || 300,
                height: ({ vpc: 600, availability_zone: 400, auto_scaling_group: 300, ha_group: 250, compliance_zone: 300 } as Record<string, number>)[type] || 200,
              },
            }
          : {}),
      };

      setNodes((nds) => nds.concat(newNode));
    },
    [reactFlowInstance, setNodes],
  );

  // Save topology
  const handleSave = useCallback(async () => {
    if (!reactFlowInstance) return;
    const flow = reactFlowInstance.toObject();
    const errs = validateTopology(flow.nodes as any);
    const blocking = errs.filter((e) => e.severity === 'error');
    setValidationErrors(errs);
    if (blocking.length > 0) {
      addToast('error', `Fix ${blocking.length} error${blocking.length > 1 ? 's' : ''} before saving`);
      return;
    }
    setSaving(true);
    try {
      await saveTopology(JSON.stringify(flow), 'User-saved topology');
      addToast('success', 'Topology saved');
    } catch (err) {
      console.error('Failed to save topology:', err);
      addToast('error', 'Failed to save topology');
    } finally {
      setSaving(false);
    }
  }, [reactFlowInstance, addToast]);

  // Load topology
  const handleLoad = useCallback(async () => {
    setLoading(true);
    try {
      const data = await loadTopology();
      const snapshotJson = data?.snapshot?.snapshot_json;
      if (snapshotJson) {
        const parsed = typeof snapshotJson === 'string'
          ? JSON.parse(snapshotJson)
          : snapshotJson;
        if (parsed.nodes) setNodes(applyZIndex(parsed.nodes));
        if (parsed.edges) setEdges(parsed.edges);
        addToast('info', 'Topology loaded');
      }
    } catch (err) {
      console.error('Failed to load topology:', err);
      addToast('error', 'Failed to load topology');
    } finally {
      setLoading(false);
    }
  }, [setNodes, setEdges, addToast]);

  // Refresh from Knowledge Graph
  const handleRefreshFromKG = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v4/network/topology/current`);
      if (response.ok) {
        const data = await response.json();
        if (data.nodes) setNodes(applyZIndex(data.nodes as Node[]));
        if (data.edges) setEdges(data.edges as Edge[]);
      }
    } catch (err) {
      console.error('Failed to refresh from KG:', err);
    } finally {
      setLoading(false);
    }
  }, [setNodes, setEdges]);

  // Promote to Infrastructure (canvas -> KG)
  const handlePromote = useCallback(async () => {
    if (!reactFlowInstance) return;
    const flow = reactFlowInstance.toObject();
    const errs = validateTopology(flow.nodes as any);
    const blocking = errs.filter((e) => e.severity === 'error');
    setValidationErrors(errs);
    if (blocking.length > 0) {
      addToast('error', `Fix ${blocking.length} error${blocking.length > 1 ? 's' : ''} before promoting`);
      return;
    }
    setPromoting(true);
    try {
      await promoteTopology(flow.nodes, flow.edges);
      addToast('success', 'Topology promoted to infrastructure');
    } catch (err) {
      console.error('Promote failed:', err);
      addToast('error', 'Failed to promote topology');
    } finally {
      setPromoting(false);
    }
  }, [reactFlowInstance, addToast]);

  // Node property update
  const handleNodeUpdate = useCallback(
    (nodeId: string, data: Record<string, unknown>) => {
      setNodes((nds) =>
        nds.map((n) =>
          n.id === nodeId ? { ...n, data: { ...n.data, ...data } } : n,
        ),
      );
    },
    [setNodes],
  );

  // Edge property update
  const handleEdgeUpdate = useCallback(
    (edgeId: string, data: Record<string, unknown>) => {
      setEdges((eds) =>
        eds.map((e) =>
          e.id === edgeId ? { ...e, data: { ...e.data, ...data } } : e,
        ),
      );
    },
    [setEdges],
  );

  // Delete a specific edge
  const handleDeleteEdge = useCallback(
    (edgeId: string) => {
      setEdges((eds) => eds.filter((e) => e.id !== edgeId));
      setSelectedEdgeId(null);
    },
    [setEdges],
  );

  // Adapter config
  const handleConfigureAdapter = useCallback(
    (nodeId: string) => {
      const node = nodes.find((n) => n.id === nodeId);
      setAdapterNodeId(nodeId);
      setAdapterNodeName(node?.data?.label as string | undefined);
      setAdapterOpen(true);
    },
    [nodes],
  );

  // Add interface as a separate draggable node — distributes around cardinal positions
  const handleAddInterface = useCallback(
    (parentNodeId: string) => {
      const parentNode = nodes.find((n) => n.id === parentNodeId);
      if (!parentNode) return;

      const ifaceId = getNextId();
      const ifaceCount = nodes.filter(
        (n) => n.type === 'interface' && (n.data as Record<string, unknown>).parentDeviceId === parentNodeId
      ).length;

      // Cardinal positions: top, right, bottom, left — cycle with offset for 5+
      const cardinalIndex = ifaceCount % 4;
      const cycle = Math.floor(ifaceCount / 4);
      const offset = cycle * 40;
      const px = parentNode.position.x;
      const py = parentNode.position.y;
      const pw = (parentNode.style?.width as number) || 56;
      const ph = (parentNode.style?.height as number) || 40;

      const positions = [
        { x: px + pw / 2 - 35 + offset, y: py - 60 - offset },           // top
        { x: px + pw + 40 + offset, y: py + ph / 2 - 14 + offset },      // right
        { x: px + pw / 2 - 35 + offset, y: py + ph + 30 + offset },      // bottom
        { x: px - 110 - offset, y: py + ph / 2 - 14 + offset },          // left
      ];
      // Edge handle pairs: interface→device attachment
      const handlePairs = [
        { sourceHandle: 'bottom', targetHandle: 'top' },     // top: iface bottom → device top
        { sourceHandle: 'left', targetHandle: 'right' },     // right: iface left → device right (swapped for target)
        { sourceHandle: 'top', targetHandle: 'bottom' },     // bottom: iface top → device bottom
        { sourceHandle: 'right', targetHandle: 'left' },     // left: iface right → device left
      ];
      const defaultRoles = ['outside', 'inside', 'management', 'sync'];

      const pos = positions[cardinalIndex];
      const handles = handlePairs[cardinalIndex];

      const newIface: Node = {
        id: ifaceId,
        type: 'interface',
        position: pos,
        zIndex: 15,
        data: {
          name: `eth${ifaceCount}`,
          ip: '',
          role: defaultRoles[cardinalIndex] || '',
          zone: '',
          parentDeviceId: parentNodeId,
          parentDeviceName: (parentNode.data as Record<string, unknown>).label || parentNodeId,
        },
      };

      const autoEdge: Edge = {
        id: `edge-${ifaceId}-${parentNodeId}`,
        source: ifaceId,
        target: parentNodeId,
        sourceHandle: handles.sourceHandle,
        targetHandle: handles.targetHandle,
        type: 'labeled',
        data: { label: 'attached_to' },
        animated: true,
        style: { strokeDasharray: '4 2' },
      };

      setNodes((nds) => nds.concat(newIface));
      setEdges((eds) => addEdge(autoEdge, eds));
    },
    [nodes, setNodes, setEdges],
  );

  // Validation click: zoom to error node
  const handleValidationClick = useCallback((nodeId: string) => {
    const node = nodes.find((n) => n.id === nodeId);
    if (node && reactFlowInstance) {
      reactFlowInstance.fitView({ nodes: [node], duration: 300, padding: 0.5 });
      setSelectedNodeId(nodeId);
    }
  }, [nodes, reactFlowInstance]);

  // IPAM import results
  const handleIPAMImported = useCallback(
    (data: { nodes: unknown[]; edges: unknown[] }) => {
      if (data.nodes) setNodes((nds) => applyZIndex([...nds, ...(data.nodes as Node[])]));
      if (data.edges) setEdges((eds) => [...eds, ...(data.edges as Edge[])]);
      setIpamOpen(false);
      addToast('success', `Imported ${(data.nodes?.length || 0)} nodes from IPAM`);
    },
    [setNodes, setEdges, addToast],
  );

  return (
    <div className="flex-1 flex flex-col overflow-hidden" style={{ backgroundColor: '#0a0f13' }}>
      {/* Toolbar */}
      <TopologyToolbar
        onSave={handleSave}
        onLoad={handleLoad}
        onImportIPAM={() => setIpamOpen(true)}
        onAdapterStatus={() => setAdapterOpen(true)}
        onRefreshFromKG={handleRefreshFromKG}
        onPromote={handlePromote}
        onUndo={handleUndo}
        onRedo={handleRedo}
        onDeleteSelected={handleDeleteSelected}
        canUndo={historyIndexRef.current > 0}
        canRedo={historyIndexRef.current < historyRef.current.length - 1}
        hasSelection={nodes.some((n) => n.selected) || edges.some((e) => e.selected)}
        saving={saving}
        loading={loading}
        promoting={promoting}
      />

      {/* Main area: palette + canvas + property panel */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left sidebar: Node Palette */}
        <NodePalette />

        {/* React Flow Canvas */}
        <div className="flex-1" ref={reactFlowWrapper}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onInit={setReactFlowInstance}
            onNodeClick={onNodeClick}
            onEdgeClick={onEdgeClick}
            onPaneClick={onPaneClick}
            onNodeDragStop={onNodeDragStop}
            onDragOver={onDragOver}
            onDrop={onDrop}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            connectionMode={ConnectionMode.Loose}
            deleteKeyCode="Delete"
            fitView
            proOptions={{ hideAttribution: true }}
            defaultEdgeOptions={{
              type: 'labeled',
              style: { stroke: '#224349', strokeWidth: 2 },
              animated: false,
            }}
          >
            <Background
              variant={BackgroundVariant.Dots}
              gap={20}
              size={1}
              color="#224349"
            />
            <Controls
              style={{
                button: { backgroundColor: '#0f2023', color: '#e2e8f0', borderColor: '#224349' },
              } as unknown as React.CSSProperties}
            />
          </ReactFlow>
        </div>

        {/* Right panel: Device Properties */}
        <DevicePropertyPanel
          selectedNode={selectedNode}
          selectedEdge={selectedEdge}
          onNodeUpdate={handleNodeUpdate}
          onEdgeUpdate={handleEdgeUpdate}
          onDeleteEdge={handleDeleteEdge}
          onConfigureAdapter={handleConfigureAdapter}
          onAddInterface={handleAddInterface}
        />
      </div>

      {/* Validation Panel */}
      <ValidationPanel
        errors={validationErrors}
        onClickError={handleValidationClick}
        onDismiss={() => setValidationErrors([])}
      />

      {/* Dialogs */}
      <IPAMUploadDialog
        open={ipamOpen}
        onClose={() => setIpamOpen(false)}
        onImported={handleIPAMImported}
      />
      <AdapterConfigDialog
        open={adapterOpen}
        onClose={() => setAdapterOpen(false)}
        nodeId={adapterNodeId}
        nodeName={adapterNodeName}
      />
    </div>
  );
}

const TopologyEditorView: React.FC = () => {
  return (
    <ReactFlowProvider>
      <TopologyEditorInner />
    </ReactFlowProvider>
  );
};

export default TopologyEditorView;
