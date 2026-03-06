import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import type {
  V4Session, ClusterHealthReport, ClusterDomainReport,
  ClusterDomainKey, TaskEvent, NamespaceWorkload, VerdictEvent,
  FleetNode,
} from '../../types';
import { API_BASE_URL } from '../../services/api';
import { SkeletonLoader } from '../shared/SkeletonLoader';
import { MetricCard } from '../shared/MetricCard';
import ChatDrawer from '../Chat/ChatDrawer';
import LedgerTriggerTab from '../Chat/LedgerTriggerTab';
import ClusterHeader from './ClusterHeader';
import CommandBar from './CommandBar';
import ExecutionDAG from './ExecutionDAG';
import FleetHeatmap from './FleetHeatmap';
import ResourceVelocity from './ResourceVelocity';
import DomainPanel from './DomainPanel';
import VerticalRibbon from './VerticalRibbon';
import RootCauseCard from './RootCauseCard';
import VerdictStack from './VerdictStack';
import RemediationCard from './RemediationCard';
import NeuralPulseSVG from './NeuralPulseSVG';

interface ClusterWarRoomProps {
  session: V4Session;
  events: TaskEvent[];
  wsConnected: boolean;
  phase: string | null;
  confidence: number;
  onGoHome: () => void;
}

const ALL_DOMAINS: ClusterDomainKey[] = ['node', 'ctrl_plane', 'network', 'storage'];

const DOMAIN_LABELS: Record<ClusterDomainKey, string> = {
  ctrl_plane: 'Control Plane',
  node: 'Compute',
  network: 'Network',
  storage: 'Storage',
};

