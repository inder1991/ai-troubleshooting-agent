import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import type {
  V4Session, ClusterHealthReport, ClusterDomainReport,
  ClusterDomainKey, TaskEvent, NamespaceWorkload, VerdictEvent,
  FleetNode,
} from '../../types';
import { API_BASE_URL } from '../../services/api';
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
      if (data.platform_health && data.platform_health !== 'PENDING') {
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

  // ── Mock Data (until backend provides namespace-level detail) ──
  const mockNamespaces = useMemo((): NamespaceWorkload[] => {
    if (!expandedReport || expandedReport.anomalies.length === 0) {
      return [{ namespace: 'default', status: 'Healthy', replica_status: 'All healthy', last_deploy: '—' }];
    }
    return [
      {
        namespace: 'checkout-api',
        status: 'Critical',
        workloads: [{
          name: expandedReport.anomalies[0]?.evidence_ref || 'pod-unknown',
          kind: 'Deployment',
          status: 'CrashLoopBackOff',
          restarts: 14,
          cpu_usage: '92%',
          memory_usage: '450Mi',
          is_trigger: true,
          age: '23s ago',
        }],
      },
      { namespace: 'payment-gateway', status: 'Healthy', replica_status: 'Replicas: 3/3', last_deploy: '2h ago' },
      { namespace: 'auth-service', status: 'Healthy', replica_status: 'Replicas: 5/5', last_deploy: '1d ago' },
    ];
  }, [expandedReport]);

  const mockFleetNodes = useMemo((): FleetNode[] => {
    const count = 120;
    const criticalIndices = [12, 45, 87, 88, 102];
    return Array.from({ length: count }, (_, i) => ({
      name: `node-${i}`,
      status: criticalIndices.includes(i) ? 'critical' as const : 'healthy' as const,
      cpu_pct: criticalIndices.includes(i) ? 94 : Math.random() * 40 + 10,
      disk_pressure: i === 87,
    }));
  }, []);

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
          <div className="col-span-12 flex items-center justify-center">
            <div className="text-center">
              <span className="material-symbols-outlined animate-spin text-4xl text-[#13b6ec] mb-4 block" style={{ fontFamily: 'Material Symbols Outlined' }}>progress_activity</span>
              <p className="text-slate-500 text-sm">Initializing cluster diagnostics...</p>
            </div>
          </div>
        )}

        {(!loading || findings) && (
          <>
            <NeuralPulseSVG hasRootCause={!!primaryChain} />

            {/* ── LEFT COLUMN (col-3) ── */}
            <section className="col-span-3 border-r border-[#1f3b42] bg-[#0f2023]/50 p-4 flex flex-col gap-4 overflow-hidden z-10">
              <ExecutionDAG domainReports={domainReports} phase={phase || 'pre_flight'} />
              <FleetHeatmap nodes={mockFleetNodes} selectedNode={selectedNode} onSelectNode={setSelectedNode} />
              <ResourceVelocity />
            </section>

            {/* ── CENTER COLUMN (col-5) ── */}
            <section className="col-span-5 flex h-full bg-[#0f2023] overflow-hidden relative border-r border-[#1f3b42]">
              <DomainPanel domain={expandedDomain} report={expandedReport} namespaces={mockNamespaces} />
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
