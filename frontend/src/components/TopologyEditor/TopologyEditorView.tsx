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
import DevicePropertyPanel from './DevicePropertyPanel';
import TopologyToolbar from './TopologyToolbar';
import IPAMUploadDialog from './IPAMUploadDialog';
import AdapterConfigDialog from './AdapterConfigDialog';
import { loadTopology, saveTopology } from '../../services/api';

const nodeTypes = {
  device: DeviceNode,
  subnet: SubnetGroupNode,
  vpc: VPCNode,
  compliance_zone: ComplianceZoneNode,
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

      const isContainer = type === 'subnet' || type === 'zone' || type === 'vpc' || type === 'compliance_zone';

      const newNode: Node = {
        id: getNextId(),
        type: isContainer ? (type === 'vpc' ? 'vpc' : type === 'compliance_zone' ? 'compliance_zone' : 'subnet') : 'device',
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
    setSaving(true);
    try {
      const flow = reactFlowInstance.toObject();
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
        saving={saving}
        loading={loading}
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
