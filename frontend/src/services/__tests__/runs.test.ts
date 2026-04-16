import { afterAll, afterEach, beforeAll, describe, expect, test, vi } from 'vitest';
import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';
import {
  createRun,
  getRun,
  cancelRun,
  subscribeEvents,
  RunTerminalError,
  InputsInvalidError,
} from '../runs';
import { WorkflowsDisabledError } from '../workflows';

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('services/runs', () => {
  test('createRun POSTs inputs + idempotency_key and returns run summary', async () => {
    let seen: any = null;
    server.use(
      http.post('*/api/v4/workflows/w1/runs', async ({ request }) => {
        seen = await request.json();
        return HttpResponse.json(
          {
            run: {
              id: 'r1',
              workflow_version_id: 'v1',
              status: 'pending',
              inputs: seen.inputs,
            },
          },
          { status: 201 },
        );
      }),
    );
    const r = await createRun('w1', {
      inputs: { service_name: 'svc' },
      idempotency_key: 'k1',
    });
    expect(r.id).toBe('r1');
    expect(seen).toEqual({ inputs: { service_name: 'svc' }, idempotency_key: 'k1' });
  });

  test('createRun 422 throws InputsInvalidError with errors', async () => {
    server.use(
      http.post('*/api/v4/workflows/w1/runs', () =>
        HttpResponse.json(
          {
            detail: {
              type: 'inputs_invalid',
              message: 'missing prop',
              errors: [{ path: ['service_name'], message: 'required' }],
            },
          },
          { status: 422 },
        ),
      ),
    );
    try {
      await createRun('w1', { inputs: {} });
      throw new Error('unreachable');
    } catch (e: any) {
      expect(e).toBeInstanceOf(InputsInvalidError);
      expect(e.errors).toHaveLength(1);
    }
  });

  test('getRun merges run summary + step_runs into RunDetail', async () => {
    server.use(
      http.get('*/api/v4/runs/r1', () =>
        HttpResponse.json({
          run: {
            id: 'r1',
            workflow_version_id: 'v1',
            status: 'running',
            inputs: { a: 1 },
          },
          step_runs: [
            { id: 'sr1', step_id: 's1', status: 'success', attempt: 1 },
          ],
        }),
      ),
    );
    const r = await getRun('r1');
    expect(r.id).toBe('r1');
    expect(r.status).toBe('running');
    expect(r.step_runs).toHaveLength(1);
    expect(r.step_runs[0].id).toBe('sr1');
  });

  test('getRun 404 throws WorkflowsDisabledError', async () => {
    server.use(
      http.get('*/api/v4/runs/r1', () => new HttpResponse(null, { status: 404 })),
    );
    await expect(getRun('r1')).rejects.toBeInstanceOf(WorkflowsDisabledError);
  });

  test('cancelRun returns summary on success', async () => {
    server.use(
      http.post('*/api/v4/runs/r1/cancel', () =>
        HttpResponse.json({
          run: {
            id: 'r1',
            workflow_version_id: 'v1',
            status: 'cancelling',
            inputs: {},
            step_runs: [],
          },
        }),
      ),
    );
    const r = await cancelRun('r1');
    expect(r.status).toBe('cancelling');
  });

  test('cancelRun 409 throws RunTerminalError with status', async () => {
    server.use(
      http.post('*/api/v4/runs/r1/cancel', () =>
        HttpResponse.json(
          { detail: { type: 'run_terminal', status: 'succeeded' } },
          { status: 409 },
        ),
      ),
    );
    try {
      await cancelRun('r1');
      throw new Error('unreachable');
    } catch (e: any) {
      expect(e).toBeInstanceOf(RunTerminalError);
      expect(e.status).toBe('succeeded');
    }
  });

  test('subscribeEvents returns EventSource with correct URL', () => {
    const created: { url: string; opts?: any }[] = [];
    class FakeEventSource {
      url: string;
      opts?: any;
      constructor(url: string, opts?: any) {
        this.url = url;
        this.opts = opts;
        created.push({ url, opts });
      }
      close() {}
    }
    const g = globalThis as any;
    const original = g.EventSource;
    g.EventSource = FakeEventSource as any;
    try {
      const es = subscribeEvents('run-xyz') as any;
      expect(es.url).toContain('/api/v4/runs/run-xyz/events');
      expect(created).toHaveLength(1);
    } finally {
      g.EventSource = original;
    }
  });
});
