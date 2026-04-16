import { API_BASE_URL } from './api';
import { WorkflowsDisabledError } from './workflows';
import type { RunDetail, StepRunDetail } from '../types';

export class RunTerminalError extends Error {
  constructor(public status: string) {
    super(`run already terminal: ${status}`);
    this.name = 'RunTerminalError';
  }
}

export class InputsInvalidError extends Error {
  constructor(
    message: string,
    public errors: Array<{ path?: unknown; message?: string }> = [],
  ) {
    super(message);
    this.name = 'InputsInvalidError';
  }
}

interface RunSummaryWire {
  id: string;
  workflow_version_id: string;
  status: RunDetail['status'];
  started_at?: string;
  ended_at?: string;
  inputs?: Record<string, unknown>;
  idempotency_key?: string;
  error?: RunDetail['error'];
}

function normalizeRun(
  summary: RunSummaryWire,
  stepRuns: StepRunDetail[] = [],
): RunDetail {
  return {
    id: summary.id,
    workflow_version_id: summary.workflow_version_id,
    status: summary.status,
    started_at: summary.started_at,
    ended_at: summary.ended_at,
    inputs: summary.inputs ?? {},
    idempotency_key: summary.idempotency_key,
    error: summary.error,
    step_runs: stepRuns,
  };
}

async function runsFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  return fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  });
}

async function handleCommon(resp: Response, path: string, method: string): Promise<unknown> {
  if (resp.status === 404) throw new WorkflowsDisabledError();
  if (resp.status === 422) {
    const body = await resp.json().catch(() => ({}));
    const d = (body?.detail ?? {}) as {
      type?: string;
      message?: string;
      errors?: Array<{ path?: unknown; message?: string }>;
    };
    throw new InputsInvalidError(d.message ?? 'invalid inputs', d.errors ?? []);
  }
  if (resp.status === 409) {
    const body = await resp.json().catch(() => ({}));
    const d = (body?.detail ?? {}) as { status?: string };
    throw new RunTerminalError(d.status ?? 'terminal');
  }
  if (!resp.ok) {
    throw new Error(`${method} ${path} failed: ${resp.status}`);
  }
  return resp.json();
}

export async function createRun(
  workflowId: string,
  body: { inputs: Record<string, unknown>; idempotency_key?: string },
): Promise<RunDetail> {
  const path = `/api/v4/workflows/${encodeURIComponent(workflowId)}/runs`;
  const resp = await runsFetch(path, {
    method: 'POST',
    body: JSON.stringify(body),
  });
  const data = (await handleCommon(resp, path, 'POST')) as { run: RunSummaryWire };
  return normalizeRun(data.run);
}

export async function getRun(runId: string): Promise<RunDetail> {
  const path = `/api/v4/runs/${encodeURIComponent(runId)}`;
  const resp = await runsFetch(path);
  const data = (await handleCommon(resp, path, 'GET')) as {
    run: RunSummaryWire;
    step_runs: StepRunDetail[];
  };
  return normalizeRun(data.run, data.step_runs ?? []);
}

export async function cancelRun(runId: string): Promise<RunDetail> {
  const path = `/api/v4/runs/${encodeURIComponent(runId)}/cancel`;
  const resp = await runsFetch(path, { method: 'POST' });
  const data = (await handleCommon(resp, path, 'POST')) as { run: RunSummaryWire };
  return normalizeRun(data.run);
}

export function subscribeEvents(
  runId: string,
  _lastEventId?: number,
): EventSource {
  // Browser EventSource sends Last-Event-ID automatically on reconnect.
  // Explicit initial Last-Event-ID would require a polyfill; deferred.
  const url = `${API_BASE_URL}/api/v4/runs/${encodeURIComponent(runId)}/events`;
  return new EventSource(url, { withCredentials: false });
}