const ClusterWarRoom: React.FC<ClusterWarRoomProps> = ({
  session, events, wsConnected, phase, confidence, onGoHome,
}) => {
  const [findings, setFindings] = useState<ClusterHealthReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedDomain, setExpandedDomain] = useState<ClusterDomainKey>('node');
  const [selectedNode, setSelectedNode] = useState<string | undefined>();

  // ── Data Fetching ──
  const fetchFindings = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v4/session/${session.session_id}/findings`);
      if (!res.ok) {
        setError(`Failed to fetch findings (HTTP ${res.status})`);
        return;
      }
      const data = await res.json();
      // Show data as soon as it's available (including partial/PENDING)
      if (data.platform_health) {
        setFindings(data as ClusterHealthReport);
        setError(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to fetch findings');
    } finally {
      setLoading(false);
    }
  }, [session.session_id]);

  useEffect(() => {
    fetchFindings();
    const interval = setInterval(fetchFindings, 5000);
    return () => clearInterval(interval);
  }, [fetchFindings]);

  // ── Derived Data ──
  const domainReports = useMemo(() => findings?.domain_reports || [], [findings]);
  const expandedReport = useMemo(
    () => domainReports.find(r => r.domain === expandedDomain),
    [domainReports, expandedDomain]
  );
  const collapsedDomains = useMemo(
    () => ALL_DOMAINS.filter(d => d !== expandedDomain),
    [expandedDomain]
  );
  const primaryChain = useMemo(
    () => findings?.causal_chains?.[0],
    [findings]
  );
  const immediateSteps = useMemo(
    () => findings?.remediation?.immediate || [],
    [findings]
  );

  // ── Namespace workloads derived from expanded domain report anomalies ──
  const namespaceWorkloads = useMemo((): NamespaceWorkload[] => {
    if (!expandedReport || expandedReport.anomalies.length === 0) {
      return [{ namespace: 'default', status: 'Healthy', replica_status: 'All healthy', last_deploy: '—' }];
    }

    // Group anomalies by namespace (parse from evidence_ref like "namespace/pod-name")
    const nsMap = new Map<string, NamespaceWorkload>();
    for (const anomaly of expandedReport.anomalies) {
      const ref = anomaly.evidence_ref || '';
      const parts = ref.split('/');
      const ns = parts.length > 1 ? parts[0] : 'default';
      const resourceName = parts.length > 1 ? parts[1] : ref;

      if (!nsMap.has(ns)) {
        nsMap.set(ns, {
          namespace: ns,
          status: anomaly.severity === 'critical' ? 'Critical' : anomaly.severity === 'warning' ? 'Degraded' : 'Healthy',
          replica_status: '',
          last_deploy: '—',
          workloads: [],
        });
      }

      const nsEntry = nsMap.get(ns)!;
      if (nsEntry.workloads) {
        nsEntry.workloads.push({
          name: resourceName,
          kind: 'Pod',
          status: anomaly.description.includes('CrashLoop') ? 'CrashLoopBackOff' : anomaly.severity === 'critical' ? 'Failed' : 'Pending',
          restarts: 0,
          cpu_usage: '',
          memory_usage: '',
          is_trigger: anomaly.severity === 'critical',
          age: '',
        });
      }

      // Escalate namespace status if this anomaly is worse
      if (anomaly.severity === 'critical') nsEntry.status = 'Critical';
      else if (anomaly.severity === 'warning' && nsEntry.status !== 'Critical') nsEntry.status = 'Degraded';
    }

    return Array.from(nsMap.values());
  }, [expandedReport]);

  // ── Fleet nodes derived from node domain report anomalies ──
  const fleetNodes = useMemo((): FleetNode[] => {
    const nodeReport = domainReports.find(r => r.domain === 'node');
    if (!nodeReport || nodeReport.anomalies.length === 0) {
      // Fallback: show a few placeholder nodes
      return Array.from({ length: 3 }, (_, i) => ({
        name: `node-${i}`,
        status: 'healthy' as const,
        cpu_pct: 20 + Math.random() * 30,
        disk_pressure: false,
      }));
    }

    // Build nodes from anomalies
    const nodeMap = new Map<string, FleetNode>();
    for (const anomaly of nodeReport.anomalies) {
      const nodeName = anomaly.evidence_ref || `node-${nodeMap.size}`;
      if (!nodeMap.has(nodeName)) {
        nodeMap.set(nodeName, {
          name: nodeName,
          status: anomaly.severity === 'critical' ? 'critical' : 'healthy',
          cpu_pct: 50,
          disk_pressure: anomaly.description.toLowerCase().includes('disk'),
        });
      } else {
        const node = nodeMap.get(nodeName)!;
        if (anomaly.severity === 'critical') node.status = 'critical';
        if (anomaly.description.toLowerCase().includes('disk')) node.disk_pressure = true;
      }
    }

    return Array.from(nodeMap.values());
  }, [domainReports]);

  const mockVerdictEvents = useMemo((): VerdictEvent[] => {
    if (!primaryChain) return [];
    return [
      { timestamp: '14:02:11', severity: 'FATAL', message: primaryChain.root_cause.description },
      ...primaryChain.cascading_effects.map(e => ({
        timestamp: '—',
        severity: 'WARN' as const,
        message: e.description,
        domain: e.domain as ClusterDomainKey,
      })),
    ];
  }, [primaryChain]);

  // ── Auto-expand most affected domain (only on initial load) ──
  const hasAutoExpanded = useRef(false);

  useEffect(() => {
    if (hasAutoExpanded.current) return;
    if (domainReports.length === 0) return;
    const worst = domainReports.reduce((prev, curr) =>
      curr.anomalies.length > prev.anomalies.length ? curr : prev
    , domainReports[0]);
    if (worst.anomalies.length > 0) {
      setExpandedDomain(worst.domain as ClusterDomainKey);
      hasAutoExpanded.current = true;
    }
  }, [domainReports]);

  return (
    <div className="flex flex-col h-full overflow-hidden bg-[#0f2023] crt-scanlines relative font-sans text-slate-300">
      <ClusterHeader
        sessionId={session.session_id}
        confidence={confidence}
        platformHealth={findings?.platform_health || ''}
        wsConnected={wsConnected}
        onGoHome={onGoHome}
      />

      {/* Domain Health Ribbon */}
      {findings && (
        <div className="grid grid-cols-4 gap-3 px-6 py-3 border-b border-[#1f3b42] shrink-0">
          {ALL_DOMAINS.map(domain => {
            const report = domainReports.find(r => r.domain === domain);
            const anomalyCount = report?.anomalies.length || 0;
            const status = report?.status || 'PENDING';
            const isHealthy = status === 'SUCCESS' && anomalyCount === 0;
            return (
              <MetricCard
                key={domain}
                title={DOMAIN_LABELS[domain]}
                value={isHealthy ? 'Healthy' : `${anomalyCount} issues`}
                trendValue={status === 'RUNNING' ? 'Scanning...' : status}
                trendDirection={isHealthy ? 'down' : anomalyCount > 0 ? 'up' : 'neutral'}
                trendType={isHealthy ? 'good' : anomalyCount > 0 ? 'bad' : 'neutral'}
                sparklineData={[anomalyCount, anomalyCount]}
              />
            );
          })}
        </div>
      )}

      {/* Error banner */}
      {error && (
        <div className="mx-6 mt-2 p-3 rounded-lg border border-red-500/30 bg-red-500/10 flex items-center justify-between">
          <span className="text-sm text-red-400">{error}</span>
          <button onClick={fetchFindings} className="text-xs text-red-300 hover:text-white px-3 py-1 rounded border border-red-500/30 hover:bg-red-500/20 transition-colors">
            Retry
          </button>
        </div>
      )}

      {/* Main War Room Grid */}
      <main className="flex-1 grid grid-cols-12 overflow-hidden relative">
        {loading && !findings && !error && (
          <>
            {/* Left column skeleton */}
            <section className="col-span-3 border-r border-[#1f3b42] p-4 flex flex-col gap-4">
              <SkeletonLoader type="card" height="h-48" />
              <SkeletonLoader type="card" height="h-28" />
              <SkeletonLoader type="card" height="h-24" />
            </section>
            {/* Center column skeleton */}
            <section className="col-span-5 border-r border-[#1f3b42] p-4 flex flex-col gap-3">
              <SkeletonLoader type="row" />
              <SkeletonLoader type="card" height="h-64" />
              <SkeletonLoader type="row" />
              <SkeletonLoader type="row" />
            </section>
            {/* Right column skeleton */}
            <section className="col-span-4 p-4 flex flex-col gap-4">
              <SkeletonLoader type="card" height="h-36" />
              <SkeletonLoader type="card" height="h-48" />
              <SkeletonLoader type="card" height="h-32" />
            </section>
          </>
        )}

        {(!loading || findings) && (
          <>
            <NeuralPulseSVG hasRootCause={!!primaryChain} />

            {/* ── LEFT COLUMN (col-3) ── */}
            <section className="col-span-3 border-r border-[#1f3b42] bg-[#0f2023]/50 p-4 flex flex-col gap-4 overflow-hidden z-10">
              <ExecutionDAG domainReports={domainReports} phase={phase || 'pre_flight'} />
              <FleetHeatmap nodes={fleetNodes} selectedNode={selectedNode} onSelectNode={setSelectedNode} />
              <ResourceVelocity />
            </section>

            {/* ── CENTER COLUMN (col-5) ── */}
            <section className="col-span-5 flex h-full bg-[#0f2023] overflow-hidden relative border-r border-[#1f3b42]">
              <DomainPanel domain={expandedDomain} report={expandedReport} namespaces={namespaceWorkloads} />
              <div className="w-[40px] flex flex-col bg-[#152a2f] border-l border-[#1f3b42] shrink-0 z-10">
                {collapsedDomains.map(d => (
                  <VerticalRibbon
                    key={d}
                    domain={d}
                    report={domainReports.find(r => r.domain === d)}
                    onClick={() => setExpandedDomain(d)}
                  />
                ))}
              </div>
            </section>

            {/* ── RIGHT COLUMN (col-4) ── */}
            <section className="col-span-4 bg-[#0f2023]/50 p-4 flex flex-col gap-4 overflow-hidden relative z-10">
              <RootCauseCard chain={primaryChain} confidence={confidence} />
              <VerdictStack events={mockVerdictEvents} />
              <RemediationCard steps={immediateSteps} blastRadius={findings?.blast_radius} />
            </section>
          </>
        )}
      </main>

      <CommandBar />
      <ChatDrawer />
      <LedgerTriggerTab />
    </div>
  );
};

export default ClusterWarRoom;
