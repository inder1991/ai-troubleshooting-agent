import type {
  StartSessionRequest,
  V4Session,
  V4SessionStatus,
  V4Findings,
  TaskEvent,
  ChatMessage,
  Integration,
  FixStatusResponse,
  ClosureStatusResponse,
  InvestigateRequest,
  InvestigateResponse,
  ToolDefinition,
  TelescopeResource,
  TelescopeResourceLogs,
  TriageStatus,
  AgentMatrixResponse,
  AgentExecutionsResponse,
} from '../types';

export const API_BASE_URL = 'http://localhost:8000';

/** Safely extract error detail from a response (handles non-JSON like 502 nginx HTML). */
const extractErrorDetail = async (response: Response, fallback: string): Promise<string> => {
  try {
    const error = await response.json();
    return error.detail || fallback;
  } catch {
    return `${fallback} (HTTP ${response.status})`;
  }
};

// ===== V3 API (preserved for backward compatibility) =====

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const sendConversationMessage = async (message: string, conversationHistory?: any[]) => {
  const response = await fetch(`${API_BASE_URL}/api/conversation`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, conversation_history: conversationHistory })
  });
  return response.json();
};

export const startTroubleshooting = async (formData: Record<string, unknown>) => {
  const response = await fetch(`${API_BASE_URL}/api/troubleshoot/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(formData)
  });
  return response.json();
};

export const getSessionStatusV3 = async (sessionId: string) => {
  const response = await fetch(`${API_BASE_URL}/api/troubleshoot/status/${sessionId}`);
  return response.json();
};

export const approveGenerated = async (sessionId: string, approved: boolean, comments?: string) => {
  const response = await fetch(`${API_BASE_URL}/api/troubleshoot/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, approved, comments })
  });
  return response.json();
};

export const listSessions = async () => {
  const response = await fetch(`${API_BASE_URL}/api/sessions`);
  return response.json();
};

export const createPullRequest = async (sessionId: string) => {
  const response = await fetch(`${API_BASE_URL}/api/troubleshoot/${sessionId}/create-pr`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pr_data: {} })
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to create pull request');
  }
  return response.json();
};

export const rejectFix = async (sessionId: string) => {
  const response = await fetch(`${API_BASE_URL}/api/troubleshoot/${sessionId}/reject-fix`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to reject fix');
  }
  return response.json();
};

export const getPRStatus = async (sessionId: string) => {
  const response = await fetch(`${API_BASE_URL}/api/troubleshoot/${sessionId}/pr-status`);
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to get PR status');
  }
  return response.json();
};

export const checkAgent3Health = async () => {
  const response = await fetch(`${API_BASE_URL}/api/pr-endpoints/health`);
  return response.json();
};

// ===== V4 API =====

export const startSessionV4 = async (request: StartSessionRequest & { profileId?: string }): Promise<V4Session> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/session/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    throw new Error(await extractErrorDetail(response, 'Failed to start session'));
  }
  const data = await response.json();
  return {
    ...data,
    // Backend now returns service_name & created_at; fall back to request data
    service_name: data.service_name || request.service_name || 'unknown',
    status: data.status || data.phase || 'initial',
    confidence: data.confidence ?? 0,
    created_at: data.created_at || new Date().toISOString(),
    updated_at: data.updated_at || data.created_at || new Date().toISOString(),
  };
};

export const sendChatMessage = async (
  sessionId: string,
  message: string
): Promise<ChatMessage> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/session/${sessionId}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  });
  if (!response.ok) {
    throw new Error(await extractErrorDetail(response, 'Failed to send message'));
  }
  // Backend returns ChatResponse {response, phase, confidence} — transform to ChatMessage
  const data = await response.json();
  return {
    role: 'assistant',
    content: data.response,
    timestamp: new Date().toISOString(),
    metadata: {
      newPhase: data.phase,
      newConfidence: data.confidence,
    },
  };
};

export const getSessionStatus = async (sessionId: string): Promise<V4SessionStatus> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/session/${sessionId}/status`);
  if (!response.ok) {
    throw new Error(await extractErrorDetail(response, 'Failed to get session status'));
  }
  return response.json();
};

export const getFindings = async (sessionId: string): Promise<V4Findings> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/session/${sessionId}/findings`);
  if (!response.ok) {
    throw new Error(await extractErrorDetail(response, 'Failed to get findings'));
  }
  return response.json();
};

export const getEvents = async (sessionId: string): Promise<TaskEvent[]> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/session/${sessionId}/events`);
  if (!response.ok) {
    throw new Error(await extractErrorDetail(response, 'Failed to get events'));
  }
  const data = await response.json();
  return data.events || data;
};

export const listSessionsV4 = async (): Promise<V4Session[]> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/sessions`);
  if (!response.ok) {
    throw new Error(await extractErrorDetail(response, 'Failed to list sessions'));
  }
  const data = await response.json();
  return data.map((s: Record<string, unknown>) => ({
    ...s,
    status: s.status || s.phase || 'initial',
    updated_at: s.updated_at || s.created_at,
  }));
};

// ===== Cluster Guard Mode =====

export const startGuardScan = async (profileId: string): Promise<V4Session> => {
  return startSessionV4({
    service_name: 'Guard Scan',
    time_window: '1h',
    capability: 'cluster_diagnostics',
    scan_mode: 'guard',
    profile_id: profileId,
  });
};

// ===== V4 Fix Pipeline =====

export const generateFix = async (
  sessionId: string,
  guidance: string = ''
): Promise<{ status: string }> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/session/${sessionId}/fix/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ guidance }),
  });
  if (!response.ok) {
    throw new Error(await extractErrorDetail(response, 'Failed to start fix generation'));
  }
  return response.json();
};

