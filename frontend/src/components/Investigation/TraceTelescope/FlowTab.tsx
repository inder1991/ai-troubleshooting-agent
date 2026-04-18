import React, { useMemo } from 'react';
import type { SpanInfo } from '../../../types';

interface FlowTabProps {
  spans: SpanInfo[];
  dependencyGraph: Record<string, string[]>;
  servicesInChain: string[];
  failureService?: string;
  hotServices: string[];
  bottleneckOperations: Array<[string, string]>;
  cascadePath: string[];
  onSelectService: (service: string | null) => void;
  selectedServiceFilter: string | null;
}

interface LayoutNode {
  service: string;
  x: number;
  y: number;
  spanCount: number;
  hasFailure: boolean;
  isHot: boolean;
  onCascade: boolean;
}

/**
 * Service-dependency graph — hand-layouted (no dagre/elk dependency for v1
 * to keep the bundle tight; can swap in later if graphs get complex).
 *
 * Layout strategy: BFS from root services → columns by depth. Within each
 * column, nodes are distributed vertically. Edges drawn as bezier curves.
 * Failure path highlighted in red; hot services in amber.
 */
export default function FlowTab(props: FlowTabProps) {
  const { spans, dependencyGraph, servicesInChain, failureService, hotServices,
          bottleneckOperations, cascadePath, onSelectService, selectedServiceFilter } = props;

  const { nodes, edges } = useMemo(
    () => layoutGraph(spans, dependencyGraph, servicesInChain, failureService, hotServices, cascadePath),
    [spans, dependencyGraph, servicesInChain, failureService, hotServices, cascadePath],
  );

  const bottleneckServices = useMemo(
    () => new Set(bottleneckOperations.map(([s]) => s)),
    [bottleneckOperations],
  );

  if (!nodes.length) {
    return (
      <div className="flex items-center justify-center h-full text-wr-text-muted">
        <p>No service dependency data available for this trace.</p>
      </div>
    );
  }

  const width = Math.max(...nodes.map((n) => n.x)) + 200;
  const height = Math.max(...nodes.map((n) => n.y)) + 120;

  return (
    <div className="relative w-full h-full overflow-auto bg-wr-bg-deep">
      <svg
        width={width}
        height={height}
        className="block"
        role="img"
        aria-label="Service dependency graph"
      >
        {/* Edges first so nodes render on top */}
        <g data-testid="flow-edges">
          {edges.map((e, i) => {
            const dx = (e.to.x - e.from.x) * 0.5;
            const d = `M${e.from.x + 80},${e.from.y + 20} C${e.from.x + 80 + dx},${e.from.y + 20} ${e.to.x - dx},${e.to.y + 20} ${e.to.x},${e.to.y + 20}`;
            return (
              <path
                key={i}
                d={d}
                fill="none"
                stroke={e.onCascade ? 'rgba(239,68,68,0.55)' : 'rgba(148,163,184,0.3)'}
                strokeWidth={e.onCascade ? 2.5 : 1.5}
                strokeLinecap="round"
              />
            );
          })}
        </g>

        {/* Nodes */}
        <g data-testid="flow-nodes">
          {nodes.map((n) => {
            const baseFill = n.hasFailure
              ? 'rgba(239,68,68,0.18)'
              : n.isHot
              ? 'rgba(251,146,60,0.18)'
              : n.onCascade
              ? 'rgba(224,159,62,0.18)'
              : 'rgba(30,30,35,0.85)';
            const stroke = n.hasFailure
              ? '#ef4444'
              : n.isHot
              ? '#fb923c'
              : n.onCascade
              ? '#e09f3e'
              : 'rgba(148,163,184,0.45)';
            const isSelected = selectedServiceFilter === n.service;
            const hasBottleneck = bottleneckServices.has(n.service);
            return (
              <g
                key={n.service}
                transform={`translate(${n.x}, ${n.y})`}
                className="cursor-pointer"
                onClick={() => onSelectService(isSelected ? null : n.service)}
                data-testid={`flow-node-${n.service}`}
              >
                <rect
                  x={0}
                  y={0}
                  width={160}
                  height={40}
                  rx={6}
                  fill={baseFill}
                  stroke={stroke}
                  strokeWidth={isSelected ? 2.5 : 1.5}
                />
                <text
                  x={12}
                  y={17}
                  fontSize={12}
                  fontWeight={600}
                  fill="rgba(232,224,212,0.92)"
                >
                  {truncate(n.service, 20)}
                </text>
                <text
                  x={12}
                  y={32}
                  fontSize={10}
                  fill="rgba(148,163,184,0.85)"
                >
                  {n.spanCount} span{n.spanCount === 1 ? '' : 's'}
                  {hasBottleneck ? ' · bottleneck' : ''}
                </text>
                {n.hasFailure && (
                  <circle cx={150} cy={8} r={5} fill="#ef4444" data-testid="failure-dot" />
                )}
                {n.isHot && !n.hasFailure && (
                  <circle cx={150} cy={8} r={4} fill="#fb923c" />
                )}
              </g>
            );
          })}
        </g>
      </svg>

      {cascadePath.length > 0 && (
        <div className="absolute top-3 left-3 bg-wr-bg/90 border border-wr-border rounded-md px-3 py-2 text-body-xs">
          <span className="font-semibold text-wr-text mb-1 block">Cascade path</span>
          <span className="text-wr-text-muted">{cascadePath.join(' → ')}</span>
        </div>
      )}
    </div>
  );
}

