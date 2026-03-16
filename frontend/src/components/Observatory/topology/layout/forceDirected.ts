import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceX,
  forceY,
  forceCollide,
  type SimulationNodeDatum,
  type SimulationLinkDatum,
} from 'd3-force';
import { Node, Edge } from 'reactflow';
import type { LayoutInput, LayoutOutput, ApiNode, ApiGroup } from './types';
import { getEdgeStyle, getEdgeLabel } from './edgeStyles';

interface SimNode extends SimulationNodeDatum {
  id: string;
  group: string;
  rank: number;
  apiNode: ApiNode;
}

interface SimLink extends SimulationLinkDatum<SimNode> {
  edgeType: string;
}

export function forceDirectedLayout(input: LayoutInput): LayoutOutput {
  const { nodes, edges, groups, canvasWidth, canvasHeight } = input;

  const cx = canvasWidth / 2;
  const cy = canvasHeight / 2;

  // Group centers
  const groupCenters: Record<string, { x: number; y: number }> = { onprem: { x: cx, y: cy } };
  const outerGroups = groups.filter(g => g.id !== 'onprem');
  const radius = Math.min(canvasWidth, canvasHeight) * 0.3;
  outerGroups.forEach((g, i) => {
    const angle = (2 * Math.PI * i) / Math.max(outerGroups.length, 1) - Math.PI / 2;
    groupCenters[g.id] = { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) };
  });

  const simNodes: SimNode[] = nodes.map(n => ({
    id: n.id,
    group: n.group,
    rank: n.rank,
    x: (groupCenters[n.group]?.x || cx) + (Math.random() - 0.5) * 100,
    y: (groupCenters[n.group]?.y || cy) + (Math.random() - 0.5) * 100,
    apiNode: n,
  }));

  const simLinks: SimLink[] = edges.map(e => ({
    source: e.source,
    target: e.target,
    edgeType: e.edge_type,
  }));

  const simulation = forceSimulation<SimNode>(simNodes)
    .force('link', forceLink<SimNode, SimLink>(simLinks).id(d => d.id).distance(150).strength(0.7))
    .force('charge', forceManyBody().strength(-300).distanceMax(400))
    .force('x', forceX<SimNode>(d => groupCenters[d.group]?.x || cx).strength(0.3))
    .force('y', forceY<SimNode>(d => groupCenters[d.group]?.y || cy).strength(0.3))
    .force('collision', forceCollide().radius(60));

  simulation.stop();
  for (let i = 0; i < 300; i++) simulation.tick();

  // Build ReactFlow nodes with group containers
  const rfNodes: Node[] = [];

  // Add group containers
  for (const group of groups) {
    const memberSims = simNodes.filter(sn => sn.group === group.id);
    if (memberSims.length === 0) continue;

    const minX = Math.min(...memberSims.map(s => s.x!)) - 40;
    const minY = Math.min(...memberSims.map(s => s.y!)) - 40;
    const maxX = Math.max(...memberSims.map(s => s.x!)) + 220;
    const maxY = Math.max(...memberSims.map(s => s.y!)) + 130;

    rfNodes.push({
      id: `group-${group.id}`,
      type: 'group',
      position: { x: minX, y: minY },
      data: { label: group.label },
      style: {
        width: maxX - minX,
        height: maxY - minY,
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
    });

    for (const sn of memberSims) {
      rfNodes.push({
        id: sn.id,
        type: 'device',
        parentNode: `group-${group.id}`,
        position: { x: sn.x! - minX, y: sn.y! - minY },
        data: {
          label: sn.apiNode.hostname,
          deviceType: sn.apiNode.device_type,
          ip: '',
          vendor: sn.apiNode.vendor,
          role: '',
          group: sn.apiNode.group,
          status: sn.apiNode.status,
          haRole: sn.apiNode.ha_role || '',
        },
      });
    }
  }

  // Edges
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