export const getFixStatus = async (
  sessionId: string
): Promise<FixStatusResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/session/${sessionId}/fix/status`);
  if (!response.ok) {
    throw new Error(await extractErrorDetail(response, 'Failed to get fix status'));
  }
  return response.json();
};

export const decideOnFix = async (
  sessionId: string,
  decision: string
): Promise<{ status: string; response: string }> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/session/${sessionId}/fix/decide`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision }),
  });
  if (!response.ok) {
    throw new Error(await extractErrorDetail(response, 'Failed to submit fix decision'));
  }
  return response.json();
};

// ===== V4 PromQL Proxy =====

export const runPromQLQuery = async (
  query: string,
  start: string,
  end: string,
  step: string = '60s'
): Promise<{ data_points: { timestamp: string; value: number }[]; current_value: number; error?: string }> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/promql/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, start, end, step }),
  });
  if (!response.ok) {
    return { data_points: [], current_value: 0, error: 'Request failed' };
  }
  return response.json();
};

// ===== V5 Governance API =====
export const getEvidenceGraph = async (sessionId: string) => {
  const response = await fetch(`${API_BASE_URL}/api/v5/session/${sessionId}/evidence-graph`);
  if (!response.ok) throw new Error('Failed to get evidence graph');
  return response.json();
};

export const getConfidence = async (sessionId: string) => {
  const response = await fetch(`${API_BASE_URL}/api/v5/session/${sessionId}/confidence`);
  if (!response.ok) throw new Error('Failed to get confidence');
  return response.json();
};

export const getReasoning = async (sessionId: string) => {
  const response = await fetch(`${API_BASE_URL}/api/v5/session/${sessionId}/reasoning`);
  if (!response.ok) throw new Error('Failed to get reasoning');
  return response.json();
};

export const submitAttestation = async (sessionId: string, gateType: string, decision: string, decidedBy: string) => {
  const response = await fetch(`${API_BASE_URL}/api/v4/session/${sessionId}/attestation`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ gate_type: gateType, decision, decided_by: decidedBy }),
  });
  if (!response.ok) throw new Error('Failed to submit attestation');
  return response.json();
};

export const getTimeline = async (sessionId: string) => {
  const response = await fetch(`${API_BASE_URL}/api/v5/session/${sessionId}/timeline`);
  if (!response.ok) throw new Error('Failed to get timeline');
  return response.json();
};

// ===== V5 Integration API =====

export const listIntegrations = async (): Promise<Integration[]> => {
  const response = await fetch(`${API_BASE_URL}/api/v5/integrations`);
  if (!response.ok) throw new Error('Failed to list integrations');
  return response.json();
};

export const addIntegration = async (data: Partial<Integration> & { auth_data: string }) => {
  const response = await fetch(`${API_BASE_URL}/api/v5/integrations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error('Failed to add integration');
  return response.json();
};

export const deleteIntegration = async (id: string) => {
  const response = await fetch(`${API_BASE_URL}/api/v5/integrations/${id}`, { method: 'DELETE' });
  if (!response.ok) throw new Error('Failed to delete integration');
  return response.json();
};

export const probeIntegration = async (id: string) => {
  const response = await fetch(`${API_BASE_URL}/api/v5/integrations/${id}/probe`, { method: 'POST' });
  if (!response.ok) throw new Error('Failed to probe integration');
  return response.json();
};

// ===== V5 Memory API =====

export const listMemoryIncidents = async () => {
  const response = await fetch(`${API_BASE_URL}/api/v5/memory/incidents`);
  if (!response.ok) throw new Error('Failed to list memory incidents');
  return response.json();
};

export const storeMemoryIncident = async (data: Record<string, unknown>) => {
  const response = await fetch(`${API_BASE_URL}/api/v5/memory/incidents`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error('Failed to store memory incident');
  return response.json();
};

export const findSimilarIncidents = async (sessionId: string) => {
  const response = await fetch(`${API_BASE_URL}/api/v5/memory/similar?session_id=${sessionId}`);
  if (!response.ok) throw new Error('Failed to find similar incidents');
  return response.json();
};

// ===== V5 Remediation API =====

export const proposeRemediation = async (sessionId: string, data: Record<string, unknown>) => {
  const response = await fetch(`${API_BASE_URL}/api/v5/session/${sessionId}/remediation/propose`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error('Failed to propose remediation');
  return response.json();
};

export const dryRunRemediation = async (sessionId: string, data: Record<string, unknown>) => {
  const response = await fetch(`${API_BASE_URL}/api/v5/session/${sessionId}/remediation/dry-run`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error('Failed to run dry-run');
  return response.json();
};

export const executeRemediation = async (sessionId: string, data: Record<string, unknown>) => {
  const response = await fetch(`${API_BASE_URL}/api/v5/session/${sessionId}/remediation/execute`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error('Failed to execute remediation');
  return response.json();
};

export const rollbackRemediation = async (sessionId: string) => {
  const response = await fetch(`${API_BASE_URL}/api/v5/session/${sessionId}/remediation/rollback`, {
    method: 'POST'
  });
  if (!response.ok) throw new Error('Failed to rollback');
  return response.json();
};

// ===== Incident Closure API =====

export const getClosureStatus = async (sessionId: string): Promise<ClosureStatusResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/session/${sessionId}/closure/status`);
  if (!response.ok) throw new Error('Failed to get closure status');
  return response.json();
};

export const createJiraIssue = async (sessionId: string, data: {
  project_key: string; summary?: string; description?: string; issue_type?: string; priority?: string;
}) => {
  const response = await fetch(`${API_BASE_URL}/api/v4/session/${sessionId}/closure/jira/create`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    throw new Error(await extractErrorDetail(response, 'Failed to create Jira issue'));
  }
  return response.json();
};

export const linkJiraIssue = async (sessionId: string, issueKey: string) => {
  const response = await fetch(`${API_BASE_URL}/api/v4/session/${sessionId}/closure/jira/link`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ issue_key: issueKey }),
  });
  if (!response.ok) {
    throw new Error(await extractErrorDetail(response, 'Failed to link Jira issue'));
  }
  return response.json();
};