// ── layout ──────────────────────────────────────────────────────────────

function layoutGraph(
  spans: SpanInfo[],
  depGraph: Record<string, string[]>,
  servicesInChain: string[],
  failureService: string | undefined,
  hotServices: string[],
  cascadePath: string[],
): { nodes: LayoutNode[]; edges: { from: LayoutNode; to: LayoutNode; onCascade: boolean }[] } {
  const services = Array.from(new Set([
    ...servicesInChain,
    ...Object.keys(depGraph),
    ...Object.values(depGraph).flat(),
    ...spans.map((s) => s.service_name || s.service),
  ]));

  // Span count per service (for node sizing info).
  const counts: Record<string, number> = {};
  for (const s of spans) {
    const name = s.service_name || s.service;
    counts[name] = (counts[name] || 0) + 1;
  }

  // Compute depth via BFS from root services (ones nobody depends on).
  const incoming: Record<string, string[]> = {};
  for (const [from, tos] of Object.entries(depGraph)) {
    for (const to of tos) incoming[to] = [...(incoming[to] || []), from];
  }
  const depth: Record<string, number> = {};
  const queue = services.filter((s) => !incoming[s] || incoming[s].length === 0);
  queue.forEach((s) => (depth[s] = 0));
  while (queue.length) {
    const svc = queue.shift()!;
    for (const child of depGraph[svc] || []) {
      if (depth[child] === undefined || depth[child] < depth[svc] + 1) {
        depth[child] = depth[svc] + 1;
        queue.push(child);
      }
    }
  }
  for (const s of services) if (depth[s] === undefined) depth[s] = 0;

  // Group by depth column.
  const byDepth: Record<number, string[]> = {};
  for (const s of services) {
    const d = depth[s];
    byDepth[d] = [...(byDepth[d] || []), s];
  }

  const X_GAP = 220;
  const Y_GAP = 70;
  const Y_OFFSET = 30;
  const nodesByService: Record<string, LayoutNode> = {};
  const cascadeSet = new Set(cascadePath);
  const hotSet = new Set(hotServices);

  for (const [depthStr, svcs] of Object.entries(byDepth)) {
    const d = Number(depthStr);
    svcs.forEach((svc, i) => {
      nodesByService[svc] = {
        service: svc,
        x: 40 + d * X_GAP,
        y: Y_OFFSET + i * Y_GAP,
        spanCount: counts[svc] || 0,
        hasFailure: svc === failureService,
        isHot: hotSet.has(svc) && svc !== failureService,
        onCascade: cascadeSet.has(svc),
      };
    });
  }

  const edges: { from: LayoutNode; to: LayoutNode; onCascade: boolean }[] = [];
  for (const [from, tos] of Object.entries(depGraph)) {
    const fromNode = nodesByService[from];
    if (!fromNode) continue;
    for (const to of tos) {
      const toNode = nodesByService[to];
      if (!toNode) continue;
      const onCasc = cascadeSet.has(from) && cascadeSet.has(to);
      edges.push({ from: fromNode, to: toNode, onCascade: onCasc });
    }
  }

  return { nodes: Object.values(nodesByService), edges };
}

function truncate(s: string, n: number): string {
  return s.length <= n ? s : s.slice(0, n - 1) + '…';
}
