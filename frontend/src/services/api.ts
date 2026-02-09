const API_BASE_URL = 'http://localhost:8000';

export const sendConversationMessage = async (message: string, conversationHistory?: any[]) => {
  const response = await fetch('http://localhost:8000/api/conversation', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, conversation_history: conversationHistory })
  });
  return response.json();
};

export const startTroubleshooting = async (formData: any) => {
  const response = await fetch(`${API_BASE_URL}/api/troubleshoot/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(formData)
  });
  return response.json();
};

export const getSessionStatus = async (sessionId: string) => {
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

/**
 * Reject Fix (Agent 3)
 * Called when user clicks "Reject" button
 * Cleans up the local branch and allows re-generation
 * 
 * @param sessionId - Troubleshooting session ID
 * @returns Rejection confirmation
 */
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

/**
 * Get PR Status (Agent 3)
 * Check the current status of PR creation
 * 
 * @param sessionId - Troubleshooting session ID
 * @returns PR status and validation results
 */
export const getPRStatus = async (sessionId: string) => {
  const response = await fetch(`${API_BASE_URL}/api/troubleshoot/${sessionId}/pr-status`);
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to get PR status');
  }
  
  return response.json();
};

/**
 * Check Agent 3 Health
 * Verify Agent 3 endpoints and GitHub token configuration
 * 
 * @returns Health status
 */
export const checkAgent3Health = async () => {
  const response = await fetch(`${API_BASE_URL}/api/pr-endpoints/health`);
  return response.json();
};