export const createRemedyIncident = async (sessionId: string, data: {
  summary?: string; urgency?: string; assigned_group?: string; service_ci?: string;
}) => {
  const response = await fetch(`${API_BASE_URL}/api/v4/session/${sessionId}/closure/remedy/create`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    throw new Error(await extractErrorDetail(response, 'Failed to create Remedy incident'));
  }
  return response.json();
};

export const previewPostMortem = async (sessionId: string): Promise<{ title: string; body_markdown: string; executive_summary: string; impact_statement: string }> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/session/${sessionId}/closure/confluence/preview`, {
    method: 'POST',
  });
  if (!response.ok) throw new Error('Failed to generate post-mortem preview');
  return response.json();
};

export const publishPostMortem = async (sessionId: string, data: {
  space_key: string; title?: string; body_markdown: string; parent_page_id?: string;
}) => {
  const response = await fetch(`${API_BASE_URL}/api/v4/session/${sessionId}/closure/confluence/publish`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    throw new Error(await extractErrorDetail(response, 'Failed to publish post-mortem'));
  }
  return response.json();
};

// ── Live Investigation Steering ──────────────────────────────────────

export const postInvestigate = async (
  sessionId: string,
  request: InvestigateRequest,
  signal?: AbortSignal
): Promise<InvestigateResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/session/${sessionId}/investigate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
    signal,
  });
  if (!response.ok) {
    throw new Error(await extractErrorDetail(response, 'Investigation request failed'));
  }
  return response.json();
};

export const getTools = async (
  sessionId: string,
  signal?: AbortSignal
): Promise<{ tools: ToolDefinition[] }> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/session/${sessionId}/tools`, { signal });
  if (!response.ok) {
    throw new Error(await extractErrorDetail(response, 'Failed to get tools'));
  }
  return response.json();
};

// ── War Room v2 API ──────────────────────────────────────────────────

export const getResource = async (
  sessionId: string,
  namespace: string,
  kind: string,
  name: string,
): Promise<TelescopeResource> => {
  const response = await fetch(
    `${API_BASE_URL}/api/v4/session/${sessionId}/resource/${namespace}/${kind}/${name}`,
  );
  if (!response.ok) {
    throw new Error(await extractErrorDetail(response, 'Failed to fetch resource'));
  }
  return response.json();
};

export const getResourceLogs = async (
  sessionId: string,
  namespace: string,
  kind: string,
  name: string,
  tailLines: number = 500,
  container?: string,
): Promise<TelescopeResourceLogs> => {
  const params = new URLSearchParams({ tail_lines: String(tailLines) });
  if (container) params.set('container', container);
  const response = await fetch(
    `${API_BASE_URL}/api/v4/session/${sessionId}/resource/${namespace}/${kind}/${name}/logs?${params}`,
  );
  if (!response.ok) {
    throw new Error(await extractErrorDetail(response, 'Failed to fetch logs'));
  }
  return response.json();
};

export const updateTriageStatus = async (
  sessionId: string,
  treeId: string,
  status: TriageStatus,
): Promise<void> => {
  const response = await fetch(
    `${API_BASE_URL}/api/v4/session/${sessionId}/causal-tree/${treeId}/triage`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    },
  );
  if (!response.ok) {
    throw new Error(await extractErrorDetail(response, 'Failed to update triage'));
  }
};

// ===== Agent Matrix API =====

export const getAgents = async (): Promise<AgentMatrixResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/agents`);
  if (!response.ok) {
    throw new Error(await extractErrorDetail(response, 'Failed to fetch agents'));
  }
  return response.json();
};

export const getAgentExecutions = async (agentId: string): Promise<AgentExecutionsResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/agents/${agentId}/executions`);
  if (!response.ok) {
    throw new Error(await extractErrorDetail(response, 'Failed to fetch agent executions'));
  }
  return response.json();
};

// ===== Network Troubleshooting API =====

export const diagnoseNetwork = async (params: {
  src_ip: string;
  dst_ip: string;
  port: number;
  protocol: string;
}): Promise<{ session_id: string; flow_id: string; status: string; message: string }> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/network/diagnose`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!response.ok) throw new Error(`Network diagnosis failed: ${response.statusText}`);
  return response.json();
};

export const getNetworkFindings = async (sessionId: string): Promise<any> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/network/session/${sessionId}/findings`);
  if (!response.ok) throw new Error(`Failed to get network findings: ${response.statusText}`);
  return response.json();
};

export const saveTopology = async (diagramJson: string, description?: string): Promise<any> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/network/topology/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ diagram_json: diagramJson, description: description || '' }),
  });
  if (!response.ok) throw new Error(`Failed to save topology: ${response.statusText}`);
  return response.json();
};

export const loadTopology = async (): Promise<any> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/network/topology/load`);
  if (!response.ok) throw new Error(`Failed to load topology: ${response.statusText}`);
  return response.json();
};

export const promoteTopology = async (nodes: unknown[], edges: unknown[]): Promise<any> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/network/topology/promote`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nodes, edges }),
  });
  if (!response.ok) throw new Error(`Failed to promote topology: ${response.statusText}`);
  return response.json();
};

export const uploadIPAM = async (file: File): Promise<any> => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetch(`${API_BASE_URL}/api/v4/network/ipam/upload`, {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) throw new Error(`Failed to upload IPAM: ${response.statusText}`);
  return response.json();
};

export const getAdapterStatus = async (): Promise<any> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/network/adapters/status`);
  if (!response.ok) throw new Error(`Failed to get adapter status: ${response.statusText}`);
  return response.json();
};

export const fetchIPAMDevices = async (): Promise<any> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/network/ipam/devices`);
  if (!response.ok) throw new Error(`Failed to fetch IPAM devices: ${response.statusText}`);
  return response.json();
};

