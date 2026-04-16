import { API_BASE_URL } from './api';
import type {
  WorkflowSummary,
  WorkflowDetail,
  VersionSummary,
  WorkflowVersionDetail,
  WorkflowDag,
} from '../types';

export class WorkflowsDisabledError extends Error {
  constructor() {
    super('Workflows feature is disabled.');
    this.name = 'WorkflowsDisabledError';
  }
}

export class CompileError extends Error {
  constructor(
    public type: string,
    message: string,
    public path?: string,
    public errors?: unknown[],
  ) {
    super(message);
    this.name = 'CompileError';
  }
}

export async function callWorkflowsApi<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const resp = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  });
  if (resp.status === 204) return undefined as T;
  if (resp.status === 404) throw new WorkflowsDisabledError();
  if (resp.status === 409) {
    const body = await resp.json().catch(() => ({}));
    const d = (body?.detail ?? {}) as { type?: string; message?: string };
    throw new Error(d.message ?? 'conflict');
  }
  if (resp.status === 422) {
    const body = await resp.json().catch(() => ({}));
    const d = (body?.detail ?? {}) as {
      type?: string;
      message?: string;
      path?: string;
      errors?: unknown[];
    };
    throw new CompileError(
      d.type ?? 'compile_error',
      d.message ?? 'invalid',
      d.path,
      d.errors,
    );
  }
  if (!resp.ok) {
    throw new Error(`${init?.method ?? 'GET'} ${path} failed: ${resp.status}`);
  }
  return (await resp.json()) as T;
}

export async function listWorkflows(): Promise<WorkflowSummary[]> {
  const data = await callWorkflowsApi<{ workflows: WorkflowSummary[] }>(
    '/api/v4/workflows',
  );
  return data.workflows;
}

export function getWorkflow(id: string): Promise<WorkflowDetail> {
  return callWorkflowsApi<WorkflowDetail>(
    `/api/v4/workflows/${encodeURIComponent(id)}`,
  );
}

export function createWorkflow(body: {
  name: string;
  description: string;
  created_by?: string;
}): Promise<WorkflowDetail> {
  return callWorkflowsApi<WorkflowDetail>('/api/v4/workflows', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function listVersions(workflowId: string): Promise<VersionSummary[]> {
  const data = await callWorkflowsApi<{ versions: VersionSummary[] }>(
    `/api/v4/workflows/${encodeURIComponent(workflowId)}/versions`,
  );
  return data.versions;
}

export function getVersion(
  workflowId: string,
  version: number,
): Promise<WorkflowVersionDetail> {
  return callWorkflowsApi<WorkflowVersionDetail>(
    `/api/v4/workflows/${encodeURIComponent(workflowId)}/versions/${version}`,
  );
}

export function createVersion(
  workflowId: string,
  dag: WorkflowDag,
): Promise<VersionSummary> {
  return callWorkflowsApi<VersionSummary>(
    `/api/v4/workflows/${encodeURIComponent(workflowId)}/versions`,
    { method: 'POST', body: JSON.stringify(dag) },
  );
}

export function deleteWorkflow(id: string): Promise<void> {
  return callWorkflowsApi<void>(
    `/api/v4/workflows/${encodeURIComponent(id)}`,
    { method: 'DELETE' },
  );
}

export function updateWorkflow(
  id: string,
  body: { name?: string; description?: string },
): Promise<WorkflowDetail> {
  return callWorkflowsApi<WorkflowDetail>(
    `/api/v4/workflows/${encodeURIComponent(id)}`,
    { method: 'PATCH', body: JSON.stringify(body) },
  );
}

export function duplicateWorkflow(id: string): Promise<WorkflowDetail> {
  return callWorkflowsApi<WorkflowDetail>(
    `/api/v4/workflows/${encodeURIComponent(id)}/duplicate`,
    { method: 'POST' },
  );
}

export function rollbackVersion(
  workflowId: string,
  version: number,
): Promise<VersionSummary> {
  return callWorkflowsApi<VersionSummary>(
    `/api/v4/workflows/${encodeURIComponent(workflowId)}/versions/${version}/rollback`,
    { method: 'POST' },
  );
}
