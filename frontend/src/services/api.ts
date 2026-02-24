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
} from '../types';

const API_BASE_URL = 'http://localhost:8000';

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
    const error = await response.json();
    throw new Error(error.detail || 'Failed to list sessions');
  }
  const data = await response.json();
  return data.map((s: Record<string, unknown>) => ({
    ...s,
    status: s.status || s.phase || 'initial',
    updated_at: s.updated_at || s.created_at,
  }));
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

export const previewPostMortem = async (sessionId: string): Promise<{ title: string; body_markdown: string }> => {
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
