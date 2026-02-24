import { useMemo } from 'react';
import type { V4Findings } from '../../../types';
import type { TopologyNodeDatum, TopologyEdgeDatum, NodeRole } from './topology.types';

interface TopologyData {
  nodes: TopologyNodeDatum[];
  edges: TopologyEdgeDatum[];
  causalPath: string[];
}

export function useTopologyData(findings: V4Findings | null): TopologyData {
  return useMemo(() => {
    if (!findings) return { nodes: [], edges: [], causalPath: [] };

    const dependencies = findings.inferred_dependencies || [];
    const patientZero = findings.patient_zero;
    const blastRadius = findings.blast_radius;
    const podStatuses = findings.pod_statuses || [];

    // 1. Collect all services
    const allServices = new Set<string>();
    const edgesRaw: { source: string; target: string; evidence?: string }[] = [];

    for (const dep of dependencies) {
      allServices.add(dep.source);
      if (dep.target) {
        allServices.add(dep.target);
        edgesRaw.push({ source: dep.source, target: dep.target, evidence: dep.evidence });
      }
      if (dep.targets) {
        for (const t of dep.targets) {
          allServices.add(t);
          edgesRaw.push({ source: dep.source, target: t, evidence: dep.evidence });
        }
      }
    }

    if (patientZero) allServices.add(patientZero.service);
    if (blastRadius) {
      allServices.add(blastRadius.primary_service);
      blastRadius.upstream_affected?.forEach((s) => allServices.add(s));
      blastRadius.downstream_affected?.forEach((s) => allServices.add(s));
    }

    if (allServices.size === 0) return { nodes: [], edges: [], causalPath: [] };

    // 2. Assign roles
    const pzService = patientZero?.service || blastRadius?.primary_service || '';
    const upstreamSet = new Set(blastRadius?.upstream_affected || []);
    const downstreamSet = new Set(blastRadius?.downstream_affected || []);

    const roleOf = (svc: string): NodeRole => {
      if (svc === pzService) return 'patient_zero';
      if (upstreamSet.has(svc)) return 'upstream';
      if (downstreamSet.has(svc)) return 'downstream';
      return 'normal';
    };

    // 3. Enrich with pod health
    const crashloopSet = new Set<string>();
    const oomSet = new Set<string>();
    for (const pod of podStatuses) {
      for (const svc of allServices) {
        if (pod.pod_name.startsWith(svc) || pod.pod_name.includes(svc)) {
          if (pod.crash_loop) crashloopSet.add(svc);
          if (pod.oom_killed) oomSet.add(svc);
        }
      }
    }
    // Fallback: if pods are crashlooping but no match found, attribute to P0
    const hasCrashloop = podStatuses.some((p) => p.crash_loop || p.oom_killed);
    if (hasCrashloop && crashloopSet.size === 0 && oomSet.size === 0 && pzService) {
      if (podStatuses.some((p) => p.crash_loop)) crashloopSet.add(pzService);
      if (podStatuses.some((p) => p.oom_killed)) oomSet.add(pzService);
    }

    // Build nodes
    const nodes: TopologyNodeDatum[] = Array.from(allServices).map((id) => ({
      id,
      role: roleOf(id),
      isCrashloop: crashloopSet.has(id),
      isOomKilled: oomSet.has(id),
    }));

    // 4. Build edges (deduplicated)
    const edgeSeen = new Set<string>();
    const serviceSet = allServices;
    const edges: TopologyEdgeDatum[] = [];

    for (const e of edgesRaw) {
      const key = `${e.source}->${e.target}`;
      if (edgeSeen.has(key)) continue;
      edgeSeen.add(key);
      if (!serviceSet.has(e.source) || !serviceSet.has(e.target)) continue;

      const isError = e.source === pzService || e.target === pzService;
      const isBlast =
        upstreamSet.has(e.source) || upstreamSet.has(e.target) ||
        downstreamSet.has(e.source) || downstreamSet.has(e.target);

      edges.push({
        source: e.source,
        target: e.target,
        type: isError ? 'error' : isBlast ? 'blast_radius' : 'normal',
        evidence: e.evidence,
      });
    }

    // 5. Derive causal path: BFS from P0 through error/blast edges to downstream
    const causalPath: string[] = [];
    if (pzService) {
      const adjacency = new Map<string, string[]>();
      for (const edge of edges) {
        if (edge.type === 'error' || edge.type === 'blast_radius') {
          if (!adjacency.has(edge.source)) adjacency.set(edge.source, []);
          adjacency.get(edge.source)!.push(edge.target);
        }
      }

      const visited = new Set<string>();
      const queue = [pzService];
      visited.add(pzService);
      while (queue.length > 0) {
        const current = queue.shift()!;
        causalPath.push(current);
        for (const neighbor of adjacency.get(current) || []) {
          if (!visited.has(neighbor)) {
            visited.add(neighbor);
            queue.push(neighbor);
          }
        }
      }

      // Mark edges in causal path as causal_path type
      const causalSet = new Set(causalPath);
      for (const edge of edges) {
        if (causalSet.has(edge.source) && causalSet.has(edge.target) &&
            (edge.type === 'error' || edge.type === 'blast_radius')) {
          edge.type = 'causal_path';
        }
      }
    }

    return { nodes, edges, causalPath };
  }, [
    findings?.inferred_dependencies,
    findings?.patient_zero,
    findings?.blast_radius,
    findings?.pod_statuses,
  ]);
}
