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
