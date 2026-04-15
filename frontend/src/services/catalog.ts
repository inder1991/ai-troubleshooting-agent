import type { CatalogAgentSummary, CatalogAgentDetail } from '../types';
import { API_BASE_URL } from './api';

export class CatalogDisabledError extends Error {
  constructor() {
    super('Catalog feature is disabled.');
    this.name = 'CatalogDisabledError';
  }
}

export async function listAgents(signal?: AbortSignal): Promise<CatalogAgentSummary[]> {
  const resp = await fetch(`${API_BASE_URL}/api/v4/catalog/agents`, { signal });
  if (resp.status === 404) throw new CatalogDisabledError();
  if (!resp.ok) throw new Error(`catalog list failed: ${resp.status}`);
  const data = await resp.json();
  return data.agents;
}

export async function getAgent(name: string, signal?: AbortSignal): Promise<CatalogAgentDetail> {
  const resp = await fetch(
    `${API_BASE_URL}/api/v4/catalog/agents/${encodeURIComponent(name)}`,
    { signal },
  );
  if (!resp.ok) throw new Error(`catalog get failed: ${resp.status}`);
  return resp.json();
}

export async function getAgentVersion(
  name: string,
  version: number,
  signal?: AbortSignal,
): Promise<CatalogAgentDetail> {
  const resp = await fetch(
    `${API_BASE_URL}/api/v4/catalog/agents/${encodeURIComponent(name)}/v/${version}`,
    { signal },
  );
  if (!resp.ok) throw new Error(`catalog get version failed: ${resp.status}`);
  return resp.json();
}
