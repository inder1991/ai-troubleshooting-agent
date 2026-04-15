import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import type {
  V4Session, ClusterHealthReport, ClusterDomainReport,
  ClusterDomainKey, TaskEvent, NamespaceWorkload,
  FleetNode,
} from '../../types';
import { API_BASE_URL } from '../../services/api';
import { SkeletonLoader } from '../shared/SkeletonLoader';
import ChatDrawer from '../Chat/ChatDrawer';
import LedgerTriggerTab from '../Chat/LedgerTriggerTab';
import ClusterHeader from './ClusterHeader';
import CommandBar from './CommandBar';
import ExecutionProgress from './ExecutionProgress';
import FleetHeatmap from './FleetHeatmap';
import DomainPanel from './DomainPanel';
import VerticalRibbon from './VerticalRibbon';
import IssuePriorityPanel from './IssuePriorityPanel';
import LifecycleSummaryStrip from './LifecycleSummaryStrip';
import HypothesisCard from './HypothesisCard';
import RemediationCard from './RemediationCard';
import EventLogViewer from './EventLogViewer';
import ScanDiff from './ScanDiff';
import UncorrelatedFindings from './UncorrelatedFindings';

interface ClusterWarRoomProps {
  session: V4Session;
  events: TaskEvent[];
  wsConnected: boolean;
  phase: string | null;
  confidence: number;
  onGoHome: () => void;
}

const ALL_DOMAINS: ClusterDomainKey[] = ['node', 'ctrl_plane', 'network', 'storage', 'rbac'];

const DOMAIN_LABELS: Record<ClusterDomainKey, string> = {
  ctrl_plane: 'Control Plane',
  node: 'Compute',
  network: 'Network',
  storage: 'Storage',
  rbac: 'RBAC',
};