export const fetchIPAMSubnets = async (): Promise<any> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/network/ipam/subnets`);
  if (!response.ok) throw new Error(`Failed to fetch IPAM subnets: ${response.statusText}`);
  return response.json();
};

export const runReachabilityMatrix = async (zoneIds: string[]): Promise<any> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/network/matrix`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ zone_ids: zoneIds }),
  });
  if (!response.ok) throw new Error(`Failed to run matrix: ${response.statusText}`);
  return response.json();
};

export const createHAGroup = async (data: {
  name: string; ha_mode: string; member_ids: string[];
  virtual_ips?: string[]; active_member_id?: string;
}): Promise<any> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/network/ha-groups`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error(`Failed to create HA group: ${response.statusText}`);
  return response.json();
};

export const listHAGroups = async (): Promise<any> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/network/ha-groups`);
  if (!response.ok) throw new Error(`Failed to list HA groups: ${response.statusText}`);
  return response.json();
};

// ===== Adapter Instance API (Multi-Instance) =====

export const listAdapterInstances = async (): Promise<{ adapters: any[] }> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/network/adapters`);
  if (!response.ok) throw new Error(`Failed to list adapter instances: ${response.statusText}`);
  return response.json();
};

export const createAdapterInstance = async (data: {
  label: string; vendor: string; api_endpoint?: string; api_key?: string; extra_config?: Record<string, unknown>;
}): Promise<{ status: string; instance_id: string; label: string }> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/network/adapters`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error(await extractErrorDetail(response, 'Failed to create adapter instance'));
  return response.json();
};

export const updateAdapterInstance = async (instanceId: string, data: {
  label?: string; api_endpoint?: string; api_key?: string; extra_config?: Record<string, unknown>; device_groups?: string[];
}): Promise<{ status: string; instance_id: string }> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/network/adapters/${instanceId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error(await extractErrorDetail(response, 'Failed to update adapter instance'));
  return response.json();
};

export const deleteAdapterInstance = async (instanceId: string): Promise<{ status: string }> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/network/adapters/${instanceId}`, { method: 'DELETE' });
  if (!response.ok) throw new Error(await extractErrorDetail(response, 'Failed to delete adapter instance'));
  return response.json();
};

export const testAdapterInstance = async (instanceId: string): Promise<{ success: boolean; message: string }> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/network/adapters/${instanceId}/test`, { method: 'POST' });
  if (!response.ok) throw new Error(`Failed to test adapter: ${response.statusText}`);
  return response.json();
};

export const testNewAdapter = async (data: {
  label: string; vendor: string; api_endpoint?: string; api_key?: string; extra_config?: Record<string, unknown>;
}): Promise<{ success: boolean; message: string }> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/network/adapters/test-new`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error(`Failed to test adapter: ${response.statusText}`);
  return response.json();
};

export const refreshAdapterInstance = async (instanceId: string): Promise<{ status: string }> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/network/adapters/${instanceId}/refresh`, { method: 'POST' });
  if (!response.ok) throw new Error(`Failed to refresh adapter: ${response.statusText}`);
  return response.json();
};

export const discoverDeviceGroups = async (instanceId: string): Promise<{ device_groups: any[] }> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/network/adapters/${instanceId}/discover`);
  if (!response.ok) throw new Error(`Failed to discover device groups: ${response.statusText}`);
  return response.json();
};

export const bindDeviceToAdapter = async (instanceId: string, deviceIds: string[]): Promise<{ status: string }> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/network/adapters/${instanceId}/bind`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ device_ids: deviceIds }),
  });
  if (!response.ok) throw new Error(await extractErrorDetail(response, 'Failed to bind devices'));
  return response.json();
};

// ── Observatory API ──

export const fetchMonitorSnapshot = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/monitor/snapshot`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch monitor snapshot'));
  return resp.json();
};

export const fetchDeviceHistory = async (deviceId: string, period: string = '24h') => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/monitor/device/${deviceId}/history?period=${period}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch device history'));
  return resp.json();
};

export const fetchDriftEvents = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/monitor/drift`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch drift events'));
  return resp.json();
};

export const promoteDiscovery = async (ip: string, name: string, deviceType: string = 'HOST') => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/monitor/discover/${ip}/promote`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, device_type: deviceType }),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to promote discovery'));
  return resp.json();
};

export const dismissDiscovery = async (ip: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/monitor/discover/${ip}/dismiss`, {
    method: 'POST',
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to dismiss discovery'));
  return resp.json();
};

// ── Alerts API ──

export const fetchAlerts = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/monitor/alerts`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch alerts'));
  return resp.json();
};

export const fetchAlertRules = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/monitor/alerts/rules`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch alert rules'));
  return resp.json();
};

export const acknowledgeAlert = async (alertKey: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/monitor/alerts/${encodeURIComponent(alertKey)}/acknowledge`, {
    method: 'POST',
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to acknowledge alert'));
  return resp.json();
};

// ── Metrics API ──

export const fetchDeviceMetrics = async (entityId: string, metric: string, timeRange = '1h', resolution = '30s') => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/monitor/metrics/device/${entityId}/${metric}?time_range=${timeRange}&resolution=${resolution}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch metrics'));
  return resp.json();
};

// ── Flow API ──

export const fetchTopTalkers = async (window = '5m', limit = 20) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/monitor/flows/top-talkers?window=${window}&limit=${limit}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch top talkers'));
  return resp.json();
};

export const fetchTrafficMatrix = async (window = '15m') => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/monitor/flows/traffic-matrix?window=${window}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch traffic matrix'));
  return resp.json();
};

export const fetchProtocolBreakdown = async (window = '1h') => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/monitor/flows/protocols?window=${window}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch protocol breakdown'));
  return resp.json();
};

export const fetchInfluxDBStatus = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/monitor/config/influxdb/status`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch InfluxDB status'));
  return resp.json();
};

