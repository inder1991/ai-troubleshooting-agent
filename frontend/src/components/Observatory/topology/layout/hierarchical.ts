import dagre from 'dagre';
import { Node, Edge } from 'reactflow';
import type { LayoutInput, LayoutOutput, ApiGroup } from './types';
import { getEdgeStyle, getEdgeLabel } from './edgeStyles';

export function hierarchicalLayout(input: LayoutInput): LayoutOutput {
  const { nodes, edges, groups, canvasWidth, canvasHeight } = input;

  // Build per-group dagre sub-graphs
  const rfNodes: Node[] = [];

  // Arrange groups: onprem at center, others around
  const groupPositions = arrangeGroupCenters(groups, canvasWidth, canvasHeight);

  for (const group of groups) {
    const memberNodes = nodes.filter(n => n.group === group.id);
    if (memberNodes.length === 0) continue;

    const g = new dagre.graphlib.Graph();
    g.setGraph({ rankdir: 'TB', ranksep: 80, nodesep: 30, marginx: 20, marginy: 20 });
    g.setDefaultEdgeLabel(() => ({}));

    for (const node of memberNodes) {
      g.setNode(node.id, { width: 180, height: 90 });
    }

    // Intra-group edges only
    for (const edge of edges) {
      const srcG = nodes.find(n => n.id === edge.source)?.group;
      const tgtG = nodes.find(n => n.id === edge.target)?.group;
      if (srcG === group.id && tgtG === group.id) {
        g.setEdge(edge.source, edge.target);
      }
    }

    dagre.layout(g);

    const gCenter = groupPositions[group.id] || { x: canvasWidth / 2, y: canvasHeight / 2 };

    // Get bounding box of dagre layout
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    g.nodes().forEach((nodeId: string) => {
      const nd = g.node(nodeId);
      minX = Math.min(minX, nd.x - nd.width / 2);
      minY = Math.min(minY, nd.y - nd.height / 2);
      maxX = Math.max(maxX, nd.x + nd.width / 2);
      maxY = Math.max(maxY, nd.y + nd.height / 2);
    });

    const layoutW = maxX - minX;
    const layoutH = maxY - minY;
    const offsetX = gCenter.x - layoutW / 2 - minX;
    const offsetY = gCenter.y - layoutH / 2 - minY;

    // Add group container node
    const padding = 40;
    const groupNode: Node = {
      id: `group-${group.id}`,
      type: 'group',
      position: { x: gCenter.x - layoutW / 2 - padding, y: gCenter.y - layoutH / 2 - padding },
      data: { label: group.label },
      style: {
        width: layoutW + 2 * padding,
        height: layoutH + 2 * padding,
        backgroundColor: `${group.accent}0A`,
        border: `2px solid ${group.accent}50`,
        borderRadius: 16,
        fontSize: 16,
        fontWeight: 800,
        color: `${group.accent}CC`,
        letterSpacing: '0.06em',
        textTransform: 'uppercase' as const,
      },
      selectable: false,
      draggable: false,
    };
    rfNodes.push(groupNode);

    // Add device nodes as children of group
    g.nodes().forEach((nodeId: string) => {
      const nd = g.node(nodeId);
      const apiNode = nodes.find(n => n.id === nodeId)!;
      rfNodes.push({
        id: nodeId,
        type: 'device',
        parentNode: `group-${group.id}`,
        position: {
          x: nd.x + offsetX - gCenter.x + layoutW / 2 + padding - nd.width / 2,
          y: nd.y + offsetY - gCenter.y + layoutH / 2 + padding - nd.height / 2,
        },
        data: {
          label: apiNode.hostname,
          deviceType: apiNode.device_type,
          ip: '',
          vendor: apiNode.vendor,
          role: '',
          group: apiNode.group,
          status: apiNode.status,
          haRole: apiNode.ha_role || '',
        },
      });
    });
  }

  // Build edges
  const rfEdges: Edge[] = edges.map(e => ({
    id: e.id,
    source: e.source,
    target: e.target,
    type: 'smoothstep',
    style: getEdgeStyle(e),
    label: getEdgeLabel(e),
    labelStyle: { fontSize: 9, fill: '#64748b' },
    labelBgStyle: { fill: '#1a1814', fillOpacity: 0.8 },
    labelBgPadding: [4, 2] as [number, number],
    animated: e.edge_type === 'tunnel',
    data: e,
  }));

  return { nodes: rfNodes, edges: rfEdges };
}

function arrangeGroupCenters(
  groups: ApiGroup[],
  width: number,
  height: number,
): Record<string, { x: number; y: number }> {
  const cx = width / 2;
  const cy = height / 2;
  const radius = Math.min(width, height) * 0.35;
  const centers: Record<string, { x: number; y: number }> = {};

  centers['onprem'] = { x: cx, y: cy };

  const ANGLES: Record<string, number> = {
    aws: 0, gcp: 60, azure: 180, oci: 240, branch: 310,
  };

  for (const group of groups) {
    if (group.id === 'onprem') continue;
    const angleDeg = ANGLES[group.id] ?? (Object.keys(centers).length * 72);
    const angleRad = (angleDeg * Math.PI) / 180;
    centers[group.id] = {
      x: cx + radius * Math.cos(angleRad),
      y: cy - radius * Math.sin(angleRad),
    };
  }

  return centers;
}