const ClusterWarRoom: React.FC<ClusterWarRoomProps> = ({
  session, events, wsConnected, phase, confidence, onGoHome,
}) => {
  const [findings, setFindings] = useState<ClusterHealthReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedDomain, setExpandedDomain] = useState<ClusterDomainKey>('node');
  const [selectedNode, setSelectedNode] = useState<string | undefined>();
  const [budgetPct, setBudgetPct] = useState<number | null>(null);
  const [centerView, setCenterView] = useState<'priority' | ClusterDomainKey>('priority');

  // ── Data Fetching ──
  const fetchFindings = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v4/session/${session.session_id}/findings`);
      if (!res.ok) {
        setError(`Failed to fetch findings (HTTP ${res.status})`);
        return;
      }
      const data = await res.json();
      // Show data as soon as domain agents produce data, not just after synthesis
      if (data.platform_health || data.domain_reports?.length > 0 || data.diagnostic_issues?.length > 0) {
        setFindings(data as ClusterHealthReport);
        setError(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to fetch findings');
    } finally {
      setLoading(false);
    }
  }, [session.session_id]);

  // ── LLM Budget Polling ──
  const fetchBudget = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v4/session/${session.session_id}/llm-summary`);
      if (res.ok) {
        const data = await res.json();
        if (data.llm_summary) {
          setBudgetPct(Math.round(data.llm_summary.budget_used_pct * 100));
        }
      }
    } catch { /* ignore */ }
  }, [session.session_id]);

  // ── Debounced fetch (throttle WebSocket-triggered rapid fetches) ──
  const lastFetchRef = useRef(0);
  const throttledFetch = useCallback(() => {
    const now = Date.now();
    if (now - lastFetchRef.current < 2000) return;
    lastFetchRef.current = now;
    fetchFindings();
    fetchBudget();
  }, [fetchFindings, fetchBudget]);

  useEffect(() => {
    throttledFetch();
    const interval = setInterval(throttledFetch, 5000);
    return () => clearInterval(interval);
  }, [throttledFetch]);

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
  const uncorrelatedFindings = useMemo(
    () => findings?.uncorrelated_findings || [],
    [findings]
  );
  const longTermSteps = useMemo(
    () => findings?.remediation?.long_term || [],
    [findings]
  );
  const diagnosticIssues = useMemo(
    () => findings?.diagnostic_issues || [],
    [findings]
  );
  const symptomMap = useMemo(
    () => findings?.symptom_map || {},
    [findings]
  );
  const causalChains = useMemo(
    () => findings?.causal_chains || [],
    [findings]
  );
  const rankedHypotheses = useMemo(
    () => findings?.ranked_hypotheses || [],
    [findings]
  );

  const allAgentsFailed = useMemo(() => {
    if (domainReports.length === 0) return false;
    return domainReports.every(r => r.status === 'FAILED' || r.status === 'SKIPPED');
  }, [domainReports]);

  // ── Truncation warnings ──
  const truncationWarnings = useMemo(() => {
    const warnings: string[] = [];
    for (const report of domainReports) {
      const flags = report.truncation_flags || {};
      for (const [key, value] of Object.entries(flags)) {
        if (!value) continue;
        const domainLabel = report.domain.replace('_', ' ');
        if (typeof value === 'number' && value > 0) {
          warnings.push(`${domainLabel}: ${value} ${key.replace('_dropped', '').replace('_', ' ')} items dropped`);
        } else if (value === true) {
          warnings.push(`${domainLabel}: ${key} data was truncated`);
        }
      }
    }
    return warnings;
  }, [domainReports]);

  // ── Scan diff delta (for guard mode) ──
  const scanDelta = useMemo(() => {
    return (findings as unknown as Record<string, unknown>)?.scan_delta as {
      new_risks: string[];
      resolved_risks: string[];
      worsened: string[];
      improved: string[];
      previous_scan_id?: string;
      previous_scanned_at?: string;
    } | undefined;
  }, [findings]);

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
          status: anomaly.severity === 'high' ? 'Critical' : anomaly.severity === 'medium' ? 'Degraded' : 'Healthy',
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
          status: anomaly.description.includes('CrashLoop') ? 'CrashLoopBackOff' : anomaly.severity === 'high' ? 'Failed' : 'Pending',
          restarts: 0,
          cpu_usage: '',
          memory_usage: '',
          is_trigger: anomaly.severity === 'high',
          age: '',
        });
      }

      // Escalate namespace status if this anomaly is worse
      if (anomaly.severity === 'high') nsEntry.status = 'Critical';
      else if (anomaly.severity === 'medium' && nsEntry.status !== 'Critical') nsEntry.status = 'Degraded';
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
          status: anomaly.severity === 'high' ? 'critical' : 'healthy',
          cpu_pct: 50,
          disk_pressure: anomaly.description.toLowerCase().includes('disk'),
        });
      } else {
        const node = nodeMap.get(nodeName)!;
        if (anomaly.severity === 'high') node.status = 'critical';
        if (anomaly.description.toLowerCase().includes('disk')) node.disk_pressure = true;
      }
    }

    return Array.from(nodeMap.values());
  }, [domainReports]);

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

  // ── Center view: resolve the domain report when viewing a domain ──
  const centerDomainReport = useMemo(() => {
    if (centerView === 'priority') return undefined;
    return domainReports.find(r => r.domain === centerView);
  }, [centerView, domainReports]);

  const centerNamespaceWorkloads = useMemo((): NamespaceWorkload[] => {
    if (centerView === 'priority' || !centerDomainReport) return [];
    if (centerDomainReport.anomalies.length === 0) {
      return [{ namespace: 'default', status: 'Healthy', replica_status: 'All healthy', last_deploy: '—' }];
    }
    const nsMap = new Map<string, NamespaceWorkload>();
    for (const anomaly of centerDomainReport.anomalies) {
      const ref = anomaly.evidence_ref || '';
      const parts = ref.split('/');
      const ns = parts.length > 1 ? parts[0] : 'default';
      const resourceName = parts.length > 1 ? parts[1] : ref;
      if (!nsMap.has(ns)) {
        nsMap.set(ns, {
          namespace: ns,
          status: anomaly.severity === 'high' ? 'Critical' : anomaly.severity === 'medium' ? 'Degraded' : 'Healthy',
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
          status: anomaly.severity === 'high' ? 'Failed' : 'Pending',
          restarts: 0,
          cpu_usage: '',
          memory_usage: '',
          is_trigger: anomaly.severity === 'high',
          age: '',
        });
      }
      if (anomaly.severity === 'high') nsEntry.status = 'Critical';
      else if (anomaly.severity === 'medium' && nsEntry.status !== 'Critical') nsEntry.status = 'Degraded';
    }
    return Array.from(nsMap.values());
  }, [centerView, centerDomainReport]);

  return (
    <div className="warroom-shell font-sans text-slate-300">
      <ClusterHeader
        sessionId={session.session_id}
        confidence={confidence}
        platformHealth={findings?.platform_health || ''}
        wsConnected={wsConnected}
        onGoHome={onGoHome}
        phase={phase || undefined}
      />

      {/* Lifecycle Summary Strip (replaces Domain Health Ribbon) */}
      {findings && (
        <LifecycleSummaryStrip
          diagnosticIssues={diagnosticIssues}
          domainReports={domainReports}
          dataCompleteness={findings.data_completeness}
          scopeCoverage={findings.scope_coverage}
          phase={phase || 'pre_flight'}
        />
      )}

      {/* Error banner */}
      {error && (
        <div className="mx-6 mt-2 p-3 rounded-lg border border-wr-severity-high/30 bg-wr-severity-high/10 flex items-center justify-between">
          <span className="text-sm text-red-400">{error}</span>
          <button onClick={fetchFindings} className="text-xs text-red-300 hover:text-white px-3 py-1 rounded border border-wr-severity-high/30 hover:bg-wr-severity-high/20 transition-colors">
            Retry
          </button>
        </div>
      )}

      {/* Truncation warning banner */}
      {truncationWarnings.length > 0 && (
        <div className="mx-6 mt-2 px-3 py-2 rounded border border-wr-severity-medium/30 bg-amber-500/5 flex items-center gap-2">
          <span className="material-symbols-outlined text-amber-500 text-[16px]">warning</span>
          <span className="text-xs text-amber-400">
            Analysis may be incomplete: {truncationWarnings.join('. ')}
          </span>
        </div>
      )}

      {/* LLM budget warning banner */}
      {budgetPct !== null && budgetPct > 80 && (
        <div className="mx-6 mt-2 px-3 py-2 rounded border border-wr-severity-medium/30 bg-wr-severity-medium/10 flex items-center gap-2">
          <span className="material-symbols-outlined text-amber-500 text-[16px]">warning</span>
          <span className="text-xs text-amber-400">
            LLM budget {budgetPct}% consumed — remaining agents using heuristic analysis
          </span>
        </div>
      )}

      {/* Main War Room Grid */}
      <main className="warroom-main grid-cols-12">
        {loading && !findings && !error && (
          <>
            {/* Left column skeleton */}
            <section className="col-span-3 border-r border-wr-border p-4 flex flex-col gap-4">
              <SkeletonLoader type="card" height="h-48" />
              <SkeletonLoader type="card" height="h-28" />
              <SkeletonLoader type="card" height="h-24" />
            </section>
            {/* Center column skeleton */}
            <section className="col-span-5 border-r border-wr-border p-4 flex flex-col gap-3">
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
            {/* ── LEFT COLUMN (col-3) ── */}
            <section className="col-span-3 border-r border-wr-border bg-wr-bg/50 p-4 flex flex-col gap-4 overflow-hidden z-10">
              <ExecutionProgress domainReports={domainReports} phase={phase || 'pre_flight'} />
              <FleetHeatmap nodes={fleetNodes} selectedNode={selectedNode} onSelectNode={setSelectedNode} />
            </section>

            {/* ── CENTER COLUMN (col-5) ── */}
            <section className="col-span-5 flex h-full bg-wr-bg overflow-hidden relative border-r border-wr-border">
              {allAgentsFailed && (
                <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
                  <span className="material-symbols-outlined text-4xl text-red-500/40 mb-3">error_outline</span>
                  <h3 className="text-sm font-bold text-red-400 mb-2">All Domain Agents Failed</h3>
                  <p className="text-body-xs text-slate-400 max-w-xs">
                    No diagnostic data could be collected. Check cluster connectivity, RBAC permissions, and API server health.
                  </p>
                  <div className="mt-4 space-y-1 text-left">
                    {domainReports.filter(r => r.failure_reason).map(r => (
                      <div key={r.domain} className="text-body-xs text-red-400/60">
                        <span className="font-mono text-slate-500">{r.domain}:</span> {r.failure_reason?.replace(/_/g, ' ')}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {!allAgentsFailed && (centerView === 'priority' ? (
                <div className="flex-1 overflow-y-auto">
                  <IssuePriorityPanel
                    diagnosticIssues={diagnosticIssues}
                    domainReports={domainReports}
                    causalChains={causalChains}
                    symptomMap={symptomMap}
                    phase={phase || 'pre_flight'}
                  />
                </div>
              ) : (
                <DomainPanel
                  domain={centerView}
                  report={centerDomainReport}
                  namespaces={centerNamespaceWorkloads}
                />
              ))}
              <div className="w-[40px] flex flex-col bg-wr-surface border-l border-wr-border shrink-0 z-10">
                <VerticalRibbon
                  domain={'node' as ClusterDomainKey}
                  isPriority
                  onClick={() => setCenterView('priority')}
                  onPriorityClick={() => setCenterView('priority')}
                  isActive={centerView === 'priority'}
                />
                {ALL_DOMAINS.map(d => (
                  <VerticalRibbon
                    key={d}
                    domain={d}
                    report={domainReports.find(r => r.domain === d)}
                    onClick={() => setCenterView(d)}
                    isActive={centerView === d}
                  />
                ))}
              </div>
            </section>

            {/* ── RIGHT COLUMN (col-4) ── */}
            <section className="col-span-4 bg-wr-bg/50 p-4 flex flex-col gap-4 overflow-y-auto relative z-10">
              <HypothesisCard
                hypotheses={rankedHypotheses}
                primaryChain={primaryChain}
                confidence={confidence}
              />
              <RemediationCard steps={immediateSteps} blastRadius={findings?.blast_radius} />
              {longTermSteps.length > 0 && (
                <div className="bg-wr-inset rounded border border-wr-border-subtle p-3">
                  <span className="text-body-xs font-semibold uppercase tracking-wider text-slate-400">Long-Term Recommendations</span>
                  <div className="mt-2 space-y-2">
                    {longTermSteps.map((step, i) => (
                      <div key={i} className="text-body-xs text-slate-400">
                        <p>{step.description}</p>
                        {step.command && <code className="text-body-xs text-wr-accent block mt-1 font-mono">$ {step.command}</code>}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              <UncorrelatedFindings findings={uncorrelatedFindings} />
              {scanDelta && <ScanDiff delta={scanDelta} />}
            </section>
          </>
        )}
      </main>

      <div className="px-6 py-2 shrink-0">
        <EventLogViewer events={events} />
      </div>
      <CommandBar />
      <ChatDrawer />
      <LedgerTriggerTab />
    </div>
  );
};

export default ClusterWarRoom;