// ── IPAM API ──

export const fetchSubnetDetail = async (subnetId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/subnets/${subnetId}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch subnet'));
  return resp.json();
};

export const createSubnet = async (data: Record<string, unknown>) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/subnets`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to create subnet'));
  return resp.json();
};

export const updateSubnet = async (subnetId: string, data: Record<string, unknown>) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/subnets/${subnetId}`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to update subnet'));
  return resp.json();
};

export const populateSubnetIPs = async (subnetId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/subnets/${subnetId}/populate`, {
    method: 'POST',
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to populate IPs'));
  return resp.json();
};

export const fetchIPs = async (params: { subnet_id?: string; status?: string; search?: string; offset?: number; limit?: number } = {}) => {
  const qs = new URLSearchParams();
  if (params.subnet_id) qs.set('subnet_id', params.subnet_id);
  if (params.status) qs.set('status', params.status);
  if (params.search) qs.set('search', params.search);
  if (params.offset !== undefined) qs.set('offset', String(params.offset));
  if (params.limit !== undefined) qs.set('limit', String(params.limit));
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/ips?${qs}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch IPs'));
  return resp.json();
};

export const updateIP = async (ipId: string, data: Record<string, unknown>) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/ips/${ipId}`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to update IP'));
  return resp.json();
};

export const reserveIP = async (ipId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/ips/${ipId}/reserve`, { method: 'POST' });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to reserve IP'));
  return resp.json();
};

export const assignIP = async (ipId: string, deviceId: string, interfaceId?: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/ips/${ipId}/assign`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ device_id: deviceId, interface_id: interfaceId || '' }),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to assign IP'));
  return resp.json();
};

export const releaseIP = async (ipId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/ips/${ipId}/release`, { method: 'POST' });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to release IP'));
  return resp.json();
};

export const fetchIPAMTree = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/tree`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch IPAM tree'));
  return resp.json();
};

export const fetchIPAMStats = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/stats`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch IPAM stats'));
  return resp.json();
};

export const fetchSubnetUtilization = async (subnetId?: string) => {
  const url = subnetId
    ? `${API_BASE_URL}/api/v4/network/ipam/utilization/${subnetId}`
    : `${API_BASE_URL}/api/v4/network/ipam/utilization`;
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch utilization'));
  return resp.json();
};

export const bulkUpdateIPStatus = async (ipIds: string[], status: string, deviceId?: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/ips/bulk-status`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ip_ids: ipIds, status, device_id: deviceId || '' }),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Bulk update failed'));
  return resp.json();
};

export const globalIPSearch = async (query: string, signal?: AbortSignal) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/search?q=${encodeURIComponent(query)}`, { signal });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Search failed'));
  return resp.json();
};

export const fetchIPConflicts = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/conflicts`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch conflicts'));
  return resp.json();
};

export const fetchNextAvailableIP = async (subnetId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/subnets/${subnetId}/next-available`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'No available IPs'));
  return resp.json();
};

export const fetchIPAuditLog = async (ipId?: string, limit = 50) => {
  const params = new URLSearchParams();
  if (ipId) params.set('ip_id', ipId);
  params.set('limit', String(limit));
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/audit-log?${params}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch audit log'));
  return resp.json();
};

export const deleteSubnet = async (subnetId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/subnets/${subnetId}`, { method: 'DELETE' });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to delete subnet'));
  return resp.json();
};

export const deleteIPAddress = async (ipId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/ips/${ipId}`, { method: 'DELETE' });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to delete IP'));
  return resp.json();
};

export const getIPByAddress = async (address: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/ips/by-address?address=${encodeURIComponent(address)}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'IP not found'));
  return resp.json();
};

export const getIPById = async (ipId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/ips/${ipId}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'IP not found'));
  return resp.json();
};

export const splitSubnet = async (subnetId: string, newPrefix: number) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/subnets/${subnetId}/split`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ new_prefix: newPrefix }),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to split subnet'));
  return resp.json();
};

export const mergeSubnets = async (subnetIds: string[]) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/subnets/merge`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ subnet_ids: subnetIds }),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to merge subnets'));
  return resp.json();
};

export const exportIPAMCSV = async (): Promise<string> => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/export`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Export failed'));
  return resp.text();
};

export const fetchDNSMismatches = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/dns-mismatches`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch DNS mismatches'));
  return resp.json();
};

export const fetchCapacityForecast = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/capacity-forecast`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch forecast'));
  return resp.json();
};

export const scanSubnet = async (subnetId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/subnets/${subnetId}/scan`, { method: 'POST' });
  return resp.json();
};

export const dnsLookupIP = async (ipId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/ips/${ipId}/dns`);
  return resp.json();
};

export const fetchUtilizationHistory = async (subnetId: string, range: string = '7d') => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/subnets/${subnetId}/utilization-history?range=${range}`);
  return resp.json();
};

export const fetchAvailableRanges = async (subnetId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/subnets/${subnetId}/available-ranges`);
  return resp.json();
};

export const fetchDHCPScopes = async (subnetId?: string) => {
  const qs = subnetId ? `?subnet_id=${subnetId}` : '';
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/dhcp-scopes${qs}`);
  return resp.json();
};

export const createDHCPScope = async (scope: Record<string, unknown>) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/dhcp-scopes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(scope),
  });
  return resp.json();
};

export const deleteDHCPScope = async (scopeId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/dhcp-scopes/${scopeId}`, { method: 'DELETE' });
  return resp.json();
};

export const fetchIPAMReport = async (type: string, format: string = 'json', filters: Record<string, string> = {}) => {
  const params = new URLSearchParams({ format, ...filters });
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/reports/${type}?${params}`);
  if (format === 'csv') {
    return resp.text();
  }
  return resp.json();
};

// ── Enterprise IPAM API: VRFs ──

export const fetchVRFs = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/vrfs`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch VRFs'));
  return resp.json();
};

