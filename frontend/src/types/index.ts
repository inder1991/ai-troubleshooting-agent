// Re-export campaign types
export type { CampaignRepoStatus, CampaignRepoFix, RemediationCampaign, TelescopeData } from './campaign';

// ===== V3 Types (preserved for backward compatibility) =====

export interface Message {
  role: 'user' | 'assistant';
  content: string;
  type: string;
  timestamp: string;
  actions?: Action[];
  data?: Record<string, unknown>;
}

export interface SessionData {
  sessionId: string | null;
  config: Record<string, unknown>;
  agent1Result: Record<string, unknown> | null;
  agent2Result: Record<string, unknown> | null;
  agent3Result: Record<string, unknown> | null;
  wsConnected: boolean;
  agent1Streaming: string;
  agent2Streaming: string;
  agent3Streaming: string;
  isAgent1Streaming: boolean;
  isAgent2Streaming: boolean;
  isAgent3Streaming: boolean;
}

export interface Action {
  id: string;
  label: string;
  icon: React.ReactNode;
  url?: string;
}

export interface Agent1Result {
  correlationId: string;
  exceptionType: string;
  exceptionMessage: string;
  stackTrace: string;
  preliminaryRca: string;
  affectedComponents: string[];
  logCount: number;
}

export interface Agent2Result {
  rootCause: string;
  callChain: string[];
  relevantFiles: string[];
  flowchart: string;
  dependencies: string[];
}

export interface Agent3Result {
  proposedFix: string;
  explanation: string;
  testSuggestions: string[];
  prTitle: string;
  prDescription: string;
  confidence: number;
}

// ===== V4 Types =====

export type DiagnosticPhase =
  | 'initial'
  | 'collecting_context'
  | 'logs_analyzed'
  | 'metrics_analyzed'
  | 'k8s_analyzed'
  | 'tracing_analyzed'
  | 'code_analyzed'
  | 'validating'
  | 're_investigating'
  | 'diagnosis_complete'
  | 'fix_in_progress'
  | 'complete'
  | 'error';

export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info';

export interface ErrorPattern {
  pattern_id: string;
  exception_type: string;
  error_message: string;
  frequency: number;
  severity: Severity;
  affected_components: string[];
  confidence_score: number;
  priority_rank: number;
  priority_reasoning: string;
  // Computed fields for display
  pattern: string;
  count: number;
  sample_message: string;
  confidence: number;
  first_seen: string | null;
  last_seen: string | null;
  // Enrichment fields
  stack_traces?: string[];
  correlation_ids?: string[];
  sample_log_ids?: string[];
  causal_role?: 'root_cause' | 'cascading_failure' | 'correlated_anomaly';
  sample_logs?: LogEvidence[];
}

export interface LogEvidence {
  log_id: string;
  index: string;
  timestamp: string;
  level: string;
  message: string;
  service?: string;
  raw_line: string;
}

export interface MetricAnomaly {
  metric_name: string;
  current_value: number;
  baseline_value: number;
  peak_value: number;
  deviation_percent: number;
  direction: 'above' | 'below';
  severity: Severity;
  timestamp: string;
  spike_start: string;
  spike_end: string;
  promql_query: string;
  correlation_to_incident: string;
  confidence_score: number;
}

export interface TimeSeriesDataPoint {
  timestamp: string;
  value: number;
}

export interface CorrelatedSignalGroup {
  group_name: string;
  signal_type: 'RED' | 'USE';
  metrics: string[];
  narrative: string;
}

export interface EventMarker {
  timestamp: string;
  label: string;
  source: string;
  severity: Severity;
}

export interface PodHealthStatus {
  pod_name: string;
  namespace: string;
  status: string;
  restart_count: number;
  ready: boolean;
  conditions: string[];
  oom_killed: boolean;
  crash_loop: boolean;
  init_container_failures?: string[];
  image_pull_errors?: string[];
  container_count?: number;
  ready_containers?: number;
  resource_requests?: Record<string, string>;
  resource_limits?: Record<string, string>;
  last_termination_reason?: string;
  last_restart_time?: string;
}

export interface K8sEvent {
  type: string;
  reason: string;
  message: string;
  count: number;
  first_timestamp: string;
  last_timestamp: string;
  involved_object: string;
  source_component?: string;
  timestamp?: string;
}

