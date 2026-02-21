import { useMemo } from 'react';
import type { InferredDependency, PatientZero, BlastRadiusData } from '../../../types';

export interface TopologyNode {
  id: string;
  x: number;
  y: number;
  role: 'patient_zero' | 'upstream' | 'downstream' | 'blast_radius' | 'normal';
}

export interface TopologyEdge {
  source: string;
  target: string;
  type: 'error' | 'blast_radius' | 'normal';
}

interface LayoutResult {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  width: number;
  height: number;
}

export function useTopologyLayout(
  dependencies: InferredDependency[],
  patientZero: PatientZero | null,
  blastRadius: BlastRadiusData | null,
): LayoutResult {
  return useMemo(() => {
    const allServices = new Set<string>();
    const edgesRaw: { source: string; target: string }[] = [];

    // Collect services and edges from dependencies
    for (const dep of dependencies) {
      allServices.add(dep.source);
      if (dep.target) {
        allServices.add(dep.target);
        edgesRaw.push({ source: dep.source, target: dep.target });
      }
      if (dep.targets) {
        for (const t of dep.targets) {
          allServices.add(t);
          edgesRaw.push({ source: dep.source, target: t });
        }
      }
    }

    // Add patient zero and blast radius services
    if (patientZero) allServices.add(patientZero.service);
    if (blastRadius) {
      allServices.add(blastRadius.primary_service);
      blastRadius.upstream_affected?.forEach((s) => allServices.add(s));
      blastRadius.downstream_affected?.forEach((s) => allServices.add(s));
    }

    if (allServices.size === 0) {
      return { nodes: [], edges: [], width: 0, height: 0 };
    }

    const pzService = patientZero?.service || blastRadius?.primary_service || '';
    const upstreamSet = new Set(blastRadius?.upstream_affected || []);
    const downstreamSet = new Set(blastRadius?.downstream_affected || []);

    // Categorize services
    const upstream: string[] = [];
    const downstream: string[] = [];
    const normal: string[] = [];

    for (const svc of allServices) {
      if (svc === pzService) continue;
      if (upstreamSet.has(svc)) upstream.push(svc);
      else if (downstreamSet.has(svc)) downstream.push(svc);
      else normal.push(svc);
    }

    // Layout constants
    const nodeSpacingX = 120;
    const rowSpacingY = 80;
    const padding = 40;

    // Position: upstream on top, patient_zero center, downstream below
    const maxCols = Math.max(upstream.length, downstream.length, normal.length, 1);
    const width = maxCols * nodeSpacingX + padding * 2;

    const nodes: TopologyNode[] = [];

    // Row 0: upstream
    const centerX = width / 2;
    upstream.forEach((svc, i) => {
      const offsetX = (i - (upstream.length - 1) / 2) * nodeSpacingX;
      nodes.push({ id: svc, x: centerX + offsetX, y: padding, role: 'upstream' });
    });

    // Row 1: patient zero + normal
    const row1Y = padding + rowSpacingY;
    if (pzService) {
      nodes.push({ id: pzService, x: centerX, y: row1Y, role: 'patient_zero' });
    }
    normal.forEach((svc, i) => {
      const offsetX = ((i + 1) - normal.length / 2) * nodeSpacingX;
      const xPos = pzService ? centerX + offsetX + nodeSpacingX : centerX + (i - (normal.length - 1) / 2) * nodeSpacingX;
      nodes.push({ id: svc, x: xPos, y: row1Y, role: 'normal' });
    });

    // Row 2: downstream
    const row2Y = padding + rowSpacingY * 2;
    downstream.forEach((svc, i) => {
      const offsetX = (i - (downstream.length - 1) / 2) * nodeSpacingX;
      nodes.push({ id: svc, x: centerX + offsetX, y: row2Y, role: 'downstream' });
    });

    const height = row2Y + padding + 20;

    // Build edges with types
    const nodeMap = new Map(nodes.map((n) => [n.id, n]));
    const edges: TopologyEdge[] = [];
    const edgeSeen = new Set<string>();

    for (const e of edgesRaw) {
      const key = `${e.source}->${e.target}`;
      if (edgeSeen.has(key)) continue;
      edgeSeen.add(key);
      if (!nodeMap.has(e.source) || !nodeMap.has(e.target)) continue;

      const isError = e.source === pzService || e.target === pzService;
      const isBlast = upstreamSet.has(e.source) || upstreamSet.has(e.target) ||
                      downstreamSet.has(e.source) || downstreamSet.has(e.target);
      edges.push({
        source: e.source,
        target: e.target,
        type: isError ? 'error' : isBlast ? 'blast_radius' : 'normal',
      });
    }

    return { nodes, edges, width: Math.max(width, 300), height: Math.max(height, 200) };
  }, [dependencies, patientZero, blastRadius]);
}
