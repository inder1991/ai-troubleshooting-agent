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

// ===== Diagnostic Scope =====

export interface DiagnosticScope {
  level: 'cluster' | 'namespace' | 'workload' | 'component';
  namespaces: string[];
  workload_key?: string;
  domains: string[];
  include_control_plane: boolean;
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
  | 'cancelled'
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
  start_offset_ms?: number;
  trace_id?: string;
  critical_path?: boolean;
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
  event_type: 'started' | 'progress' | 'success' | 'warning' | 'error' | 'tool_call' | 'phase_change' | 'finding' | 'summary' | 'attestation_required' | 'auto_approved' | 'fix_proposal' | 'fix_approved' | 'waiting_for_input' | 'reasoning' | 'thinking';
  message: string;
  timestamp: string;
  sequence_number?: number;
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
  capability?: CapabilityType;
  findings_count?: number;
  critical_count?: number;
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

export interface PendingAction {
  type: 'attestation_required' | 'fix_approval' | 'repo_confirm' | 'campaign_execute_confirm' | 'code_agent_question';
  blocking: boolean;
  actions: string[];
  expires_at: string | null;
  context: Record<string, unknown>;
  version: number;
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
  capability?: CapabilityType;
  pending_action: PendingAction | null;
}

export interface SuggestedPromQLQuery {
  metric: string;
  query: string;
  rationale: string;
}

// ── Multi-hypothesis engine types ─────────────────────────────────────

export interface HypothesisEvidenceSummary {
  signal_name: string;
  signal_type: string;
  source_agent: string;
  strength: number;
}

export interface DiagHypothesis {
  hypothesis_id: string;
  category: string;
  status: 'active' | 'eliminated' | 'winner';
  confidence: number;
  evidence_for: HypothesisEvidenceSummary[];
  evidence_against: HypothesisEvidenceSummary[];
  evidence_for_count: number;
  evidence_against_count: number;
  downstream_effects: string[];
  elimination_reason: string | null;
  elimination_phase: string | null;
}

export interface HypothesisEliminationEntry {
  hypothesis_id: string;
  reason: string;
  phase: string;
  confidence: number;
}

export interface DiagHypothesisResult {
  status: 'resolved' | 'inconclusive';
  winner_id: string | null;
  elimination_log: HypothesisEliminationEntry[];
  recommendations: string[];
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
  evidence_graph?: EvidenceGraphData;
  // Multi-hypothesis engine
  hypotheses?: DiagHypothesis[];
  hypothesis_result?: DiagHypothesisResult;
  // Diagnostic scope (returned by backend)
  diagnostic_scope?: DiagnosticScope;
  scope_coverage?: number;
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
  | 'not_started' | 'queued' | 'generating' | 'retrying' | 'awaiting_review'
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
  scope?: DiagnosticScope;
  // Ad-hoc cluster auth fields (used when no saved profile / use_temp_cluster)
  auth_method?: 'token' | 'kubeconfig' | 'service_account';
  auth_token?: string;
  kubeconfig_content?: string;
  role?: string;
  // Database diagnostics fields
  focus?: ('queries' | 'connections' | 'replication' | 'storage' | 'schema')[];
  database_type?: 'postgres' | 'mongodb';
  sampling_mode?: 'light' | 'standard' | 'deep';
  include_explain_plans?: boolean;
  parent_session_id?: string;
  table_filter?: string[];
  extra?: Record<string, unknown>;
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
  | 'cluster_diagnostics'
  | 'network_troubleshooting'
  | 'database_diagnostics'
  | 'troubleshoot_pipeline';

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
  auth_method?: 'token' | 'kubeconfig' | 'service_account';
  kubeconfig_content?: string;   // for temporary cluster only
  role?: string;                 // RBAC role metadata for temp cluster
  elk_index?: string;            // optional ELK log index
  use_temp_cluster?: boolean;    // true when user chose "Use a different cluster"
  resource_type?: string;
  workload?: string;
  include_control_plane?: boolean;
  profile_id?: string;
  save_cluster?: boolean;
  cluster_name?: string;
}

export interface NetworkTroubleshootingForm {
  capability: 'network_troubleshooting';
  src_ip: string;
  dst_ip: string;
  port: string;
  protocol: 'tcp' | 'udp';
}

export interface DatabaseDiagnosticsForm {
  capability: 'database_diagnostics';
  profile_id: string;
  time_window: '15m' | '1h' | '6h' | '24h';
  focus: ('queries' | 'connections' | 'replication' | 'storage' | 'schema')[];
  table_filter?: string[];
  database_type: 'postgres' | 'mongodb';
  connection_uri?: string;
  sampling_mode: 'light' | 'standard' | 'deep';
  include_explain_plans: boolean;
  parent_session_id?: string;
  context_source?: 'user_selected' | 'auto_triggered';
}

// ===== Cluster Diagnostics Types =====
export interface ClusterDomainAnomaly {
  domain: string;
  anomaly_id: string;
  description: string;
  evidence_ref: string;
  severity?: 'high' | 'medium' | 'low';
}

export interface ClusterDomainReport {
  domain: string;
  status: 'PENDING' | 'RUNNING' | 'SUCCESS' | 'PARTIAL' | 'FAILED' | 'SKIPPED';
  failure_reason?: string;
  confidence: number;
  anomalies: ClusterDomainAnomaly[];
  ruled_out: string[];
  evidence_refs: string[];
  truncation_flags: Record<string, boolean | number>;
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
  affected_namespaces: string[];
  affected_pods: string[];
  affected_nodes: string[];
}

export interface ClusterRemediationStep {
  command?: string;
  description: string;
  risk_level?: string;
  effort_estimate?: string;
  rollback?: string;
  pre_check?: string;
  verify?: string;
  expected_output?: string;
  dry_run?: string;
  validation_errors?: string[];
  validation?: SolutionValidation;
}

export interface ClusterHealthReport {
  session_id?: string;
  diagnostic_id?: string;
  platform: string;
  platform_version: string;
  platform_health: 'HEALTHY' | 'DEGRADED' | 'CRITICAL' | 'UNKNOWN' | 'PENDING' | 'PARTIAL_TIMEOUT';
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
  scan_mode?: string;
  diagnostic_scope?: DiagnosticScope;
  scope_coverage?: number;
  issue_clusters?: IssueCluster[];
  causal_search_space?: CausalSearchSpace;
  topology_snapshot?: TopologySnapshot;
  diagnostic_issues?: DiagnosticIssue[];
  critical_incidents?: DiagnosticIssue[];
  other_findings?: DiagnosticIssue[];
  symptom_map?: Record<string, string>;
  ranked_hypotheses?: RankedHypothesis[];
  hypothesis_selection?: { root_causes: RankedHypothesis[]; selection_method: string; llm_reasoning_needed: boolean };
  issue_lifecycle_summary?: Record<IssueLifecycleState, number>;
  signals_count?: number;
  pattern_matches_count?: number;
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

// ---------------------------------------------------------------------------
// Diagnostic Intelligence types
// ---------------------------------------------------------------------------

export type IssueLifecycleState =
  | 'ACTIVE_DISRUPTION' | 'WORSENING' | 'NEW' | 'EXISTING'
  | 'LONG_STANDING' | 'INTERMITTENT' | 'SYMPTOM' | 'RESOLVED' | 'ACKNOWLEDGED';

export interface DiagnosticIssue {
  issue_id: string;
  state: IssueLifecycleState;
  priority_score: number;
  first_seen: string;
  last_state_change: string;
  state_duration_seconds: number;
  event_count_recent: number;
  event_count_baseline: number;
  restart_velocity: number;
  severity_trend: string;
  is_root_cause: boolean;
  is_symptom: boolean;
  root_cause_id: string;
  blast_radius: number;
  affected_resources: string[];
  signals: string[];
  pattern_matches: string[];
  anomaly_ids: string[];
  description: string;
  severity: string;
}

export interface RankedHypothesis {
  hypothesis_id: string;
  cause: string;
  cause_type: string;
  source: string;
  confidence: number;
  evidence_score: number;
  contradiction_penalty: number;
  explains_count: number;
  blast_radius: number;
  root_resource: string;
  causal_chain: string[];
  depth: number;
  supporting_evidence: { signal_type: string; relevance: string; weight: number }[];
  contradicting_evidence: { signal_type: string; relevance: string; weight: number }[];
}

export interface RemediationSimulation {
  action: string;
  target: string;
  impact: string;
  side_effects: string[];
  recovery: string;
}

export interface SolutionValidation {
  risk_level: string;
  warnings: string[];
  requires_confirmation: boolean;
  blocked: boolean;
  block_reason?: string;
  simulation?: RemediationSimulation;
  remediation_confidence: number;
  confidence_label: string;
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
  | ClusterDiagnosticsForm
  | NetworkTroubleshootingForm
  | DatabaseDiagnosticsForm
  | PipelineCapabilityForm;

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

export interface ReasoningStepData {
  step_number: number;
  timestamp: string;
  decision: string;
  reasoning: string;
  confidence_at_step: number;
  agent?: string;
  description?: string;
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

export type ClusterDomainKey = 'ctrl_plane' | 'node' | 'network' | 'storage' | 'rbac';

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

// Evidence Graph types (Phase 1)
export interface GraphNode {
  id: string;
  node_type: 'error_event' | 'metric_anomaly' | 'k8s_event' | 'trace_span' | 'code_change' | 'config_change' | 'code_location';
  data: Record<string, unknown>;
  timestamp: number;
  confidence: number;
  severity: string;
  agent_source: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  edge_type: 'causes' | 'triggers' | 'manifests_as' | 'correlates_with' | 'precedes' | 'located_in';
  confidence: number;
  reasoning: string;
  created_by: string;
  temporal_delta_ms?: number;
}

export interface CausalPath {
  root: string;
  leaf: string;
  path: string[];
  total_confidence: number;
}

export interface EvidenceGraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  root_causes: Array<{ node_id: string; score: number }>;
  causal_paths: CausalPath[];
}

// Chat Tool Call types (Phase 2)
export interface ChatToolCallEvent {
  tool: string;
  input: Record<string, unknown>;
  status: 'running' | 'complete' | 'error';
  result_summary?: string;
  tool_use_id?: string;
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

// ===== Agent Matrix Types =====

export interface AgentLLMConfig {
  model: string;
  temperature: number;
  context_window: number;
  mode: string;
}

export interface AgentExecution {
  session_id: string;
  timestamp: string;
  status: string;
  duration_ms: number;
  confidence: number;
  summary: string;
  trace?: AgentTraceEntry[];
}

export interface AgentTraceEntry {
  timestamp: string;
  level: 'info' | 'warn' | 'error';
  message: string;
}

export interface AgentInfo {
  id: string;
  name: string;
  workflow: 'app_diagnostics' | 'cluster_diagnostics' | 'database_diagnostics' | 'assistant';
  role: 'orchestrator' | 'analysis' | 'validation' | 'fix_generation' | 'domain_expert';
  description: string;
  icon: string;
  level: number;
  llm_config: AgentLLMConfig;
  timeout_s: number;
  tools: string[];
  tool_health_checks: Record<string, string>;
  architecture_stages: string[];
  status: 'active' | 'degraded' | 'offline';
  degraded_tools: string[];
  recent_executions: AgentExecution[];
}

export interface AgentMatrixSummary {
  total: number;
  active: number;
  degraded: number;
  offline: number;
}

export interface AgentMatrixResponse {
  agents: AgentInfo[];
  summary: AgentMatrixSummary;
}

export interface AgentExecutionsResponse {
  agent_id: string;
  executions: AgentExecution[];
}

// ===== Adapter Instance Types =====

export interface AdapterInstance {
  instance_id: string;
  label: string;
  vendor: string;
  api_endpoint: string;
  extra_config: Record<string, unknown>;
  device_groups: string[];
  created_at: string;
  updated_at: string;
}

export interface AdapterInstanceStatus extends AdapterInstance {
  status: 'connected' | 'stale' | 'auth_failed' | 'unreachable' | 'not_configured';
  message: string;
  snapshot_age_seconds: number;
  last_refresh: string;
}

export interface DeviceGroupInfo {
  name: string;
  serial_numbers: string[];
  connected_devices: number;
}

// ===== Network Troubleshooting Types =====

export interface NetworkFindingsState {
  diagnosis_status?: string;
  confidence?: number;
  confidence_breakdown?: {
    path_confidence: number;
    path_source: string;
    firewall_confidence: number;
    contradiction_bonus: number;
    penalties: Array<{ type: string; impact: number }>;
    overall: number;
  };
  executive_summary?: string;
  final_path?: {
    hops: string[];
    source: string;
    hop_count: number;
    has_nat: boolean;
    blocked: boolean;
  };
  firewall_verdicts?: Array<{
    device_id: string;
    device_name: string;
    action: string;
    rule_id?: string;
    rule_name?: string;
    confidence: number;
    match_type: string;
    details?: string;
    matched_source?: string;
    matched_destination?: string;
    matched_ports?: string;
    security_grade?: string;
  }>;
  nat_translations?: Array<{
    device_id: string;
    direction: string;
    original_src?: string;
    translated_src?: string;
    original_dst?: string;
    translated_dst?: string;
  }>;
  identity_chain?: Array<{
    stage: string;
    ip: string;
    port: number;
    device_id?: string;
  }>;
  trace_hops?: Array<{
    hop_number: number;
    ip: string;
    rtt_ms: number;
    status: string;
    device_id?: string;
    device_name?: string;
    attribution_confidence?: number;
  }>;
  contradictions?: Array<{
    type: string;
    detail: string;
  }>;
  next_steps?: string[];
  evidence?: Array<{
    type: string;
    detail: string;
  }>;
  nacl_verdicts?: NACLVerdict[];
  vpc_boundary_crossings?: VPCCrossing[];
  vpn_segments?: VPNSegment[];
  load_balancers_in_path?: LBHop[];
}

export interface NetworkFindings {
  session_id: string;
  flow_id: string;
  phase: string;
  error?: string;
  return_state?: NetworkFindingsState;
  state: {
    diagnosis_status?: string;
    confidence?: number;
    confidence_breakdown?: {
      path_confidence: number;
      path_source: string;
      firewall_confidence: number;
      contradiction_bonus: number;
      penalties: Array<{ type: string; impact: number }>;
      overall: number;
    };
    executive_summary?: string;
    final_path?: {
      hops: string[];
      source: string;
      hop_count: number;
      has_nat: boolean;
      blocked: boolean;
    };
    firewall_verdicts?: Array<{
      device_id: string;
      device_name: string;
      action: string;
      rule_id?: string;
      rule_name?: string;
      confidence: number;
      match_type: string;
      details?: string;
      matched_source?: string;
      matched_destination?: string;
      matched_ports?: string;
      security_grade?: string;
    }>;
    nat_translations?: Array<{
      device_id: string;
      direction: string;
      original_src?: string;
      translated_src?: string;
      original_dst?: string;
      translated_dst?: string;
    }>;
    identity_chain?: Array<{
      stage: string;
      ip: string;
      port: number;
      device_id?: string;
    }>;
    trace_hops?: Array<{
      hop_number: number;
      ip: string;
      rtt_ms: number;
      status: string;
      device_id?: string;
      device_name?: string;
      attribution_confidence?: number;
    }>;
    contradictions?: Array<{
      type: string;
      detail: string;
    }>;
    next_steps?: string[];
    evidence?: Array<{
      type: string;
      detail: string;
    }>;
    nacl_verdicts?: NACLVerdict[];
    vpc_boundary_crossings?: VPCCrossing[];
    vpn_segments?: VPNSegment[];
    load_balancers_in_path?: LBHop[];
  };
}

// ===== Enterprise Network Types =====

export interface VPCInfo {
  id: string; name: string; cloud_provider: 'aws'|'azure'|'gcp'|'oci';
  region: string; cidr_blocks: string[]; account_id: string; compliance_zone: string;
}

export interface VPNTunnelInfo {
  id: string; name: string; tunnel_type: 'ipsec'|'gre'|'ssl';
  encryption: string; status: 'up'|'down'|'degraded';
}

export interface DirectConnectInfo {
  id: string; name: string; provider: 'aws_dx'|'azure_er'|'oci_fc';
  bandwidth_mbps: number; status: 'up'|'down'|'degraded';
}

export interface NACLVerdict {
  nacl_id: string; nacl_name: string; action: 'allow'|'deny';
  inbound: { action: string; rule_number: number; matched_rule_id: string };
  outbound: { action: string; rule_number: number; matched_rule_id: string };
}

export interface VPCCrossing {
  from_vpc: string; to_vpc: string;
}

export interface VPNSegment {
  device_id: string; name: string; tunnel_type: string; encryption: string;
}

export interface LBHop {
  device_id: string; device_name: string; device_type: string;
}


// ── IPAM Types ──

export type IPStatus = 'available' | 'reserved' | 'assigned' | 'deprecated';
export type IPType = 'static' | 'dynamic' | 'gateway' | 'network' | 'broadcast';

export interface IPAddress {
  id: string;
  address: string;
  subnet_id: string;
  status: IPStatus;
  ip_type: IPType;
  assigned_device_id: string;
  assigned_interface_id: string;
  hostname: string;
  mac_address: string;
  vendor: string;
  description: string;
  last_seen: string;
  created_at: string;
  owner_team: string;
  application: string;
  environment: string;
  discovery_source: string;
  confidence_score: number;
}

export interface IPAuditEvent {
  id: number;
  ip_id: string;
  address: string;
  action: string;
  old_status: string;
  new_status: string;
  device_id: string;
  details: string;
  timestamp: string;
}

export interface IPConflict {
  address: string;
  cnt: number;
  subnet_ids: string;
  statuses: string;
}

export interface IPAMSubnet {
  id: string;
  cidr: string;
  vlan_id: number;
  zone_id: string;
  gateway_ip: string;
  description: string;
  site: string;
  parent_subnet_id: string;
  region: string;
  environment: string;
  ip_version: number;
  vpc_id: string;
  cloud_provider: string;
  vrf_id: string;
  subnet_role: string;
  address_block_id: string;
  site_id: string;
  total?: number;
  available?: number;
  assigned?: number;
  reserved?: number;
  deprecated?: number;
  utilization_pct?: number;
}

export interface DNSMismatch {
  type: 'missing_hostname' | 'duplicate_hostname';
  address?: string;
  hostname?: string;
  subnet_cidr?: string;
  device_id?: string;
  count?: number;
  addresses?: string;
  detail: string;
}

export interface CapacityForecast {
  subnet_id: string;
  cidr: string;
  region: string;
  environment: string;
  total: number;
  available: number;
  assigned: number;
  reserved: number;
  utilization_pct: number;
  days_until_full: number | null;
  risk_level: 'critical' | 'warning' | 'ok';
}

export interface IPAMDevice {
  id: string;
  name: string;
  management_ip: string;
  device_type: string;
  zone_id: string;
  vlan_id: number;
  description: string;
  vendor: string;
  location: string;
}

export interface IPAMTreeNode {
  id: string;
  label: string;
  type: 'global' | 'region' | 'vpc' | 'zone' | 'subnet' | 'site' | 'vrf' | 'address_block';
  cidr?: string;
  utilization_pct?: number;
  children: IPAMTreeNode[];
}

export interface IPAMStats {
  total_subnets: number;
  total_ips: number;
  assigned_ips: number;
  available_ips: number;
  reserved_ips: number;
  deprecated_ips: number;
  overall_utilization_pct: number;
}

export interface DHCPScope {
  id: string;
  name: string;
  scope_cidr: string;
  server_ip: string;
  subnet_id: string;
  total_leases: number;
  active_leases: number;
  free_count: number;
  source: string;
  last_updated: string;
}

export interface ReportTemplate {
  id: string;
  name: string;
  type: 'subnet_inventory' | 'ip_allocation' | 'conflict_report' | 'capacity_forecast';
  description: string;
}

// ── Enterprise IPAM Types ──

export interface VRFInfo {
  id: string;
  name: string;
  rd: string;
  rt_import: string[];
  rt_export: string[];
  description: string;
  device_ids: string[];
  is_default: boolean;
}

export interface RegionInfo {
  id: string;
  name: string;
  description: string;
}

export interface SiteInfo {
  id: string;
  name: string;
  region_id: string;
  site_type: string;
  address: string;
  description: string;
}

export interface AddressBlockInfo {
  id: string;
  cidr: string;
  name: string;
  vrf_id: string;
  site_id: string;
  description: string;
  rir: string;
}

export interface CloudAccountInfo {
  id: string;
  name: string;
  provider: string;
  account_id: string;
  region: string;
  credentials_ref: string;
  sync_enabled: boolean;
  last_sync: string;
}

export interface ReservedRange {
  id: string;
  subnet_id: string;
  start_ip: string;
  end_ip: string;
  reason: string;
  owner_team: string;
  created_at: string;
}

export interface IPCorrelationChain {
  ip: { address: string; status: string; owner_team: string };
  interface?: { name: string; status: string; vlan_id: number };
  device?: { name: string; status: string; latency_ms: number };
  vlan?: { vlan_number: number; name: string };
  subnet?: { cidr: string; utilization_pct: number; subnet_role: string };
}

export interface VLANInfo {
  id: string;
  vlan_number: number;
  name: string;
  description: string;
  vrf_id: string;
  site_id: string;
  subnet_ids: string[];
}

// ===== Protocol-First Device Monitoring Types =====

export interface SNMPCredentials {
  version: '1' | '2c' | '3';
  community: string;
  port: number;
  v3_user?: string;
  v3_auth_protocol?: string;
  v3_auth_key?: string;
  v3_priv_protocol?: string;
  v3_priv_key?: string;
}

export interface ProtocolConfig {
  protocol: 'snmp' | 'gnmi' | 'restconf' | 'ssh_cli' | 'cloud_api';
  priority: number;
  enabled: boolean;
  snmp?: SNMPCredentials;
}

export interface PingConfig {
  enabled: boolean;
  count: number;
  interval: number;
  timeout: number;
}

export interface PingResult {
  rtt_avg: number;
  rtt_min: number;
  rtt_max: number;
  packet_loss_pct: number;
  reachable: boolean;
  timestamp: number;
}

export interface MonitoredDevice {
  device_id: string;
  hostname: string;
  management_ip: string;
  sys_object_id: string | null;
  matched_profile: string | null;
  vendor: string;
  model: string;
  os_family: string;
  protocols: ProtocolConfig[];
  vendor_adapter_id: string | null;
  discovered: boolean;
  tags: string[];
  ping_config: PingConfig | null;
  last_collected: number | null;
  last_ping: PingResult | null;
  status: 'up' | 'down' | 'unreachable' | 'new';
  neighbors?: DeviceNeighbor[];
}

export interface DeviceNeighbor {
  device_id: string;
  hostname: string;
  relationship: 'parent' | 'child' | 'peer';
}

export interface DiscoveryConfig {
  config_id: string;
  cidr: string;
  snmp_version: '1' | '2c' | '3';
  community: string;
  v3_user?: string;
  v3_auth_protocol?: string;
  v3_auth_key?: string;
  v3_priv_protocol?: string;
  v3_priv_key?: string;
  port: number;
  interval_seconds: number;
  excluded_ips: string[];
  tags: string[];
  ping: PingConfig;
  enabled: boolean;
  last_scan: number | null;
  devices_found: number;
}

export interface DeviceProfileSummary {
  name: string;
  vendor: string;
  device_type: string;
  sysobjectid_patterns: string[];
  metric_count: number;
}

export interface CollectedDataResult {
  device_id: string;
  protocol: string;
  timestamp: number;
  cpu_pct: number | null;
  mem_pct: number | null;
  uptime_seconds: number | null;
  temperature: number | null;
  interface_metrics: Record<string, Record<string, number>>;
  metadata: Record<string, string>;
  custom_metrics: Record<string, number>;
}

export interface CollectorHealthStatus {
  status: string;
  device_count: number;
  discovery_config_count: number;
  profile_count: number;
  snmp_available: boolean;
  pysnmp_available: boolean;
}

// ===== NDM Enhanced Types =====

export interface TrapEvent {
  event_id: string;
  device_ip: string;
  device_id: string | null;
  oid: string;
  value: string;
  severity: 'critical' | 'major' | 'minor' | 'warning' | 'info';
  timestamp: number;
}

export interface SyslogEntry {
  event_id: string;
  device_ip: string;
  device_id: string | null;
  facility: string;
  severity: string;
  severity_code: number;
  hostname: string;
  app_name: string;
  message: string;
  timestamp: number;
}

export interface FlowConversation {
  src_ip: string;
  dst_ip: string;
  bytes: number;
  packets: number;
  flows: number;
  avg_latency: number;
}

export interface FlowApplication {
  app_name: string;
  bytes: number;
  packets: number;
  flows: number;
  percentage: number;
}

export interface FlowASN {
  asn: number;
  bytes: number;
  packets: number;
  flows: number;
}

export interface FlowVolumePoint {
  time: string;
  bytes: number;
  packets: number;
}

export interface InterfaceMetrics {
  name: string;
  status: 'up' | 'down' | 'unknown';
  speed: number;
  in_octets: number;
  out_octets: number;
  in_errors: number;
  out_errors: number;
  in_discards: number;
  out_discards: number;
  utilization_pct: number;
}

export interface DeviceMetricsSnapshot {
  device_id: string;
  cpu_pct: number | null;
  mem_pct: number | null;
  uptime_seconds: number | null;
  temperature: number | null;
  interface_metrics: Record<string, Record<string, number>>;
}

export interface DeviceMetricsHistory {
  timestamps: string[];
  cpu_pct: (number | null)[];
  mem_pct: (number | null)[];
  temperature: (number | null)[];
}

export interface TrapSummary {
  counts_by_severity: Record<string, number>;
  top_oids: Array<{ oid: string; count: number }>;
}

export interface SyslogSummary {
  counts_by_severity: Record<string, number>;
  counts_by_facility: Record<string, number>;
}

export type NDMTabType = 'overview' | 'devices' | 'interfaces' | 'netflow' | 'syslog' | 'traps' | 'topology';

// ===== Environment Health Types =====

export interface HealthNode {
  id: string;
  name: string;
  type: 'cluster' | 'database' | 'network' | 'service';
  status: 'healthy' | 'degraded' | 'critical' | 'offline';
  latencyMs?: number;
}

// ── Cloud Integration Types ──

export interface CloudAccount {
  account_id: string;
  provider: 'aws' | 'azure' | 'oracle' | 'gcp';
  display_name: string;
  auth_method: string;
  regions: string[];
  sync_enabled: boolean;
  last_sync_status: 'never' | 'ok' | 'error' | 'paused';
  consecutive_failures: number;
}

export interface CloudResource {
  resource_id: string;
  provider: string;
  account_id: string;
  region: string;
  resource_type: string;
  native_id: string;
  name: string | null;
  raw_preview: string | null;
  tags: string | null;
  sync_tier: number;
  last_seen_ts: string;
  is_deleted: boolean;
  deleted_at: string | null;
}

export interface CloudResourceDetail extends CloudResource {
  raw: Record<string, unknown> | null;
  raw_compressed?: never;  // excluded from API response
}

export interface CloudResourceRelation {
  relation_id: string;
  source_resource_id: string;
  target_resource_id: string;
  relation_type: string;
  metadata: string | null;
  last_seen_ts: string;
}

export interface CloudSyncJob {
  sync_job_id: string;
  account_id: string;
  tier: number;
  started_at: string;
  finished_at: string | null;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'paused';
  items_seen: number;
  items_created: number;
  items_updated: number;
  items_deleted: number;
  api_calls: number;
}

export interface CloudSyncStatus {
  tier_1_last_sync: string | null;
  tier_2_last_sync: string | null;
  tier_3_last_sync: string | null;
  next_sync: string | null;
}

// ── Notification / Alert Routing Types ──

export interface NotificationChannel {
  id: string;
  name: string;
  type: 'slack' | 'email' | 'webhook' | 'pagerduty';
  config: Record<string, string>;
}

export interface AlertRouting {
  id: string;
  rule_id: string;
  rule_name?: string;
  channel_id: string;
  channel_name?: string;
}

export interface EscalationStep {
  level: number;
  channel_id: string;
  wait_minutes: number;
  channel_name?: string;
}

export interface EscalationPolicy {
  id: string;
  name: string;
  steps: EscalationStep[];
}

// ── Audit Log Types ──

export interface AuditLogEntry {
  id: string;
  timestamp: string;
  user: string;
  action: string;
  entity_type: string;
  entity_id: string;
  details: string;
  ip: string;
}

// ── Navigator Aliases ──

export type ReasoningStep = ReasoningStepData;

export interface AgentConfidence {
  agent: string;
  confidence: number;
  reasoning: string;
}

// ── MIB Browser Types ──

export interface MIBEntry {
  oid: string;
  name: string;
  module: string;
  description: string;
  syntax: string;
  access: 'read-only' | 'read-write' | 'read-create' | 'not-accessible' | 'accessible-for-notify';
  status: 'current' | 'deprecated' | 'obsolete' | 'mandatory';
  value?: string | number | null;
  children?: string[];
}

// ── Alert History Types ──

export interface AlertHistoryEntry {
  id: string;
  timestamp: number;
  severity: 'critical' | 'warning' | 'info';
  entity_id: string;
  metric: string;
  message: string;
  state: 'firing' | 'resolved';
  duration?: number;
}

// ── Composite Alert Types ──

export interface CompositeAlertCondition {
  metric: string;
  operator: string;
  threshold: number;
}

export interface CompositeAlertRule {
  id: string;
  name: string;
  logic: 'AND' | 'OR';
  duration_seconds: number;
  conditions: CompositeAlertCondition[];
  severity?: string;
  created_at?: string;
}

// ── DNS Monitoring Types ──

export interface DNSServer {
  id: string;
  ip: string;
  name?: string;
  status: string;
}

export interface DNSWatchedHostname {
  hostname: string;
  record_type: string;
}

export interface DNSMetrics {
  queries_total: number;
  total_queries: number;
  avg_latency_ms: number;
  nxdomain_count: number;
  success_rate: number;
}

export interface DNSQueryResult {
  hostname: string;
  record_type: string;
  server_ip: string;
  values: string[];
  records: Array<{ value: string; ttl: number }>;
  latency_ms: number;
  success: boolean;
  status: string;
  error: string | null;
}

export interface DNSNXDomainEntry {
  hostname: string;
  count: number;
  first_seen: string;
  last_seen: string;
}

// ── Topology Design Types ──

export type DesignStatus = 'draft' | 'reviewed' | 'simulated' | 'approved' | 'parked' | 'applied' | 'verified';

export interface TopologyDesign {
  id: string;
  name: string;
  description: string;
  status: DesignStatus;
  snapshot_json: string;
  version: number;
  created_at: string;
  updated_at: string;
  applied_by?: string;
}

export interface DesignDiff {
  added: Array<{ id: string; data?: { label?: string; deviceType?: string; ip?: string; vendor?: string } }>;
  new_edges: Array<{ source: string; target: string; data?: { label?: string } }>;
  conflicts: Array<{ type: string; ip?: string; planned_device?: string; conflicts_with?: string; planned_subnet?: string; vlan_id?: string; zone?: string }>;
  edge_errors: Array<{ edge_id: string; reason: string }>;
  live_count: number;
  can_apply: boolean;
}

// ── Topology Path Types ──

export interface TopologyPathHop {
  device_name: string;
  ip: string;
}

export interface TopologyPath {
  hops: TopologyPathHop[];
  latency_ms: number;
  confidence: number;
}

// ── Simulation Types ──

export interface SimulationResult {
  summary: { errors: number; warnings: number; passed: number };
  integrity_checks: Array<{ severity: 'error' | 'warning'; type: string; device?: string; description: string }>;
  connectivity_tests: Array<{ result: string; source: string; target: string; blocked_by?: string }>;
}

// ---------------------------------------------------------------------------
// Cluster Registry & Recommendations types
// ---------------------------------------------------------------------------

export interface ClusterRegistryEntry {
  cluster_id: string;
  cluster_name: string;
  provider: string;
  node_count: number;
  pod_count: number;
  health_status: string;
  monthly_cost: number;
  idle_pct: number;
  recommendation_count: number;
  critical_count: number;
  last_scan_at: string;
  total_savings_usd: number;
}

export interface ProactiveFindingDTO {
  finding_id: string;
  check_type: string;
  severity: string;
  lifecycle_state: string;
  title: string;
  description: string;
  affected_resources: string[];
  affected_workloads: string[];
  days_until_impact: number;
  estimated_savings_usd: number;
  recommendation: string;
  commands: string[];
  dry_run_command: string;
  rollback_command: string;
  confidence: number;
  source: string;
}

export interface ScoredRecommendationDTO {
  recommendation_id: string;
  category: string;
  score: number;
  title: string;
  description: string;
  severity: string;
  source: string;
  affected_resources: string[];
  affected_workloads: string[];
  commands: string[];
  dry_run_command: string;
  rollback_command: string;
  days_until_impact: number;
  estimated_savings_usd: number;
  risk_level: string;
  confidence: number;
}

export interface ClusterCostSummaryDTO {
  cluster_id: string;
  provider: string;
  node_count: number;
  pod_count: number;
  current_monthly_cost: number;
  projected_monthly_cost: number;
  projected_savings_usd: number;
  idle_cpu_pct: number;
  idle_memory_pct: number;
  instance_breakdown: { instance_type: string; count: number; unit_cost: number; total_cost: number }[];
  namespace_costs: { namespace: string; cpu_requested: number; pod_count: number; estimated_cost: number; cost_pct: number }[];
}

export interface ClusterRecommendationSnapshotDTO {
  cluster_id: string;
  cluster_name: string;
  provider: string;
  scanned_at: string;
  proactive_findings: ProactiveFindingDTO[];
  cost_summary: ClusterCostSummaryDTO | null;
  scored_recommendations: ScoredRecommendationDTO[];
  total_savings_usd: number;
  critical_count: number;
  optimization_count: number;
  security_count: number;
}

// ===== CI/CD Live Board Types =====

export type DeliveryKind = 'commit' | 'build' | 'sync';
export type DeliverySource = 'github' | 'jenkins' | 'argocd';
export type CICDInstanceSource = 'jenkins' | 'argocd';

export interface DeliveryItem {
  kind: DeliveryKind;
  id: string;
  title: string;
  source: DeliverySource;
  source_instance: string;
  status: string;
  author: string | null;
  git_sha: string | null;
  git_repo: string | null;
  target: string | null;
  timestamp: string;          // ISO-8601
  duration_s: number | null;
  url: string;
}

export interface SourceError {
  name: string;
  source: CICDInstanceSource | string;
  message: string;
}

export interface CICDStreamResponse {
  items: DeliveryItem[];
  source_errors: SourceError[];
  server_ts: string;
}

export interface CommitFileDetail {
  filename: string;
  status: string;             // "added" | "modified" | "removed" | "renamed"
  additions: number;
  deletions: number;
  patch: string;
}

export interface CommitDetail {
  commit_sha: string;
  message: string;
  author: string;
  files: CommitFileDetail[];
}

export interface PipelineCapabilityForm {
  capability: 'troubleshoot_pipeline';
  cluster_id: string;
  time_window_minutes: number;
  git_repo?: string;
  service_hint?: string;
  profile_id?: string;
}

export interface CatalogCostHint {
  llm_calls: number;
  typical_duration_s: number;
}

export interface CatalogAgentSummary {
  name: string;
  version: number;
  description: string;
  category: string;
  tags: string[];
  cost_hint?: CatalogCostHint | null;
}

export interface CatalogAgentDetail extends CatalogAgentSummary {
  deprecated_versions: number[];
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  trigger_examples: string[];
  timeout_seconds: number;
  retry_on: string[];
}

// ----- Phase 2/3 Workflow DAG + Run shapes -----

export interface WorkflowSummary {
  id: string;
  name: string;
  description: string;
  created_at: string;
  created_by?: string;
}

export interface VersionSummary {
  version_id: string;
  workflow_id: string;
  version: number;
  created_at: string;
}

export interface WorkflowDetail extends WorkflowSummary {
  latest_version?: { version: number; created_at: string };
}

export interface WorkflowVersionDetail {
  workflow_id: string;
  version: number;
  created_at: string;
  dag: WorkflowDag;
  compiled: unknown;
}

export type RefExpr =
  | { ref: { from: 'input'; path: string } }
  | { ref: { from: 'env'; path: string } }
  | { ref: { from: 'node'; node_id: string; path: string } };

export type LiteralExpr = { literal: unknown };

export type TransformExpr =
  | { op: 'coalesce' | 'concat'; args: MappingExpr[] };

export type PredicateExpr =
  | { op: 'eq' | 'in' | 'exists'; left?: MappingExpr; right?: MappingExpr; args?: MappingExpr[] }
  | { op: 'and' | 'or'; args: PredicateExpr[] }
  | { op: 'not'; arg: PredicateExpr };

export type MappingExpr = RefExpr | LiteralExpr | TransformExpr;

export interface StepSpec {
  id: string;
  agent: string;
  agent_version: number | 'latest';
  inputs: Record<string, MappingExpr>;
  when?: PredicateExpr;
  on_failure?: 'fail' | 'continue' | 'fallback';
  fallback_step_id?: string;
  parallel_group?: string;
  concurrency_group?: string;
  timeout_seconds_override?: number;
  retry_on_override?: string[];
}

export interface WorkflowDag {
  inputs_schema: Record<string, unknown>;
  steps: StepSpec[];
}

export type RunStatus =
  | 'pending'
  | 'running'
  | 'cancelling'
  | 'cancelled'
  | 'succeeded'
  | 'failed';

export type StepRunStatus =
  | 'pending'
  | 'running'
  | 'success'
  | 'failed'
  | 'skipped'
  | 'cancelled';

export interface StepRunDetail {
  id: string;
  step_id: string;
  status: StepRunStatus;
  attempt: number;
  started_at?: string;
  ended_at?: string;
  duration_ms?: number;
  output?: unknown;
  error?: { type?: string; class?: string; message?: string };
}

export interface RunDetail {
  id: string;
  workflow_version_id: string;
  status: RunStatus;
  started_at?: string;
  ended_at?: string;
  inputs: Record<string, unknown>;
  error?: { type?: string; message?: string };
  idempotency_key?: string;
  step_runs: StepRunDetail[];
}

export interface RunListResponse {
  runs: Array<{
    id: string;
    workflow_version_id: string;
    status: RunStatus;
    started_at?: string;
    ended_at?: string;
  }>;
  total: number;
  limit: number;
  offset: number;
}

export interface RerunData {
  workflow_version_id: string;
  inputs: Record<string, unknown>;
}