export interface SpanInfo {
  span_id: string;
  service: string;
  operation: string;
  duration_ms: number;
  status: string;
  error: boolean;
  parent_span_id: string | null;
  error_message?: string;
  tags?: Record<string, string>;
}

export interface PatientZero {
  service: string;
  evidence: string;
  first_error_time: string;
}

export interface InferredDependency {
  source: string;
  target?: string;
  evidence?: string;
  targets?: string[];  // from deterministic inference
}

export interface ReasoningChainStep {
  step: number;
  observation: string;
  inference: string;
  tool?: string;
}

export interface ServiceFlowStep {
  service: string;
  timestamp: string;
  operation: string;
  status: 'ok' | 'error' | 'timeout';
  status_detail: string;
  message: string;
  is_new_service: boolean;
}

export interface Finding {
  finding_id: string;
  agent_name: string;
  category: string;
  summary: string;
  title: string;
  description: string;
  severity: Severity;
  confidence_score: number;
  confidence: number;
  evidence: string[];
  suggested_fix?: string;
  critic_verdict?: CriticVerdict;
  breadcrumbs?: Breadcrumb[];
  negative_findings?: NegativeFinding[];
  resource_refs?: ResourceRef[];
}

export interface NegativeFinding {
  agent: string;
  category: string;
  description: string;
  agent_name?: string;
  what_was_checked?: string;
  result?: string;
  implication?: string;
  source_reference?: string;
}

export interface CriticVerdict {
  finding_id: string;
  agent_source: string;
  finding_index: number;
  finding_title: string;
  verdict: 'validated' | 'challenged' | 'insufficient_data';
  confidence: number;
  confidence_in_verdict: number;
  reasoning: string;
  recommendation?: string;
  contradicting_evidence?: Breadcrumb[];
}

export interface Breadcrumb {
  timestamp: string;
  agent_name: string;
  action: string;
  detail: string;
  source_type?: string;
  source_reference?: string;
  raw_evidence?: string;
}

