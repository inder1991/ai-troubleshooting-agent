import React, { useMemo } from 'react';
import type {
  DiagnosticIssue,
  ClusterDomainReport,
  ClusterCausalChain,
  ClusterDomainAnomaly,
  IssueLifecycleState,
} from '../../types';

interface IssuePriorityPanelProps {
  diagnosticIssues?: DiagnosticIssue[];
  domainReports: ClusterDomainReport[];
  causalChains?: ClusterCausalChain[];
  symptomMap?: Record<string, string>;
  phase: string;
}

const STATE_CONFIG: Record<string, { label: string; color: string; dotColor: string; borderClass: string }> = {
  ACTIVE_DISRUPTION: { label: 'Active Disruptions', color: '#ef4444', dotColor: 'bg-red-500', borderClass: 'border-l-red-500' },
  WORSENING:         { label: 'Escalating', color: '#f59e0b', dotColor: 'bg-amber-500', borderClass: 'border-l-amber-500' },
  NEW:               { label: 'New Issues', color: '#e09f3e', dotColor: 'bg-[#e09f3e]', borderClass: 'border-l-[#e09f3e]' },
  EXISTING:          { label: 'Known Issues', color: '#64748b', dotColor: 'bg-slate-500', borderClass: 'border-l-slate-600' },
  LONG_STANDING:     { label: 'Long-Standing', color: '#475569', dotColor: 'bg-slate-600', borderClass: 'border-l-slate-700' },
  INTERMITTENT:      { label: 'Intermittent', color: '#6366f1', dotColor: 'bg-indigo-500', borderClass: 'border-l-indigo-500' },
  SYMPTOM:           { label: 'Symptoms', color: '#94a3b8', dotColor: 'bg-slate-400', borderClass: 'border-l-slate-400' },
};

const TIER_ORDER: IssueLifecycleState[] = [
  'ACTIVE_DISRUPTION', 'WORSENING', 'NEW', 'EXISTING', 'LONG_STANDING', 'INTERMITTENT', 'SYMPTOM',
];

/** Derive synthetic DiagnosticIssue entries from legacy domain reports + causal chains. */
function deriveFallbackIssues(
  domainReports: ClusterDomainReport[],
  causalChains?: ClusterCausalChain[],
): DiagnosticIssue[] {
  const rootCauseIds = new Set<string>();
  const symptomIds = new Set<string>();

  causalChains?.forEach(chain => {
    rootCauseIds.add(chain.root_cause.anomaly_id);
    chain.cascading_effects.forEach(eff => symptomIds.add(eff.anomaly_id));
  });

  const issues: DiagnosticIssue[] = [];

  domainReports.forEach(report => {
    report.anomalies.forEach(a => {
      let state: IssueLifecycleState = 'EXISTING';
      let isRoot = false;
      let isSymptom = false;

      if (rootCauseIds.has(a.anomaly_id)) {
        state = 'ACTIVE_DISRUPTION';
        isRoot = true;
      } else if (symptomIds.has(a.anomaly_id)) {
        state = 'SYMPTOM';
        isSymptom = true;
      } else if (a.severity === 'high') {
        state = 'WORSENING';
      }

      issues.push({
        issue_id: a.anomaly_id,
        state,
        priority_score: state === 'ACTIVE_DISRUPTION' ? 100 : state === 'WORSENING' ? 75 : state === 'SYMPTOM' ? 20 : 50,
        first_seen: '',
        last_state_change: '',
        state_duration_seconds: 0,
        event_count_recent: 0,
        event_count_baseline: 0,
        restart_velocity: 0,
        severity_trend: '',
        is_root_cause: isRoot,
        is_symptom: isSymptom,
        root_cause_id: '',
        blast_radius: 0,
        affected_resources: [],
        signals: [],
        pattern_matches: [],
        anomaly_ids: [a.anomaly_id],
        description: a.description,
        severity: a.severity || 'medium',
      });
    });
  });

  return issues.sort((a, b) => b.priority_score - a.priority_score);
}

