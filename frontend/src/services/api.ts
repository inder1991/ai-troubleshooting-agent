import type {
  StartSessionRequest,
  V4Session,
  V4SessionStatus,
  V4Findings,
  TaskEvent,
  ChatMessage,
  Integration,
} from '../types';

const API_BASE_URL = 'http://localhost:8000';

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
    const error = await response.json();
    throw new Error(error.detail || 'Failed to start session');
  }
  return response.json();
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
    const error = await response.json();
    throw new Error(error.detail || 'Failed to send message');
  }
  return response.json();
};

export const getSessionStatus = async (sessionId: string): Promise<V4SessionStatus> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/session/${sessionId}/status`);
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to get session status');
  }
  return response.json();
};

export const getFindings = async (sessionId: string): Promise<V4Findings> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/session/${sessionId}/findings`);
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to get findings');
  }
  return response.json();
};

export const getEvents = async (sessionId: string): Promise<TaskEvent[]> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/session/${sessionId}/events`);
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to get events');
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
  const response = await fetch(`${API_BASE_URL}/api/v5/session/${sessionId}/attestation`, {
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
