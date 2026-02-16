import React, { useEffect, useState, useCallback } from 'react';
import { BarChart3, AlertTriangle, Server, GitBranch } from 'lucide-react';
import type { V4Findings, TimelineEventData, EvidenceNodeData, CausalEdgeData, ChangeCorrelation, PastIncidentMatch, BlastRadiusData, SeverityData, RemediationDecisionData, RunbookMatchData } from '../types';
import { getFindings, getTimeline, getEvidenceGraph } from '../services/api';
import TimelineCard from './Dashboard/TimelineCard';
import EvidenceGraphCard from './Dashboard/EvidenceGraphCard';
import ChangeCorrelationCard from './Dashboard/ChangeCorrelationCard';
import PastIncidentCard from './Dashboard/PastIncidentCard';
import ImpactCard from './Dashboard/ImpactCard';
import RemediationPanel from './Remediation/RemediationPanel';

interface ResultsPanelProps {
  sessionId: string;
}

const ResultsPanel: React.FC<ResultsPanelProps> = ({ sessionId }) => {
  const [findings, setFindings] = useState<V4Findings | null>(null);
  const [loading, setLoading] = useState(true);
  const [timelineEvents, setTimelineEvents] = useState<TimelineEventData[]>([]);
  const [graphNodes, setGraphNodes] = useState<EvidenceNodeData[]>([]);
  const [graphEdges, setGraphEdges] = useState<CausalEdgeData[]>([]);
  const [rootCauses, setRootCauses] = useState<string[]>([]);
  const [pastIncidents] = useState<PastIncidentMatch[]>([
    {
      fingerprint_id: 'fp-001',
      session_id: 'sess-a1b2c3d4-e5f6-7890',
      similarity_score: 0.87,
      root_cause: 'Connection pool exhaustion due to leaked database connections after deployment',
      resolution_steps: [
        'Rolled back deployment v2.3.1',
        'Increased connection pool max size from 10 to 25',
        'Added connection timeout of 30s',
      ],
      error_patterns: ['ConnectionTimeout', 'PoolExhausted'],
      affected_services: ['order-svc', 'inventory-svc'],
      time_to_resolve: 2340,
    },
    {
      fingerprint_id: 'fp-002',
      session_id: 'sess-x9y8z7w6-v5u4-3210',
      similarity_score: 0.62,
      root_cause: 'Redis timeout misconfiguration causing cascading failures',
      resolution_steps: [
        'Reverted Redis timeout from 2s to 5s',
        'Added circuit breaker for Redis calls',
      ],
      error_patterns: ['ConnectionTimeout', 'RedisCommandTimeout'],
      affected_services: ['order-svc', 'cache-svc'],
      time_to_resolve: 1800,
    },
  ]);
  const [changeCorrelations] = useState<ChangeCorrelation[]>([
    {
      change_id: 'placeholder-1',
      change_type: 'code_deploy',
      risk_score: 0.85,
      temporal_correlation: 0.92,
      author: 'deploy-bot',
      description: 'Deployed v2.3.1 with updated connection pool settings',
      files_changed: ['src/config/db.ts', 'src/services/pool.ts'],
      timestamp: new Date().toISOString(),
    },
    {
      change_id: 'placeholder-2',
      change_type: 'config_change',
      risk_score: 0.45,
      temporal_correlation: 0.60,
      author: 'ops-team',
      description: 'Updated Redis timeout from 5s to 2s',
      files_changed: ['configmap.yaml'],
      timestamp: new Date(Date.now() - 3600000).toISOString(),
    },
    {
      change_id: 'placeholder-3',
      change_type: 'dependency_update',
      risk_score: 0.2,
      temporal_correlation: 0.15,
      author: 'dependabot',
      description: 'Bumped axios from 1.6.0 to 1.6.2',
      files_changed: ['package.json', 'package-lock.json'],
      timestamp: new Date(Date.now() - 86400000).toISOString(),
    },
  ]);

  const [remediationDecision] = useState<RemediationDecisionData | null>({
    proposed_action: 'Restart deployment order-svc with increased memory limits',
    action_type: 'restart',
    is_destructive: false,
    dry_run_available: true,
    rollback_plan: 'Scale back to previous resource limits and replica count',
    pre_checks: ['Verify current pod health', 'Check pending traffic drain'],
    post_checks: ['Verify pods are running', 'Run smoke tests', 'Check error rate'],
  });
  const [runbookMatches] = useState<RunbookMatchData[]>([
    {
      runbook_id: 'rb-001',
      title: 'OOM Recovery Playbook',
      match_score: 0.85,
      steps: [
        'Increase memory limits by 50%',
        'Restart affected deployment',
        'Monitor for 15 minutes',
        'Verify error rate returns to baseline',
      ],
      success_rate: 0.92,
      source: 'internal',
    },
  ]);

  const [blastRadius] = useState<BlastRadiusData>({
    primary_service: 'order-svc',
    upstream_affected: ['api-gateway', 'auth-svc'],
    downstream_affected: ['inventory-svc', 'payment-svc', 'notification-svc'],
    shared_resources: ['postgres-primary', 'redis-cluster'],
    estimated_user_impact: '~5000 users potentially affected',
    scope: 'namespace',
  });
  const [severityData] = useState<SeverityData>({
    recommended_severity: 'P2',
    reasoning: "Service tier 'critical' with blast radius scope 'namespace'",
    factors: { service_tier: 'critical', blast_radius_scope: 'namespace' },
  });

  const fetchFindings = useCallback(async () => {
    try {
      const data = await getFindings(sessionId);
      setFindings(data);
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  const fetchCausalData = useCallback(async () => {
    try {
      const [tlData, egData] = await Promise.all([
        getTimeline(sessionId),
        getEvidenceGraph(sessionId),
      ]);
      if (tlData?.events) setTimelineEvents(tlData.events);
      if (egData?.nodes) setGraphNodes(egData.nodes);
      if (egData?.edges) setGraphEdges(egData.edges);
      if (egData?.root_causes) setRootCauses(egData.root_causes);
    } catch {
      // silently fail - causal data may not be available yet
    }
  }, [sessionId]);

  useEffect(() => {
    fetchFindings();
    fetchCausalData();
    const interval = setInterval(() => {
      fetchFindings();
      fetchCausalData();
    }, 5000);
    return () => clearInterval(interval);
  }, [fetchFindings, fetchCausalData]);

  if (loading && !findings) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-[#07b6d5] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const errorCount = findings?.error_patterns?.length ?? 0;
  const anomalyCount = findings?.metric_anomalies?.length ?? 0;
  const podCount = findings?.pod_statuses?.length ?? 0;
  const findingsCount = findings?.findings?.length ?? 0;

  return (
    <div className="h-full overflow-y-auto p-4 space-y-3">
      <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
        Active Results
      </h3>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 gap-2">
        <div className="bg-[#1e2f33]/50 border border-[#224349] rounded-lg p-3">
          <div className="flex items-center gap-2 mb-1">
            <AlertTriangle className="w-3.5 h-3.5 text-red-400" />
            <span className="text-xs text-gray-400">Errors</span>
          </div>
          <span className="text-lg font-bold text-white">{errorCount}</span>
        </div>
        <div className="bg-[#1e2f33]/50 border border-[#224349] rounded-lg p-3">
          <div className="flex items-center gap-2 mb-1">
            <BarChart3 className="w-3.5 h-3.5 text-yellow-400" />
            <span className="text-xs text-gray-400">Anomalies</span>
          </div>
          <span className="text-lg font-bold text-white">{anomalyCount}</span>
        </div>
        <div className="bg-[#1e2f33]/50 border border-[#224349] rounded-lg p-3">
          <div className="flex items-center gap-2 mb-1">
            <Server className="w-3.5 h-3.5 text-blue-400" />
            <span className="text-xs text-gray-400">Pods</span>
          </div>
          <span className="text-lg font-bold text-white">{podCount}</span>
        </div>
        <div className="bg-[#1e2f33]/50 border border-[#224349] rounded-lg p-3">
          <div className="flex items-center gap-2 mb-1">
            <GitBranch className="w-3.5 h-3.5 text-[#07b6d5]" />
            <span className="text-xs text-gray-400">Findings</span>
          </div>
          <span className="text-lg font-bold text-white">{findingsCount}</span>
        </div>
      </div>

      {/* Finding Details */}
      {findings?.findings && findings.findings.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mt-4">
            Key Findings
          </h4>
          {findings.findings.map((f, idx) => (
            <div
              key={idx}
              className="bg-[#1e2f33]/50 border border-[#224349] rounded-lg p-3"
            >
              <div className="flex items-start justify-between mb-1">
                <span className="text-sm font-medium text-white">{f.title}</span>
                <span
                  className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                    f.severity === 'critical'
                      ? 'bg-red-500/20 text-red-400'
                      : f.severity === 'high'
                      ? 'bg-orange-500/20 text-orange-400'
                      : f.severity === 'medium'
                      ? 'bg-yellow-500/20 text-yellow-400'
                      : 'bg-green-500/20 text-green-400'
                  }`}
                >
                  {f.severity}
                </span>
              </div>
              <p className="text-xs text-gray-400 line-clamp-2">{f.description}</p>
              <div className="mt-1.5 flex items-center gap-2">
                <div className="flex-1 h-1 bg-[#224349] rounded-full overflow-hidden">
                  <div
                    className="h-full bg-[#07b6d5] rounded-full"
                    style={{ width: `${Math.round(f.confidence * 100)}%` }}
                  />
                </div>
                <span className="text-xs text-gray-500 font-mono">
                  {Math.round(f.confidence * 100)}%
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Error Patterns */}
      {findings?.error_patterns && findings.error_patterns.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mt-4">
            Error Patterns
          </h4>
          {findings.error_patterns.slice(0, 5).map((ep, idx) => (
            <div
              key={idx}
              className="bg-[#1e2f33]/50 border border-[#224349] rounded-lg p-3"
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-mono text-white truncate flex-1 mr-2">
                  {ep.pattern}
                </span>
                <span className="text-xs text-red-400 font-mono">{ep.count}x</span>
              </div>
              <p className="text-xs text-gray-500 truncate">{ep.sample_message}</p>
            </div>
          ))}
        </div>
      )}

      {/* Remediation */}
      <RemediationPanel
        sessionId={sessionId}
        decision={remediationDecision}
        runbookMatches={runbookMatches}
      />

      {/* Impact Analysis */}
      <ImpactCard blastRadius={blastRadius} severity={severityData} />

      {/* Incident Timeline */}
      <TimelineCard events={timelineEvents} />

      {/* Evidence Graph */}
      <EvidenceGraphCard nodes={graphNodes} edges={graphEdges} rootCauses={rootCauses} />

      {/* Past Incident Matches */}
      <PastIncidentCard incidents={pastIncidents} />

      {/* Change Correlations */}
      <ChangeCorrelationCard changes={changeCorrelations} />
    </div>
  );
};

export default ResultsPanel;