export const createVRF = async (data: Record<string, unknown>) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/vrfs`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to create VRF'));
  return resp.json();
};

export const updateVRF = async (vrfId: string, data: Record<string, unknown>) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/vrfs/${vrfId}`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to update VRF'));
  return resp.json();
};

export const deleteVRF = async (vrfId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/vrfs/${vrfId}`, { method: 'DELETE' });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to delete VRF'));
  return resp.json();
};

// ── Enterprise IPAM API: Regions ──

export const fetchRegions = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/regions`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch regions'));
  return resp.json();
};

export const createRegion = async (data: Record<string, unknown>) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/regions`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to create region'));
  return resp.json();
};

export const updateRegion = async (regionId: string, data: Record<string, unknown>) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/regions/${regionId}`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to update region'));
  return resp.json();
};

export const deleteRegion = async (regionId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/regions/${regionId}`, { method: 'DELETE' });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to delete region'));
  return resp.json();
};

// ── Enterprise IPAM API: Sites ──

export const fetchSites = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/sites`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch sites'));
  return resp.json();
};

export const createSite = async (data: Record<string, unknown>) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/sites`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to create site'));
  return resp.json();
};

export const updateSite = async (siteId: string, data: Record<string, unknown>) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/sites/${siteId}`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to update site'));
  return resp.json();
};

export const deleteSite = async (siteId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/sites/${siteId}`, { method: 'DELETE' });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to delete site'));
  return resp.json();
};

// ── Enterprise IPAM API: Address Blocks ──

export const fetchAddressBlocks = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/address-blocks`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch address blocks'));
  return resp.json();
};

export const createAddressBlock = async (data: Record<string, unknown>) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/address-blocks`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to create address block'));
  return resp.json();
};

export const deleteAddressBlock = async (blockId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/address-blocks/${blockId}`, { method: 'DELETE' });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to delete address block'));
  return resp.json();
};

export const fetchAddressBlockUtilization = async (blockId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/address-blocks/${blockId}/utilization`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch block utilization'));
  return resp.json();
};

export const allocateSubnetFromBlock = async (blockId: string, prefix: number) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/address-blocks/${blockId}/allocate`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prefix }),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to allocate subnet'));
  return resp.json();
};

// ── Enterprise IPAM API: Reserved Ranges ──

export const fetchReservedRanges = async (subnetId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/subnets/${subnetId}/reserved-ranges`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch reserved ranges'));
  return resp.json();
};

export const createReservedRange = async (subnetId: string, data: Record<string, unknown>) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/subnets/${subnetId}/reserved-ranges`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to create reserved range'));
  return resp.json();
};

export const deleteReservedRange = async (rangeId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/reserved-ranges/${rangeId}`, { method: 'DELETE' });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to delete reserved range'));
  return resp.json();
};

// ── Enterprise IPAM API: VLANs ──

export const fetchVLANs = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/vlans`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch VLANs'));
  return resp.json();
};

export const createVLAN = async (data: Record<string, unknown>) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/vlans`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to create VLAN'));
  return resp.json();
};

export const updateVLAN = async (vlanId: string, data: Record<string, unknown>) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/vlans/${vlanId}`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to update VLAN'));
  return resp.json();
};

export const deleteVLAN = async (vlanId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/vlans/${vlanId}`, { method: 'DELETE' });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to delete VLAN'));
  return resp.json();
};

export const fetchVLANInterfaces = async (vlanId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/vlans/${vlanId}/interfaces`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch VLAN interfaces'));
  return resp.json();
};

// ── Enterprise IPAM API: IP Correlation ──

export const fetchIPCorrelation = async (ipId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/ips/${ipId}/correlation`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch IP correlation'));
  return resp.json();
};

// ── Enterprise IPAM API: Cloud Accounts ──

export const fetchCloudAccounts = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/cloud-accounts`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch cloud accounts'));
  return resp.json();
};

export const createCloudAccount = async (data: Record<string, unknown>) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/cloud-accounts`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to create cloud account'));
  return resp.json();
};

export const updateCloudAccount = async (accountId: string, data: Record<string, unknown>) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/cloud-accounts/${accountId}`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to update cloud account'));
  return resp.json();
};

export const deleteCloudAccount = async (accountId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/cloud-accounts/${accountId}`, { method: 'DELETE' });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to delete cloud account'));
  return resp.json();
};

export const syncCloudAccount = async (accountId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/ipam/cloud-accounts/${accountId}/sync`, { method: 'POST' });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to sync cloud account'));
  return resp.json();
};

// ── Database Diagnostics API ──

export const fetchDBProfiles = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/db/profiles`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch DB profiles'));
  return resp.json();
};

export const createDBProfile = async (data: Record<string, unknown>) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/profiles`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to create DB profile'));
  return resp.json();
};

export const updateDBProfile = async (id: string, data: Record<string, unknown>) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/profiles/${id}`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to update DB profile'));
  return resp.json();
};

export const deleteDBProfile = async (id: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/profiles/${id}`, { method: 'DELETE' });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to delete DB profile'));
  return resp.json();
};

export const fetchDBProfileHealth = async (profileId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/profiles/${profileId}/health`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch DB health'));
  return resp.json();
};

export const startDBDiagnostic = async (profileId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/diagnostics/start`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile_id: profileId }),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to start diagnostic'));
  return resp.json();
};

export const fetchDBDiagnosticRun = async (runId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/diagnostics/${runId}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch diagnostic run'));
  return resp.json();
};

export const fetchDBDiagnosticHistory = async (profileId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/diagnostics/history?profile_id=${profileId}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch diagnostic history'));
  return resp.json();
};

// ── Database Monitoring API ──