function formatAge(seconds: number): string {
  if (seconds <= 0) return '';
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h`;
  return `${Math.round(seconds / 86400)}d`;
}

const IssuePriorityPanel: React.FC<IssuePriorityPanelProps> = ({
  diagnosticIssues,
  domainReports,
  causalChains,
  symptomMap,
  phase,
}) => {
  const issues = useMemo(() => {
    if (diagnosticIssues && diagnosticIssues.length > 0) return diagnosticIssues;
    return deriveFallbackIssues(domainReports, causalChains);
  }, [diagnosticIssues, domainReports, causalChains]);

  const grouped = useMemo(() => {
    const map: Partial<Record<IssueLifecycleState, DiagnosticIssue[]>> = {};
    issues.forEach(issue => {
      if (!map[issue.state]) map[issue.state] = [];
      map[issue.state]!.push(issue);
    });
    return map;
  }, [issues]);

  if (issues.length === 0) {
    return (
      <div className="p-4">
        <p className="text-[11px] text-slate-600 animate-pulse">
          {phase === 'complete' ? 'No issues detected.' : 'Scanning for issues...'}
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-y-auto custom-scrollbar max-h-[600px] space-y-4 pr-1">
      {TIER_ORDER.map(state => {
        const bucket = grouped[state];
        if (!bucket || bucket.length === 0) return null;
        const cfg = STATE_CONFIG[state];
        if (!cfg) return null;

        return (
          <div key={state}>
            {/* Section header */}
            <div className="flex items-center gap-2 mb-2 px-1">
              <span className={`w-2 h-2 rounded-full ${cfg.dotColor}`} />
              <span className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: cfg.color }}>
                {cfg.label}
              </span>
              <span className="text-[10px] text-slate-600 font-mono">{bucket.length}</span>
            </div>

            {/* Issue rows */}
            <div className="space-y-1">
              {bucket.map(issue => (
                <IssueRow key={issue.issue_id} issue={issue} state={state} symptomMap={symptomMap} />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
};

/* ---- Tier-specific row rendering ---- */

interface IssueRowProps {
  issue: DiagnosticIssue;
  state: IssueLifecycleState;
  symptomMap?: Record<string, string>;
}

const IssueRow: React.FC<IssueRowProps> = ({ issue, state, symptomMap }) => {
  const cfg = STATE_CONFIG[state];

  if (state === 'ACTIVE_DISRUPTION') {
    return (
      <div className={`border-l-2 ${cfg?.borderClass ?? ''} pl-3 py-2 bg-[#1a1814]/60 rounded-r`}>
        <p className="text-[13px] font-semibold text-slate-200 leading-snug">{issue.description}</p>
        <div className="flex items-center gap-3 mt-1">
          {issue.blast_radius > 0 && (
            <span className="text-[10px] text-red-400 font-mono">blast: {issue.blast_radius}</span>
          )}
          {issue.priority_score > 0 && (
            <span className="text-[10px] text-slate-500 font-mono">score: {issue.priority_score}</span>
          )}
          {issue.affected_resources.length > 0 && (
            <span className="text-[10px] text-slate-600 font-mono">
              {issue.affected_resources.length} resources
            </span>
          )}
        </div>
      </div>
    );
  }

  if (state === 'WORSENING') {
    return (
      <div className={`border-l-2 ${cfg?.borderClass ?? ''} pl-3 py-1.5 bg-[#1a1814]/40 rounded-r`}>
        <p className="text-[12px] text-slate-300 leading-snug">{issue.description}</p>
        <div className="flex items-center gap-3 mt-0.5">
          {issue.first_seen && (
            <span className="text-[10px] text-slate-600 font-mono">seen: {issue.first_seen}</span>
          )}
          {issue.restart_velocity > 0 && (
            <span className="text-[10px] text-amber-500/70 font-mono">vel: {issue.restart_velocity}/h</span>
          )}
        </div>
      </div>
    );
  }

  if (state === 'SYMPTOM') {
    const rootDesc = symptomMap?.[issue.issue_id] || issue.root_cause_id || 'unknown';
    return (
      <div className="pl-4 py-1">
        <p className="text-[11px] italic text-slate-500 leading-snug">
          {issue.description}
        </p>
        <p className="text-[10px] text-slate-600 mt-0.5">
          &rarr; caused by {rootDesc}
        </p>
      </div>
    );
  }

  // EXISTING, LONG_STANDING, NEW, INTERMITTENT — known-style rows
  return (
    <div className={`border-l-2 ${cfg?.borderClass ?? ''} pl-3 py-1`}>
      <p className="text-[11px] text-slate-400 leading-snug">{issue.description}</p>
      {issue.state_duration_seconds > 0 && (
        <span className="text-[10px] text-slate-600 font-mono">age: {formatAge(issue.state_duration_seconds)}</span>
      )}
    </div>
  );
};

export default IssuePriorityPanel;
