import type { StepSpec, MappingExpr, PredicateExpr, StepRunStatus } from '../../../../types';
import type { DagModel, DagNode, DagEdge } from './dagTypes';

export type EdgeStatus = 'pending' | 'active' | 'completed' | 'failed';

/* ── MappingExpr walker ────────────────────────────────────────── */

function collectNodeIdsFromMapping(expr: MappingExpr, out: string[]): void {
  if ('ref' in expr) {
    const r = expr.ref as { from: string; node_id?: string };
    if (r.from === 'node' && r.node_id) {
      out.push(r.node_id);
    }
    return;
  }
  if ('literal' in expr) return;
  // TransformExpr — has op + args
  if ('op' in expr && 'args' in expr) {
    for (const arg of (expr as { args: MappingExpr[] }).args) {
      collectNodeIdsFromMapping(arg, out);
    }
  }
}

/* ── PredicateExpr walker ──────────────────────────────────────── */

function collectNodeIdsFromPredicate(pred: PredicateExpr, out: string[]): void {
  // Runtime convention: `not` may use `args: [inner]` instead of `arg`
  const p = pred as Record<string, unknown>;

  if (p.op === 'and' || p.op === 'or') {
    for (const child of (p.args as PredicateExpr[])) {
      collectNodeIdsFromPredicate(child, out);
    }
    return;
  }

  if (p.op === 'not') {
    // support both runtime `args: [inner]` and type-level `arg`
    if (Array.isArray(p.args) && p.args.length > 0) {
      collectNodeIdsFromPredicate(p.args[0] as PredicateExpr, out);
    } else if (p.arg) {
      collectNodeIdsFromPredicate(p.arg as PredicateExpr, out);
    }
    return;
  }

  // leaf ops: eq, in, exists — may have left/right or args
  if (Array.isArray(p.args)) {
    for (const a of p.args as MappingExpr[]) {
      collectNodeIdsFromMapping(a, out);
    }
  }
  if (p.left) collectNodeIdsFromMapping(p.left as MappingExpr, out);
  if (p.right) collectNodeIdsFromMapping(p.right as MappingExpr, out);
}

/* ── Public API ────────────────────────────────────────────────── */

export function extractDependencies(step: StepSpec): string[] {
  const ids: string[] = [];

  // 1. Input mappings
  for (const expr of Object.values(step.inputs)) {
    collectNodeIdsFromMapping(expr, ids);
  }

  // 2. When predicate
  if (step.when) {
    collectNodeIdsFromPredicate(step.when, ids);
  }

  // 3. Fallback
  if (step.fallback_step_id) {
    ids.push(step.fallback_step_id);
  }

  // deduplicate while preserving order
  return [...new Set(ids)];
}

export function buildDagModel(
  steps: StepSpec[],
  statusMap: Map<string, { status: StepRunStatus; duration_ms?: number; error?: { type?: string; message?: string } }>,
): DagModel {
  const stepIds = new Set(steps.map((s) => s.id));

  const nodes: DagNode[] = steps.map((s) => {
    const info = statusMap.get(s.id);
    return {
      id: s.id,
      agent: s.agent,
      agentVersion: s.agent_version,
      status: info?.status ?? 'pending',
      duration_ms: info?.duration_ms,
      error: info?.error,
    };
  });

  const edges: DagEdge[] = [];
  for (const step of steps) {
    const deps = extractDependencies(step);
    for (const dep of deps) {
      if (stepIds.has(dep)) {
        edges.push({ source: dep, target: step.id });
      }
    }
  }

  return { nodes, edges };
}

export function computeFailurePath(model: DagModel): {
  highlighted: Set<string>;
  dimmed: Set<string>;
} {
  const failedIds = model.nodes.filter((n) => n.status === 'failed').map((n) => n.id);

  if (failedIds.length === 0) {
    return { highlighted: new Set(), dimmed: new Set() };
  }

  // Build adjacency maps
  const parents = new Map<string, string[]>(); // target → sources
  const children = new Map<string, string[]>(); // source → targets
  for (const e of model.edges) {
    if (!parents.has(e.target)) parents.set(e.target, []);
    parents.get(e.target)!.push(e.source);
    if (!children.has(e.source)) children.set(e.source, []);
    children.get(e.source)!.push(e.target);
  }

  const highlighted = new Set<string>();
  const visitedUp = new Set<string>();
  const visitedDown = new Set<string>();

  // Walk upstream (causal chain) from each failed node
  function walkUp(id: string) {
    if (visitedUp.has(id)) return;
    visitedUp.add(id);
    highlighted.add(id);
    for (const p of parents.get(id) ?? []) {
      walkUp(p);
    }
  }

  // Walk downstream (blast radius) from each failed node
  function walkDown(id: string) {
    if (visitedDown.has(id)) return;
    visitedDown.add(id);
    highlighted.add(id);
    for (const c of children.get(id) ?? []) {
      walkDown(c);
    }
  }

  for (const fid of failedIds) {
    walkUp(fid);
    walkDown(fid);
  }

  // Dimmed = all non-highlighted nodes
  const dimmed = new Set<string>();
  for (const n of model.nodes) {
    if (!highlighted.has(n.id)) {
      dimmed.add(n.id);
    }
  }

  return { highlighted, dimmed };
}

export function isEdgeOnFailurePath(edge: DagEdge, highlighted: Set<string>): boolean {
  return highlighted.has(edge.source) && highlighted.has(edge.target);
}

export function edgeStatus(sourceStatus: StepRunStatus): EdgeStatus {
  switch (sourceStatus) {
    case 'running':
      return 'active';
    case 'success':
      return 'completed';
    case 'failed':
      return 'failed';
    default:
      return 'pending';
  }
}
