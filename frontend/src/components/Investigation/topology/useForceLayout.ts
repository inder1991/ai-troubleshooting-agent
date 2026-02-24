import { useMemo } from 'react';
import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCenter,
  forceCollide,
  type SimulationLinkDatum,
} from 'd3-force';
import type {
  TopologyNodeDatum,
  TopologyEdgeDatum,
  ResolvedNode,
  ResolvedEdge,
  ForceLayoutResult,
} from './topology.types';
import { NODE_RADIUS, TOPOLOGY_PADDING } from './topology.types';

export function useForceLayout(
  nodes: TopologyNodeDatum[],
  edges: TopologyEdgeDatum[],
  width: number,
  height: number,
): ForceLayoutResult {
  return useMemo(() => {
    if (nodes.length === 0 || width === 0 || height === 0) {
      return { nodes: [], edges: [], width, height };
    }

    // 1. Deep clone nodes (d3 mutates them)
    const simNodes: TopologyNodeDatum[] = nodes.map((n) => ({ ...n }));

    // 2. Deep clone edges with string IDs (d3 will replace with object refs)
    const simEdges: SimulationLinkDatum<TopologyNodeDatum>[] = edges.map((e) => ({
      source: e.source,
      target: e.target,
    }));

    // 3. Create simulation
    const simulation = forceSimulation<TopologyNodeDatum>(simNodes)
      .force(
        'link',
        forceLink<TopologyNodeDatum, SimulationLinkDatum<TopologyNodeDatum>>(simEdges)
          .id((d) => d.id)
          .distance(100)
          .strength(0.8),
      )
      .force('charge', forceManyBody().strength(-300))
      .force('center', forceCenter(width / 2, height / 2))
      .force('collide', forceCollide<TopologyNodeDatum>(NODE_RADIUS + 15));

    // 4. Pin P0 to center
    for (const node of simNodes) {
      if (node.role === 'patient_zero') {
        node.fx = width / 2;
        node.fy = height / 2;
      }
    }

    // 5. Run 300 ticks synchronously (deterministic, no rAF overhead)
    for (let i = 0; i < 300; i++) simulation.tick();
    simulation.stop();

    // 6. Clamp positions within bounds
    const minX = TOPOLOGY_PADDING + NODE_RADIUS;
    const maxX = width - TOPOLOGY_PADDING - NODE_RADIUS;
    const minY = TOPOLOGY_PADDING + NODE_RADIUS;
    const maxY = height - TOPOLOGY_PADDING - NODE_RADIUS;

    const resolvedNodes: ResolvedNode[] = simNodes.map((n) => ({
      id: n.id,
      role: n.role,
      x: Math.max(minX, Math.min(maxX, n.x ?? width / 2)),
      y: Math.max(minY, Math.min(maxY, n.y ?? height / 2)),
      isCrashloop: n.isCrashloop,
      isOomKilled: n.isOomKilled,
    }));

    // 7. Resolve edges: build lookup, compute pathD strings
    const nodeMap = new Map(resolvedNodes.map((n) => [n.id, n]));

    const resolvedEdges: ResolvedEdge[] = edges
      .map((e, i) => {
        const src = nodeMap.get(e.source);
        const tgt = nodeMap.get(e.target);
        if (!src || !tgt) return null;

        // Compute edge direction and offset by node radius
        const dx = tgt.x - src.x;
        const dy = tgt.y - src.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const nx = dx / dist;
        const ny = dy / dist;

        const x1 = src.x + nx * NODE_RADIUS;
        const y1 = src.y + ny * NODE_RADIUS;
        const x2 = tgt.x - nx * NODE_RADIUS;
        const y2 = tgt.y - ny * NODE_RADIUS;

        const pathId = `edge-path-${i}`;
        const pathD = `M ${x1} ${y1} L ${x2} ${y2}`;

        return {
          source: src,
          target: tgt,
          type: e.type,
          evidence: e.evidence,
          pathId,
          pathD,
        } as ResolvedEdge;
      })
      .filter((e): e is ResolvedEdge => e !== null);

    return { nodes: resolvedNodes, edges: resolvedEdges, width, height };
  }, [nodes, edges, width, height]);
}
