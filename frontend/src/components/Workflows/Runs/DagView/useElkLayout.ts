import { useState, useEffect, useMemo } from 'react';
import ELK from 'elkjs/lib/elk.bundled.js';
import type { DagModel, PositionedDag, PositionedNode, PositionedEdge } from './dagTypes';

const NODE_WIDTH = 200;
const NODE_HEIGHT = 80;

let _elk: InstanceType<typeof ELK> | null = null;
function getElk() {
  if (!_elk) _elk = new ELK();
  return _elk;
}

/**
 * Compute a structural key from node IDs + edge pairs.
 * Status changes do NOT affect this key.
 */
export function structuralKey(dag: DagModel): string {
  const nodeIds = dag.nodes.map((n) => n.id).sort().join(',');
  const edgePairs = dag.edges
    .map((e) => `${e.source}->${e.target}`)
    .sort()
    .join(',');
  return `${nodeIds}|${edgePairs}`;
}

export function useElkLayout(dag: DagModel): {
  layout: PositionedDag | null;
  loading: boolean;
  error: Error | null;
} {
  const key = useMemo(() => structuralKey(dag), [dag]);

  const [layout, setLayout] = useState<PositionedDag | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    const elkGraph = {
      id: 'root',
      layoutOptions: {
        'elk.algorithm': 'layered',
        'elk.direction': 'DOWN',
        'elk.edgeRouting': 'ORTHOGONAL',
        'elk.layered.spacing.nodeNodeBetweenLayers': '60',
      },
      children: dag.nodes.map((n) => ({
        id: n.id,
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
      })),
      edges: dag.edges.map((e) => ({
        id: `${e.source}->${e.target}`,
        sources: [e.source],
        targets: [e.target],
      })),
    };

    getElk()
      .layout(elkGraph)
      .then((result) => {
        if (cancelled) return;

        const positionedNodes: PositionedNode[] = (result.children ?? []).map((child) => {
          const original = dag.nodes.find((n) => n.id === child.id)!;
          return {
            ...original,
            x: child.x ?? 0,
            y: child.y ?? 0,
            width: child.width ?? NODE_WIDTH,
            height: child.height ?? NODE_HEIGHT,
          };
        });

        const positionedEdges: PositionedEdge[] = (result.edges ?? []).map((elkEdge) => {
          const source = (elkEdge as any).sources?.[0] ?? '';
          const target = (elkEdge as any).targets?.[0] ?? '';
          const points: Array<{ x: number; y: number }> = [];

          const sections = (elkEdge as any).sections ?? [];
          for (const section of sections) {
            if (section.startPoint) points.push(section.startPoint);
            if (section.bendPoints) points.push(...section.bendPoints);
            if (section.endPoint) points.push(section.endPoint);
          }

          return { source, target, points };
        });

        setLayout({
          nodes: positionedNodes,
          edges: positionedEdges,
          width: result.width ?? 0,
          height: result.height ?? 0,
        });
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err : new Error(String(err)));
        setLayout(null);
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [key]); // Only re-run when structural key changes

  return { layout, loading, error };
}
