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
  | 'complete';

export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info';

export interface ErrorPattern {
  pattern: string;
  count: number;
  severity: Severity;
  first_seen: string;
  last_seen: string;
  sample_message: string;
  confidence: number;
}

export interface MetricAnomaly {
  metric_name: string;
  current_value: number;
  baseline_value: number;
  deviation_percent: number;
  direction: 'above' | 'below';
  severity: Severity;
  timestamp: string;
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
}

export interface K8sEvent {
  type: string;
  reason: string;
  message: string;
  count: number;
  first_timestamp: string;
  last_timestamp: string;
  involved_object: string;
}

export interface SpanInfo {
  span_id: string;
  service: string;
  operation: string;
  duration_ms: number;
  status: string;
  error: boolean;
  parent_span_id: string | null;
}

export interface Finding {
  agent: string;
  category: string;
  title: string;
  description: string;
  severity: Severity;
  confidence: number;
  evidence: string[];
  suggested_fix?: string;
}

export interface NegativeFinding {
  agent: string;
  category: string;
  description: string;
}

export interface CriticVerdict {
  finding_index: number;
  finding_title: string;
  verdict: 'confirmed' | 'plausible' | 'weak' | 'rejected';
  confidence: number;
  reasoning: string;
}

export interface Breadcrumb {
  timestamp: string;
  agent: string;
  action: string;
  detail: string;
}

export interface TokenUsage {
  agent: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

export interface TaskEvent {
  session_id: string;
  agent: string;
  event_type: 'started' | 'progress' | 'success' | 'warning' | 'error';
  message: string;
  timestamp: string;
  data?: Record<string, unknown>;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

export interface V4Session {
  session_id: string;
  service_name: string;
  status: DiagnosticPhase;
  confidence: number;
  created_at: string;
  updated_at: string;
}

export interface V4SessionStatus {
  session_id: string;
  service_name: string;
  phase: DiagnosticPhase;
  confidence: number;
  findings_count: number;
  token_usage: TokenUsage[];
  breadcrumbs: Breadcrumb[];
  created_at: string;
  updated_at: string;
}

export interface V4Findings {
  session_id: string;
  findings: Finding[];
  negative_findings: NegativeFinding[];
  critic_verdicts: CriticVerdict[];
  error_patterns: ErrorPattern[];
  metric_anomalies: MetricAnomaly[];
  pod_statuses: PodHealthStatus[];
  k8s_events: K8sEvent[];
  trace_spans: SpanInfo[];
  impacted_files: CodeImpact[];
}

export interface CodeImpact {
  file_path: string;
  impact_type: 'root_cause' | 'affected' | 'dependency' | 'test';
  description: string;
  fix_area?: string;
}

export interface StartSessionRequest {
  service_name: string;
  time_window: string;
  trace_id?: string;
  namespace?: string;
  repo_url?: string;
}

export interface V4WebSocketMessage {
  type: 'task_event' | 'chat_response';
  data: TaskEvent | ChatMessage;
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
  weighted_final: number;
}

export interface AttestationGateData {
  gate_type: 'discovery_complete' | 'pre_remediation' | 'post_remediation';
  human_decision: 'approve' | 'reject' | 'modify' | null;
  decided_by: string | null;
  decided_at: string | null;
  proposed_action: string | null;
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
  severity: 'info' | 'warning' | 'error' | 'critical';
}

export interface ChangeCorrelation {
  change_id: string;
  change_type: 'code_deploy' | 'config_change' | 'infra_change' | 'dependency_update';
  risk_score: number;
  temporal_correlation: number;
  author: string;
  description: string;
  files_changed: string[];
  timestamp: string | null;
}

export interface HypothesisData {
  hypothesis_id: string;
  description: string;
  confidence: number;
  causal_chain: string[];
}

// ===== V5 Impact & Risk Types =====
export interface BlastRadiusData {
  primary_service: string;
  upstream_affected: string[];
  downstream_affected: string[];
  shared_resources: string[];
  estimated_user_impact: string;
  scope: 'single_service' | 'service_group' | 'namespace' | 'cluster_wide';
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
