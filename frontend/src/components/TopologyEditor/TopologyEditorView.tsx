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
import { validateTopology, type ValidationError, getNthHostFromCIDR, isCIDRSubsetOf, isIPInCIDR } from '../../utils/networkValidation';
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

/** Placement guardrails: warn when on-prem devices are placed in cloud containers. */
const CLOUD_ONLY_CONTAINERS = new Set(['vpc', 'availability_zone', 'auto_scaling_group']);
const ON_PREM_ONLY_DEVICES = new Set(['switch', 'vlan', 'mpls']);

function checkPlacementWarning(deviceType: string, containerType: string): string | null {
  if (CLOUD_ONLY_CONTAINERS.has(containerType) && ON_PREM_ONLY_DEVICES.has(deviceType)) {
    return `${deviceType.replace(/_/g, ' ')} is an on-prem device — consider using cloud-native equivalents in ${containerType.replace(/_/g, ' ')}`;
  }
  return null;
}

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

  // Snapshot after meaningful changes + auto-save to localStorage (debounced)
  const pushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const initialLoadDone = useRef(false);
  useEffect(() => {
    if (pushTimerRef.current) clearTimeout(pushTimerRef.current);
    pushTimerRef.current = setTimeout(() => {
      pushHistory();
      // Auto-save to localStorage so work survives sleep/refresh
      if (initialLoadDone.current && (nodes.length > 0 || edges.length > 0)) {
        try {
          localStorage.setItem('topology_autosave', JSON.stringify({ nodes, edges, savedAt: Date.now() }));
        } catch { /* quota exceeded — ignore */ }
      }
    }, 500);
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

  // Load topology on mount — try backend first, fall back to localStorage autosave
  useEffect(() => {
    (async () => {
      let loaded = false;
      try {
        setLoading(true);
        const data = await loadTopology();
        const snapshotJson = data?.snapshot?.snapshot_json;
        if (snapshotJson) {
          const parsed = typeof snapshotJson === 'string'
            ? JSON.parse(snapshotJson)
            : snapshotJson;
          if (parsed.nodes?.length) {
            setNodes(applyZIndex(parsed.nodes));
            if (parsed.edges) setEdges(parsed.edges);
            loaded = true;
          }
        }
      } catch {
        // Backend unavailable
      }
      // Fall back to localStorage autosave
      if (!loaded) {
        try {
          const saved = localStorage.getItem('topology_autosave');
          if (saved) {
            const parsed = JSON.parse(saved);
            if (parsed.nodes?.length) {
              setNodes(applyZIndex(parsed.nodes));
              if (parsed.edges) setEdges(parsed.edges);
              loaded = true;
            }
          }
        } catch { /* corrupt data — ignore */ }
      }
      initialLoadDone.current = true;
      setLoading(false);
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

  // Selection handlers — sync ReactFlow's visual selection with our state
  useEffect(() => {
    setNodes((nds) => nds.map((n) => ({ ...n, selected: n.id === selectedNodeId })));
  }, [selectedNodeId, setNodes]);

  useEffect(() => {
    setEdges((eds) => eds.map((e) => ({ ...e, selected: e.id === selectedEdgeId })));
  }, [selectedEdgeId, setEdges]);

  const onNodeClick = useCallback(
    (event: React.MouseEvent, node: Node) => {
      // For container nodes, check if user clicked on an edge or a child node underneath
      if (CONTAINER_TYPES.has(node.type || '')) {
        const target = event.currentTarget as HTMLElement;
        const nodeWrapper = target.closest('.react-flow__node') as HTMLElement | null;
        if (nodeWrapper) {
          // Temporarily hide this container to see what's beneath it
          const origVisibility = nodeWrapper.style.visibility;
          nodeWrapper.style.visibility = 'hidden';
          const elements = document.elementsFromPoint(event.clientX, event.clientY);
          nodeWrapper.style.visibility = origVisibility;

          const thisRect = nodeWrapper.getBoundingClientRect();

          // Priority 1: check for an edge underneath
          for (const el of elements) {
            const edgeGroup = el.closest('.react-flow__edge');
            if (edgeGroup) {
              const testId = edgeGroup.getAttribute('data-testid') || '';
              const edgeId = testId.replace('rf__edge-', '');
              if (edgeId) {
                setSelectedEdgeId(edgeId);
                setSelectedNodeId(null);
                return;
              }
            }
          }

          // Priority 2: check for a CHILD node underneath (smaller than this container)
          for (const el of elements) {
            const childWrapper = el.closest('.react-flow__node') as HTMLElement | null;
            if (childWrapper && childWrapper !== nodeWrapper) {
              const childRect = childWrapper.getBoundingClientRect();
              // Only select if it's smaller (a child), not larger (a parent)
              if (childRect.width * childRect.height < thisRect.width * thisRect.height) {
                const childId = childWrapper.getAttribute('data-id');
                if (childId && childId !== node.id) {
                  setSelectedNodeId(childId);
                  setSelectedEdgeId(null);
                  return;
                }
              }
            }
          }
        }
      }
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

  // Auto-provision an interface when a device is placed into a subnet
  const autoProvisionInterface = useCallback(
    (deviceNode: Node, subnetNode: Node) => {
      const subnetCidr = (subnetNode.data as Record<string, unknown>).cidr as string;
      if (!subnetCidr) return;

      // Check if this device already has interfaces — skip if so
      const existingIfaces = nodes.filter(
        (n) => n.type === 'interface' && (n.data as Record<string, unknown>).parentDeviceId === deviceNode.id
      );
      if (existingIfaces.length > 0) return;

      // Count existing interfaces in this subnet to offset IP
      const subnetIfaces = nodes.filter(
        (n) => n.type === 'interface' && (n.data as Record<string, unknown>).subnetId === subnetNode.id
      );
      const ip = getNthHostFromCIDR(subnetCidr, subnetIfaces.length + 10) || '';

      const ifaceId = getNextId();
      const pw = (deviceNode.style?.width as number) || 56;
      const ph = (deviceNode.style?.height as number) || 40;
      // Place at cardinal index 0 (top) — matches handleAddInterface's first position
      const newIface: Node = {
        id: ifaceId,
        type: 'interface',
        position: {
          x: deviceNode.position.x + pw / 2 - 35,
          y: deviceNode.position.y - 60,
        },
        zIndex: 15,
        data: {
          name: 'eth0',
          ip,
          role: 'outside',
          zone: '',
          parentDeviceId: deviceNode.id,
          parentDeviceName: (deviceNode.data as Record<string, unknown>).label || deviceNode.id,
          subnetId: subnetNode.id,
        },
      };

      // iface ABOVE device: iface.bottom(source) → device.top(target) — matches handleAddInterface index 0
      const autoEdge: Edge = {
        id: `edge-${ifaceId}-${deviceNode.id}`,
        source: ifaceId,
        target: deviceNode.id,
        sourceHandle: 'bottom',
        targetHandle: 'top',
        type: 'labeled',
        data: { label: 'attached_to' },
        animated: true,
        style: { strokeDasharray: '4 2' },
      };

      setNodes((nds) => nds.concat(newIface));
      setEdges((eds) => addEdge(autoEdge, eds));
      addToast('info', `Auto-created eth0 (${ip || 'no IP'}) for ${(deviceNode.data as Record<string, unknown>).label}`);
    },
    [nodes, setNodes, setEdges, addToast],
  );

  // Containment tracking: when any node is dragged, check if it lands inside a valid container
  const onNodeDragStop = useCallback(
    (_: React.MouseEvent, draggedNode: Node) => {
      const draggedType = draggedNode.type || 'device';

      let foundSubnet: Node | undefined;

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

        // Track if device was dropped into a subnet for auto-provisioning
        if (draggedType === 'device' && newParentId) {
          const parent = containers.find((c) => c.id === newParentId);
          if (parent && parent.type === 'subnet') {
            foundSubnet = parent;
          }
        }

        // CIDR containment warning: subnet dragged into VPC
        if (draggedNode.type === 'subnet' && newParentId) {
          const parentVpc = containers.find((c) => c.id === newParentId && c.type === 'vpc');
          if (parentVpc) {
            const subCidr = (draggedNode.data as Record<string, unknown>).cidr as string;
            const vpcCidr = (parentVpc.data as Record<string, unknown>).cidr as string;
            if (subCidr && vpcCidr && !isCIDRSubsetOf(subCidr, vpcCidr)) {
              addToast('warning', `Subnet CIDR ${subCidr} is not within VPC CIDR ${vpcCidr}`);
            }
          }
        }

        // Placement guardrail: on-prem device in cloud container
        if (draggedType === 'device' && newParentId) {
          const parent = containers.find((c) => c.id === newParentId);
          if (parent) {
            const warning = checkPlacementWarning(
              (draggedNode.data as Record<string, unknown>).deviceType as string || '',
              parent.type || ''
            );
            if (warning) addToast('warning', warning);
          }
        }

        return currentNodes.map((n) =>
          n.id === draggedNode.id
            ? { ...n, data: { ...n.data, parentContainerId: newParentId || '' } }
            : n
        );
      });

      // Auto-provision interface after state update
      if (foundSubnet && draggedType === 'device') {
        autoProvisionInterface(draggedNode, foundSubnet);
      }
    },
    [setNodes, addToast, autoProvisionInterface]
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

      setNodes((nds) => {
        const updatedNodes = nds.concat(newNode);

        // If dropping a device, check if it lands in a container
        if (!isContainer) {
          const containers = updatedNodes.filter(
            (n) => CONTAINER_TYPES.has(n.type || '') && n.id !== newNode.id
          );
          let parentContainer: Node | undefined;
          let smallestArea = Infinity;
          for (const container of containers) {
            const allowed = NESTABLE_IN_CONTAINER[container.type || ''];
            if (!allowed || !allowed.has('device')) continue;
            const cw = (container.style?.width as number) || 300;
            const ch = (container.style?.height as number) || 200;
            if (position.x >= container.position.x && position.x <= container.position.x + cw &&
                position.y >= container.position.y && position.y <= container.position.y + ch) {
              const area = cw * ch;
              if (area < smallestArea) { smallestArea = area; parentContainer = container; }
            }
          }

          if (parentContainer) {
            // Placement guardrail
            const warning = checkPlacementWarning(type, parentContainer.type || '');
            if (warning) addToast('warning', warning);

            // Auto-provision interface if dropped into subnet
            if (parentContainer.type === 'subnet') {
              setTimeout(() => autoProvisionInterface(newNode, parentContainer!), 50);
            }

            return updatedNodes.map((n) =>
              n.id === newNode.id ? { ...n, data: { ...n.data, parentContainerId: parentContainer!.id } } : n
            );
          }
        }

        return updatedNodes;
      });
    },
    [reactFlowInstance, setNodes, addToast, autoProvisionInterface],
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
      // Edge handle pairs: must match source-type handles to target-type handles.
      // Both DeviceNode & InterfaceNode: top=target, left=target, bottom=source, right=source.
      // 'edgeSource' indicates which node is the edge source (the other is edge target).
      const handlePairs = [
        // iface ABOVE device: iface.bottom(src) → device.top(tgt)
        { edgeSource: 'interface' as const, sourceHandle: 'bottom', targetHandle: 'top' },
        // iface RIGHT of device: device.right(src) → iface.left(tgt)
        { edgeSource: 'device' as const,    sourceHandle: 'right',  targetHandle: 'left' },
        // iface BELOW device: device.bottom(src) → iface.top(tgt)
        { edgeSource: 'device' as const,    sourceHandle: 'bottom', targetHandle: 'top' },
        // iface LEFT of device: iface.right(src) → device.left(tgt)
        { edgeSource: 'interface' as const, sourceHandle: 'right',  targetHandle: 'left' },
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

      // Determine edge source/target based on which node has a valid source-type handle
      const edgeSrcId = handles.edgeSource === 'interface' ? ifaceId : parentNodeId;
      const edgeTgtId = handles.edgeSource === 'interface' ? parentNodeId : ifaceId;

      const autoEdge: Edge = {
        id: `edge-${ifaceId}-${parentNodeId}`,
        source: edgeSrcId,
        target: edgeTgtId,
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
            elementsSelectable={true}
            edgesFocusable={true}
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
          allNodes={nodes}
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
