import React, { useEffect, useState, useCallback } from 'react';
import { BarChart3, AlertTriangle, Server, GitBranch } from 'lucide-react';
import type { V4Findings, TimelineEventData, EvidenceNodeData, CausalEdgeData, ChangeCorrelation, PastIncidentMatch, BlastRadiusData, SeverityData, RemediationDecisionData, RunbookMatchData } from '../types';
import { getFindings, getTimeline, getEvidenceGraph, findSimilarIncidents } from '../services/api';
import TimelineCard from './Dashboard/TimelineCard';
import EvidenceGraphCard from './Dashboard/EvidenceGraphCard';
import ChangeCorrelationCard from './Dashboard/ChangeCorrelationCard';
import PastIncidentCard from './Dashboard/PastIncidentCard';
import ImpactCard from './Dashboard/ImpactCard';
import RemediationPanel from './Remediation/RemediationPanel';

interface ResultsPanelProps {
  sessionId: string;
}

/** Derive blast radius from findings data. */
function deriveBlastRadius(findings: V4Findings | null): BlastRadiusData | null {
  if (!findings || findings.findings.length === 0) return null;
  const services = new Set<string>();
  for (const f of findings.findings) {
    if (f.agent_name) services.add(f.agent_name);
  }
  const pods = findings.pod_statuses || [];
  const namespaces = new Set(pods.map((p) => p.namespace).filter(Boolean));
  const primaryService = findings.findings[0]?.title?.split(' ')[0] || 'unknown-svc';
  const scope = namespaces.size > 1 ? 'cluster_wide' : pods.length > 3 ? 'namespace' : 'single_service';

  return {
    primary_service: primaryService,
    upstream_affected: [],
    downstream_affected: [...services].slice(0, 3),
    shared_resources: [],
    estimated_user_impact: pods.length > 0 ? `${pods.length} pod(s) affected` : 'Unknown',
    scope: scope as BlastRadiusData['scope'],
  };
}

/** Derive severity from findings data. */
function deriveSeverity(findings: V4Findings | null): SeverityData | null {
  if (!findings || findings.findings.length === 0) return null;
  const critCount = findings.findings.filter((f) => f.severity === 'critical').length;
  const highCount = findings.findings.filter((f) => f.severity === 'high').length;
  let severity: SeverityData['recommended_severity'] = 'P4';
  if (critCount > 0) severity = 'P1';
  else if (highCount > 0) severity = 'P2';
  else if (findings.findings.length > 3) severity = 'P3';

  return {
    recommended_severity: severity,
    reasoning: `${critCount} critical, ${highCount} high severity findings across ${findings.findings.length} total`,
    factors: {
      critical_findings: String(critCount),
      high_findings: String(highCount),
      total_findings: String(findings.findings.length),
    },
  };
}

/** Derive change correlations from code impacts. */
function deriveChangeCorrelations(findings: V4Findings | null): ChangeCorrelation[] {
  if (!findings) return [];
  const impacts = findings.impacted_files || [];
  return impacts.map((ci, i) => ({
    change_id: `impact-${i}`,
    change_type: ci.impact_type === 'direct_error' ? 'code_deploy' as const : 'config_change' as const,
    risk_score: ci.impact_type === 'direct_error' ? 0.9 : 0.4,
    temporal_correlation: 0,
    author: '',
    description: ci.relationship,
    files_changed: [ci.file_path],
    timestamp: null,
  }));
}

/** Derive remediation from findings suggested fixes. */
function deriveRemediation(findings: V4Findings | null): RemediationDecisionData | null {
  if (!findings) return null;
  const withFix = findings.findings.find((f) => f.suggested_fix);
  if (!withFix) return null;
  return {
    proposed_action: withFix.suggested_fix || '',
    action_type: 'code_fix',
    is_destructive: false,
    dry_run_available: false,
    rollback_plan: 'Revert the applied fix and restore previous state',
    pre_checks: ['Review proposed changes', 'Verify affected services'],
    post_checks: ['Run smoke tests', 'Monitor error rate'],
  };
}

const ResultsPanel: React.FC<ResultsPanelProps> = ({ sessionId }) => {
  const [findings, setFindings] = useState<V4Findings | null>(null);
  const [loading, setLoading] = useState(true);
  const [timelineEvents, setTimelineEvents] = useState<TimelineEventData[]>([]);
  const [graphNodes, setGraphNodes] = useState<EvidenceNodeData[]>([]);
  const [graphEdges, setGraphEdges] = useState<CausalEdgeData[]>([]);
  const [rootCauses, setRootCauses] = useState<string[]>([]);
  const [pastIncidents, setPastIncidents] = useState<PastIncidentMatch[]>([]);
  const [changeCorrelations, setChangeCorrelations] = useState<ChangeCorrelation[]>([]);
  const [remediationDecision, setRemediationDecision] = useState<RemediationDecisionData | null>(null);
  const [runbookMatches] = useState<RunbookMatchData[]>([]);
  const [blastRadius, setBlastRadius] = useState<BlastRadiusData | null>(null);
  const [severityData, setSeverityData] = useState<SeverityData | null>(null);

  const fetchFindings = useCallback(async () => {
    try {
      const data = await getFindings(sessionId);
      setFindings(data);

      // Derive computed data from findings
      setBlastRadius(deriveBlastRadius(data));
      setSeverityData(deriveSeverity(data));
      setChangeCorrelations(deriveChangeCorrelations(data));
      setRemediationDecision(deriveRemediation(data));
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

  const fetchSimilarIncidents = useCallback(async () => {
    try {
      const data = await findSimilarIncidents(sessionId);
      if (data?.similar_incidents) setPastIncidents(data.similar_incidents);
    } catch {
      // silently fail - memory store may be empty
    }
  }, [sessionId]);

  useEffect(() => {
    fetchFindings();
    fetchCausalData();
    fetchSimilarIncidents();
    const interval = setInterval(() => {
      fetchFindings();
      fetchCausalData();
    }, 5000);
    return () => clearInterval(interval);
  }, [fetchFindings, fetchCausalData, fetchSimilarIncidents]);

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
