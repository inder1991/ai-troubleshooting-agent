import React, { useCallback, useRef, useState, useEffect, DragEvent } from 'react';
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
import NodePalette from './NodePalette';
import DeviceNode from './DeviceNode';
import SubnetGroupNode from './SubnetGroupNode';
import VPCNode from './VPCNode';
import ComplianceZoneNode from './ComplianceZoneNode';
import HAGroupNode from './HAGroupNode';
import DevicePropertyPanel from './DevicePropertyPanel';
import TopologyToolbar from './TopologyToolbar';
import IPAMUploadDialog from './IPAMUploadDialog';
import AdapterConfigDialog from './AdapterConfigDialog';
import ValidationPanel from './ValidationPanel';
import { validateTopology, type ValidationError } from '../../utils/networkValidation';
import { loadTopology, saveTopology, promoteTopology, API_BASE_URL } from '../../services/api';

const nodeTypes = {
  device: DeviceNode,
  subnet: SubnetGroupNode,
  vpc: VPCNode,
  compliance_zone: ComplianceZoneNode,
  ha_group: HAGroupNode,
};

let idCounter = 0;
const getNextId = () => `node_${Date.now()}_${idCounter++}`;

function TopologyEditorInner() {
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const [reactFlowInstance, setReactFlowInstance] = useState<ReactFlowInstance | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);
  const [ipamOpen, setIpamOpen] = useState(false);
  const [adapterOpen, setAdapterOpen] = useState(false);
  const [adapterNodeId, setAdapterNodeId] = useState<string | null>(null);
  const [adapterNodeName, setAdapterNodeName] = useState<string | undefined>(undefined);
  const [promoting, setPromoting] = useState(false);
  const [validationErrors, setValidationErrors] = useState<ValidationError[]>([]);

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
          if (parsed.nodes) setNodes(parsed.nodes);
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
            style: { stroke: '#07b6d5', strokeWidth: 2 },
            animated: true,
          },
          eds,
        ),
      );
    },
    [setEdges],
  );

  // Selection handler
  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      setSelectedNode(node);
    },
    [],
  );

  const onPaneClick = useCallback(() => {
    setSelectedNode(null);
  }, []);

  // Containment tracking: when a device is dragged, check if it lands inside a container
  const onNodeDragStop = useCallback(
    (_: React.MouseEvent, draggedNode: Node) => {
      if (draggedNode.type !== 'device') return;

      const containers = nodes.filter(
        (n) => (n.type === 'vpc' || n.type === 'subnet' || n.type === 'compliance_zone' || n.type === 'ha_group') && n.id !== draggedNode.id
      );

      let newParentId: string | undefined = undefined;

      for (const container of containers) {
        const cw = (container.style?.width as number) || 300;
        const ch = (container.style?.height as number) || 200;
        const cx = container.position.x;
        const cy = container.position.y;
        const dx = draggedNode.position.x;
        const dy = draggedNode.position.y;

        if (dx >= cx && dx <= cx + cw && dy >= cy && dy <= cy + ch) {
          newParentId = container.id;
          break;
        }
      }

      setNodes((nds) =>
        nds.map((n) =>
          n.id === draggedNode.id
            ? { ...n, data: { ...n.data, parentContainerId: newParentId || '' } }
            : n
        )
      );
    },
    [nodes, setNodes]
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

      const isContainer = type === 'subnet' || type === 'zone' || type === 'vpc' || type === 'compliance_zone' || type === 'ha_group';

      const newNode: Node = {
        id: getNextId(),
        type: isContainer ? (type === 'vpc' ? 'vpc' : type === 'compliance_zone' ? 'compliance_zone' : type === 'ha_group' ? 'ha_group' : 'subnet') : 'device',
        position,
        data: {
          label: type.charAt(0).toUpperCase() + type.slice(1).replace('_', ' '),
          deviceType: type,
          ip: '',
          vendor: '',
          zone: '',
          status: 'healthy',
          ...(isContainer ? { cidr: '10.0.0.0/24' } : {}),
        },
        ...(isContainer
          ? { style: { width: type === 'vpc' ? 400 : 300, height: type === 'vpc' ? 300 : 200 } }
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
    if (blocking.length > 0) return; // block save
    setSaving(true);
    try {
      await saveTopology(JSON.stringify(flow), 'User-saved topology');
    } catch (err) {
      console.error('Failed to save topology:', err);
    } finally {
      setSaving(false);
    }
  }, [reactFlowInstance]);

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
        if (parsed.nodes) setNodes(parsed.nodes);
        if (parsed.edges) setEdges(parsed.edges);
      }
    } catch (err) {
      console.error('Failed to load topology:', err);
    } finally {
      setLoading(false);
    }
  }, [setNodes, setEdges]);

  // Refresh from Knowledge Graph
  const handleRefreshFromKG = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v4/network/topology/current`);
      if (response.ok) {
        const data = await response.json();
        if (data.nodes) setNodes(data.nodes as Node[]);
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
    if (blocking.length > 0) return; // block promote
    setPromoting(true);
    try {
      await promoteTopology(flow.nodes, flow.edges);
    } catch (err) {
      console.error('Promote failed:', err);
    } finally {
      setPromoting(false);
    }
  }, [reactFlowInstance]);

  // Node property update
  const handleNodeUpdate = useCallback(
    (nodeId: string, data: Record<string, unknown>) => {
      setNodes((nds) =>
        nds.map((n) =>
          n.id === nodeId ? { ...n, data: { ...n.data, ...data } } : n,
        ),
      );
      setSelectedNode((prev) =>
        prev && prev.id === nodeId
          ? { ...prev, data: { ...prev.data, ...data } }
          : prev,
      );
    },
    [setNodes],
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

  // Validation click: zoom to error node
  const handleValidationClick = useCallback((nodeId: string) => {
    const node = nodes.find((n) => n.id === nodeId);
    if (node && reactFlowInstance) {
      reactFlowInstance.fitView({ nodes: [node], duration: 300, padding: 0.5 });
      setSelectedNode(node);
    }
  }, [nodes, reactFlowInstance]);

  // IPAM import results
  const handleIPAMImported = useCallback(
    (data: { nodes: unknown[]; edges: unknown[] }) => {
      if (data.nodes) setNodes((nds) => [...nds, ...(data.nodes as Node[])]);
      if (data.edges) setEdges((eds) => [...eds, ...(data.edges as Edge[])]);
      setIpamOpen(false);
    },
    [setNodes, setEdges],
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
            onPaneClick={onPaneClick}
            onNodeDragStop={onNodeDragStop}
            onDragOver={onDragOver}
            onDrop={onDrop}
            nodeTypes={nodeTypes}
            connectionMode={ConnectionMode.Loose}
            fitView
            proOptions={{ hideAttribution: true }}
            defaultEdgeOptions={{
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
          onNodeUpdate={handleNodeUpdate}
          onConfigureAdapter={handleConfigureAdapter}
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