export interface TokenUsage {
  agent_name: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

export interface TaskEvent {
  session_id: string;
  agent_name: string;
  event_type: 'started' | 'progress' | 'success' | 'warning' | 'error' | 'tool_call' | 'phase_change' | 'finding' | 'summary' | 'attestation_required' | 'fix_proposal' | 'fix_approved' | 'waiting_for_input';
  message: string;
  timestamp: string;
  details?: Record<string, unknown>;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  metadata?: {
    type?: string;
    patient_zero_service?: string;
    /** Phase returned from chat response — used for instant phase sync */
    newPhase?: string;
    /** Confidence returned from chat response — used for instant confidence sync */
    newConfidence?: number;
    // Campaign fix proposal fields
    repo_url?: string;
    service_name?: string;
    causal_role?: string;
    fix_explanation?: string;
    fixed_files?: string[];
  };
}

export interface V4Session {
  session_id: string;
  incident_id?: string;
  service_name: string;
  status: DiagnosticPhase;
  confidence: number;
  created_at: string;
  updated_at: string;
}

export interface V4SessionStatus {
  session_id: string;
  incident_id?: string;
  service_name: string;
  phase: DiagnosticPhase;
  confidence: number;
  findings_count: number;
  token_usage: TokenUsage[];
  breadcrumbs: Breadcrumb[];
  agents_completed?: string[];
  created_at: string;
  updated_at: string;
}

export interface SuggestedPromQLQuery {
  metric: string;
  query: string;
  rationale: string;
}

// M8: Array fields marked optional — backend may omit them during partial state
export interface V4Findings {
  session_id: string;
  /** Backend returns this field when findings are empty (e.g., "No findings yet") */
  message?: string;
  incident_id?: string;
  target_service?: string;
  findings: Finding[];
  negative_findings?: NegativeFinding[];
  critic_verdicts?: CriticVerdict[];
  error_patterns?: ErrorPattern[];
  metric_anomalies?: MetricAnomaly[];
  correlated_signals?: CorrelatedSignalGroup[];
  event_markers?: EventMarker[];
  pod_statuses?: PodHealthStatus[];
  k8s_events?: K8sEvent[];
  trace_spans?: SpanInfo[];
  impacted_files?: CodeImpact[];
  diff_analysis?: DiffAnalysisItem[];
  suggested_fix_areas?: SuggestedFixArea[];
  root_cause_location?: CodeImpact | null;
  code_call_chain?: string[];
  code_dependency_graph?: Record<string, string[]>;
  code_shared_resource_conflicts?: string[];
  code_cross_repo_findings?: CrossRepoFinding[];
  code_mermaid_diagram?: string;
  code_overall_confidence?: number;
  change_correlations?: ChangeCorrelation[];
  change_summary?: string | null;
  change_high_priority_files?: HighPriorityFile[];
  blast_radius?: BlastRadiusData | null;
  severity_recommendation?: SeverityData | null;
  past_incidents?: PastIncidentMatch[];
  service_flow?: ServiceFlowStep[];
  flow_source?: string | null;
  flow_confidence?: number;
  patient_zero?: PatientZero | null;
  inferred_dependencies?: InferredDependency[];
  reasoning_chain?: ReasoningChainStep[];
  suggested_promql_queries?: SuggestedPromQLQuery[];
  time_series_data?: Record<string, TimeSeriesDataPoint[]>;
  fix_data?: FixResult | null;
  closure_state?: IncidentClosureState | null;
  campaign?: import('./campaign').RemediationCampaign | null;
  /** Manual evidence pins collected from live investigation steering (user_chat / quick_action) */
  evidence_pins?: EvidencePinV2[];
  causal_forest?: CausalTree[];
  // Cluster diagnostic capability fields
  guard_scan_result?: GuardScanResult | null;
  issue_clusters?: IssueCluster[] | null;
  causal_search_space?: CausalSearchSpace | null;
  scan_mode?: 'diagnostic' | 'guard';
  topology_snapshot?: TopologySnapshot | null;
  platform?: string;
  platform_version?: string;
  platform_health?: string;
  data_completeness?: number;
  causal_chains?: Array<Record<string, unknown>>;
  uncorrelated_findings?: Array<Record<string, unknown>>;
  domain_reports?: ClusterDomainReport[];
  remediation?: Record<string, unknown>;
  execution_metadata?: Record<string, unknown>;
}

export type FixStatus =
  | 'not_started' | 'generating' | 'awaiting_review'
  | 'human_feedback' | 'verification_in_progress'
  | 'verified' | 'verification_failed'
  | 'approved' | 'rejected'
  | 'pr_creating' | 'pr_created' | 'failed';

export interface FixVerificationResult {
  verdict: 'approve' | 'reject' | 'needs_changes';
  confidence: number;
  issues_found: string[];
  regression_risks: string[];
  suggestions: string[];
  reasoning: string;
}

// Single file within a multi-file fix
export interface FixedFile {
  file_path: string;
  original_code: string;
  fixed_code: string;
  diff: string;
}

// Matches backend FixStatusResponse — returned by GET /fix/status
export interface FixStatusResponse {
  fix_status: FixStatus;
  target_file: string;
  diff: string;
  fix_explanation: string;
  fixed_files: { file_path: string; diff: string }[];
  verification_result: FixVerificationResult | null;
  pr_url: string | null;
  pr_number: number | null;
  attempt_count: number;
}

// Full fix result — returned in V4Findings.fix_data (from state.fix_result)
export interface FixResult {
  fix_status: FixStatus;
  target_file: string;
  original_code: string;
  generated_fix: string;
  diff: string;
  fixed_files: FixedFile[];
  fix_explanation: string;
  verification_result: FixVerificationResult | null;
  pr_url: string | null;
  pr_number: number | null;
  attempt_count: number;
  max_attempts: number;
  human_feedback: string[];
  pr_data: {
    branch_name: string;
    commit_sha: string;
    pr_title: string;
    pr_body: string;
    diff: string;
    file_diffs: Record<string, string>;
    validation: Record<string, unknown>;
    impact: Record<string, unknown>;
    fixed_code: string;
    fixed_files: string[];
    status: string;
    token_usage: Record<string, unknown>;
  } | null;
}

export interface CodeImpact {
  file_path: string;
  impact_type: 'direct_error' | 'caller' | 'callee' | 'shared_resource' | 'config' | 'test';
  relevant_lines: { start: number; end: number }[];
  code_snippet: string;
  relationship: string;
  fix_relevance: 'must_fix' | 'should_review' | 'informational';
}

export interface DiffAnalysisItem {
  file: string;
  commit_sha: string;
  verdict: 'likely_cause' | 'unrelated' | 'contributing';
  reasoning: string;
}

export interface SuggestedFixArea {
  file_path: string;
  description: string;
  suggested_change: string;
}

export interface CrossRepoFinding {
  repo: string;
  role: string;
  evidence: string;
}

export interface StartSessionRequest {
  service_name: string;
  time_window: string;
  trace_id?: string;
  namespace?: string;
  elk_index?: string;
  repo_url?: string;
  profile_id?: string;
  capability?: string;
  cluster_url?: string;
  scan_mode?: 'diagnostic' | 'guard';
}

export interface V4WebSocketMessage {
  type: 'task_event' | 'chat_response' | 'chat_chunk' | 'profile_change' | 'connected';
  data: TaskEvent | ChatMessage | Record<string, unknown>;
}

export interface DiagnosisSummary {
  overall_confidence: number;
  findings: Finding[];
  critic_verdicts: CriticVerdict[];
  breadcrumbs: Breadcrumb[];
  root_cause_summary: string;
}

// ===== Action Center Types =====

export type CapabilityType =
  | 'troubleshoot_app'
  | 'pr_review'
  | 'github_issue_fix'
  | 'cluster_diagnostics';

export interface TroubleshootAppForm {
  capability: 'troubleshoot_app';
  service_name: string;
  time_window: string;
  trace_id?: string;
  namespace?: string;
  elk_index?: string;
  repo_url?: string;
  profile_id?: string;
}

export interface PRReviewForm {
  capability: 'pr_review';
  repo_url: string;
  pr_number: string;
  branch_name?: string;
  focus_areas?: string[];
}

export interface GithubIssueFixForm {
  capability: 'github_issue_fix';
  repo_url: string;
  issue_number: string;
  target_branch?: string;
  priority?: 'low' | 'medium' | 'high' | 'critical';
}

export interface ClusterDiagnosticsForm {
  capability: 'cluster_diagnostics';
  cluster_url: string;
  namespace?: string;
  symptoms?: string;
  auth_token?: string;
  auth_method?: 'token' | 'kubeconfig';
  resource_type?: string;
  profile_id?: string;
  save_cluster?: boolean;
  cluster_name?: string;
}

// ===== Cluster Diagnostics Types =====
export interface ClusterDomainAnomaly {
  domain: string;
  anomaly_id: string;
  description: string;
  evidence_ref: string;
  severity?: string;
}

export interface ClusterDomainReport {
  domain: string;
  status: 'PENDING' | 'RUNNING' | 'SUCCESS' | 'PARTIAL' | 'FAILED';
  failure_reason?: string;
  confidence: number;
  anomalies: ClusterDomainAnomaly[];
  ruled_out: string[];
  evidence_refs: string[];
  truncation_flags: Record<string, boolean>;
  data_gathered_before_failure?: string[];
  duration_ms: number;
}

export interface ClusterCausalLink {
  order: number;
  domain: string;
  anomaly_id: string;
  description: string;
  link_type: string;
  evidence_ref: string;
}

export interface ClusterCausalChain {
  chain_id: string;
  confidence: number;
  root_cause: ClusterDomainAnomaly;
  cascading_effects: ClusterCausalLink[];
}

export interface ClusterBlastRadius {
  summary: string;
  affected_namespaces: number;
  affected_pods: number;
  affected_nodes: number;
}

export interface ClusterRemediationStep {
  command?: string;
  description: string;
  risk_level?: string;
  effort_estimate?: string;
}

export interface ClusterHealthReport {
  diagnostic_id: string;
  platform: string;
  platform_version: string;
  platform_health: 'HEALTHY' | 'DEGRADED' | 'CRITICAL' | 'UNKNOWN' | 'PENDING';
  data_completeness: number;
  blast_radius?: ClusterBlastRadius;
  causal_chains?: ClusterCausalChain[];
  uncorrelated_findings?: ClusterDomainAnomaly[];
  domain_reports?: ClusterDomainReport[];
  remediation?: {
    immediate?: ClusterRemediationStep[];
    long_term?: ClusterRemediationStep[];
  };
  execution_metadata?: Record<string, number>;
}

// --- Topology ---
export interface TopologyNode {
  kind: string;
  name: string;
  namespace?: string;
  status?: string;
  node_name?: string;
  labels?: Record<string, string>;
}

export interface TopologySnapshot {
  nodes: Record<string, TopologyNode>;
  edges: Array<{ from_key: string; to_key: string; relation: string }>;
  built_at: string;
  stale: boolean;
  resource_version?: string;
}

// --- Alert Correlation ---
export interface RootCandidate {
  resource_key: string;
  hypothesis: string;
  supporting_signals: string[];
  confidence: number;
}

export interface IssueCluster {
  cluster_id: string;
  alerts: Array<{ resource_key: string; alert_type: string; severity: string }>;
  root_candidates: RootCandidate[];
  confidence: number;
  correlation_basis: string[];
  affected_resources: string[];
}

// --- Causal Firewall ---
export interface BlockedLink {
  from_resource: string;
  to_resource: string;
  reason_code: string;
  invariant_id: string;
  invariant_description: string;
  timestamp?: string;
}

export interface CausalSearchSpace {
  valid_links: Array<Record<string, unknown>>;
  annotated_links: Array<Record<string, unknown>>;
  blocked_links: BlockedLink[];
  total_evaluated: number;
  total_blocked: number;
  total_annotated: number;
}

// --- Guard Mode ---
export interface CurrentRisk {
  category: string;
  severity: string;
  resource: string;
  description: string;
  affected_count: number;
  issue_cluster_id?: string;
}

export interface PredictiveRisk {
  category: string;
  severity: string;
  resource: string;
  description: string;
  predicted_impact: string;
  time_horizon: string;
  trend_data: Array<Record<string, unknown>>;
}

export interface ScanDelta {
  new_risks: string[];
  resolved_risks: string[];
  worsened: string[];
  improved: string[];
  previous_scan_id?: string;
  previous_scanned_at?: string;
}

export interface GuardScanResult {
  scan_id: string;
  scanned_at: string;
  platform: string;
  platform_version: string;
  current_risks: CurrentRisk[];
  predictive_risks: PredictiveRisk[];
  delta: ScanDelta;
  overall_health: 'HEALTHY' | 'DEGRADED' | 'CRITICAL' | 'UNKNOWN';
  risk_score: number;
}

export type CapabilityFormData =
  | TroubleshootAppForm
  | PRReviewForm
  | GithubIssueFixForm
  | ClusterDiagnosticsForm;

// ===== V5 Integration Types =====
export interface Integration {
  id: string;
  name: string;
  cluster_type: 'openshift' | 'kubernetes';
  cluster_url: string;
  auth_method: 'kubeconfig' | 'token' | 'service_account';
  prometheus_url: string | null;
  elasticsearch_url: string | null;
  status: 'active' | 'unreachable' | 'expired';
  auto_discovered: Record<string, unknown>;
  created_at: string;
  last_verified: string | null;
}

// ===== V5 Governance Types =====
export interface EvidencePinData {
  claim: string;
  supporting_evidence: string[];
  source_agent: string;
  source_tool: string;
  confidence: number;
  timestamp: string;
  evidence_type: 'log' | 'metric' | 'trace' | 'k8s_event' | 'code' | 'change';
}

export interface ConfidenceLedgerData {
  log_confidence: number;
  metrics_confidence: number;
  tracing_confidence: number;
  k8s_confidence: number;
  code_confidence: number;
  change_confidence: number;
  critic_adjustment?: number;
  weighted_final: number;
  weights?: Record<string, number>;
}

export interface AttestationGateData {
  gate_type: 'discovery_complete' | 'pre_remediation' | 'post_remediation';
  human_decision: 'approve' | 'reject' | 'modify' | null;
  decided_by: string | null;
  decided_at: string | null;
  proposed_action: string | null;
  findings_count?: number;
  confidence?: number;
}

export interface ReasoningStepData {
  step_number: number;
  timestamp: string;
  decision: string;
  reasoning: string;
  confidence_at_step: number;
}

// ===== V5 Causal Intelligence Types =====

export interface EvidenceNodeData {
  id: string;
  claim: string;
  source_agent: string;
  evidence_type: string;
  node_type: 'symptom' | 'cause' | 'contributing_factor' | 'context';
  confidence: number;
  timestamp: string;
}

export interface CausalEdgeData {
  source_id: string;
  target_id: string;
  relationship: string;
  confidence: number;
  reasoning: string;
}

export interface TimelineEventData {
  timestamp: string;
  source: string;
  event_type: string;
  description: string;
  evidence_node_id?: string;
  severity: 'info' | 'warning' | 'error' | 'critical';
}

export interface ChangeCorrelation {
  change_id: string;
  change_type: 'code_deploy' | 'config_change' | 'infra_change' | 'dependency_update';
  risk_score: number;
  temporal_correlation: number;
  scope_overlap?: number;
  author: string;
  description: string;
  files_changed: string[];
  timestamp: string | null;
  service_name?: string;
  reasoning?: string;
}

export interface HighPriorityFile {
  file_path: string;
  risk_score: number;
  sha: string;
  description: string;
}

export interface HypothesisData {
  hypothesis_id: string;
  description: string;
  confidence: number;
  causal_chain: string[];
}

// ===== V5 Impact & Risk Types =====
export interface BusinessCapabilityImpact {
  capability: string;
  risk_level: 'critical' | 'high' | 'medium' | 'low';
  affected_services: string[];
}

export interface BlastRadiusData {
  primary_service: string;
  upstream_affected: string[];
  downstream_affected: string[];
  shared_resources: string[];
  estimated_user_impact: string;
  scope: 'single_service' | 'service_group' | 'namespace' | 'cluster_wide';
  business_impact?: BusinessCapabilityImpact[];
}

export interface SeverityData {
  recommended_severity: 'P1' | 'P2' | 'P3' | 'P4';
  reasoning: string;
  factors: Record<string, string>;
}

// ===== V5 Post-Mortem Memory Types =====
export interface PastIncidentMatch {
  fingerprint_id: string;
  session_id: string;
  similarity_score: number;
  root_cause: string;
  resolution_steps: string[];
  error_patterns: string[];
  affected_services: string[];
  time_to_resolve: number;
}

// ===== V5 Remediation Types =====

export interface RemediationDecisionData {
  proposed_action: string;
  action_type: 'restart' | 'scale' | 'rollback' | 'config_change' | 'code_fix';
  is_destructive: boolean;
  dry_run_available: boolean;
  rollback_plan: string;
  pre_checks: string[];
  post_checks: string[];
}

export interface RunbookMatchData {
  runbook_id: string;
  title: string;
  match_score: number;
  steps: string[];
  success_rate: number;
  source: 'internal' | 'vendor' | 'ai_generated';
}

// ===== Incident Closure Types =====

export type ClosurePhase = 'not_started' | 'remediation' | 'tracking' | 'knowledge' | 'closed';

export interface JiraActionResult {
  status: 'success' | 'failed' | 'skipped';
  issue_key: string;
  issue_url: string;
  error: string;
  created_at: string | null;
}

export interface RemedyActionResult {
  status: 'success' | 'failed' | 'skipped';
  incident_number: string;
  incident_url: string;
  error: string;
  created_at: string | null;
}

export interface ConfluenceActionResult {
  status: 'success' | 'failed' | 'skipped';
  page_id: string;
  page_url: string;
  space_key: string;
  error: string;
  created_at: string | null;
}

export interface IntegrationAvailability {
  configured: boolean;
  status: string;
  has_credentials: boolean;
}

// M7: Fields marked optional — backend may send partial closure state
export interface IncidentClosureState {
  phase: ClosurePhase;
  jira_result?: JiraActionResult;
  remedy_result?: RemedyActionResult;
  confluence_result?: ConfluenceActionResult;
  postmortem_preview?: string;
  closed_at?: string | null;
}

export interface ClosureStatusResponse {
  closure_state: IncidentClosureState;
  integrations: Record<'jira' | 'confluence' | 'remedy', IntegrationAvailability>;
  can_start_closure: boolean;
  pre_filled: {
    jira_summary: string;
    jira_description: string;
    jira_priority: string;
    remedy_summary: string;
    remedy_urgency: string;
    confluence_title: string;
  };
}

export interface PostmortemDossierData {
  title: string;
  body_markdown: string;
  executive_summary: string;
  impact_statement: string;
}

/* ── Cluster War Room UI types ─────────────────── */

export type ClusterDomainKey = 'ctrl_plane' | 'node' | 'network' | 'storage';

export interface FleetNode {
  name: string;
  status: 'healthy' | 'warning' | 'critical' | 'unknown';
  cpu_pct?: number;
  memory_pct?: number;
  disk_pressure?: boolean;
  pod_count?: number;
}

export interface NamespaceWorkload {
  namespace: string;
  status: 'Healthy' | 'Degraded' | 'Critical' | 'Unknown';
  replica_status?: string;
  last_deploy?: string;
  workloads?: WorkloadDetail[];
}

export interface WorkloadDetail {
  name: string;
  kind: 'Deployment' | 'StatefulSet' | 'DaemonSet' | 'CronJob' | 'Job' | 'Pod';
  status: 'Running' | 'CrashLoopBackOff' | 'Pending' | 'Failed' | 'Completed';
  restarts?: number;
  cpu_usage?: string;
  memory_usage?: string;
  age?: string;
  is_trigger?: boolean;
}

export interface VerdictEvent {
  timestamp: string;
  severity: 'FATAL' | 'WARN' | 'INFO';
  message: string;
  domain?: ClusterDomainKey;
}

// ── Live Investigation Steering ──────────────────────────────────────

export interface RouterContext {
  active_namespace: string | null;
  active_service: string | null;
  active_pod: string | null;
  time_window: { start: string; end: string };
  session_id: string;
  incident_id: string;
  discovered_services: string[];
  discovered_namespaces: string[];
  pod_names: string[];
  active_findings_summary: string;
  last_agent_phase: string;
  elk_index?: string;
}

export interface QuickActionPayload {
  intent: string;
  params: Record<string, unknown>;
}

export interface InvestigateRequest {
  command?: string;
  query?: string;
  quick_action?: QuickActionPayload;
  context: RouterContext;
}

export interface InvestigateResponse {
  pin_id: string;
  intent: string;
  params: Record<string, unknown>;
  path_used: 'fast' | 'smart';
  status: 'executing' | 'error';
  error?: string;
}

export type EvidencePinDomain = 'compute' | 'network' | 'storage' | 'control_plane' | 'security' | 'unknown';
export type ValidationStatus = 'pending_critic' | 'validated' | 'rejected';
export type CausalRole = 'root_cause' | 'cascading_symptom' | 'correlated' | 'informational';

export interface EvidencePinV2 {
  id: string;
  claim: string;
  source: 'auto' | 'manual';
  source_agent: string | null;
  source_tool: string;
  triggered_by: 'automated_pipeline' | 'user_chat' | 'quick_action';
  evidence_type: string;
  supporting_evidence: string[];
  raw_output: string | null;
  confidence: number;
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info' | null;
  causal_role: CausalRole | null;
  domain: EvidencePinDomain;
  validation_status: ValidationStatus;
  namespace: string | null;
  service: string | null;
  resource_name: string | null;
  timestamp: string;
  time_window: { start: string; end: string } | null;
}

// ── War Room v2 Types ──────────────────────────────────────────────────

export interface ResourceRef {
  type: string;
  name: string;
  namespace: string | null;
  status: string | null;
  age: string | null;
}

export interface CommandStep {
  order: number;
  description: string;
  command: string;
  command_type: 'kubectl' | 'oc' | 'helm' | 'shell';
  is_dry_run: boolean;
  dry_run_command: string | null;
  validation_command: string | null;
}

export interface OperationalRecommendation {
  id: string;
  title: string;
  urgency: 'immediate' | 'short_term' | 'preventive';
  category: 'scale' | 'rollback' | 'restart' | 'config_patch' | 'network' | 'storage';
  commands: CommandStep[];
  rollback_commands: CommandStep[];
  risk_level: 'safe' | 'caution' | 'destructive';
  prerequisites: string[];
  expected_outcome: string;
  resource_refs: ResourceRef[];
}

export type TriageStatus = 'untriaged' | 'acknowledged' | 'mitigated' | 'resolved';

export interface CausalTree {
  id: string;
  root_cause: Finding;
  severity: 'critical' | 'warning' | 'info';
  blast_radius: BlastRadiusData | null;
  cascading_symptoms: Finding[];
  correlated_signals: CorrelatedSignalGroup[];
  operational_recommendations: OperationalRecommendation[];
  triage_status: TriageStatus;
  resource_refs: ResourceRef[];
}

export interface TelescopeResource {
  yaml: string;
  events: K8sEvent[];
  error?: string;
}

export interface TelescopeResourceLogs {
  logs: string;
  error?: string;
}

export interface ToolParam {
  name: string;
  type: 'string' | 'select' | 'number' | 'boolean';
  required: boolean;
  default_from_context?: string;
  options?: string[];
  placeholder?: string;
}

export interface ToolDefinition {
  intent: string;
  label: string;
  icon: string;
  slash_command: string;
  category: 'logs' | 'metrics' | 'cluster' | 'network' | 'security' | 'code';
  description: string;
  params_schema: ToolParam[];
  requires_context: string[];
}