export const fetchDBMonitorStatus = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/db/monitor/status`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch monitor status'));
  return resp.json();
};

export const fetchDBMonitorMetrics = async (profileId: string, metric: string, duration = '1h', resolution = '1m') => {
  const resp = await fetch(`${API_BASE_URL}/api/db/monitor/metrics/${profileId}/${metric}?duration=${duration}&resolution=${resolution}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch metrics'));
  return resp.json();
};

export const startDBMonitor = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/db/monitor/start`, { method: 'POST' });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to start monitor'));
  return resp.json();
};

export const stopDBMonitor = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/db/monitor/stop`, { method: 'POST' });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to stop monitor'));
  return resp.json();
};

export const fetchDBAlertRules = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/db/alerts/rules`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch alert rules'));
  return resp.json();
};

export const createDBAlertRule = async (rule: Record<string, unknown>) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/alerts/rules`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(rule),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to create alert rule'));
  return resp.json();
};

export const deleteDBAlertRule = async (ruleId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/alerts/rules/${ruleId}`, { method: 'DELETE' });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to delete alert rule'));
  return resp.json();
};

export const updateDBAlertRule = async (ruleId: string, rule: Record<string, unknown>) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/alerts/rules/${ruleId}`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(rule),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to update alert rule'));
  return resp.json();
};

export const fetchDBActiveAlerts = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/db/alerts/active`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch active alerts'));
  return resp.json();
};

export const fetchDBAlertHistory = async (profileId?: string, severity?: string, limit = 50) => {
  const params = new URLSearchParams();
  if (profileId) params.set('profile_id', profileId);
  if (severity) params.set('severity', severity);
  params.set('limit', String(limit));
  const resp = await fetch(`${API_BASE_URL}/api/db/alerts/history?${params}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch alert history'));
  return resp.json();
};

export const fetchDBSchema = async (profileId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/schema/${profileId}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch schema'));
  return resp.json();
};

export const fetchDBTableDetail = async (profileId: string, tableName: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/schema/${profileId}/table/${tableName}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch table detail'));
  return resp.json();
};

// ── Database Operations / Remediation API ──

export const createRemediationPlan = async (data: { profile_id: string; action: string; params: Record<string, unknown>; finding_id?: string }) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/remediation/plan`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to create plan'));
  return resp.json();
};

export const suggestRemediation = async (profileId: string, runId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/remediation/suggest`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile_id: profileId, run_id: runId }),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to suggest remediation'));
  return resp.json();
};

export const fetchRemediationPlans = async (profileId: string, status?: string) => {
  const params = new URLSearchParams({ profile_id: profileId });
  if (status) params.set('status', status);
  const resp = await fetch(`${API_BASE_URL}/api/db/remediation/plans?${params}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch plans'));
  return resp.json();
};

export const fetchRemediationPlan = async (planId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/remediation/plans/${planId}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch plan'));
  return resp.json();
};

export const approveRemediationPlan = async (planId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/remediation/approve/${planId}`, { method: 'POST' });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to approve plan'));
  return resp.json();
};

export const rejectRemediationPlan = async (planId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/remediation/reject/${planId}`, { method: 'POST' });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to reject plan'));
  return resp.json();
};

export const executeRemediationPlan = async (planId: string, approvalToken: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/remediation/execute/${planId}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approval_token: approvalToken }),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to execute plan'));
  return resp.json();
};

export const fetchRemediationLog = async (profileId: string, limit = 50) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/remediation/log?profile_id=${profileId}&limit=${limit}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch audit log'));
  return resp.json();
};

export const fetchConfigRecommendations = async (profileId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/config/${profileId}/recommendations`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch config recommendations'));
  return resp.json();
};

export const killDBQuery = async (profileId: string, pid: number) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/queries/${profileId}/kill/${pid}`, { method: 'POST' });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to kill query'));
  return resp.json();
};

export const fetchDBActiveQueries = async (profileId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/profiles/${profileId}/queries`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch active queries'));
  return resp.json();
};

// ===== Protocol-First Device Monitoring =====

export const listMonitoredDevices = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/collector/devices`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to list devices'));
  return resp.json();
};

export const addMonitoredDevice = async (config: {
  ip_address: string;
  snmp_version?: string;
  community_string?: string;
  port?: number;
  v3_user?: string;
  v3_auth_protocol?: string;
  v3_auth_key?: string;
  v3_priv_protocol?: string;
  v3_priv_key?: string;
  tags?: string[];
  profile?: string | null;
  ping?: { enabled: boolean };
  hostname?: string;
}) => {
  const resp = await fetch(`${API_BASE_URL}/api/collector/devices`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to add device'));
  return resp.json();
};

export const getMonitoredDevice = async (deviceId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/collector/devices/${deviceId}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to get device'));
  return resp.json();
};

export const updateMonitoredDevice = async (deviceId: string, updates: {
  hostname?: string;
  tags?: string[];
  ping?: { enabled: boolean };
  profile?: string;
}) => {
  const resp = await fetch(`${API_BASE_URL}/api/collector/devices/${deviceId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to update device'));
  return resp.json();
};

export const deleteMonitoredDevice = async (deviceId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/collector/devices/${deviceId}`, { method: 'DELETE' });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to delete device'));
  return resp.json();
};

export const testMonitoredDevice = async (deviceId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/collector/devices/${deviceId}/test`, { method: 'POST' });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to test device'));
  return resp.json();
};

export const collectMonitoredDevice = async (deviceId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/collector/devices/${deviceId}/collect`, { method: 'POST' });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to collect device'));
  return resp.json();
};

export const pingMonitoredDevice = async (deviceId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/collector/devices/${deviceId}/ping`, { method: 'POST' });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to ping device'));
  return resp.json();
};

