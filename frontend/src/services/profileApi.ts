import type { ClusterProfile, GlobalIntegration, EndpointTestResult } from '../types/profiles';

const API_BASE_URL = 'http://localhost:8000';

// ===== Profile API =====

export const listProfiles = async (): Promise<ClusterProfile[]> => {
  const response = await fetch(`${API_BASE_URL}/api/v5/profiles/`);
  if (!response.ok) throw new Error('Failed to list profiles');
  return response.json();
};

export const createProfile = async (data: Record<string, unknown>): Promise<ClusterProfile> => {
  const response = await fetch(`${API_BASE_URL}/api/v5/profiles/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error('Failed to create profile');
  return response.json();
};

export const updateProfile = async (id: string, data: Record<string, unknown>): Promise<ClusterProfile> => {
  const response = await fetch(`${API_BASE_URL}/api/v5/profiles/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error('Failed to update profile');
  return response.json();
};

export const deleteProfile = async (id: string): Promise<void> => {
  const response = await fetch(`${API_BASE_URL}/api/v5/profiles/${id}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error('Failed to delete profile');
};

export const activateProfile = async (id: string): Promise<void> => {
  const response = await fetch(`${API_BASE_URL}/api/v5/profiles/${id}/activate`, {
    method: 'POST',
  });
  if (!response.ok) throw new Error('Failed to activate profile');
};

export const getActiveProfile = async (): Promise<ClusterProfile | null> => {
  const response = await fetch(`${API_BASE_URL}/api/v5/profiles/active`);
  if (!response.ok) throw new Error('Failed to get active profile');
  const data = await response.json();
  return data.active_profile ?? null;
};

export const testEndpoint = async (
  profileId: string,
  endpointName: string,
  url?: string
): Promise<EndpointTestResult> => {
  const response = await fetch(`${API_BASE_URL}/api/v5/profiles/${profileId}/test-endpoint`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ endpoint_name: endpointName, url: url || undefined }),
  });
  if (!response.ok) throw new Error('Failed to test endpoint');
  return response.json();
};

export const probeProfile = async (id: string): Promise<Record<string, unknown>> => {
  const response = await fetch(`${API_BASE_URL}/api/v5/profiles/${id}/probe`, {
    method: 'POST',
  });
  if (!response.ok) throw new Error('Failed to probe profile');
  return response.json();
};

// ===== Global Integrations API =====

export const createGlobalIntegration = async (
  data: Record<string, unknown>
): Promise<GlobalIntegration> => {
  const response = await fetch(`${API_BASE_URL}/api/v5/global-integrations/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error('Failed to create global integration');
  return response.json();
};

export const deleteGlobalIntegration = async (id: string): Promise<void> => {
  const response = await fetch(`${API_BASE_URL}/api/v5/global-integrations/${id}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error('Failed to delete global integration');
};

export const listGlobalIntegrations = async (): Promise<GlobalIntegration[]> => {
  const response = await fetch(`${API_BASE_URL}/api/v5/global-integrations/`);
  if (!response.ok) throw new Error('Failed to list global integrations');
  return response.json();
};

export const updateGlobalIntegration = async (
  id: string,
  data: Record<string, unknown>
): Promise<GlobalIntegration> => {
  const response = await fetch(`${API_BASE_URL}/api/v5/global-integrations/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error('Failed to update global integration');
  return response.json();
};

export const testGlobalIntegration = async (
  id: string
): Promise<EndpointTestResult> => {
  const response = await fetch(`${API_BASE_URL}/api/v5/global-integrations/${id}/test`, {
    method: 'POST',
  });
  if (!response.ok) throw new Error('Failed to test global integration');
  return response.json();
};

export const saveAllGlobalIntegrations = async (
  integrations: Record<string, unknown>[]
): Promise<{ status: string; updated: number }> => {
  const response = await fetch(`${API_BASE_URL}/api/v5/global-integrations/save-all`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ integrations }),
  });
  if (!response.ok) throw new Error('Failed to save all global integrations');
  return response.json();
};