export const listDiscoveryConfigs = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/collector/discovery`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to list discovery configs'));
  return resp.json();
};

export const addDiscoveryConfig = async (config: {
  cidr: string;
  snmp_version?: string;
  community?: string;
  v3_user?: string;
  v3_auth_protocol?: string;
  v3_auth_key?: string;
  v3_priv_protocol?: string;
  v3_priv_key?: string;
  port?: number;
  interval_seconds?: number;
  excluded_ips?: string[];
  tags?: string[];
  ping?: { enabled: boolean };
}) => {
  const resp = await fetch(`${API_BASE_URL}/api/collector/discovery`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to add discovery config'));
  return resp.json();
};

export const deleteDiscoveryConfig = async (configId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/collector/discovery/${configId}`, { method: 'DELETE' });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to delete discovery config'));
  return resp.json();
};

export const triggerDiscoveryScan = async (configId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/collector/discovery/${configId}/scan`, { method: 'POST' });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to trigger scan'));
  return resp.json();
};

export const listDeviceProfiles = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/collector/profiles`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to list profiles'));
  return resp.json();
};

export const getCollectorHealth = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/collector/health`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to get collector health'));
  return resp.json();
};

// ===== NDM Enhanced API Functions =====

export const fetchTrapEvents = async (filters?: {
  device_id?: string; severity?: string; oid?: string;
  time_from?: number; time_to?: number; limit?: number;
}) => {
  const params = new URLSearchParams();
  if (filters?.device_id) params.set('device_id', filters.device_id);
  if (filters?.severity) params.set('severity', filters.severity);
  if (filters?.oid) params.set('oid', filters.oid);
  if (filters?.time_from) params.set('time_from', String(filters.time_from));
  if (filters?.time_to) params.set('time_to', String(filters.time_to));
  if (filters?.limit) params.set('limit', String(filters.limit));
  const resp = await fetch(`${API_BASE_URL}/api/collector/traps?${params}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch traps'));
  return resp.json();
};

export const fetchTrapSummary = async (timeFrom?: number, timeTo?: number) => {
  const params = new URLSearchParams();
  if (timeFrom) params.set('time_from', String(timeFrom));
  if (timeTo) params.set('time_to', String(timeTo));
  const resp = await fetch(`${API_BASE_URL}/api/collector/traps/summary?${params}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch trap summary'));
  return resp.json();
};

export const fetchSyslogEntries = async (filters?: {
  device_id?: string; severity?: string; facility?: string;
  search?: string; time_from?: number; time_to?: number; limit?: number;
}) => {
  const params = new URLSearchParams();
  if (filters?.device_id) params.set('device_id', filters.device_id);
  if (filters?.severity) params.set('severity', filters.severity);
  if (filters?.facility) params.set('facility', filters.facility);
  if (filters?.search) params.set('search', filters.search);
  if (filters?.time_from) params.set('time_from', String(filters.time_from));
  if (filters?.time_to) params.set('time_to', String(filters.time_to));
  if (filters?.limit) params.set('limit', String(filters.limit));
  const resp = await fetch(`${API_BASE_URL}/api/collector/syslog?${params}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch syslog'));
  return resp.json();
};

export const fetchSyslogSummary = async (timeFrom?: number, timeTo?: number) => {
  const params = new URLSearchParams();
  if (timeFrom) params.set('time_from', String(timeFrom));
  if (timeTo) params.set('time_to', String(timeTo));
  const resp = await fetch(`${API_BASE_URL}/api/collector/syslog/summary?${params}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch syslog summary'));
  return resp.json();
};

export const fetchDeviceMetricsSnapshot = async (deviceId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/collector/devices/${deviceId}/metrics`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch device metrics'));
  return resp.json();
};

export const fetchDeviceMetricsHistory = async (deviceId: string, window: string = '1h') => {
  const resp = await fetch(`${API_BASE_URL}/api/collector/devices/${deviceId}/metrics/history?window=${window}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch metrics history'));
  return resp.json();
};

export const fetchDeviceInterfaces = async (deviceId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/collector/devices/${deviceId}/interfaces`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch interfaces'));
  return resp.json();
};

export const fetchDeviceSyslog = async (deviceId: string, limit: number = 100) => {
  const resp = await fetch(`${API_BASE_URL}/api/collector/devices/${deviceId}/syslog?limit=${limit}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch device syslog'));
  return resp.json();
};

export const fetchDeviceTraps = async (deviceId: string, limit: number = 100) => {
  const resp = await fetch(`${API_BASE_URL}/api/collector/devices/${deviceId}/traps?limit=${limit}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch device traps'));
  return resp.json();
};

export const fetchFlowConversations = async (window: string = '5m', limit: number = 50) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/flows/conversations?window=${window}&limit=${limit}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch conversations'));
  return resp.json();
};

export const fetchFlowApplications = async (window: string = '1h', limit: number = 30) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/flows/applications?window=${window}&limit=${limit}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch applications'));
  return resp.json();
};

export const fetchFlowASN = async (window: string = '1h', limit: number = 30) => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/flows/asn?window=${window}&limit=${limit}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch ASN data'));
  return resp.json();
};

export const fetchFlowVolumeTimeline = async (window: string = '1h', interval: string = '1m') => {
  const resp = await fetch(`${API_BASE_URL}/api/v4/network/flows/volume-timeline?window=${window}&interval=${interval}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch volume timeline'));
  return resp.json();
};

export const fetchAggregateMetrics = async (tag?: string): Promise<{avg_cpu: number; avg_mem: number; avg_temp: number; device_count: number}> => {
  const params = tag ? `?tag=${encodeURIComponent(tag)}` : '';
  const resp = await fetch(`${API_BASE_URL}/api/collector/devices/aggregate-metrics${params}`);
  if (!resp.ok) return { avg_cpu: 0, avg_mem: 0, avg_temp: 0, device_count: 0 };
  return resp.json();
};
